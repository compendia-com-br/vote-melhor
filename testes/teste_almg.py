#!/usr/bin/env python3
"""Controles de almg.py (deputado estadual de MG) e da ligacao em criterios.py.

COMO RODAR:  python3 testes/teste_almg.py
             python3 testes/teste_almg.py --sem-rede   (so a parte offline)

O defeito que este arquivo existe para nao deixar nascer: falha de CONSULTA
lida como "nao achado". As duas saem iguais num quadro comparativo se ninguem
as separar, e "nao achado" e lido como "nao fez nada". Foi relatado em
achar_deputado (Camara), que respondia "nao consegui consultar a Camara agora"
para QUALQUER excecao, inclusive defeito de codigo — por isso a secao CAMARA.

Tres partes:
  OFFLINE  — sem rede. Casamento por nome (homonimo nao escolhe), autoria
             confirmada pelo id da matricula (e nao pelo texto do nome),
             falha de transporte x nao achado x defeito de codigo, e o
             quadro de criterios.py para MG e para outra UF.
  CAMARA   — sem rede. achar_deputado passa a dizer QUAL falha, e defeito
             de codigo sobe em vez de virar "falha de rede".
  REDE     — bate na ALMG de verdade, num diretorio temporario (sem cache
             antigo). Controle positivo: Coronel Henrique, deputado estadual
             em exercicio (id ALMG 26149 em 03/10/2026), achado por nome e
             com proposicoes sob "educacao". Controles negativos: nome
             inventado -> nao achado; palavra inventada -> zero.
             SEM REDE, A PARTE REDE REPROVA — teste que passa sem ter medido
             nao prova nada.

Nomes de pessoa na parte OFFLINE sao inventados (Fulano/Beltrano de Teste).
Nenhum CPF ou titulo de eleitor e lido ou escrito.
"""
import atexit, contextlib, io, json, os, shutil, sqlite3, sys, tempfile, urllib.error

TMP = tempfile.mkdtemp(prefix="vote-melhor-teste-almg-")
atexit.register(shutil.rmtree, TMP, True)
os.environ["VOTE_MELHOR_DADOS"] = TMP          # antes de importar: RAIZ e lida no import
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "plugins", "vote-melhor", "ferramentas"))
import almg
import criterios

falhas = []
def checa(nome, cond, detalhe=""):
    print(f"  [{'ok ' if cond else 'FALHA'}] {nome}{': ' + detalhe if detalhe else ''}")
    if not cond:
        falhas.append(nome)

checa("o teste roda fora da base real", almg.CACHE.startswith(TMP), almg.CACHE)

# --------------------------------------------------------------------- OFFLINE
print("\nOFFLINE — casamento por nome")
DEPS = [
    {"id": 1, "nome": "Fulano de Teste", "partido": "X", "situacoes": []},
    {"id": 2, "nome": "Beltrano Teste", "partido": "Y", "situacoes": []},
    {"id": 3, "nome": "Beltrano Teste Filho", "partido": "Z", "situacoes": []},
    {"id": 4, "nome": "Mário Exemplo", "partido": "W", "situacoes": []},
]
e, a, m = almg.casar("FULANO DE TESTE", DEPS)
checa("nome identico, caixa diferente -> achei", e == "achei" and a[0]["id"] == 1, m)
e, a, m = almg.casar("MARIO EXEMPLO", DEPS)
checa("TSE sem acento casa ALMG com acento", e == "achei" and a[0]["id"] == 4, m)
e, a, m = almg.casar("BELTRANO", DEPS)
checa("dois nomes parecidos -> homonimos, nao escolhe", e == "homonimos" and len(a) == 2, m)
e, a, m = almg.casar("Beltrano Teste", DEPS)
checa("nome exato vence o parcial mais longo", e == "achei" and a[0]["id"] == 2, m)
e, a, m = almg.casar("Zzqx Inventado Silva", DEPS)
checa("nome inventado -> nao_achado", e == "nao_achado" and not a, m)
e, a, m = almg.casar("ARIO", DEPS)
checa("pedaco de palavra nao casa ('ario' em 'mario')", e == "nao_achado", m)

print("\nOFFLINE — autoria confirmada pelo id, nao pelo texto")
# o caso medido: busca aut="Coronel Henrique" devolveu item cujo unico
# "Henrique" era OUTRO deputado. Aqui, com nomes inventados.
item_outro = {"autor": "Deputado Beltrano Teste Filho     Z\n", "matricula": "3\n"}
item_meu = {"autor": "Deputado Fulano de Teste     X\nDeputada Ciclana     Y\n",
            "matricula": "1\n9\n"}
