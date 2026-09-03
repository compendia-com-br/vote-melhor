#!/usr/bin/env python3
"""Camada de critérios — o que o eleitor declara que importa, cruzado com o que
existe de verificável sobre cada candidato.

O QUE ESTE SCRIPT NUNCA FAZ, e por quê:

  Não pontua.      Se a ferramenta produz um número por candidato, ela recomenda,
                   e o aviso de neutralidade vira enfeite.
  Não ordena.      Ordem alfabética já é ordem. A ordem aqui é a que o usuário
                   pediu, ou o número na urna.
  Não dá nível.    "Alta aderência", "forte em educação" são juízo, não dado.
  Não preenche.    Onde não há material, sai "sem material verificável" — e a
                   coluna diz por quê, porque célula vazia num comparativo é lida
                   como defeito do candidato, e quase sempre é ausência de fonte.

O que ele FAZ: para cada eixo declarado, mostra o material verificável que existe
sobre aquele candidato naquele eixo, com a fonte. Quem julga é quem lê.
"""
import argparse, json, os, re, sqlite3, sys, time, unicodedata, urllib.parse, urllib.request

RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
BANCO = os.path.join(RAIZ, "dados", "tse.sqlite")
EIXOS = os.path.join(RAIZ, "dados", "meus-eixos.json")


def limpar(t):
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


# Onde cada eixo pode ter material verificável, e onde não pode.
# Isto não é opinião: é o mapa das fontes que a ferramenta alcança.
ONDE_HA_MATERIAL = {
    "cadastro": "registro de candidatura no TSE (partido, cargo, situação, bens, ocupação)",
    "proposta": "proposta de governo protocolada — SÓ para cargo executivo, por lei",
    "mandato":  "registro de mandato federal — SÓ deputado federal e senador",
}

AVISO_PROPOSTA = (
    "Senador, deputado federal e deputado estadual NÃO têm documento oficial de\n"
    "  propostas: a lei só exige de cargo executivo. Para esses, tudo que existir\n"
    "  é material de campanha, ou seja, alegação — e entra como alegação, com fonte."
)


def abrir():
    if not os.path.exists(BANCO):
        print(f"Banco não encontrado em {BANCO}.\n"
              f"Rode antes:  python3 ferramentas/coletar_tse.py --listar <UF>", file=sys.stderr)
        sys.exit(2)
    cx = sqlite3.connect(BANCO)
    cx.create_function("limpar", 1, limpar)
    cx.row_factory = sqlite3.Row
    return cx


def cmd_declarar(textos):
    """Grava os eixos ANTES de ver a lista. Critério declarado depois de ver os
    nomes é racionalização, não critério."""
    eixos = [t.strip() for t in textos if t.strip()]
    if not eixos:
        print("Nenhum eixo. Exemplo:\n"
              '  --declarar "educação básica" "saneamento" "gasto público"', file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(EIXOS), exist_ok=True)
    with open(EIXOS, "w", encoding="utf-8") as f:
        json.dump({"eixos": eixos}, f, ensure_ascii=False, indent=1)
    print(f"Eixos gravados em {EIXOS}\n")
    for i, e in enumerate(eixos, 1):
        print(f"  {i}. {e}")
    print("\n  Eles foram declarados ANTES de você ver a lista de candidatos.")
    print("  Isso é de propósito: critério escolhido depois de ver os nomes")
    print("  costuma ser justificativa do que já se decidiu.")
    return 0


def ler_eixos():
    if not os.path.exists(EIXOS):
        print("Nenhum eixo declarado ainda. Rode antes:\n"
              '  python3 ferramentas/criterios.py --declarar "tema 1" "tema 2"', file=sys.stderr)
        sys.exit(2)
    with open(EIXOS, encoding="utf-8") as f:
        return json.load(f)["eixos"]


API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"


def _get(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "vote-melhor/0.3 (Compendia; ferramenta de transparencia)"})
    time.sleep(0.5)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def achar_deputado(nome, uf):
    """Casa o candidato do TSE com o deputado em exercicio, por nome e UF.

    A juncao e por NOME, nao por CPF — o banco nao guarda CPF. Nome nao e chave:
    homonimo existe. Por isso o resultado sai marcado como juncao a conferir, e
    nunca como fato sobre a pessoa."""
    try:
        d = _get(f"{API_CAMARA}/deputados?siglaUf={uf}&itens=100")
    except Exception:
        return None, "nao consegui consultar a Camara agora"
    alvo = limpar(nome)
    exatos = [x for x in d["dados"] if limpar(x["nome"]) == alvo]
    if len(exatos) == 1:
        return exatos[0], "nome identico"
    parciais = [x for x in d["dados"]
                if alvo in limpar(x["nome"]) or limpar(x["nome"]) in alvo]
    if len(parciais) == 1:
        return parciais[0], "nome parcial — CONFERIR se e a mesma pessoa"
    if len(parciais) > 1:
        return None, f"{len(parciais)} homonimos — juncao incerta, nao afirmo nada"
    return None, "nao esta entre os deputados em exercicio hoje"


