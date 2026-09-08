<img src="assets/marca/assinatura-horizontal.svg" alt="Compendia" width="300">

# Vote Melhor

Monta a ficha de candidatura de eleição brasileira a partir do dado oficial do TSE. O
"melhor" é sobre a decisão de quem vota, não sobre o candidato — a ferramenta reúne o dado
oficial, não classifica, não pontua e não recomenda voto.

Cobertura nacional: 20.005 candidaturas, das 27 UFs mais a cédula presidencial (`BR`), em
seis cargos — presidente, governador, senador, deputado federal, deputado estadual e
deputado distrital. Medido em 07/09/2026 — a base é recoletada até a eleição de
4 de outubro de 2026, e este número envelhece. A data de cada coleta fica em `FONTE.md`,
gerado junto do pacote do GPT — esse arquivo não vem neste repositório, de propósito
(veja [`gpt/COMO-PUBLICAR.md`](gpt/COMO-PUBLICAR.md)).

Uma coleção **Compendia**.

## O que tem aqui

| Pasta | O que é |
|---|---|
| `plugins/vote-melhor` | o plugin do Claude Code — instalável, com os seis scripts, as skills e o comando que conduz a consulta |
| `gpt` | o pacote do GPT personalizado — descrição de vitrine, instruções, e o passo a passo para gerar a base de conhecimento (que não vem neste repositório) |
| `docs` | especificação e plano da distribuição pública deste repositório |
| `ferramentas` | ferramentas de manutenção do próprio repositório — não fazem parte do plugin instalado |
| `testes` | linha de base e sondas de verificação |

Detalhe de uso e o que o plugin não faz, por decisão, em
[plugins/vote-melhor/README.md](plugins/vote-melhor/README.md).

## O que ele não faz, por decisão

- **Não classifica candidato, não pontua e não ordena por mérito.** A situação impressa é
  a string literal do TSE; a ordem é a que você pediu, ou o número na urna.
- **Não recomenda voto.** O "melhor" do nome é a decisão de quem vota, nunca uma nota que
  a ferramenta calcula.
- **Não emite "ficha limpa" nem "ficha suja".** A Lei Complementar 135/2010 exige
  condenação por órgão colegiado, e isso não existe como campo consultável por máquina —
  um veredito desses seria inferência apresentada como dado.
- **Não é pesquisa eleitoral nem propaganda eleitoral.** O porquê de cada uma, com a lei
  citada, está na seção Aviso legal, abaixo.

## Como instalar no Claude Code

```
/plugin marketplace add compendia-com-br/vote-melhor
/plugin install vote-melhor@compendia-civico
```

Depois de instalado, `/vote-melhor` pergunta a UF e conduz o resto.

## Sem Claude Code, direto pela linha de comando

Ferramenta gratuita de utilidade pública é para quem não usa Claude Code também. O comando
`/vote-melhor` acima só automatiza os mesmos seis scripts — dá para rodá-los sozinho, com
Python 3 puro, sem instalar nada.

A partir da raiz deste repositório clonado, quatro passos levam à primeira ficha completa:

```
# 1. Baixa o cadastro de candidatos de uma UF (aqui, MG) direto do TSE
python3 plugins/vote-melhor/ferramentas/coletar_tse.py --listar MG

# 2. Lista quem foi baixado, filtrando por cargo — cada linha traz um id
python3 plugins/vote-melhor/ferramentas/consultar.py --uf MG --cargo Governador

# 3. Baixa o detalhe de UM candidato, com o id que apareceu no passo 2
python3 plugins/vote-melhor/ferramentas/coletar_tse.py --detalhe <id> --uf MG

# 4. Monta a ficha desse candidato
python3 plugins/vote-melhor/ferramentas/consultar.py --ficha <id>
```

Os passos 3 e 4 pedem `id`, não nome, porque nome de urna se repete entre candidatos e o
`id` não. Sem o passo 2 não tem como saber o `id` de ninguém.

O passo 3 é separado do passo 1 de propósito: a listagem traz todo mundo de uma vez, mas o
detalhe é **uma requisição por pessoa** — baixar o de todos junto seriam centenas de
requisições ao TSE para ver a ficha de um. Pular o passo 3 funciona, e a ficha sai; o que
ela não traz, medido em MG, são 11 dos 22 campos — nascimento, naturalidade, sexo, cor/raça,
estado civil, instrução, ocupação, bens declarados, gasto de campanha e o motivo da
situação saem como `sem dado (detalhe não coletado)`.

Cada script tem `--help` com o resto das opções — buscar por nome, coletar o país inteiro
de uma vez, registro de mandato na Câmara e no Senado. Onde o dado fica está abaixo, em
"Onde o dado fica".

## Como montar no ChatGPT

Quem não usa Claude Code pode montar um GPT personalizado com o mesmo dado e a mesma
guarda contra recomendar voto. Passo a passo, campo por campo da tela do GPT Builder, em
[gpt/COMO-PUBLICAR.md](gpt/COMO-PUBLICAR.md).

## Onde o dado fica, e por que não é versionado

Na máquina de quem coleta, em `~/.local/share/vote-melhor` — ou onde a variável de
ambiente `VOTE_MELHOR_DADOS` apontar. Nunca dentro do plugin instalado, e nunca dentro
deste repositório.

O TSE publica título de eleitor em toda listagem de candidatos e CPF no detalhe, sob
licença Creative Commons Atribuição. É dado público, mas ainda de terceiro — por isso não
entra em commit, e o coletor descarta ou mascara os dois campos antes de gravar qualquer
coisa no banco local.

## Licença e marca

O código é **Apache License 2.0** — texto completo em [LICENSE](LICENSE). Livre para usar,
estudar, modificar e redistribuir, inclusive de forma comercial, sem pedir permissão.

A licença não cede marca (§6 do Apache-2.0): "Vote Melhor" e "Compendia" continuam marcas
da Compendia mesmo depois de um fork. Quem redistribuir uma versão modificada troca de
nome. Detalhe e o porquê em
[plugins/vote-melhor/LICENCA.md](plugins/vote-melhor/LICENCA.md).

## Aviso legal

Este software não é pesquisa eleitoral (a Lei 9.504/97, no art. 33, exige registro prévio
no TSE para isso) e não é propaganda eleitoral — ele não classifica, não pontua, não ordena
por mérito e não recomenda voto. Texto completo, com o porquê de cada guarda, em
[AVISO-LEGAL.md](AVISO-LEGAL.md).

## Fontes e atribuição

O dado vem de três fontes públicas oficiais. A atribuição ao TSE (URL e data da coleta) é
impressa em toda ficha de candidatura emitida (`consultar.py --ficha`). A atribuição à
Câmara e ao Senado aparece quando o registro de mandato federal é consultado
(`camara.py --registro` / `senado.py --registro`), cada um com a própria URL e data da
coleta:

- **Tribunal Superior Eleitoral (TSE)** — DivulgaCandContas e Portal de Dados Abertos, sob
  licença Creative Commons Atribuição (CC BY).
- **Câmara dos Deputados** — Dados Abertos.
- **Senado Federal** — Dados Abertos.

Texto completo em [NOTICE](NOTICE).

---

<img src="assets/marca/simbolo-compendia.svg" alt="" width="12"> © 2026 **Compendia** · [compendia.com.br](https://compendia.com.br)
· contato@compendia.com.br · +55 34 98430-9000
