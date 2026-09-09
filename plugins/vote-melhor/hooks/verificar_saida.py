#!/usr/bin/env python3
"""Guarda de neutralidade do vote-melhor.

Por que hook e nao skill: skill so vale quando carregada, e a regra que precisa
recusar tem de valer mesmo quando ninguem carregou nada. Regra que depende de ser
carregada para valer nao e regra.

O que ele barra, na SAIDA, nunca na entrada:
  1. documento de identificacao de terceiro escapando para arquivo de dossie
  2. superlativo e comparativo entre candidatos
  3. nota, score ou percentual de adequacao por candidato
  4. veredito de elegibilidade que a lei nao autoriza derivar

Ele BARRA por padrao (exit 2). VOTE_MELHOR_AVISAR=1 devolve o comportamento antigo:
imprime o achado e deixa passar (exit 0).

O padrao era avisar, e o motivo escrito era que falso positivo em hook que barra faz o
usuario desligar o hook. Medido em 09/09/2026, esse motivo caiu:

  - a guarda nao dispara em saida legitima: tres fichas e um panorama de 24 KB, zero achados;
  - o que ela acusava eram documentos do proprio projeto CITANDO a construcao proibida, e
    isso foi separado de afirmar em 3e313a9;
  - a ferramenta virou publica, e quem instala nao descobre sozinho uma variavel de ambiente.
    Protecao que depende de configurar nao protege o recem-chegado, que e quem mais precisa.

O escape continua existindo de proposito, e a propria mensagem o ensina: hook que nao deixa
trabalhar e hook que o usuario desinstala, e ai nao protege ninguem.
"""
import json, os, re, sys, unicodedata

