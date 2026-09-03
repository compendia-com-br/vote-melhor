---
name: consulta-tse
description: Use quando precisar do dado de candidatura — listar candidatos de uma UF, achar candidato por nome, montar ficha, conferir a situação do registro na hora, ou descobrir qual eleição está vigente. Use também quando o dado local parecer velho, quando a coleta falhar, ou quando alguém perguntar de onde veio um número da ficha.
---

# Consulta ao TSE

Todo dado desta ferramenta passa por dois scripts, e **nunca** por leitura direta do SQLite
nem por chamada de rede improvisada.

```bash
F="${CLAUDE_PLUGIN_ROOT}/ferramentas"
python3 "$F/coletar_tse.py" --help
python3 "$F/consultar.py"   --help
```

## Os quatro movimentos

**1. Qual eleição está valendo** — sempre primeiro, e sempre pelo dado:

```bash
python3 "$F/coletar_tse.py" --eleicoes
```

Devolve as eleições ordinárias com id, ano, data e abrangência. **Nunca deduza o id pelo
ano**: a de 2016 tem id `2`, a de 2014 tem `680`, a de 2026 tem `20322002026`.

**2. Coletar a UF** — primeira vez vai à rede, depois lê do cache:

```bash
python3 "$F/coletar_tse.py" --listar MG
```

O script imprime quantas requisições fez. Segunda execução da mesma UF deve dizer **zero**.

**3. Encontrar e listar**:

```bash
python3 "$F/consultar.py" --uf MG --cargo "DEPUTADO FEDERAL"
python3 "$F/consultar.py" --nome kalil
```

A busca por nome ignora acento e caixa.

**4. A ficha**:

```bash
python3 "$F/coletar_tse.py" --detalhe <id>
python3 "$F/consultar.py" --ficha <id>
```

O detalhe é uma requisição por candidato e traz os campos que a listagem deixa nulos. Só
busque detalhe de quem vai entrar no dossiê.

## A saída é literal

**Cole a ficha como ela sai.** Ela tem formato fixo justamente para que duas fichas sejam
comparáveis lado a lado. Reordenar campo, omitir linha de "sem dado", fundir dois campos
numa frase ou abrir com um resumo destrói a comparabilidade — que é o produto.

## Respeite o servidor

O TSE é serviço público mantido com dinheiro público, e já bloqueia robô. O script pausa
entre requisições de propósito. **Nada de varredura, nada de laço buscando detalhe de mil
candidatos.** Detalhe se busca para quem entrou no dossiê, e ponto.

Se aparecer erro de bloqueio, a mensagem já explica: é o Akamai, a lista de cabeçalhos não
pode ser enxugada, e a ordem dela importa. Não tente contornar aumentando frequência.

## Frescor, e por que a divergência é a informação

Situação de candidatura muda até perto da eleição. A base local envelhece.

Quando a base e a consulta da hora divergirem, **imprima as duas com as duas datas**. Não
sobrescreva em silêncio: a mudança de "deferido" para "indeferido com recurso" é o fato mais
relevante que a ficha pode trazer naquele dia.

## Quando o dado não existe

Campo nulo sai como "sem dado", e é isso que se diz. Não preencha por dedução, não complete
com o que "provavelmente é", e não trate ausência como negativa.
