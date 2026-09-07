#!/usr/bin/env python3
"""Registro de mandato federal — Câmara dos Deputados.

O que este cliente entrega, e o que ele NAO entrega, foi medido em 02/09/2026,
nao suposto:

  FUNCIONA                                   MEDIDO
  /deputados?siglaUf=MG                      200, 53 deputados
  /deputados/{id}                            200, objeto
  /proposicoes?idDeputadoAutor={id}          200, 323 paginas para o id 74646
  /deputados/{id}/orgaos                     200, comissoes
  /deputados/{id}/frentes                    200, 54 frentes
  /deputados/{id}/historico                  200, partido e situacao no tempo

  NAO FUNCIONA                               MEDIDO
  /deputados/{id}/despesas                   200 com ZERO itens em 6 de 6
                                             combinacoes (3 deputados x 2 anos)
  /votacoes?idDeputado={id}                  HTTP 400

Por isso o eixo "como gastou" e o eixo "como votou" NAO existem nesta ferramenta.
Nao invente proxy: ausencia de fonte se declara, nao se contorna.

LIMITE DE COBERTURA, que precisa ser dito em toda saida:
  Este registro existe para deputado federal e senador. Deputado ESTADUAL esta em
  27 assembleias sem padrao, e governador e presidente tem historico executivo que
  nao esta aqui. Celula vazia num quadro comparativo e lida como "sem realizacao" —
  por isso a saida diz, sempre, a que categoria a ausencia pertence.
"""
import argparse, json, os, sys, time, unicodedata, urllib.request

API = "https://dadosabertos.camara.leg.br/api/v2"
RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
CACHE = os.path.join(RAIZ, "dados", "cache-camara")
PAUSA = 0.5


