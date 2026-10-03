#!/usr/bin/env python3
"""Registro de mandato estadual em Minas Gerais — Assembleia Legislativa (ALMG).

Acha o deputado estadual na ALMG por nome e lista as proposicoes de autoria
dele que a busca da ALMG devolve para uma palavra-chave.

COMO RODAR:
  python3 almg.py --buscar "Coronel Henrique"
  python3 almg.py --proposicoes 26149 --termo educacao --termo agropecuaria
  python3 almg.py --buscar "..." --forcar        (ignora o cache do dia)

O que este cliente usa, e o que ele NAO usa, foi medido em 03/10/2026 contra
https://dadosabertos.almg.gov.br — nao escrito sobre a documentacao. A
documentacao (OpenAPI 3.0.1, versao 2.3) mora em /api/ajuda/swagger/endpoints/lastest.
O endereco antigo /ws/... responde 302 para /api/v2/...

  FUNCIONA                                           MEDIDO
  /api/v2/deputados/em_exercicio                     200, 77 deputados, chave "list"
  /api/v2/deputados/que_exerceram_mandato            200, 4, chave "listaDeputado"
  /api/v2/deputados/que_renunciaram                  200, 5, chave "list"
  /api/v2/legislaturas/19/deputados/em_exercicio     200, 76, chave "listaDeputado"
  /api/v2/proposicoes/pesquisa/direcionada           200, envelope "resultado" com
     ?aut=<nome>&ass=<termo>&sitTram=2&ord=0&tp=N    noOcorrencias, listaItem, consulta
  /api/v2/deputados/{id inexistente}                 404 (JSON "Recurso nao encontrado")

  O ENVELOPE MUDA DE NOME ENTRE LISTAS DO MESMO TIPO ("list" num endpoint,
  "listaDeputado" no vizinho). Por isso extrair_lista() aceita os dois e recusa
  em voz alta quando nao acha nenhum — resposta fora do formato medido NAO e
  "deputado nao achado".

  ARMADILHAS MEDIDAS, e o que este script faz com cada uma:

  1. /legislaturas/pesquisa_deputados?nome= QUEBRA SEM ACENTO: "Mário Henrique"
     acha, "Mario Henrique" devolve vazio; "Betão" acha, "Betao" nao. O nome de
     urna do TSE nem sempre tem o acento que a ALMG usa. Por isso a busca de
     deputado NAO usa esse filtro: baixa as listas (uma vez por dia, em cache) e
     compara aqui, sem acento, com limpar().

  2. O filtro aut= da pesquisa de proposicoes e busca por TEXTO, nao por pessoa:
     o proprio servidor ecoa a consulta como MATCH(autor: ...). Medido: aut=
     "Coronel Henrique" + ass=agropecuaria trouxe, entre 100 itens, um RQN cujo
     unico "Henrique" na autoria era o deputado Carlos Henrique. Por isso cada
     item passa por autoria_confirmada(), que procura o ID do deputado no campo
     "matricula" (um id por coautor; 201 de 201 itens alinhados com o campo
     autor, medido) e so cai para o nome quando a matricula falta. E o total que o servidor diz (noOcorrencias) NUNCA e
     impresso como contagem de autoria — ele conta o que a busca de texto achou.

  3. O filtro ass= NAO quebra com acento (ao contrario da Camara): educacao e
     educação deram 161 e 161; saude/saúde 156 e 156; agropecuaria/agropecuária
     187 e 187 (aut="Coronel Henrique", sitTram=2). aut= tambem nao: Betão e
     Betao deram 3150 e 3150. O termo vai sem acento mesmo assim, por coerencia
     com criterios.py.

  4. "agro" sozinho quase nao casa: 1 resultado, contra 138 para agricultura,
     187 para agropecuaria, 56 para rural, 17 para produtor (mesmo autor, com
     ou sem th=true, o tesauro nao muda "agro"). A busca e por termo indexado
     nos campos ementa, assuntoGeral, indexacao, observacao, evento, apelido,
     resumo e assunto — nao por tema. Ausencia sob um termo nao e ausencia de
     atuacao no tema.

  5. Autoria coletiva e comum: uma PEC aparece com 30+ deputados na autoria.
     A saida marca quantos assinam, para que coautoria nao seja lida como
     autoria individual.

  LIMITE DE USO DA PROPRIA ALMG (pagina /documentacao/index, lida em 03/10/2026):
  no maximo duas requisicoes simultaneas e no minimo UM SEGUNDO entre o fim de
  uma e o inicio da outra, sob pena de bloqueio sem aviso. PAUSA = 1.5 s, uma
  requisicao por vez.

  CONTROLES MEDIDOS:
    nome inventado ("Zzqx Inventado Silva") como aut=  -> 0 ocorrencias
    palavra inventada ("xzqwvb") com aut= real          -> 0 ocorrencias
    "Cabo Diego" como aut=, e "Diego" em pesquisa_deputados -> 0 / lista vazia

LIMITE DE COBERTURA, que precisa ser dito em toda saida:
  So Minas Gerais. As outras 26 assembleias nao tem padrao comum e nao sao
  consultadas. As listas usadas cobrem as legislaturas 19 e 20 (2019 a 2027);
  quem foi deputado estadual antes disso nao e procurado. Quem nao aparece
  aqui nao tem registro NESTA fonte — ausencia de FONTE, nao juizo sobre a
  pessoa. Contagem de proposicao e volume de autoria, nao qualidade.
"""
import argparse, http.client, json, os, re, socket, sys, time, unicodedata
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

