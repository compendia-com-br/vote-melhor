#!/usr/bin/env python3
"""Varre TODO o historico do git — nao so a arvore atual — atras de CPF e
titulo de eleitor, por VALOR.

COMO RODAR:  python3 ferramentas/varrer_historico.py
             python3 ferramentas/varrer_historico.py --repo /outro/repositorio
             python3 ferramentas/varrer_historico.py --autoteste

O Passo 4 do plano de distribuicao publica (docs/superpowers/plans/
2026-09-07-distribuicao-publica.md) trazia isto como o portao antes de tornar
o repositorio publico:

    git log --all --numstat --format="%H" | grep -i "cpf|titulo|credencial|senha|token"

--numstat imprime NOME DE ARQUIVO e contagem de linhas adicionadas/removidas —
nunca o CONTEUDO do arquivo. O grep casava o NOME, nao o dado dentro dele: um
arquivo chamado "candidatos.csv" com um CPF de verdade dentro passava liso, e
um arquivo chamado "cpf-antigo.txt" vazio disparava. E uma varredura que nao
varre, rodando bem na frente do portao mais caro do plano.

Este script varre o CONTEUDO de cada blob de cada commit alcancavel por
qualquer ref (branch, tag, remoto rastreado) — inclusive um blob que so
existiu num commit e foi apagado num commit seguinte, que nao aparece em
nenhum grep sobre a arvore atual. Reaproveita cpf_valido() e titulo_valido()
de verificar_dados.py: e a mesma conta que ja prova que o SQLite local esta
limpo, aplicada agora ao historico do git.

Nunca imprime o documento encontrado por extenso — a ferramenta que caça
vazamento nao pode ela mesma virar o vazamento (este projeto ja cometeu esse
erro uma vez, em verificar_dados.py; ver o comentario acima do print em
main() daquele arquivo). Cada achado sai com o valor mascarado, relatado por
commit, caminho e tipo.

Codigos: 0 limpo · 2 achou documento · 1 erro de uso ou repositorio invalido.
--autoteste sai 0 se os controles passarem, 1 se a varredura nao for confiavel.
"""
import argparse
import os
import subprocess
import sys
import tempfile

# Importar modulo do plugin escreve .pyc ao lado dele. Bloqueamos antes de
# manipular sys.path e fazer o import — mesmo padrao de testes/teste_*.py.
sys.dont_write_bytecode = True
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_REPO_PADRAO = os.path.dirname(_AQUI)
sys.path.insert(0, os.path.join(_RAIZ_REPO_PADRAO, "plugins", "vote-melhor", "ferramentas"))
import verificar_dados as vd  # noqa: E402  (import depois do sys.path de proposito)


def _git(repo, *args, entrada=None):
    """Roda git no repositorio `repo`. `entrada`, quando dado, vai para o
    stdin (usado pelo --batch). Devolve stdout em bytes."""
    r = subprocess.run(["git", "-C", repo, *args], input=entrada,
                        capture_output=True)
    if r.returncode != 0:
        erro = r.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} falhou: {erro}")
    return r.stdout


def _objetos_alcancaveis(repo):
    """(sha, caminho) de todo objeto alcancavel por QUALQUER ref — nao so o
    HEAD atual. `--all` e o que torna isto uma varredura de historico e nao
    de arvore: inclui branch abandonado, tag, e commit que só um remoto
    rastreado ainda enxerga. Caminho vem vazio para commit e para a arvore
    raiz; blob e arvore normalmente vem com caminho."""
    saida = _git(repo, "rev-list", "--objects", "--all").decode("utf-8", "replace")
    pares = []
    for linha in saida.splitlines():
        if not linha:
            continue
        partes = linha.split(" ", 1)
        sha = partes[0]
        caminho = partes[1] if len(partes) > 1 else ""
        pares.append((sha, caminho))
    return pares


def _tipos(repo, shas):
    """git cat-file --batch-check: um sha por linha de entrada, um tipo por
    linha de saida, na mesma ordem — sem um subprocesso por objeto."""
    entrada = ("\n".join(shas) + "\n").encode("utf-8") if shas else b""
    saida = _git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype)",
                 entrada=entrada).decode("utf-8", "replace")
    tipos = {}
    for linha in saida.splitlines():
        campos = linha.split(" ")
        if len(campos) >= 2 and campos[1] != "missing":
            tipos[campos[0]] = campos[1]
    return tipos