def limpar(t):
    """Sem acento e sem caixa. Casar texto em portugues sem normalizar acento
    falha calado — o padrao 'e ficha limpa' nunca acha 'e' ficha limpa'."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def pegar(caminho, apelido=None, forcar=False):
    """GET com cache em disco. Devolve (dados, url, de_cache)."""
    url = f"{API}{caminho}"
    if apelido:
        os.makedirs(CACHE, exist_ok=True)
        arq = os.path.join(CACHE, f"{apelido}__{time.strftime('%Y-%m-%d')}.json")
        if os.path.exists(arq) and not forcar:
            with open(arq, encoding="utf-8") as f:
                return json.load(f), url, True
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "vote-melhor/0.3 (Compendia; ferramenta de transparencia)",
    })
    time.sleep(PAUSA)
    with urllib.request.urlopen(req, timeout=30) as r:
        texto = r.read().decode("utf-8")
    dados = json.loads(texto)
    if apelido:
        with open(arq, "w", encoding="utf-8") as f:
            f.write(texto)
    return dados, url, False


def contar_paginas(caminho):
    """Conta o total lendo o link 'last', em vez de paginar tudo.
    Uma requisicao em vez de N — e o servidor e publico."""
    d, url, _ = pegar(f"{caminho}&itens=1")
    for l in d.get("links", []):
        if l.get("rel") == "last":
            import re
            m = re.search(r"pagina=(\d+)", l["href"])
            if m:
                return int(m.group(1)), url
    return len(d.get("dados", [])), url


def cmd_buscar(nome, uf, forcar):
    d, url, cache = pegar(f"/deputados?siglaUf={uf}&itens=100",
                          f"deputados_{uf}", forcar)
    alvo = limpar(nome)
    achados = [x for x in d["dados"] if alvo in limpar(x["nome"])]
    print(f"Deputados federais de {uf} em exercício com \"{nome}\" no nome")
    print(f"fonte: {url}  [{'cache' if cache else 'rede'}]\n")
    if not achados:
        print("  nenhum. Isso NÃO quer dizer que a pessoa não exerceu mandato:")
        print("  esta lista traz só quem está em exercício HOJE. Ex-deputado não aparece.")
        return 0
    for x in achados:
        print(f"  {x['id']:<8} {x['nome']:<38} {x.get('siglaPartido','?'):<8} {x.get('siglaUf','')}")
    print()
    print("  Quem não aparece nesta lista não exerce mandato de deputado federal")
    print("  hoje — é ausência de fonte, não ausência de realização.")
    return 0


def cmd_registro(ident, forcar):
    det, url_det, c1 = pegar(f"/deputados/{ident}", f"dep_{ident}", forcar)
    p = det["dados"]
    st = p.get("ultimoStatus", {})

    n_prop, url_prop = contar_paginas(f"/proposicoes?idDeputadoAutor={ident}")
    org, url_org, _ = pegar(f"/deputados/{ident}/orgaos?itens=100", f"org_{ident}", forcar)
    fre, url_fre, _ = pegar(f"/deputados/{ident}/frentes", f"fre_{ident}", forcar)
    his, url_his, _ = pegar(f"/deputados/{ident}/historico", f"his_{ident}", forcar)

    L = 66
    print("=" * L)
    print("REGISTRO DE MANDATO FEDERAL — dado da Câmara, sem interpretação")
    print("=" * L)
    print(f"{'Nome':<26}: {p.get('nomeCivil','sem dado')}")
    print(f"{'Nome parlamentar':<26}: {st.get('nome','sem dado')}")
    print(f"{'Partido e UF':<26}: {st.get('siglaPartido','?')} / {st.get('siglaUf','?')}")
    print(f"{'Situação':<26}: {st.get('situacao','sem dado')}")
    print(f"{'Condição eleitoral':<26}: {st.get('condicaoEleitoral','sem dado')}")
    print(f"{'Escolaridade':<26}: {p.get('escolaridade') or 'sem dado'}")
    print("-" * L)
    print(f"{'Proposições de autoria':<26}: {n_prop}")
    print(f"{'Comissões e órgãos':<26}: {len(org.get('dados',[]))}")
    for o in org.get("dados", [])[:6]:
        print(f"{'':28}- {o.get('siglaOrgao','')} — {o.get('titulo','')}")
    print(f"{'Frentes parlamentares':<26}: {len(fre.get('dados',[]))}")
    print(f"{'Registros de histórico':<26}: {len(his.get('dados',[]))}")
    vistos, linha = set(), []
    for h in his.get("dados", []):
        sig = h.get("siglaPartido")
        if sig and sig not in vistos:
            vistos.add(sig); linha.append(f"{h.get('dataHora','')[:4]} {sig}")
    if linha:
        print(f"{'Partidos no período':<26}: {' → '.join(linha)}")
    print("-" * L)
    print("NÃO DISPONÍVEL nesta fonte, medido em 02/09/2026:")
    print("  Despesas de gabinete  : endpoint responde 200 com ZERO itens")
    print("                          (3 deputados × 2 anos, 6 de 6 vazios)")
    print("  Como votou            : /votacoes?idDeputado devolve HTTP 400")
    print("  Presença em plenário  : não há endpoint")
    print("  Estes eixos não existem na ferramenta. Ausência de fonte se declara.")
    print("-" * L)
    print("Fonte e data da coleta")
    for rot, u in (("detalhe", url_det), ("proposições", url_prop),
                   ("órgãos", url_org), ("frentes", url_fre), ("histórico", url_his)):
        print(f"  {rot:<12}: {u}")
    print(f"  coletado em {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print()
    print("  Contagem de proposições é VOLUME de autoria, não qualidade nem")
    print("  aprovação. Este script não pontua, não ordena e não recomenda voto.")
    print()
    print("  Este registro existe porque esta pessoa exerce mandato de deputado")
    print("  federal; quem nunca exerceu não tem este registro — ausência de")
    print("  fonte, não ausência de realização.")
    print("=" * L)
    return 0


def cmd_cobertura(uf, forcar):
    """Diz que fatia da cédula tem registro federal. Existe porque célula vazia
    num comparativo é lida como 'sem realização' — e sem esta conta ninguém sabe
    que o eixo cobre uma fatia pequena."""
    d, url, cache = pegar(f"/deputados?siglaUf={uf}&itens=100", f"deputados_{uf}", forcar)
    n = len(d["dados"])
    print(f"Cobertura do registro de mandato federal em {uf}")
    print(f"fonte: {url}  [{'cache' if cache else 'rede'}]\n")
    print(f"  Deputados federais de {uf} em exercício hoje: {n}")
    print()
    print("  Em eleição geral a cédula tem 6 votos: presidente, governador,")
    print("  senador (2), deputado federal e deputado estadual.")
    print()
    print("  Registro de mandato existe para:")
    print("    deputado federal em exercício  — sim, por esta API")
    print("    senador                        — outra API, do Senado")
    print("    deputado estadual              — NÃO (27 assembleias sem padrão)")
    print("    governador e presidente        — NÃO (histórico executivo)")
    print("    candidato que nunca exerceu    — NÃO EXISTE registro para medir")
    print()
    print("  Portanto o eixo cobre uma fração pequena de quem está na cédula.")
    print("  Célula vazia aqui NÃO significa 'sem realização': significa que a")
    print("  categoria daquele candidato não tem fonte federal consultável.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Registro de mandato federal (Câmara).")
    ap.add_argument("--buscar", metavar="NOME", help="acha deputado em exercício por nome")
    ap.add_argument("--uf", default="MG", help="UF da busca (padrão MG)")
    ap.add_argument("--registro", metavar="ID", help="o registro de mandato de UM deputado")
    ap.add_argument("--cobertura", action="store_true",
                    help="diz que fatia da cédula este eixo cobre")
    ap.add_argument("--forcar", action="store_true", help="ignora o cache do dia")
    a = ap.parse_args()
    try:
        if a.buscar:      return cmd_buscar(a.buscar, a.uf, a.forcar)
        if a.registro:    return cmd_registro(a.registro, a.forcar)
        if a.cobertura:   return cmd_cobertura(a.uf, a.forcar)
        ap.print_help()
    except urllib.error.HTTPError as e:
        print(f"ERRO: a Câmara respondeu HTTP {e.code} para {e.url}", file=sys.stderr)
        print("  Se for 400, o endpoint provavelmente não aceita esse filtro.", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"ERRO de rede: {e.reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