# Modulo irmao: a regra de juncao por nome e uma so para ALMG, Camara e Senado.
# dont_write_bytecode antes do import — esta pasta viaja inteira na
# distribuicao e nao pode levar __pycache__.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import juncao as _juncao

API = "https://dadosabertos.almg.gov.br/api/v2"
RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
CACHE = os.path.join(RAIZ, "dados", "cache-almg")
PAUSA = 1.5          # a ALMG pede >= 1 s entre requisicoes
LEGISLATURA_ATUAL = 20

# (caminho, legislatura, situacao). Os da legislatura atual nao tem prefixo
# /legislaturas/20 porque e assim que a API os publica — medido acima.
LISTAS = [
    ("/deputados/em_exercicio",          20, "em exercicio"),
    ("/deputados/que_exerceram_mandato", 20, "exerceu mandato"),
    ("/deputados/que_se_afastaram",      20, "afastado"),
    ("/deputados/que_renunciaram",       20, "renunciou"),
    ("/deputados/que_perderam_mandato",  20, "perdeu o mandato"),
    ("/legislaturas/19/deputados/em_exercicio",          19, "em exercicio no fim da legislatura"),
    ("/legislaturas/19/deputados/que_exerceram_mandato", 19, "exerceu mandato"),
    ("/legislaturas/19/deputados/que_se_afastaram",      19, "afastado"),
    ("/legislaturas/19/deputados/que_renunciaram",       19, "renunciou"),
    ("/legislaturas/19/deputados/que_perderam_mandato",  19, "perdeu o mandato"),
]


class FalhaDeConsulta(Exception):
    """A ALMG nao respondeu, ou respondeu fora do formato medido.

    Existe para que falha de CONSULTA nunca vire "nao achado". As duas coisas
    saem iguais num quadro comparativo se ninguem as separar — e "nao achado"
    e lido como "nao fez nada"."""


# O que e falha de transporte (rede, servidor, timeout). Erro de codigo
# (TypeError, NameError...) NAO entra: tem de subir como traceback, senao um
# defeito da ferramenta se disfarca de "a ALMG esta fora do ar".
FALHAS_DE_TRANSPORTE = (urllib.error.URLError, socket.timeout, TimeoutError,
                        ConnectionError, http.client.HTTPException)