item_sem_matricula = {"autor": "Deputado Beltrano Teste     Y\n"}
checa("outro deputado com nome parecido nao conta",
      not almg.autoria_confirmada(item_outro, 2, "Beltrano Teste"))
checa("id na matricula conta", almg.autoria_confirmada(item_meu, 1, "Fulano de Teste"))
checa("sem matricula, cai para o nome exato",
      almg.autoria_confirmada(item_sem_matricula, 2, "Beltrano Teste"))
checa("coautoria coletiva vem marcada", "autoria coletiva: 2" in almg.linha_item(item_meu),
      almg.linha_item(item_meu))
req = {"siglaTipoProjeto": "RQN", "numero": "1", "ano": "2026", "assunto": "Requer algo.",
       "autor": "Deputado Fulano de Teste   X", "matricula": "1"}
checa("requerimento sem ementa mostra o assunto", "Requer algo." in almg.linha_item(req))

print("\nOFFLINE — falha de consulta x nao achado x defeito de codigo")
original_urlopen = almg.urllib.request.urlopen
original_pausa = almg.PAUSA
almg.PAUSA = 0
def com_urlopen(fn):
    almg.urllib.request.urlopen = fn
    try:
        return almg.achar("Fulano de Teste", forcar=True)
    finally:
        almg.urllib.request.urlopen = original_urlopen

def sem_rede(*a, **k):
    raise urllib.error.URLError("Name or service not known (simulado)")
e, a, m = com_urlopen(sem_rede)
checa("rede caiu -> estado 'falha', nao 'nao_achado'", e == "falha", m)
checa("a mensagem diz que foi a rede", "rede" in m, m)

def http_503(*a, **k):
    raise urllib.error.HTTPError("https://exemplo.invalid", 503, "x", {}, None)
e, a, m = com_urlopen(http_503)
checa("HTTP 503 -> 'falha' com o codigo", e == "falha" and "503" in m, m)

class Resposta:
    def __init__(self, corpo): self.corpo = corpo.encode("utf-8")
    def read(self): return self.corpo
    def __enter__(self): return self
    def __exit__(self, *a): return False
e, a, m = com_urlopen(lambda *a, **k: Resposta('{"outraCoisa": []}'))
checa("envelope fora do formato medido -> 'falha', nao 'nao_achado'", e == "falha", m)
e, a, m = com_urlopen(lambda *a, **k: Resposta("<html>manutencao</html>"))
checa("corpo que nao e JSON -> 'falha'", e == "falha", m)

def defeito(*a, **k):
    raise TypeError("defeito de codigo simulado")
estourou = None
try:
    com_urlopen(defeito)
except TypeError as x:
    estourou = x
checa("CONTROLE NEGATIVO: defeito de codigo sobe, nao vira 'falha de rede'",
      estourou is not None)
almg.PAUSA = original_pausa

print("\nOFFLINE — o quadro de criterios.py")
os.makedirs(os.path.dirname(criterios.BANCO), exist_ok=True)
with open(criterios.EIXOS, "w", encoding="utf-8") as f:
    json.dump({"eixos": ["educação", "agro"]}, f)
cx = sqlite3.connect(criterios.BANCO)
cx.execute("CREATE TABLE candidatura (id, nomeUrna, numero, cargo_nome, ufCandidatura, "
           "partido_sigla, descricaoSituacao)")
cx.executemany("INSERT INTO candidatura VALUES (?,?,?,?,?,?,?)", [
    ("FALSO-MG", "FULANO DE TESTE", 99999, "Deputado Estadual", "MG", "X", "Deferido"),
    ("FALSO-SP", "BELTRANO TESTE", 99998, "Deputado Estadual", "SP", "Y", "Deferido"),
])
cx.commit(); cx.close()

def quadro(achar_falso, prop_falso=None):
    orig_a, orig_p = criterios._almg.achar, criterios._almg.proposicoes
    criterios._almg.achar = achar_falso
    if prop_falso:
        criterios._almg.proposicoes = prop_falso
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            criterios.cmd_cruzar(["FALSO-MG", "FALSO-SP"])
    finally:
        criterios._almg.achar, criterios._almg.proposicoes = orig_a, orig_p
    return buf.getvalue()

chamados = []
def achar_falha(nome, forcar=False):
    chamados.append(nome)
    return "falha", [], "nao consegui consultar a ALMG agora (erro de rede: simulado)"
