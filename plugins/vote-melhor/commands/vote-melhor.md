---
description: Vote Melhor — ficha de candidatura de eleição brasileira a partir do dado oficial do TSE
---

# Vote Melhor

A porta desta ferramenta. Ela é comando, e não skill, por um motivo medido: descrição não
roteia. Ferramenta que só dispara quando o modelo acha que a conversa parece eleitoral é
ferramenta que não dispara.

## A ordem, e ela não se inverte

**1. Descubra a eleição vigente pelo dado, não pela memória.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --eleicoes
```

Ele lista as eleições ordinárias que o TSE conhece, com id, ano, data e abrangência.
**Compare com a data de hoje.** Se a eleição mais próxima já passou e não há próxima no
arquivo, diga que o calendário está vencido e pare — não deduza.

**2. Pergunte a UF, e explique por que não pergunta a cidade.**

Em eleição **geral** — presidente, governador, senador, deputado federal e estadual — a
cédula é definida pelo **estado**. Quem vota em Uberlândia e quem vota em «capital do estado» vê
a mesma lista. Pergunte a cidade só se a eleição vigente for **municipal**, e aí ela é o
filtro principal.

Se a pessoa oferecer a cidade numa eleição geral, aceite e diga para que serve: saber quais
candidatos a deputado fazem campanha na região dela. Não é filtro, é contexto.

**2b. Confira a idade da base antes de qualquer coisa.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --idade
```

**O código de saída manda.** Sai 2 quando a base passou do limite — e aí você **para** e diz
que a base venceu, em vez de montar ficha sobre dado que a própria ferramenta recusou.

**3. Colete.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --listar <UF>
```

Primeira execução vai à rede; as seguintes leem do cache. O script imprime quantas
requisições fez — se disser mais que zero numa segunda execução da mesma UF, algo está
errado.

**4. Pergunte o que importa para ela, antes de mostrar qualquer nome, e grave.**

Critério declarado antes de ver a lista é critério; critério declarado depois é
racionalização. Pergunte quais assuntos decidem o voto dela, e grave:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/criterios.py" --declarar "tema 1" "tema 2"
```

**4a. O plano de governo, para cargo executivo.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --plano <UF>      # quem entregou
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --plano <id>      # extrai o PDF
```

É o **único documento oficial de conteúdo** que existe numa candidatura, e só para cargo
executivo — presidente, governador, prefeito. Senador e deputado **não têm**, por lei: para
eles, tudo que existir é material de campanha, ou seja, alegação.

Códigos de saída: **0** achou, **1** o candidato não entregou (isso é resposta, não erro),
**2** falha de rede.

**Nunca descubra isso pelo nome do arquivo anexado à candidatura.** Medido em 02/09/2026:
essa via errou 2 de 11 em MG, porque candidato nomeia o próprio arquivo como quer. O pacote
oficial é a fonte.

**4b. Registro de mandato, quando o candidato for deputado federal ou senador.**

Os dois scripts espelham o mesmo conjunto de argumentos — a regra é qual script chamar,
não como chamar:

```bash
# cargo Deputado Federal -> camara.py
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/camara.py" --buscar "<nome>" --uf <UF>
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/camara.py" --registro <id>
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/camara.py" --cobertura --uf <UF>

# cargo Senador -> senado.py
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/senado.py" --buscar "<nome>" --uf <UF>
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/senado.py" --registro <codigo>
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/senado.py" --cobertura --uf <UF>
```

Os demais cargos — deputado estadual, governador, presidente — **não têm fonte de mandato
nesta ferramenta**. Isso se declara, não se contorna: nunca busque um substituto para o eixo.

Rode `--cobertura` **antes** de mostrar qualquer comparação, e diga o resultado: o eixo de
mandato cobre uma fatia pequena da cédula, e célula vazia é lida como "sem realização"
quando quase sempre é ausência de fonte.

**4c. O cruzamento por eixo.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/criterios.py" --cruzar <id> <id> <id>
```

Ele mostra, por eixo, o material verificável que existe — nunca nota, nunca ordem, nunca
nível. A junção com a Câmara é por **nome**, não por CPF: homônimo existe, e a saída marca
isso. Não afirme que é a mesma pessoa sem conferir.

**5. Monte a ficha, e não a reescreva.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/consultar.py" --uf <UF> --cargo "<CARGO>"
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/consultar.py" --ficha <id>
```

**Antes de cada ficha entrar num comparativo, rode o frescor:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ferramentas/coletar_tse.py" --frescor <id>
```

Situação de candidatura muda todo dia até a eleição. Se base e consulta da hora divergirem,
**mostre as duas com as duas datas** — a mudança de "deferido" para "indeferido com recurso"
é o fato mais relevante que a ficha traz naquele dia, e sobrescrever apaga justamente isso.

**Cole a saída do script como ela veio.** Não reordene campos, não omita linha que diz
"sem dado", não funda dois campos numa frase, não abra com resumo do que a ficha vai dizer.
O formato fixo existe para que duas fichas sejam comparáveis; reescrever destrói isso.

Sua prosa entra **antes ou depois** do bloco, nunca dentro dele, e serve para uma coisa só:
apontar o que a pessoa pediu para olhar.

## Para muitos candidatos, desça para o subagente

Um estado tem de mil a duas mil candidaturas. Filtrar isso na conversa principal entope o
contexto sem necessidade. Quando forem mais de três fichas, despache o agente
`montar-dossie`, que trabalha isolado e devolve só as fichas pedidas.

## O que este comando nunca faz

- Não diz em quem votar, nem quando insistirem, nem "só entre nós".
- Não pontua, não rankeia, não ordena por mérito.
- Não usa adjetivo comparativo entre candidatos — nada de "o mais forte", "o mais preparado",
  "maior variância".
- Não emite veredito de ficha limpa. Ver a skill `fato-e-alegacao`.