def limpar(t):
    """Sem acento e sem caixa — mesma funcao de criterios.py e camara.py."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def agora():
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def quando_arquivo(caminho):
    ts = os.path.getmtime(caminho)
    return datetime.fromtimestamp(ts).astimezone().replace(microsecond=0).isoformat()


def descrever(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"a ALMG respondeu HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"erro de rede: {e.reason}"
    return f"erro de rede: {type(e).__name__}: {e}"


def pegar(caminho, apelido=None, forcar=False):
    """GET com cache em disco por dia. Devolve (dados, url, de_cache, quando).

    Levanta FalhaDeConsulta em erro de transporte e em corpo que nao e JSON.
    quando e o instante em que O DADO foi obtido (do cache: mtime do arquivo)."""
    sep = "&" if "?" in caminho else "?"
    url = f"{API}{caminho}{sep}formato=json"
    arq = None
    if apelido:
        os.makedirs(CACHE, exist_ok=True)
        seguro = re.sub(r"[^a-z0-9_.-]", "_", limpar(apelido))
        arq = os.path.join(CACHE, f"{seguro}__{time.strftime('%Y-%m-%d')}.json")
        if os.path.exists(arq) and not forcar:
            with open(arq, encoding="utf-8") as f:
                return json.load(f), url, True, quando_arquivo(arq)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "vote-melhor/0.3 (Compendia; ferramenta de transparencia)"})
    time.sleep(PAUSA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            texto = r.read().decode("utf-8")
    except FALHAS_DE_TRANSPORTE as e:
        raise FalhaDeConsulta(f"{descrever(e)} — {url}") from e
    try:
        dados = json.loads(texto)
    except ValueError as e:
        raise FalhaDeConsulta(f"a ALMG respondeu algo que nao e JSON — {url}") from e
    if arq:
        with open(arq, "w", encoding="utf-8") as f:
            f.write(texto)
    return dados, url, False, agora()


def extrair_lista(d, url):
    """As listas de deputados vem em "list" ou em "listaDeputado" — medido."""
    if isinstance(d, dict):
        for k in ("list", "listaDeputado"):
            if isinstance(d.get(k), list):
                return d[k]
    raise FalhaDeConsulta(f"resposta fora do formato medido (sem 'list' nem "
                          f"'listaDeputado') — {url}")


def listar_deputados(forcar=False):
    """Todos os deputados das listas em LISTAS, sem repetir id. Cada um leva
    as situacoes em que aparece. Devolve (deputados, urls)."""
    por_id, urls = {}, []
    for caminho, leg, sit in LISTAS:
        apelido = "lista" + caminho.replace("/", "_")
        d, url, _c, _q = pegar(caminho, apelido, forcar)
        urls.append(url)
        for x in extrair_lista(d, url):
            if "id" not in x or "nome" not in x:
                raise FalhaDeConsulta(f"item de lista sem id ou nome — {url}")
            reg = por_id.setdefault(x["id"], {"id": x["id"], "nome": x["nome"],
                                              "partido": x.get("partido", "?"),
                                              "situacoes": []})
            reg["situacoes"].append(f"legislatura {leg}: {sit}")
    return list(por_id.values()), urls


def casar(nome, deputados):
    """Casa o nome de urna do TSE com a lista da ALMG. Devolve (estado, achados, motivo).

    estado: "achei" | "homonimos" | "parcial" | "nao_achado". So "achei" liga
    registro — a regra (e o porque medido) esta em juncao.py, a mesma para
    ALMG, Camara e Senado."""
    estado, achados, motivo = _juncao.casar(nome, deputados, lambda d: d["nome"])
    if estado == "nao_achado" and motivo == "sem parlamentar de nome identico":
        motivo = "nao consta nas listas da ALMG das legislaturas 19 e 20"
    return estado, achados, motivo


def achar(nome, forcar=False):
    """(estado, achados, motivo). estado "falha" quando a ALMG nao respondeu —
    nunca confundido com "nao_achado"."""
    try:
        deps, _urls = listar_deputados(forcar)
    except FalhaDeConsulta as e:
        return "falha", [], f"nao consegui consultar a ALMG agora ({e})"
    return casar(nome, deputados=deps)


def autores(item):
    """Nomes de deputado na autoria. O campo vem como linhas
    "Deputado <nome>   <partido>" (colunas separadas por 2+ espacos)."""
    nomes = []
    for linha in (item.get("autor") or "").split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        nome = re.split(r"\s{2,}", linha)[0]
        nome = re.sub(r"^(Deputad[oa])\s+", "", nome)
        nomes.append(nome)
    return nomes


def matriculas(item):
    """Ids ALMG da autoria. O campo "matricula" traz um id por linha, na mesma
    ordem das linhas de "autor" — medido em 03/10/2026: 201 de 201 itens com o
    mesmo numero de ids e de nomes, e o id 26149 presente exatamente nos itens
    em que "Coronel Henrique" esta na autoria."""
    return re.findall(r"\d+", item.get("matricula") or "")


def autoria_confirmada(item, id_almg, nome_almg):
    """O id na matricula e a prova; o nome so vale quando a matricula falta.
    Id nao tem homonimo; nome tem."""
    ids = matriculas(item)
    if ids:
        return str(id_almg) in ids
    alvo = limpar(nome_almg)
    return any(limpar(n) == alvo for n in autores(item))


def proposicoes(id_almg, nome_almg, termo, limite=3, tamanho=100, forcar=False):
    """Proposicoes em que nome_almg aparece na autoria e que a busca da ALMG
    devolve para o termo. Levanta FalhaDeConsulta se a ALMG nao responder.

    nome_almg tem de ser o nome COMO A ALMG O ESCREVE (da lista), nao o nome de
    urna do TSE: e ele que vai no filtro aut=. A autoria e confirmada pelo id. Devolve dict com: itens (ate `limite`, mais recentes primeiro),
    confirmados (quantos dos `tamanho` primeiros resultados tem o nome na
    autoria), devolvidos (quantos itens vieram), total_busca (noOcorrencias,
    que conta a busca de TEXTO, nao autoria), url."""
    t = limpar(termo)
    q = urllib.parse.urlencode({"aut": nome_almg, "ass": t, "sitTram": 2,
                                "ord": 0, "tp": tamanho, "p": 1})
    d, url, _c, quando = pegar(f"/proposicoes/pesquisa/direcionada?{q}",
                               f"prop_{nome_almg}_{t}_{tamanho}", forcar)
    r = d.get("resultado") if isinstance(d, dict) else None
    if not isinstance(r, dict) or r.get("erro") is True:
        raise FalhaDeConsulta(f"resposta fora do formato medido (sem 'resultado') — {url}")
    lista = r.get("listaItem") or []
    meus = [i for i in lista if autoria_confirmada(i, id_almg, nome_almg)]
    return {"itens": meus[:limite], "confirmados": len(meus), "devolvidos": len(lista),
            "total_busca": r.get("noOcorrencias"), "url": url, "quando": quando}


def linha_item(i):
    # requerimento (RQN, RQC) nao tem ementa: o texto vem em "assunto" — medido
    em = " ".join((i.get("ementa") or i.get("assunto") or "").split())
    n = max(len(matriculas(i)), len(autores(i)))
    coaut = "" if n <= 1 else f" [autoria coletiva: {n} deputados]"
    return f"{i.get('siglaTipoProjeto','?')} {i.get('numero','?')}/{i.get('ano','?')}{coaut} — {em[:78]}"


def resumo(r):
    """Uma linha que diz o que foi contado e sobre que universo. O total da
    busca (noOcorrencias) e da busca de TEXTO, e pode incluir outro autor
    (armadilha 2 do cabecalho) — por isso sai rotulado como tal."""
    s = (f"{r['confirmados']} com este deputado na autoria, entre os {r['devolvidos']} "
         f"primeiros resultados")
    if r["total_busca"] and r["total_busca"] > r["devolvidos"]:
        s += f" (a busca de texto devolveu {r['total_busca']}; so a 1a pagina foi lida)"
    return s


def cmd_buscar(nome, forcar):
    estado, achados, motivo = achar(nome, forcar)
    print(f"Deputados estaduais de MG (ALMG, legislaturas 19 e 20) para \"{nome}\"")
    if estado == "falha":
        print(f"  {motivo}")
        print("  Isso e falha de CONSULTA, nao ausencia de registro. Tente de novo mais tarde.")
        return 2
    print(f"  resultado: {motivo}\n")
    for d in achados:
        print(f"  {d['id']:<8} {d['nome']:<34} {d['partido']:<14} {'; '.join(d['situacoes'])}")
    if estado == "nao_achado":
        print("  nenhum. Ausencia de FONTE, nao juizo sobre a pessoa: estas listas")
        print("  trazem so quem foi deputado estadual em MG de 2019 em diante.")
    print("\n  A juncao e por NOME, nao por documento. Confira que e a mesma pessoa.")
    return 0


def cmd_proposicoes(ident, termos, forcar):
    try:
        deps, _ = listar_deputados(forcar)
    except FalhaDeConsulta as e:
        print(f"nao consegui consultar a ALMG agora ({e})", file=sys.stderr)
        return 2
    dep = next((d for d in deps if str(d["id"]) == str(ident)), None)
    if dep is None:
        print(f"id {ident} nao esta nas listas da ALMG das legislaturas 19 e 20.")
        return 1
    print(f"{dep['nome']} ({dep['partido']}) — id ALMG {dep['id']}")
    for t in termos:
        try:
            r = proposicoes(dep["id"], dep["nome"], t, forcar=forcar)
        except FalhaDeConsulta as e:
            print(f"\n  termo \"{limpar(t)}\": nao consegui consultar a ALMG agora ({e})")
            continue
        print(f"\n  termo \"{limpar(t)}\": {resumo(r)}")
        for i in r["itens"]:
            print(f"    {linha_item(i)}")
        print(f"  fonte: {r['url']}")
    print()
    print("  Contagem e VOLUME de autoria sob um termo, nao qualidade nem aprovacao.")
    print("  Ausencia sob um termo e ausencia de PROPOSICAO COM ESSE TERMO, nao de atuacao.")
    print("  Este script nao pontua, nao ordena por merito e nao recomenda voto.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Registro de mandato estadual em MG (ALMG).")
    ap.add_argument("--buscar", metavar="NOME", help="acha deputado estadual de MG por nome")
    ap.add_argument("--proposicoes", metavar="ID", help="proposicoes de autoria de UM deputado (id ALMG)")
    ap.add_argument("--termo", action="append", default=[], help="palavra-chave (repita para varias)")
    ap.add_argument("--forcar", action="store_true", help="ignora o cache do dia")
    a = ap.parse_args()
    if a.buscar:
        return cmd_buscar(a.buscar, a.forcar)
    if a.proposicoes:
        if not a.termo:
            print("Diga ao menos um --termo.", file=sys.stderr); return 1
        return cmd_proposicoes(a.proposicoes, a.termo, a.forcar)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
