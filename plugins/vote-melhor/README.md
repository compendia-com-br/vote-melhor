<img src="../../assets/marca/assinatura-horizontal.svg" alt="Compendia" width="300">

# Vote Melhor

**O "melhor" é sobre a sua decisão, não sobre o candidato.** A ferramenta não escolhe por
você: ela reúne o dado oficial para que você escolha com mais informação do que teria sem
ela. Não classifica, não pontua, não ordena por mérito e não recomenda voto.

Monta a ficha de candidatura de eleição brasileira a partir do dado oficial do TSE, com
cobertura nacional: as 27 UFs mais a cédula presidencial (`BR`), em seis cargos.

Uma coleção **Compendia**.

## O que ele faz

Pergunta em qual UF você vota, coleta o cadastro de candidatos daquele estado direto do TSE,
e monta a ficha de quem você quiser olhar — em **formato fixo**, com fonte e data de coleta
em cada campo. Também traz o registro de mandato de quem já foi deputado federal ou
senador, direto da Câmara dos Deputados e do Senado Federal.

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
sem cadastro. Os seis scripts usam só a biblioteca padrão.

## Os seis scripts

| Script | Faz |
|---|---|
| `coletar_tse.py` | baixa o cadastro de candidatura direto do TSE — por UF, ou `--pais` para coletar as 27 UFs e a cédula presidencial de uma vez |
| `consultar.py` | lê o cache local e monta a ficha de um candidato |
| `criterios.py` | cruza o material verificável de um candidato com os eixos que você declarou importar — sem pontuar nem dar nível |
| `camara.py` | registro de mandato federal, direto da Câmara dos Deputados |
| `senado.py` | registro de mandato de senador, direto do Senado Federal |
| `verificar_dados.py` | prova, por valor e não por nome de campo, que o banco local não guarda CPF nem título de eleitor |

## Onde o dado fica

Na sua máquina, em `~/.local/share/vote-melhor` — ou onde a variável de ambiente
`VOTE_MELHOR_DADOS` apontar — e em lugar nenhum mais. Não há servidor, não há telemetria, e
o plugin não sabe quem você pesquisou.

Esse diretório traz documento de identificação de candidato — o TSE publica título de
eleitor em toda listagem e CPF no detalhe, sob licença Creative Commons Atribuição. É dado
público, e ainda assim o coletor descarta ou mascara os dois campos antes de gravar
qualquer coisa no banco. Esse diretório **nunca fica dentro deste repositório nem dentro
do plugin instalado** — por isso não precisa de `.gitignore` nenhum: ele mora fora daqui.

## Frescor

Situação de candidatura muda até perto da eleição: deferido vira indeferido, indeferido vai
a recurso. A base local envelhece. Toda ficha imprime **a data em que aquele campo foi
coletado**, e quando a base diverge da consulta da hora, as duas aparecem com as duas datas —
nunca sobrescritas em silêncio, porque a divergência é a informação.

## Licença

Apache License 2.0 — texto completo em [`../../LICENSE`](../../LICENSE). Livre para usar,
estudar, modificar e redistribuir, inclusive de forma comercial, sem pedir permissão.

A licença não cede marca: "Vote Melhor" e "Compendia" continuam marcas da Compendia mesmo
depois de um fork. Quem redistribuir uma versão modificada troca de nome. Detalhe e o
porquê em [LICENCA.md](LICENCA.md).

---

<img src="../../assets/marca/simbolo-compendia.svg" alt="" width="12"> © 2026 **Compendia** · [compendia.com.br](https://compendia.com.br)
· contato@compendia.com.br · +55 34 93618-0015
