#!/usr/bin/env python3
"""Registro de mandato de senador — Senado Federal.

O que este cliente entrega, e o que ele NAO entrega, foi medido em 07/09/2026,
nao suposto — nao escrito sobre a documentacao do Senado.

  FUNCIONA                                        MEDIDO
  /senador/lista/atual                            200, 129367 bytes, 81 senadores
  /senador/lista/atual?uf=UF                      200, filtro no servidor (3 para
                                                   MG; minusculo "mg" funciona igual)
  /senador/{cod}                                  200, objeto (cod 5732 = Rodrigo
                                                   Pacheco)
  /senador/{cod}/mandatos                         200, lista, mais recente primeiro
                                                   (cod 739: 2 mandatos, ordem OK)
  /senador/{cod}/comissoes                        200, lista (28 para o 5732, 12
                                                   sem DataFim = em exercicio hoje)
  /senador/{cod}/autorias        *fim de vida*     200, lista (304 para o 5732)
  /senador/{cod}/relatorias      *fim de vida*     200, lista (284 para o 5732)
  /senador/{cod}/votacoes        *fim de vida*     200, lista (1142 para o 5732,
                                                   voto nominal por materia)

  NAO FUNCIONA (200 no corpo, sem a chave         MEDIDO
  que teria o dado — nao lista vazia visivel)
  /senador/lista/atual?uf=<UF invalida>           200, 301 bytes, SEM a chave
                                                   "Parlamentares" (nao "[]")
  /senador/{codigo inexistente}                   200, 304 bytes, SEM a chave
                                                   "Parlamentar" (nao "{}")
  pedido sem header Accept: application/json      200, mas devolve XML, nao JSON
                                                   (por isso o header e obrigatorio)

  *fim de vida* — os tres endpoints marcados respondem 200 com dado real hoje,
  mas o proprio JSON do Senado traz Metadados.Descontinuacao em cada um, com
  DataDesativacaoCompleta = "2026-02-01" — MAIS DE 7 MESES ANTES desta medicao
  (07/09/2026). O servico continua no ar depois da propria data que o Senado
  deu para desativa-lo por completo. Isto pode parar amanha, sem mudar de
  codigo de status: e o mesmo tipo de modo de falha silenciosa que a Camara
  mostrou (200 vazio) — aqui e uma validade ja vencida, nao um corpo vazio.
  Substituto documentado, nao medido nesta tarefa: /dadosabertos/processo
  (autorias e relatorias) e /dadosabertos/votacao (votacoes).

  Caso de colecao com um item so (citado no briefing como risco): testado em
  Mandato (cod 5732, 1 mandato) e em Telefone (cod 5672, 1 telefone) — os dois
  vieram como LISTA de um elemento, nao como objeto solto. Nao reproduzi o
  colapso ao vivo nesta medicao. A funcao caminhar() abaixo trata os dois jeitos
  do mesmo modo, porque o dia em que faltar essa defesa nao avisa antes.

Por isso "Materias de autoria", "Materias de relatoria" e "Votacoes
registradas" saem sempre com o aviso de fim de vida junto, e um silencio
futuro nestes tres NAO deve ser lido como bug deste script.

LIMITE DE COBERTURA, que precisa ser dito em toda saida:
  Este registro existe para senador em exercicio. Quem nunca exerceu mandato
  no Senado NAO tem registro aqui, e isso e ausencia de fonte — nao e ausencia
  de realizacao. Celula vazia num quadro comparativo e lida como "nao fez
  nada", por isso a saida diz sempre a que categoria a ausencia pertence.
"""
import argparse, json, os, sys, time, unicodedata, urllib.error, urllib.request

API = "https://legis.senado.leg.br/dadosabertos"
RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
CACHE = os.path.join(RAIZ, "dados", "cache-senado")
PAUSA = 0.5


