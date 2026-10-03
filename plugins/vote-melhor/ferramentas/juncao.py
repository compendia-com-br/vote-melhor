#!/usr/bin/env python3
# juncao.py — casa o nome de urna do TSE com o nome de um parlamentar
# (ALMG, Camara, Senado). Uma regra so, para as tres casas.
#
# A juncao e por NOME, nao por documento — o banco nao guarda CPF. Nome nao e
# chave, e o erro aqui tem lado: ligar um candidato ao registro de OUTRA pessoa
# poe as proposicoes de um parlamentar debaixo do nome de outro. Nao ligar
# custa so uma consulta manual. Por isso:
#
#   * so nome IDENTICO (sem acento, sem caixa) liga registro;
#   * nome PARECIDO vira estado "parcial": aparece como possibilidade, nunca
#     puxa registro nem proposicao;
#   * parecido e por PALAVRA inteira, e so quando o nome mais curto tem duas
#     palavras ou mais — nome de uma palavra so nao casa por semelhanca.
#
# Medido em 03/10/2026 (944 candidatos a deputado estadual de MG x 77
# deputados em exercicio na ALMG): o parcial antigo ligava "SILVA" a Arnaldo
# Silva, "MARIA" a Maria Clara Marra, e "LUIZINHO ABACAXI" a Luizinho (PT), que
# tem candidatura propria. Na Camara e no Senado o parcial era por PEDACO de
# texto: "ANA" casava dentro de "MARIANA".
import unicodedata


def limpar(t):
    t = unicodedata.normalize("NFD", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def _contem(maior, menor):
    """maior contem menor como PALAVRAS inteiras."""
    return f" {menor} " in f" {maior} "


def casar(nome, itens, nome_de):
    """(estado, achados, motivo).

    estado: "achei" | "homonimos" | "parcial" | "nao_achado".
    So "achei" autoriza usar o registro. Os outros tres nunca ligam."""
    alvo = limpar(nome)
    if not alvo:
        return "nao_achado", [], "nome vazio"
    exatos = [x for x in itens if limpar(nome_de(x)) == alvo]
    if len(exatos) == 1:
        return "achei", exatos, "nome identico"
    if len(exatos) > 1:
        return "homonimos", exatos, (f"{len(exatos)} parlamentares com o mesmo nome — "
                                     "juncao incerta, nao afirmo nada")
    parecidos = []
    for x in itens:
        outro = limpar(nome_de(x))
        menor, maior = sorted((alvo, outro), key=len)
        if len(menor.split()) >= 2 and _contem(maior, menor):
            parecidos.append(x)
    if parecidos:
        return "parcial", parecidos, ("nome PARECIDO, nao identico — pode ser outra pessoa; "
                                      "o registro NAO foi usado. Confira e consulte pelo id")
    if len(alvo.split()) == 1:
        return "nao_achado", [], ("nome de uma palavra so, sem parlamentar de nome identico — "
                                  "nome curto nao se casa por semelhanca")
    return "nao_achado", [], "sem parlamentar de nome identico"
