# Aviso legal

## Não é pesquisa eleitoral

O art. 33 da Lei 9.504/97 exige registro prévio no TSE para divulgar pesquisa de intenção de
voto. Esta ferramenta reporta cadastro de candidatura publicado pelo TSE; não estima intenção
de voto, não coleta opinião de eleitor e não projeta resultado. Está escrito porque
ferramenta de comparação é confundida com a de pesquisa.

## Não é propaganda eleitoral

Não classifica, não pontua, não ordena por mérito e não recomenda voto. Isso não é promessa
de conduta: o hook `plugins/vote-melhor/hooks/verificar_saida.py` fiscaliza a saída, com controle positivo e
negativo calibrados. Por padrão ele **detecta e avisa** — imprime o achado e deixa passar.
Defina `VOTE_MELHOR_ESTRITO=1` para que ele **barre** a saída em vez de só avisar. O padrão
é avisar porque falso positivo em hook que barra leva a desligar o hook, e hook desligado
não protege nada.

## LGPD

O dado tratado é público, publicado pelo TSE sob CC BY. O coletor descarta CPF e título de
eleitor na ingestão, antes de tocar o banco, e a verificação em `plugins/vote-melhor/ferramentas/verificar_dados.py`
valida isso por inspeção do valor — não por nome de campo.

---

Este documento nomeia riscos. Não é parecer jurídico, e quem o escreveu não é advogado. A
decisão de publicar e usar é de quem publica e de quem usa.
