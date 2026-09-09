# Aviso legal

## Não é pesquisa eleitoral

O art. 33 da Lei 9.504/97 exige registro prévio no TSE para divulgar pesquisa de intenção de
voto. Esta ferramenta reporta cadastro de candidatura publicado pelo TSE; não estima intenção
de voto, não coleta opinião de eleitor e não projeta resultado. Está escrito porque
ferramenta de comparação é confundida com a de pesquisa.

## Não é propaganda eleitoral

Não classifica, não pontua, não ordena por mérito e não recomenda voto. Isso não é promessa
de conduta: o hook `plugins/vote-melhor/hooks/verificar_saida.py` fiscaliza o que é **gravado
em arquivo** (dispara em `Write` e `Edit`), com controle positivo e negativo calibrados. Ele
**não** lê a ficha que aparece na conversa nem a saída impressa de um comando no terminal —
só o texto que vira arquivo, como um dossiê salvo em disco. Por padrão ele **barra a
gravação** e diz o que encontrou, citando o trecho e o que escrever no lugar. Quem precisar
apenas do aviso define `VOTE_MELHOR_AVISAR=1`, e a própria mensagem ensina isso a quem for
barrado — hook que não deixa trabalhar é hook que o usuário desinstala.

## LGPD

O dado tratado é público, publicado pelo TSE sob CC BY. Na ingestão, antes de tocar o banco, o
coletor age em duas camadas: descarta CPF e título de eleitor quando o nome do campo já diz o
que ele é, e mascara o documento quando ele aparece dentro do valor de outro campo — como um
CPF embutido no nome de um arquivo anexado. A verificação em
`plugins/vote-melhor/ferramentas/verificar_dados.py` confere as duas camadas por inspeção do
valor — não por nome de campo.

---

Este documento nomeia riscos. Não é parecer jurídico, e quem o escreveu não é advogado. A
decisão de publicar e usar é de quem publica e de quem usa.
