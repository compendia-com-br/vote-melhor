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

Ele avisa e deixa passar (exit 0) por padrao. Com VOTE_MELHOR_ESTRITO=1 ele BARRA
(exit 2). O padrao e avisar porque falso positivo em hook que barra faz o usuario
desligar o hook, e hook desligado nao protege nada.
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
    r"|\bnada\s+consta\b",
    re.IGNORECASE)

REGRAS = [
    (DOC,      "documento de identificacao de terceiro"),
    (COMPARA,  "comparativo entre candidatos"),
    (NOTA,     "nota ou ranking por candidato"),
    (VEREDITO, "veredito de elegibilidade"),
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
# O PRECO, dito de propria boca: `Fulano "e ficha limpa"` passa. E hole conhecido. A guarda
# existe contra DERIVA da saida, nao contra adversario — e deriva nao poe o proprio veredito
# entre aspas. Quem quiser fechar isso precisa de analise de sujeito, nao de mais uma lista.
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

    estrito = os.environ.get("VOTE_MELHOR_ESTRITO") == "1"
    linhas = ["vote-melhor — a guarda de neutralidade encontrou:"]
    vistos = set()
    for rotulo, detalhe, trecho in achados:
        if rotulo in vistos:
            continue
        vistos.add(rotulo)
        linhas.append(f"  - {rotulo}: \"{trecho}\"")
        linhas.append(f"    {EXPLICA.get(rotulo,'')}")
    print("\n".join(linhas), file=sys.stderr)
    return 2 if estrito else 0

if __name__ == "__main__":
    sys.exit(main())