def limpar(t):
    """Sem acento e sem caixa. Casar texto em portugues sem normalizar acento
    falha calado — o padrao 'favaro' nunca acha 'Fávaro'. Ja mordeu este
    projeto quatro vezes."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def caminhar(obj, *chaves):
    """Desce um envelope profundo com .get em cada chave, sem nunca lancar
    KeyError. Devolve [] quando o caminho quebra em qualquer ponto —
    inclusive quando o Senado responde 200 sem a propria chave (medido: UF
    invalida e codigo de senador inexistente respondem assim, cada um sem a
    chave que teria o dado — nao uma lista vazia visivel).

    Quando o valor final e um dict solto, devolve [dict]: colecao de um item
    as vezes chega sem colchetes em envelopes deste formato. Nao reproduzi
    esse colapso ao vivo nesta medicao (Mandato e Telefone com 1 item vieram
    como lista mesmo assim) — a defesa fica escrita do mesmo jeito, porque o
    dia em que faltar nao avisa antes.
    """
    cur = obj
    for chave in chaves:
        if not isinstance(cur, dict) or chave not in cur:
            return []
        cur = cur[chave]
    if cur is None:
        return []
    return cur if isinstance(cur, list) else [cur]


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


def cmd_buscar(nome, uf, forcar):
    d, url, cache = pegar(f"/senador/lista/atual?uf={uf}", f"senadores_{uf}", forcar)
    lista = caminhar(d, "ListaParlamentarEmExercicio", "Parlamentares", "Parlamentar")
    alvo = limpar(nome)
    achados = [p for p in lista if alvo in limpar(
        p.get("IdentificacaoParlamentar", {}).get("NomeParlamentar", ""))]
    print(f"Senadores de {uf} em exercício com \"{nome}\" no nome")
    print(f"fonte: {url}  [{'cache' if cache else 'rede'}]\n")
    if not achados:
        print("  nenhum. Isso NÃO quer dizer que a pessoa não exerceu mandato:")
        print("  esta lista traz só quem está em exercício HOJE. Ex-senador não aparece.")
        print("  Zero também pode ser UF errada: confira a sigla — todo estado tem 3")
        print("  cadeiras de senador, então zero nunca é a contagem real de uma UF válida.")
        return 0
    for p in achados:
        ip = p.get("IdentificacaoParlamentar", {})
        print(f"  {ip.get('CodigoParlamentar','?'):<8} {ip.get('NomeParlamentar','?'):<28} "
              f"{ip.get('SiglaPartidoParlamentar','?'):<14} {ip.get('UfParlamentar','')}")
    print()
    print("  Quem não aparece nesta lista não exerce mandato de senador hoje —")
    print("  é ausência de fonte, não ausência de realização.")
    return 0


def cmd_registro(cod, forcar):
    det, url_det, _ = pegar(f"/senador/{cod}", f"sen_{cod}", forcar)
    achado = caminhar(det, "DetalheParlamentar", "Parlamentar")
    if not achado:
        print(f"ERRO: código {cod} não corresponde a nenhum senador nesta fonte.", file=sys.stderr)
        print("  Medido: código inexistente responde HTTP 200 sem a chave 'Parlamentar' —", file=sys.stderr)
        print("  isso não é falha de rede, é ausência de registro para este código.", file=sys.stderr)
        return 1
    p = achado[0]
    ip = p.get("IdentificacaoParlamentar", {})

    man, url_man, _ = pegar(f"/senador/{cod}/mandatos", f"man_{cod}", forcar)
    mandatos = caminhar(man, "MandatoParlamentar", "Parlamentar", "Mandatos", "Mandato")

    com, url_com, _ = pegar(f"/senador/{cod}/comissoes", f"com_{cod}", forcar)
    comissoes = caminhar(com, "MembroComissaoParlamentar", "Parlamentar", "MembroComissoes", "Comissao")
    comissoes_hoje = [c for c in comissoes if not c.get("DataFim")]

    aut, url_aut, _ = pegar(f"/senador/{cod}/autorias", f"aut_{cod}", forcar)
    autorias = caminhar(aut, "MateriasAutoriaParlamentar", "Parlamentar", "Autorias", "Autoria")

    rel, url_rel, _ = pegar(f"/senador/{cod}/relatorias", f"rel_{cod}", forcar)
    relatorias = caminhar(rel, "MateriasRelatoriaParlamentar", "Parlamentar", "Relatorias", "Relatoria")

    vot, url_vot, _ = pegar(f"/senador/{cod}/votacoes", f"vot_{cod}", forcar)
    votacoes = caminhar(vot, "VotacaoParlamentar", "Parlamentar", "Votacoes", "Votacao")

    L = 66
    print("=" * L)
    print("REGISTRO DE MANDATO DE SENADOR — dado do Senado, sem interpretação")
    print("=" * L)
    print(f"{'Nome':<26}: {ip.get('NomeCompletoParlamentar') or 'sem dado'}")
    print(f"{'Nome parlamentar':<26}: {ip.get('NomeParlamentar','sem dado')}")
    print(f"{'Partido e UF':<26}: {ip.get('SiglaPartidoParlamentar','?')} / {ip.get('UfParlamentar','?')}")
    if mandatos:
        m0 = mandatos[0]
        leg1 = m0.get("PrimeiraLegislaturaDoMandato", {}) or {}
        leg2 = m0.get("SegundaLegislaturaDoMandato", {}) or {}
        fim = leg2.get("DataFim") or leg1.get("DataFim") or "sem dado"
        print(f"{'Condição no mandato':<26}: {m0.get('DescricaoParticipacao','sem dado')}")
        print(f"{'Início do mandato':<26}: {leg1.get('DataInicio','sem dado')}")
        print(f"{'Fim do mandato (8 anos)':<26}: {fim}")
    else:
        print(f"{'Mandato':<26}: sem dado")
    print("-" * L)
    print(f"{'Comissões (total)':<26}: {len(comissoes)}")
    print(f"{'Comissões (hoje)':<26}: {len(comissoes_hoje)}")
    for c in comissoes_hoje[:6]:
        ident = c.get("IdentificacaoComissao", {}) or {}
        print(f"{'':28}- {ident.get('SiglaComissao','')} — {ident.get('NomeComissao','')}")
    print(f"{'Matérias de autoria':<26}: {len(autorias)}")
    print(f"{'Matérias de relatoria':<26}: {len(relatorias)}")
    print(f"{'Votações registradas':<26}: {len(votacoes)}")
    print("-" * L)
    print("AVISO medido em 07/09/2026 — leia antes de comparar com outro candidato:")
    print("  Autoria, relatoria e votações vêm de endpoints que o próprio Senado")
    print("  marca como desativados por completo desde 01/02/2026, e mesmo assim")
    print("  respondem com dado real hoje. Podem parar amanhã sem mudar de código")
    print("  de status — isso não seria bug deste script, seria o Senado por fim")
    print("  aplicando a própria desativação. Estes três números são VOLUME, não")
    print("  qualidade nem alinhamento de voto: não pontuam, não ordenam.")
    print("-" * L)
    print("Fonte e data da coleta")
    for rot, u in (("detalhe", url_det), ("mandatos", url_man), ("comissões", url_com),
                   ("autorias", url_aut), ("relatorias", url_rel), ("votações", url_vot)):
        print(f"  {rot:<12}: {u}")
    print(f"  coletado em {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print()
    print("  Este script não pontua, não ordena e não recomenda voto.")
    print()
    print("  Este registro existe porque esta pessoa exerce mandato de senador;")
    print("  quem nunca exerceu não tem este registro — ausência de fonte, não")
    print("  ausência de realização.")
    print("=" * L)
    return 0


def cmd_cobertura(uf, forcar):
    """Diz que fatia da cédula tem registro de senador. Existe pela mesma razão
    do camara.py: célula vazia num comparativo é lida como 'sem realização' —
    e sem esta conta ninguém sabe que o eixo cobre só quem está em exercício."""
    d, url, cache = pegar(f"/senador/lista/atual?uf={uf}", f"senadores_{uf}", forcar)
    lista = caminhar(d, "ListaParlamentarEmExercicio", "Parlamentares", "Parlamentar")
    n = len(lista)
    print(f"Cobertura do registro de mandato de senador em {uf}")
    print(f"fonte: {url}  [{'cache' if cache else 'rede'}]\n")
    print(f"  Senadores de {uf} em exercício hoje: {n}")
    if n == 0:
        print(f"  Zero pode ser UF errada — confira a sigla ({uf}). Todo estado tem 3")
        print("  cadeiras de senador; zero nunca é o valor real de uma UF válida.")
    print()
    print("  Em eleição geral a cédula tem 6 votos: presidente, governador,")
    print("  senador (2), deputado federal e deputado estadual.")
    print()
    print("  Registro de mandato existe para:")
    print("    senador em exercício           — sim, por esta API")
    print("    deputado federal em exercício  — outra API, da Câmara")
    print("    deputado estadual              — NÃO (27 assembleias sem padrão)")
    print("    governador e presidente        — NÃO (histórico executivo)")
    print("    candidato que nunca exerceu    — NÃO EXISTE registro para medir")
    print()
    print("  Portanto o eixo cobre uma fração pequena de quem está na cédula.")
    print("  Célula vazia aqui NÃO significa 'sem realização': significa que a")
    print("  categoria daquele candidato não tem fonte consultável no Senado.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Registro de mandato de senador (Senado Federal).")
    ap.add_argument("--buscar", metavar="NOME", help="acha senador em exercício por nome")
    ap.add_argument("--uf", default="MG", help="UF da busca (padrão MG)")
    ap.add_argument("--registro", metavar="CODIGO", help="o registro de mandato de UM senador")
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
        print(f"ERRO: o Senado respondeu HTTP {e.code} para {e.url}", file=sys.stderr)
        print("  Se for 404, o caminho provavelmente está errado.", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"ERRO de rede: {e.reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
