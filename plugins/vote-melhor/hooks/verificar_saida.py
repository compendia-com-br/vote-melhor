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
    # "e o mais forte", "sao os mais preparados" — qualquer superlativo com artigo
    r"|\b(?:e|eh|sao|fica|ficou|parece)\s+(?:o|a|os|as)\s+(?:mais|menos)\s+\w+"
    # substantivo + "mais X" perto de candidato/curriculo/proposta
    r"|\b(?:curriculo|proposta|historico|ficha|trajetoria)\b[^.]{0,40}\b(?:mais|menos)\s+\w+"
    r"|\b(?:melhor|pior)\s+(?:candidat|opcao|escolha|nome)"
    r"|\bmais\s+(?:preparad|qualificad|confiavel|honest|competent|experient)"
    r"|\b(?:maior|menor)\s+(?:variancia|risco|chance|aposta)\s+d(?:os|as|e)\s+(?:tres|quatro|candidatos)",
    re.IGNORECASE)

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


def achar(texto):
    texto = sem_acento(texto or "")
    saida = []
    for regras, rotulo in REGRAS:
        pares = regras if isinstance(regras, list) else [(regras, rotulo)]
        for rx, detalhe in pares:
            for m in rx.finditer(texto or ""):
                saida.append((rotulo, detalhe, m.group(0)[:70]))
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