def proposicoes_do_eixo(id_dep, eixo, limite=3):
    """Proposicoes de autoria cuja ementa casa com o eixo.

    O filtro keywords da Camara QUEBRA com acento — medido em 02/09/2026:
    'educacao' devolve 2 itens, 'educacao' com cedilha devolve erro. Por isso a
    palavra vai sem acento."""
    termo = limpar(eixo).split()[0]
    url = (f"{API_CAMARA}/proposicoes?idDeputadoAutor={id_dep}"
           f"&keywords={urllib.parse.quote(termo)}&itens={limite}&ordem=DESC&ordenarPor=id")
    try:
        d = _get(url)
    except Exception:
        return [], url
    return d.get("dados", []), url


def cmd_cruzar(ids):
    eixos = ler_eixos()
    cx = abrir()
    L = 74
    print("=" * L)
    print("MATERIAL VERIFICAVEL POR EIXO — sem nota, sem ordem, sem nivel")
    print("=" * L)
    print("Seus eixos:", "; ".join(eixos))
    print()

    for ident in ids:
        r = cx.execute("SELECT * FROM candidatura WHERE id = ?", (ident,)).fetchone()
        if r is None:
            print(f"  id {ident}: nao esta no banco desta UF."); print(); continue
        d = dict(r)
        cargo = d.get("cargo_nome") or "sem dado"
        nome  = d.get("nomeUrna") or "sem dado"
        uf    = d.get("ufCandidatura") or ""
        print("-" * L)
        print(f"{nome}  —  {cargo}  —  {d.get('partido_sigla','?')}  —  n {d.get('numero','?')}")
        print(f"  situacao do registro: {d.get('descricaoSituacao','sem dado')}")

        executivo = limpar(cargo) in ("presidente", "governador", "prefeito")
        federal   = limpar(cargo) in ("deputado federal", "senador")

        dep, motivo = (None, "cargo sem fonte federal")
        if federal:
            dep, motivo = achar_deputado(nome, uf)
            if dep:
                print(f"  registro federal: id {dep['id']} ({motivo})")
            else:
                print(f"  registro federal: nao localizado — {motivo}")
        print()

        for e in eixos:
            print(f"  EIXO: {e}")
            if executivo:
                print("    proposta de governo protocolada no TSE — leia o documento.")
                print("    A ferramenta nao resume nem avalia promessa.")
            elif dep:
                props, url = proposicoes_do_eixo(dep["id"], e)
                if props:
                    termo = limpar(e).split()[0]
                    print(f"    proposicoes de autoria que a Camara indexa sob \"{termo}\":")
                    for x in props:
                        em = (x.get("ementa") or "").strip().replace("\n", " ")
                        print(f"      {x.get('siglaTipo')} {x.get('numero')}/{x.get('ano')} — {em[:78]}")
                    print(f"    fonte: {url}")
                else:
                    print("    nenhuma proposicao de autoria indexada sob essa palavra.")
                    print("    Isso e ausencia de PROPOSICAO COM ESSE TERMO, nao ausencia de")
                    print("    atuacao: a busca e por termo indexado, nao por tema.")
            else:
                print("    sem material verificavel neste eixo para este candidato.")
                print("    E ausencia de FONTE, nao juizo sobre a pessoa.")
            print()

    print("=" * L)
    print("Nota sobre proposta:")
    print(" ", AVISO_PROPOSTA)
    print()
    print("A busca de proposicao usa o indexador da Camara, que casa por termo")
    print("indexado — nem sempre a palavra aparece na ementa visivel. Leia a ementa")
    print("antes de afirmar que a proposicao trata do seu eixo.")
    print()
    print("A juncao com a Camara e feita por NOME, nao por CPF. Nome nao e chave:")
    print("homonimo existe. Confira que e a mesma pessoa antes de usar o registro.")
    print()
    print("Este quadro nao pontua, nao ordena por merito e nao recomenda voto.")
    print("=" * L)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Eixos do eleitor cruzados com material verificável.")
    ap.add_argument("--declarar", nargs="+", metavar="EIXO",
                    help="grava os temas que decidem seu voto (faça ANTES de ver a lista)")
    ap.add_argument("--eixos", action="store_true", help="mostra os eixos declarados")
    ap.add_argument("--cruzar", nargs="+", metavar="ID",
                    help="mostra o material verificável de cada candidato, por eixo")
    a = ap.parse_args()
    if a.declarar: return cmd_declarar(a.declarar)
    if a.eixos:
        for i, e in enumerate(ler_eixos(), 1): print(f"  {i}. {e}")
        return 0
    if a.cruzar: return cmd_cruzar(a.cruzar)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