def _conteudo_dos_blobs(repo, shas_blob):
    """git cat-file --batch: le o CONTEUDO de cada blob pedido, num so
    processo. Cada objeto sai como '<sha> blob <tamanho>\\n<tamanho bytes>\\n'.
    O parsing usa o primeiro '\\n' para achar o fim do cabecalho (o
    cabecalho e sempre texto puro, o conteudo binario vem depois dele, nunca
    misturado)."""
    if not shas_blob:
        return {}
    entrada = ("\n".join(shas_blob) + "\n").encode("utf-8")
    bruto = _git(repo, "cat-file", "--batch", entrada=entrada)
    conteudos = {}
    i = 0
    while i < len(bruto):
        fim_cab = bruto.index(b"\n", i)
        cabecalho = bruto[i:fim_cab].decode("utf-8", "replace").split(" ")
        sha, tamanho = cabecalho[0], int(cabecalho[2])
        inicio = fim_cab + 1
        conteudos[sha] = bruto[inicio:inicio + tamanho]
        i = inicio + tamanho + 1  # +1 pula o '\n' que o git acrescenta apos cada bloco
    return conteudos


def _commits_de(repo, caminho, sha_blob):
    """So chamado para um achado: em quais commits este blob aparece neste
    caminho. Caro (um `ls-tree` por commit candidato) de proposito restrito
    aos poucos achados — nunca ao historico inteiro, que e varrido uma vez
    so via _conteudo_dos_blobs."""
    if not caminho:
        return ["(objeto sem caminho — arvore ou commit solto)"]
    saida = _git(repo, "log", "--all", "--format=%H", "--", caminho).decode(
        "utf-8", "replace")
    commits = [c for c in saida.splitlines() if c]
    achados_em = []
    for c in commits:
        r = subprocess.run(["git", "-C", repo, "ls-tree", c, "--", caminho],
                            capture_output=True, text=True)
        if sha_blob in r.stdout:
            achados_em.append(c[:12])
    return achados_em or ["(commit nao identificado)"]


def varrer_historico(repo):
    """Devolve a lista de achados no historico inteiro do repositorio git em
    `repo`. Lista vazia = historico limpo. Cada achado:
    {"commits": [...], "caminho": str, "tipo": "cpf"|"titulo", "valor_mascarado": str}
    — nunca o documento por extenso.
    """
    pares = _objetos_alcancaveis(repo)
    tipos = _tipos(repo, [sha for sha, _ in pares])
    shas_blob = sorted({sha for sha, _ in pares if tipos.get(sha) == "blob"})
    conteudos = _conteudo_dos_blobs(repo, shas_blob)

    achados = []
    cache_por_blob = {}  # sha -> [(tipo, valor), ...] — um blob identico repetido
    # em varios caminhos/commits (arquivo copiado, ou nunca mudou) e analisado
    # uma vez so, nao uma vez por aparicao.
    for sha, caminho in pares:
        dado = conteudos.get(sha)
        if dado is None:
            continue  # nao e blob (commit ou arvore) — ja filtrado por _tipos
        if sha not in cache_por_blob:
            texto = dado.decode("utf-8", "replace")
            encontrados = []
            for seq in vd.SEQ.findall(texto):
                tipo = ("cpf" if vd.cpf_valido(seq)
                        else "titulo" if vd.titulo_valido(seq) else None)
                if tipo:
                    encontrados.append((tipo, seq))
            cache_por_blob[sha] = encontrados
        for tipo, seq in cache_por_blob[sha]:
            achados.append({
                "commits": _commits_de(repo, caminho, sha),
                "caminho": caminho or "(sem caminho — objeto solto)",
                "tipo": tipo,
                "valor_mascarado": vd._prever_mascara(seq, ""),
            })
    return achados


