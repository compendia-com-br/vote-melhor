# Aviso legal

## Não é pesquisa eleitoral

O art. 33 da Lei 9.504/97 exige registro prévio no TSE para divulgar pesquisa de intenção de
voto. Esta ferramenta reporta cadastro de candidatura publicado pelo TSE; não estima intenção
de voto, não coleta opinião de eleitor e não projeta resultado. Está escrito porque
ferramenta de comparação é confundida com a de pesquisa.

## Não é propaganda eleitoral

Não classifica, não pontua, não ordena por mérito e não recomenda voto. Isso não é promessa
de conduta: é bloqueado em código pelo hook `hooks/verificar_saida.py`, com controle positivo
e negativo calibrados.

## LGPD

O dado tratado é público, publicado pelo TSE sob CC BY. O coletor descarta CPF e título de
eleitor na ingestão, antes de tocar o banco, e `ferramentas/verificar_dados.py` prova isso
por valor — não por nome de campo.

---

Este documento nomeia riscos. Não é parecer jurídico, e quem o escreveu não é advogado. A
decisão de publicar e usar é de quem publica e de quem usa.