s = quadro(achar_falha)
checa("so o candidato de MG consulta a ALMG", chamados == ["FULANO DE TESTE"], str(chamados))
checa("falha de consulta sai como NAO CONSULTADO", "NAO CONSULTADO" in s)
checa("falha de consulta nao sai como 'nao localizado'",
      "registro estadual: nao localizado" not in s)
checa("outra UF: assembleia nao coberta, dito com a UF", "assembleia de SP nao e consultada" in s)

def achar_ok(nome, forcar=False):
    return "achei", [{"id": 1, "nome": "Fulano de Teste", "partido": "X",
                      "situacoes": ["legislatura 20: em exercicio"]}], "nome identico"
def prop_ok(id_almg, nome, termo, **k):
    itens = [] if "agro" in almg.limpar(termo) else [req]
    return {"itens": itens, "confirmados": len(itens), "devolvidos": len(itens),
            "total_busca": len(itens), "url": "https://dadosabertos.almg.gov.br/api/v2/x",
            "quando": "agora"}
s = quadro(achar_ok, prop_ok)
checa("achado: imprime o id ALMG", "id ALMG 1" in s)
checa("eixo com material: imprime o item e a fonte", "RQN 1/2026" in s and "fonte:" in s)
checa("eixo sem material: ausencia de PROPOSICAO COM ESSE TERMO",
      "ausencia de PROPOSICAO COM ESSE TERMO" in s)
checa("o quadro nao recomenda voto", "nao recomenda voto" in s)

# --------------------------------------------------------------------- CAMARA
print("\nCAMARA — achar_deputado diz QUAL falha, e nao engole defeito")
orig_get = criterios._get
def com_get(fn):
    criterios._get = fn
    try:
        return criterios.achar_deputado("FULANO DE TESTE", "MG")
    finally:
        criterios._get = orig_get
r, m = com_get(sem_rede)
checa("rede caiu -> motivo com 'rede'", r is None and "rede" in m, m)
r, m = com_get(http_503)
checa("HTTP 503 -> motivo com o codigo", r is None and "503" in m, m)
def nao_json(url): raise ValueError("Expecting value")
r, m = com_get(nao_json)
checa("corpo que nao e JSON -> falha de CONSULTA", r is None and "JSON" in m, m)
r, m = com_get(lambda url: {"dados": [{"id": 7, "nome": "Fulano de Teste"}]})
checa("resposta boa -> achado", r is not None and r["id"] == 7, m)
r, m = com_get(lambda url: {"outra": 1})
checa("envelope sem 'dados' -> falha de CONSULTA, nao 'nao esta entre'",
      r is None and "formato" in m, m)
estourou = None
try:
    com_get(defeito)
except TypeError as x:
    estourou = x
checa("CONTROLE NEGATIVO: defeito de codigo sobe", estourou is not None)

# ------------------------------------------------------------------------ REDE
if "--sem-rede" in sys.argv:
    print("\nREDE — pulada a pedido (--sem-rede). Nada foi medido na ALMG.")
else:
    print("\nREDE — ALMG de verdade, cache temporario vazio (leva ~20 s, 1 requisicao por vez)")
    e, a, m = almg.achar("CORONEL HENRIQUE", forcar=True)
    if e == "falha":
        checa("ALMG respondeu", False, f"NAO MEDIDO — {m}")
    else:
        checa("controle positivo: Coronel Henrique achado por nome",
              e == "achei" and a and a[0]["id"] == 26149, f"{e} {m} {a[:1]}")
        if e == "achei":
            dep = a[0]
            checa("ele esta em exercicio na legislatura 20",
                  any("legislatura 20: em exercicio" == s for s in dep["situacoes"]),
                  "; ".join(dep["situacoes"]))
            r = almg.proposicoes(dep["id"], dep["nome"], "educação")
            checa("controle positivo: proposicoes de autoria sob 'educacao'",
                  r["confirmados"] > 0 and r["itens"], f"{r['confirmados']} de {r['devolvidos']}")
            checa("todo item listado tem o id dele na matricula",
                  all(str(dep["id"]) in almg.matriculas(i) for i in r["itens"]))
            r = almg.proposicoes(dep["id"], dep["nome"], "xzqwvb")
            checa("controle negativo: palavra inventada -> zero",
                  r["confirmados"] == 0 and r["devolvidos"] == 0, str(r["total_busca"]))
        e, a, m = almg.achar("ZZQX INVENTADO SILVA")
        checa("controle negativo: nome inventado -> nao_achado", e == "nao_achado", m)
        e, a, m = almg.achar("HENRIQUE")
        checa("homonimo real: 'Henrique' -> homonimos, nao escolhe",
              e == "homonimos" and len(a) >= 2, f"{m}: {[x['nome'] for x in a]}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
