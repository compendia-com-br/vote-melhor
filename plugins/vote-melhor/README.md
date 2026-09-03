# Vote Melhor

**O "melhor" é sobre a sua decisão, não sobre o candidato.** A ferramenta não escolhe por
você: ela reúne o dado oficial para que você escolha com mais informação do que teria sem
ela. Não classifica, não pontua, não ordena por mérito e não recomenda voto.

Monta a ficha de candidatura de eleição brasileira a partir do dado oficial do TSE.

Uma coleção **Compendia**.

## O que ele faz

Pergunta em qual UF você vota, coleta o cadastro de candidatos daquele estado direto do TSE,
e monta a ficha de quem você quiser olhar — em **formato fixo**, com fonte e data de coleta
em cada campo.

## O que ele não faz, por decisão

- **Não classifica candidato.** A situação impressa é a string literal do TSE.
- **Não emite "ficha limpa".** A Lei Complementar 135/2010 trata de condenação por órgão
  colegiado, e isso não existe como campo consultável por máquina. Um veredito desses seria
  inferência apresentada como dado.
- **Não ordena por mérito e não pontua.** A ordem é a que você pediu, ou o número na urna.
- **Não recomenda voto.**

## Como usar

```
/vote-melhor
```

Ele pergunta a UF e conduz o resto.

## Requisitos

Python 3 e conexão. **Nada além disso** — sem `pip install`, sem `npm`, sem chave de API,
sem cadastro. Os dois scripts usam só a biblioteca padrão.

## Onde o dado fica

Na sua máquina, em `dados/`, e em lugar nenhum mais. Não há servidor, não há telemetria, e
o plugin não sabe quem você pesquisou.

A pasta `dados/` traz documento de identificação de candidato — o TSE publica título de
eleitor em toda listagem e CPF no detalhe, sob licença Creative Commons Atribuição. É dado
público, e ainda assim: **não versione essa pasta.** O `.gitignore` já cobre.

## Frescor

Situação de candidatura muda até perto da eleição: deferido vira indeferido, indeferido vai
a recurso. A base local envelhece. Toda ficha imprime **a data em que aquele campo foi
coletado**, e quando a base diverge da consulta da hora, as duas aparecem com as duas datas —
nunca sobrescritas em silêncio, porque a divergência é a informação.
