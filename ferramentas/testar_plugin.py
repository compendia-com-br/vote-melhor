#!/usr/bin/env python3
"""Valida o plugin antes de empacotar. Adaptado do testar_plugins.py dos
compendia-acervo: seções de estrutura e frontmatter valem na íntegra; a seção de
corpus saiu e deu lugar aos testes de dado e de guarda.

Certo, vazio e quebrado são três estados. Um validador que passa com o plugin
vazio não está medindo nada — por isso ele exige contagem mínima, não presença.
"""
import json, os, re, subprocess, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
falhas, avisos = [], []
def f(m): falhas.append(m)
def w(m): avisos.append(m)

mk = json.load(open(f"{BASE}/.claude-plugin/marketplace.json", encoding="utf-8"))
print(f"marketplace: {mk['name']} — dono: {mk['owner']['name']} — {len(mk['plugins'])} plugin(s)\n")

for entrada in mk["plugins"]:
    k = entrada["name"]
    d = f"{BASE}/plugins/{k}"
    print(f"── {k}")
    if not os.path.isdir(d):
        f(f"{k}: pasta não existe"); continue

    # 1) plugin.json
    pj = f"{d}/.claude-plugin/plugin.json"
    if not os.path.exists(pj):
        f(f"{k}: sem plugin.json"); continue
    meta = json.load(open(pj, encoding="utf-8"))
    if meta.get("name") != k: f(f"{k}: name '{meta.get('name')}' != pasta")
    for campo in ("version", "description", "author", "license"):
        if not meta.get(campo): f(f"{k}: plugin.json sem '{campo}'")
    autor = (meta.get("author") or {}).get("name")
    if autor != "Compendia": f(f"{k}: autoria é '{autor}', esperado 'Compendia'")
    print(f"   autoria: {autor} | licença: {meta.get('license')}")

    # 2) skills — pasta vazia derruba o plugin
    sk = f"{d}/skills"
    dirs = sorted(x for x in os.listdir(sk) if os.path.isdir(f"{sk}/{x}")) if os.path.isdir(sk) else []
    vazias, ok = [], 0
    for s in dirs:
        p = f"{sk}/{s}/SKILL.md"
        if not os.path.exists(p): vazias.append(s); continue
        txt = open(p, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
        if not m: f(f"{k}/{s}: sem frontmatter"); continue
        nome = re.search(r"^name:\s*(.+)$", m.group(1), re.M)
        desc = re.search(r"^description:\s*(.+)$", m.group(1), re.M | re.S)
        if not nome or nome.group(1).strip() != s: f(f"{k}/{s}: name != pasta")
        if not desc: f(f"{k}/{s}: sem description")
        elif len(desc.group(1).strip()) < 80: w(f"{k}/{s}: description curta")
        elif re.search(r"\b(primeiro|depois|em seguida|passo \d)\b", desc.group(1), re.I):
            w(f"{k}/{s}: description parece resumir processo — ela deve dizer QUANDO usar")
        if len(txt[m.end():].splitlines()) < 25: w(f"{k}/{s}: corpo curto")
        ok += 1
    if vazias: f(f"{k}: PASTA DE SKILL VAZIA (derruba o plugin): {', '.join(vazias)}")
    if ok < 3: f(f"{k}: só {ok} skills — validador não aceita plugin quase vazio")
    print(f"   skills: {ok}")

    # 3) comando, agente, hook
    cmds = [x for x in os.listdir(f"{d}/commands")] if os.path.isdir(f"{d}/commands") else []
    ags  = [x for x in os.listdir(f"{d}/agents")] if os.path.isdir(f"{d}/agents") else []
    if not cmds: f(f"{k}: sem comando — a porta não pode ser skill (description não roteia)")
    if not ags:  w(f"{k}: sem agente")
    print(f"   comandos: {len(cmds)} | agentes: {len(ags)}")

    hk = f"{d}/hooks/hooks.json"
    if not os.path.exists(hk): f(f"{k}: sem hooks.json — a guarda não pode ser skill")
    else:
        json.load(open(hk, encoding="utf-8"))
        print("   hook: hooks.json válido")

    # 4) scripts embarcados e só stdlib
    fer = f"{d}/ferramentas"
    for arq in ("coletar_tse.py", "consultar.py", "camara.py", "criterios.py", "verificar_dados.py"):
        if not os.path.exists(f"{fer}/{arq}"): f(f"{k}: falta ferramentas/{arq}")
    TERCEIROS = ("requests", "httpx", "pandas", "numpy", "bs4", "lxml", "selenium", "playwright")
    for arq in os.listdir(fer) if os.path.isdir(fer) else []:
        if not arq.endswith(".py"): continue
        src = open(f"{fer}/{arq}", encoding="utf-8").read()
        for t in TERCEIROS:
            if re.search(rf"^\s*(?:import|from)\s+{t}\b", src, re.M):
                f(f"{k}/{arq}: importa '{t}' — o plugin tem que rodar só com stdlib")
        # compila em memória: py_compile escreveria __pycache__ dentro do que validamos
        try:
            compile(src, f"{fer}/{arq}", "exec")
        except SyntaxError as e:
            f(f"{k}/{arq}: erro de sintaxe na linha {e.lineno}")
    print("   scripts: compilam, só stdlib")

    # A duplicata na raiz ja existiu: 4 scripts com md5 identico, sem sincronizador,
    # e o validador so conferia existencia. Medido em 07/09/2026. Um par que se
    # desalinha nao da erro — da comportamento diferente entre o que se testa e o
    # que se distribui, e isso nao aparece em teste nenhum.
    EMBARCADOS = ["camara.py", "coletar_tse.py", "consultar.py", "criterios.py",
                  "senado.py", "verificar_dados.py"]
    for arq in EMBARCADOS:
        # BASE, nao caminho relativo: testar_plugin.py ja resolve tudo por
        # BASE (linha 11) e roda de qualquer diretorio. Caminho relativo aqui
        # daria "0 falhas" para quem rodasse de outra pasta — um validador que
        # passa por nao ter olhado.
        if os.path.exists(os.path.join(BASE, "ferramentas", arq)):
            f(f"duplicata: ferramentas/{arq} existe na raiz. A unica copia "
              f"e plugins/vote-melhor/ferramentas/{arq}")

    # 5) NENHUM dado embarcado
    embarcado = []
    for raiz, _, arqs in os.walk(d):
        for a in arqs:
            if a.endswith((".sqlite", ".zip", ".csv")) or "/dados" in raiz:
                embarcado.append(os.path.relpath(f"{raiz}/{a}", d))
    if embarcado: f(f"{k}: DADO EMBARCADO no plugin: {embarcado[:5]}")
    else: print("   dado embarcado: nenhum")

    # 5b) lixo de build não vai para o pacote
    lixo = [os.path.relpath(r, d) for r, _, _ in os.walk(d) if os.path.basename(r) == "__pycache__"]
    if lixo: f(f"{k}: __pycache__ no pacote: {lixo}")

    # 6) a guarda pega o que tem que pegar — controle positivo
    hookpy = f"{d}/hooks/verificar_saida.py"
    if os.path.exists(hookpy):
        casos = [("O currículo dele é o mais forte dos três candidatos.", True),
                 ("Ele é ficha limpa, pode votar tranquilo.", True),
                 ('{"cpf":"12345678901"}', True),
                 ("Situação do registro    : Aguardando julgamento", False)]
        erros = 0
        for texto, deve in casos:
            ev = json.dumps({"tool_input": {"content": texto}})
            r = subprocess.run([sys.executable, hookpy], input=ev, capture_output=True, text=True)
            pegou = "guarda de neutralidade" in r.stderr
            if pegou != deve: erros += 1
        if erros: f(f"{k}: a guarda errou {erros} de {len(casos)} controles")
        else: print(f"   guarda: {len(casos)}/{len(casos)} controles corretos")
    print()

print("="*60)
for a in avisos: print(f"AVISO  {a}")
for x in falhas: print(f"FALHA  {x}")
print("="*60)
print(f"{len(falhas)} falha(s), {len(avisos)} aviso(s)")
sys.exit(1 if falhas else 0)