def _autoteste():
    """Controle positivo E negativo, num repositorio git temporario — nunca
    no repositorio de verdade. Varredura que acha zero e indistinguivel de
    varredura quebrada; por isso este modo PROVA que a varredura acharia um
    documento se houvesse um, antes de confiar no resultado "limpo" do
    repositorio real.

    O controle positivo commita um CPF sintetico e depois o REMOVE num
    segundo commit — a arvore atual do repositorio de teste fica limpa, e
    so o historico guarda o documento. E o cenario exato que --numstat sobre
    a arvore atual nunca pegaria, e a razao de este script existir.
    """
    falhas = []

    def checa(nome, condicao, detalhe):
        print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
        if not condicao:
            falhas.append(nome)

    with tempfile.TemporaryDirectory() as d:
        def git(*args):
            subprocess.run(["git", "-C", d, *args], capture_output=True, check=True)

        git("init", "-q")
        git("config", "user.email", "autoteste@local")
        git("config", "user.name", "Autoteste varrer_historico")

        # CPF sintetico valido (digitos verificadores corretos), usado em
        # documentacao publica brasileira como exemplo — nao pertence a
        # ninguem. Commitado e DEPOIS apagado: some da arvore, fica no historico.
        cpf_exemplo = "52998224725"
        caminho_sujo = os.path.join(d, "vazado.txt")
        with open(caminho_sujo, "w") as fh:
            fh.write(f"cpf do candidato anotado a mao: {cpf_exemplo}\n")
        git("add", "vazado.txt")
        git("commit", "-q", "-m", "commit com documento sintetico (autoteste)")
        os.remove(caminho_sujo)
        git("add", "-A")
        git("commit", "-q", "-m", "remove o arquivo — some da arvore, nao do historico")

        # Numeros que NAO sao documento: gasto de campanha (11 digitos, CPF
        # invalido) e id de candidato do TSE (12 digitos, título invalido —
        # a faixa de UF de "130002539775" e 97, fora de 01-28). Mesmos dois
        # casos do controle negativo de testes/teste_verificar_dados.py.
        caminho_limpo = os.path.join(d, "limpo.txt")
        with open(caminho_limpo, "w") as fh:
            fh.write("gasto de campanha: 12345678901\nid candidato: 130002539775\n")
        git("add", "limpo.txt")
        git("commit", "-q", "-m", "commit sem documento (autoteste)")

        achados = varrer_historico(d)
        tipos_achados = sorted({a["tipo"] for a in achados})
        arvore_atual_limpa = not os.path.exists(caminho_sujo)
        veio_de_arquivo_limpo = any(a["caminho"] == "limpo.txt" for a in achados)

        print("AUTOTESTE — prova que a varredura acharia um documento real\n")
        checa("controle positivo: acha o CPF sintetico mesmo apagado da arvore atual",
              "cpf" in tipos_achados, f"tipos achados={tipos_achados}")
        checa("a arvore ATUAL do repositorio de teste esta limpa "
              "(prova que o achado veio do historico, nao da arvore)",
              arvore_atual_limpa, f"arquivo ainda existe? {not arvore_atual_limpa}")
        checa("controle negativo: numero que nao e documento nao dispara",
              not veio_de_arquivo_limpo, f"achados em limpo.txt={veio_de_arquivo_limpo}")

    print()
    if falhas:
        print(f"AUTOTESTE REPROVADO: {len(falhas)} controle(s) — {falhas}")
        print("A varredura NAO esta confiavel. Nao use o resultado dela no "
              "portao de publicacao ate corrigir.")
        return 1
    print("AUTOTESTE OK — a varredura acha o que precisa achar.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Varre TODO o historico do git (nao so a arvore atual) "
                     "atras de CPF e titulo de eleitor, por valor.")
    ap.add_argument("--repo", default=_RAIZ_REPO_PADRAO,
                     help=f"repositorio a varrer (padrao: {_RAIZ_REPO_PADRAO})")
    ap.add_argument("--autoteste", action="store_true",
                     help="controle positivo e negativo, num repositorio git "
                          "temporario — nunca no repositorio real")
    a = ap.parse_args()

    if a.autoteste:
        return _autoteste()

    repo = os.path.abspath(a.repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"Nao e um repositorio git (sem .git): {repo}", file=sys.stderr)
        return 1

    print(f"Varredura por valor do HISTORICO INTEIRO em {repo}")
    print("(todo blob de todo commit alcancavel por qualquer ref — nao so a arvore atual)\n")
    try:
        achados = varrer_historico(repo)
    except RuntimeError as e:
        print(f"Erro ao rodar git: {e}", file=sys.stderr)
        return 1

    if not achados:
        print("Nenhum CPF e nenhum titulo de eleitor encontrado em nenhum "
              "commit alcancavel.")
        print("Rode com --autoteste antes de confiar neste resultado: "
              "varredura que acha zero e indistinguivel de varredura quebrada.")
        return 0

    print(f"ACHOU {len(achados)} documento(s) de identificacao no historico:\n")
    for a_ in achados:
        commits = ", ".join(a_["commits"])
        print(f"  {a_['tipo']:>6}  {a_['caminho']}  commit(s)={commits}  "
              f"{a_['valor_mascarado']}")
    print("\nEsses valores estao no historico do git, nao so na arvore atual.")
    print("Tornar o repositorio publico agora clonaria e indexaria isso para sempre.")
    return 2


if __name__ == "__main__":
    # sys.exit(main() or 0), nao main() solto: portao que diz ACHOU e sai 0
    # nao para script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