# --- 1. documento de terceiro em arquivo gerado -------------------------------
DOC = [
    (re.compile(r'"cpf"\s*:\s*"\d{11}"'), "CPF em JSON"),
    (re.compile(r'"tituloEleitor"\s*:\s*"\d{12}"'), "titulo de eleitor em JSON"),
    (re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b'), "CPF formatado"),
]

# --- 2. comparativo e superlativo ---------------------------------------------
# so pega quando ha COMPARACAO entre candidatos; "mais de 500 mil" nao entra.
COMPARA = re.compile(
    # "o mais X dos tres", "a menos Y dos candidatos"
    r"\b(?:o|a)\s+(?:mais|menos)\s+\w+\s+d(?:os|as|e)\s+(?:tres|quatro|cinco|todos|candidatos)"
    # atributo de candidato + comparativo: "curriculo mais forte dos tres" e o achado
    # real da linha de base. "ficha" NAO entra: neste projeto ela e o nome da saida,
    # e "uma ficha que omite o que o eleitor mais quer" nao compara ninguem.
    r"|\b(?:curriculo|proposta|historico|trajetoria)\s+(?:\w+\s+){0,2}(?:mais|menos)\s+\w+"
    # rotulo: "**Mais solido**: **Fulano**". Sem verbo, o comparativo antigo nao via —
    # e essa e a forma mais direta de ranquear que a linha de base produziu. Exige nome
    # proprio depois dos dois pontos, senao "E o mais importante: diga isso" cairia junto.
    r"|(?:^|\n)\s*\**\s*(?:mais|menos)\s+\w+\s*\**\s*:\s*\**\s*[A-Z]"
    r"|\b(?:melhor|pior)\s+(?:candidat|opcao|escolha|nome)"
    r"|\bmais\s+(?:preparad|qualificad|confiavel|honest|competent|experient)"
    r"|\b(?:maior|menor)\s+(?:variancia|risco|chance|aposta)\s+d(?:os|as|e)\s+(?:tres|quatro|candidatos)",
    re.IGNORECASE)

# Superlativo solto — "e o mais X", "a ficha ... mais Y". Sozinho ele nao acusa nada:
# "o erro mais comum e o mais caro" e "E o mais importante:" sao prosa, e a guarda barrava
# a propria skill fato-e-alegacao por causa deles. Medido em 09/09/2026: 3 falsos positivos
# em 1 arquivo. Por isso ele so vale quando ha candidato por perto (CONTEXTO abaixo).
COMPARA_FRACO = re.compile(
    r"\b(?:e|eh|sao|fica|ficou|parece)\s+(?:o|a|os|as)\s+(?:mais|menos)\s+\w+",
    re.IGNORECASE)

# O que faz um superlativo virar comparacao ELEITORAL. Sem nenhum destes na mesma vizinhanca,
# "o mais caro" fala de outra coisa.
CONTEXTO = re.compile(
    r"\b(candidat|governador|senador|deputad|presidente|prefeit|vereador|chapa|urna|"
    r"partido|coligacao|chapa)", re.IGNORECASE)  # nao entra "eleitor": e prosa deste projeto

# --- 3. nota, score, ranking ---------------------------------------------------
NOTA = re.compile(
    r"\b(?:nota|score|pontuacao|indice)\s*(?:de|:)?\s*\d+(?:[.,]\d+)?\s*(?:/|de)\s*\d+"
    r"|\b\d+\s*de\s*\d+\s+eixos\b"
    r"|\b\d{1,3}\s*%\s+de\s+(?:aderencia|alinhamento|compatibilidade|afinidade|match)"
    r"|\baderencia\s+de\s+\d{1,3}\s*%",
    re.IGNORECASE)

# --- 4. veredito de elegibilidade ---------------------------------------------
VEREDITO = re.compile(
    r"\b(?:e|eh|esta|nao e|nao esta)\s+ficha\s+(?:limpa|suja)\b"
    r"|\bficha\s+(?:limpa|suja)\s*[:\-]\s*(?:sim|nao)\b"
    r"|\b(?:e|esta)\s+(?:inelegivel|elegivel)\b"
    r"|\bnada\s+consta\b"
    # a linha de base disse "nao esta apto a ser eleito" e a guarda nao viu: ela so
    # conhecia "inelegivel". A lei nao muda porque a frase mudou de palavra.
    r"|\b(?:nao\s+)?(?:esta|e|eh)\s+apto\s+a\s+ser\s+eleit"
    # so a forma NEGATIVA: "se pode ser eleito" e a PERGUNTA que o eleitor faz, e a
    # skill fato-e-alegacao a cita ao dizer quando ser usada. Afirmar que alguem NAO
    # pode ser eleito e que a lei nao autoriza.
    r"|\bnao\s+pode\s+ser\s+eleit",
    re.IGNORECASE)

# --- 5. prognostico eleitoral -------------------------------------------------
# A afirmacao mais perigosa das que a linha de base produziu, e a guarda nao via nenhuma
# delas: "seu voto nao sera computado", "a votacao sera anulada", "candidatura perdida".
# Alem de falsa no caso medido, e o terreno que o art. 33 da Lei 9.504/97 regula — dizer
# quem tem chance e o que a lei chama de pesquisa, e pesquisa exige registro previo no TSE.
PROGNOSTICO = re.compile(
    r"\bvot(?:o|acao)\s+(?:\w+\s+){0,3}(?:sera|vai\s+ser|seria)\s+(?:anulad|perdid|desperdicad)"
    r"|\bvoto\s+(?:nao\s+)?(?:sera|vai\s+ser)\s+(?:computad|contad|valid)"
    r"|\bcandidatura\s+perdida\b"
    r"|\bvoto\s+(?:perdido|jogado\s+fora|desperdicado|inutil)\b"
    r"|\bnao\s+adianta\s+votar\b"
    r"|\bchances?\s+reais\b"
    r"|\bsem\s+chance\s+de\s+(?:ganhar|vencer|se\s+eleger)"
    r"|\bvai\s+(?:ganhar|vencer|perder)\s+a\s+eleicao\b",
    re.IGNORECASE)

# --- 6. juizo de capacidade ---------------------------------------------------
# "partido nanista", "capacidade de execucao questionavel". Nada no cadastro do TSE sustenta
# isso: e opiniao com roupa de informacao, dita sobre pessoa que esta concorrendo.
CAPACIDADE = re.compile(
    r"\bpartido\s+nanista\b|\bnanic[oa]\b"
    r"|\bcapacidade\s+de\s+(?:execucao|entrega|realizacao|gestao)\s+"
    r"(?:questionavel|duvidosa|baixa|limitada|fraca)"
    r"|\bsem\s+estrutura\s+para\s+(?:governar|administrar|gerir)"
    r"|\bnao\s+(?:tem|teria)\s+como\s+(?:governar|entregar|cumprir)",
    re.IGNORECASE)

# --- 7. fonte oficial inventada ------------------------------------------------
# Medido em 09/09/2026: o GPT mandou o eleitor conferir em `www2.camara.leg.br` grafado com
# acento — dominio que nem resolve. A instrucao ja proibia montar URL por palpite, e ele
# montou: proibicao sem alternativa nao segura falha de forma. Endereco errado com cara de
# oficial e pior que endereco nenhum, porque quem confia clica.
#
# O discriminador e estrutural, nao uma lista de erros possiveis: dominio terminado em
# .leg.br, .jus.br ou .gov.br carrega autoridade de Estado. Se nao for um dos verificados
# por ferramentas/verificar_fontes.py, foi inventado. Host com caractere fora de ASCII cai
# junto — foi exatamente a forma do erro medido.
OFICIAIS = {
    # paginas que uma pessoa abre, conferidas por verificar_fontes.py
    "divulgacandcontas.tse.jus.br", "www.camara.leg.br",
    "www25.senado.leg.br", "www.tse.jus.br",
    # endpoints que as ferramentas deste projeto usam
    "dadosabertos.camara.leg.br", "legis.senado.leg.br",
    "dadosabertos.tse.jus.br", "cdn.tse.jus.br",
}
AUTORIDADE = (".leg.br", ".jus.br", ".gov.br")
URL = re.compile(r"https?://([^\s/)\"'<>\]]+)")

REGRAS = [
    (DOC,      "documento de identificacao de terceiro"),
    (COMPARA,  "comparativo entre candidatos"),
    (NOTA,     "nota ou ranking por candidato"),
    (VEREDITO, "veredito de elegibilidade"),
    (PROGNOSTICO, "prognostico eleitoral"),
    (CAPACIDADE, "juizo de capacidade"),
]

EXPLICA = {
    "documento de identificacao de terceiro":
        "o dado e publico, mas nao ha finalidade para ele num dossie. Tire da saida.",
    "comparativo entre candidatos":
        "adjetivo comparativo empurra o voto sem nomear ninguem. Diga o fato, nao o nivel.",
    "nota ou ranking por candidato":
        "se a ferramenta produz um numero por candidato, ela recomenda.",
    "veredito de elegibilidade":
        "a LC 135/2010 exige condenacao por orgao colegiado, e isso nao e campo consultavel. "
        "Imprima a string literal do TSE.",
    "prognostico eleitoral":
        "dizer quem tem chance, ou que o voto se perde, e o que a Lei 9.504/97 chama de "
        "pesquisa — e pesquisa exige registro previo no TSE. Diga a situacao, nao o desfecho.",
    "juizo de capacidade":
        "o cadastro do TSE nao traz nada que sustente isso. E opiniao sobre pessoa que esta "
        "concorrendo. Diga o que ela declarou e o que ja exerceu, com a fonte.",
    "fonte oficial inventada":
        "endereco com cara de orgao publico que nao esta na lista verificada. Rode "
        "ferramentas/verificar_fontes.py e cite so o que esta em FONTES.md — endereco "
        "errado com autoridade de Estado e pior que endereco nenhum.",
}

def sem_acento(t):
    """Tira acento antes de casar. Sem isso, "e ficha limpa" nao pega
    "e' ficha limpa", e a guarda fica silenciosa achando que esta funcionando.
    Medido em 02/09/2026: 3 de 7 controles positivos escapavam por causa disso."""
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


# CITAR nao e AFIRMAR. Um documento que ensina a regra precisa escrever a construcao que
# proibe, e a guarda casava os dois do mesmo jeito — a ponto de BARRAR a edicao dela mesma,
# das instrucoes do GPT, da skill fato-e-alegacao e do registro RED. Medido em 09/09/2026.
#
# O discriminador e a MARCACAO, nao o verbo que introduz. Tentei uma lista de marcas de
# atribuicao ("segundo", "afirma", "nunca escreva") e ela furou em tres casos reais do
# proprio projeto: "Nunca de ... superlativo (", "Assim nao:", "- Escrever". Lista de
# palavras da confianca falsa; a marcacao e estrutural.
#
# O buraco que isso abria — atribuir um veredito a alguem e esconder atras de aspas — esta
# fechado para a classe mais grave, o veredito de elegibilidade: ver SUJEITO abaixo.
def mascarar_mencao(texto):
    """Apaga as regioes onde a construcao proibida esta CITADA, nao afirmada.

    Troca por espaco do mesmo tamanho, para nao deslocar posicao nenhuma.
    """
    def branco(m):
        return " " * len(m.group(0))

    # aspas TRIPLAS primeiro: uma docstring tem numero impar de aspas e desalinha o
    # pareamento de todas as aspas simples depois dela. Medido: sem isto, a guarda
    # ainda acusava 6 construcoes no proprio codigo-fonte dela.
    texto = re.sub(r'""".*?"""', branco, texto, flags=re.S)
    texto = re.sub(r"'''.*?'''", branco, texto, flags=re.S)
    texto = re.sub(r"```.*?```", branco, texto, flags=re.S)   # bloco de codigo
    texto = re.sub(r"`[^`\n]+`", branco, texto)               # codigo de linha
    texto = re.sub(r"«[^»]{0,300}»", branco, texto, flags=re.S)
    texto = re.sub(r"[“][^”]{0,300}[”]", branco, texto, flags=re.S)
    texto = re.sub(r'"[^"]{0,300}"', branco, texto, flags=re.S)
    # bloco de citacao do markdown: "> ..." e a pergunta de quem lê, reproduzida.
    # Sem isto a guarda acusava a PERGUNTA DO ELEITOR como se fosse saida da ferramenta.
    texto = re.sub(r"^[ \t]*>.*$", branco, texto, flags=re.M)
    return texto


# Aspas escondem a mencao — e escondiam tambem a EVASAO: `Fulano "e ficha limpa"`. O que
# separa os dois nao e o verbo, e o SUJEITO: citacao vem depois de dois pontos, parentese,
# marcador de lista ou verbo minusculo ("nunca escreva", "- Escrever"); atribuicao a uma
# pessoa vem depois de um nome proprio. Medido em 09/09/2026 sobre os 41 arquivos
# versionados: pega as duas formas de evasao, nao pega nenhuma das cinco formas legitimas
# de citacao, e nao acusa nenhum documento do projeto.
#
# Vale SO para o veredito de elegibilidade, que e a classe mais grave — a que a LC 135/2010
# nao autoriza derivar. Para as outras, aspas continuam sendo citacao.
SUJEITO = re.compile(r'(?:^|[^\w])[A-Z][a-z]{2,}\s+"')


def achar(texto):
    cru = sem_acento(texto or "")
    # DOCUMENTO nao aceita a defesa de `eu estava citando`: citar `e ficha limpa` e
    # legitimo, imprimir um CPF nao e — entre aspas ou fora delas. Por isso a regra 1 corre
    # no texto CRU. Medido: sem esta separacao, o mascaramento comia {"cpf":"..."} inteiro
    # e cegava o detector de documento, que e a regra mais consequente das quatro.
    texto = mascarar_mencao(cru)
    saida = []
    for regras, rotulo in REGRAS:
        fonte = cru if rotulo == "documento de identificacao de terceiro" else texto
        pares = regras if isinstance(regras, list) else [(regras, rotulo)]
        for rx, detalhe in pares:
            for m in rx.finditer(fonte):
                saida.append((rotulo, detalhe, m.group(0)[:70]))
    # veredito de elegibilidade escondido atras de aspas, atribuido a um nome proprio
    for m in re.finditer(r'"[^"]{0,300}"', cru, re.S):
        ini = max(0, m.start() - 40)
        if SUJEITO.search(cru[ini:m.start() + 1]) and VEREDITO.search(m.group(0)):
            saida.append(("veredito de elegibilidade", "veredito de elegibilidade",
                          m.group(0)[:70]))
    # fonte oficial inventada: dominio de autoridade que nao esta na lista verificada
    for m in URL.finditer(texto):
        host = m.group(1).lower().rstrip(".")
        if host in OFICIAIS:
            continue
        if any(ord(c) > 127 for c in host) or host.endswith(AUTORIDADE):
            saida.append(("fonte oficial inventada", "fonte oficial inventada",
                          m.group(0)[:70]))
    # superlativo solto: so acusa se houver candidato na mesma vizinhanca
    for m in COMPARA_FRACO.finditer(texto):
        ini = max(0, m.start() - 200)
        fim = min(len(texto), m.end() + 200)
        if CONTEXTO.search(texto[ini:fim]):
            saida.append(("comparativo entre candidatos",
                          "comparativo entre candidatos", m.group(0)[:70]))
    return saida

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    alvo = ""
    ti = ev.get("tool_input") or {}
    for k in ("content", "new_string", "command"):
        if isinstance(ti.get(k), str):
            alvo += ti[k] + "\n"
    tr = ev.get("tool_response") or {}
    if isinstance(tr, dict):
        for k in ("stdout", "output"):
            if isinstance(tr.get(k), str):
                alvo += tr[k] + "\n"
    if not alvo.strip():
        return 0

    achados = achar(alvo)
    if not achados:
        return 0

    # Barra por padrao. VOTE_MELHOR_ESTRITO=1 continua valendo para quem ja o usava.
    avisar = os.environ.get("VOTE_MELHOR_AVISAR") == "1"
    estrito = not avisar
    linhas = ["vote-melhor — a guarda de neutralidade encontrou:"]
    vistos = set()
    for rotulo, detalhe, trecho in achados:
        if rotulo in vistos:
            continue
        vistos.add(rotulo)
        linhas.append(f"  - {rotulo}: \"{trecho}\"")
        linhas.append(f"    {EXPLICA.get(rotulo,'')}")
    if estrito:
        linhas.append("  Isto barrou a escrita. Corrija o texto — ou, se for engano,")
        linhas.append("  rode de novo com VOTE_MELHOR_AVISAR=1 para so avisar.")
    print("\n".join(linhas), file=sys.stderr)
    return 2 if estrito else 0

if __name__ == "__main__":
    sys.exit(main())
