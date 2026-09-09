# Vote Melhor — distribuição gratuita de utilidade pública

**Data:** 07/09/2026 · **Autor:** Compendia · **Estado:** aprovado, aguardando plano

Levar o `vote-melhor` de plugin privado a ferramenta pública gratuita, em duas
plataformas: plugin do Claude Code e GPT personalizado no ChatGPT.

---

## 1. Decisões tomadas

| Decisão | Escolha | Quem decidiu |
|---|---|---|
| Licença | **Apache-2.0** | Thiago, 07/09/2026 |
| Forma do GPT | **método + base nacional** (opções 2 e 4) | Thiago, 07/09/2026 |
| Mesma forma no Claude | sim | Thiago, 07/09/2026 |
| Dado embarcado no plugin do Claude | **não** — o plugin leva o código, o dado nasce na máquina de quem usa | mantido do desenho anterior |
| Dado embarcado no GPT | **sim** — o ChatGPT não tem shell; a base vai como arquivo de conhecimento datado | consequência da medição §2 |
| Repositório público | **só com confirmação explícita na hora** | passo irreversível |

## 2. As três medições que amarram o desenho

Medidas em 07/09/2026, nesta máquina.

**a) Toda superfície do TSE recusa cliente HTTP comum.**

| Superfície | `curl` puro | coletor local (`http.client`, ordem de cabeçalho do Chrome) |
|---|---|---|
| `divulgacandcontas.tse.jus.br/divulga/rest/v1/eleicao/eleicao-atual` | 403 | 200 |
| `cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/…` | 403 | 200 |
| `dadosabertos.tse.jus.br/api/3/action/package_show` | 403 | 200 |

**Consequência:** uma Action de GPT personalizado é um cliente HTTP comum e levaria
403 nos três. O GPT **não terá Actions**. A base vai como arquivo de conhecimento.

**b) O Senado responde a cliente comum.** `legis.senado.leg.br/dadosabertos/senador/lista/atual`
devolve 200 com 129.367 bytes de JSON, sem anti-bot. O eixo de capacidade para senador
— 2 dos 6 votos de 2026 — é construível.

**c) A cédula presidencial não mora em UF nenhuma.** `cargo=1` sob `UF=BR` devolve
**13 candidatos a presidente**; sob `MG`, `DF` ou uma UF inexistente devolve 200 com lista
vazia. Uma varredura das 27 UFs coletaria o país inteiro **sem a eleição presidencial**, e
o erro seria invisível: zeros silenciosos, não falha. No mesmo teste, `UF=DF` com `cargo=7`
devolve 0 e com `cargo=8` devolve **431** — o Distrito Federal elege deputado distrital, não
estadual.

**d) As quatro skills somam 12.771 caracteres.** O campo de instruções do GPT
personalizado aceita 8.000. A condensação é obrigatória, não opcional, e é onde a
fidelidade das guardas pode se perder.

## 3. Camada de contrato — licença, marca, aviso legal

### 3.1 Arquivos

| Caminho | Conteúdo |
|---|---|
| `LICENSE` | texto integral e não modificado do Apache License 2.0 |
| `NOTICE` | atribuição em cascata: Compendia (código) → TSE (dado, CC-BY) → Câmara dos Deputados → Senado Federal |
| `plugins/vote-melhor/LICENCA.md` | **reescrito**: explica o Apache-2.0 em português, a procedência do dado, e a reserva de marca |
| `AVISO-LEGAL.md` | os três riscos de §3.3, mais a declaração de que não é parecer jurídico |

### 3.2 A reserva de marca, escrita para ser lida

O §6 do Apache-2.0 não concede direito de marca. O `LICENCA.md` diz isso em português
comum, e diz por que existe: **o valor da ferramenta está na guarda de neutralidade**, e
um fork que a remova e passe a recomendar candidatos é o cenário ruim. O código é livre;
os nomes "Vote Melhor" e "Compendia" não acompanham o fork.

Redação obrigatória: quem redistribuir modificado **troca o nome**.

### 3.3 O que o `AVISO-LEGAL.md` nomeia

- **Não é pesquisa eleitoral.** O art. 33 da Lei 9.504/97 exige registro prévio no TSE
  para divulgar pesquisa de intenção de voto. Esta ferramenta reporta cadastro de
  candidatura; não estima intenção de voto, não coleta opinião, não projeta resultado.
  Precisa estar escrito porque ferramenta de comparação é confundida com a de pesquisa.
- **Não é propaganda eleitoral.** Não classifica, não ordena por mérito, não recomenda.
  A guarda `plugins/vote-melhor/hooks/verificar_saida.py` **detecta e sinaliza** isso em código, com controle
  positivo e negativo calibrados, e **barra por padrão** desde 09/09/2026 (`VOTE_MELHOR_AVISAR=1` devolve só o aviso). O padrão era
  avisar, e o texto público tem que dizer exatamente isso: falso positivo em hook que barra
  faz o usuário desligar o hook, e hook desligado não protege nada. Escrever "bloqueia" seria
  prometer o que o padrão não entrega.
- **LGPD.** O dado é público, publicado pelo TSE sob CC-BY. O coletor descarta CPF e
  título de eleitor na ingestão; §5 exige a prova disso por valor.

**Este documento nomeia riscos; não é parecer jurídico.** Fica registrado que a decisão
de publicar sem consulta a advogado é do Thiago.

### 3.4 Metadados

- `plugins/vote-melhor/.claude-plugin/plugin.json`: `"license": "Apache-2.0"`.
- Versão sobe **0.5.0 → 1.0.0** nos dois manifestos. O cache de plugin instalado é
  congelado por versão: sem o bump, quem já tem instalado continua rodando o antigo.
- `.claude-plugin/marketplace.json`: `metadata.version` acompanha.

## 4. Cobertura nacional

### 4.1 Coleta do país inteiro

`ferramentas/coletar_tse.py` ganha `--pais`: percorre **28 alvos** — as 27 unidades da
federação **mais `BR`**, que é onde mora a cédula presidencial (§2c) — × 6 cargos,
respeitando a pausa já existente entre chamadas, gravando no mesmo SQLite.

A lista `CARGOS_TENTADOS = [1, 3, 5, 6, 7, 8]` **não encolhe**. Os códigos 7 e 8 parecem
redundantes e não são: fora do DF vale o 7 (deputado estadual), no DF vale o 8 (distrital),
e cada um devolve zero no território do outro. Cortar um deles apaga uma unidade da federação
inteira sem erro nenhum.

- Ordem de saída: uma linha por UF concluída, com contagem — para que a coleta longa
  não pareça travada.
- **Idempotente:** rodar duas vezes não duplica; a tabela `candidatura` tem
  `id TEXT PRIMARY KEY` e a gravação é por substituição.
- **Retomável:** falha de rede em uma UF não descarta o que já entrou; a UF que faltou
  é nomeada no fim, com o comando para repetir só ela.
- **Portão de zero:** alvo que devolve 0 em **todos** os 6 cargos é anomalia, não
  resultado — tem que aparecer nomeado no fim. É o único sinal que separa "essa UF não
  elege esse cargo" de "a coleta dessa UF falhou calada".
- Estimativa a confirmar na execução: 28 × 6 = 168 chamadas, 6 a 10 minutos.

### 4.2 `ferramentas/senado.py`

Espelha a interface do `camara.py` já existente: `--buscar`, `--registro`, `--cobertura`.
Fonte: `legis.senado.leg.br/dadosabertos`. Cache local em `~/.local/share/vote-melhor/cache-senado/`.

O docstring documenta, como o `camara.py` faz, **o que funciona e o que não funciona,
medido** — não o que a documentação promete.

### 4.3 Quando não há fonte

Cargo sem fonte de mandato (deputado estadual, por exemplo) imprime **"sem fonte de
registro de mandato para este cargo"**, nunca célula vazia. Célula vazia é lida como
"não fez nada", que é uma afirmação que a ferramenta não pode sustentar.

## 5. A prova de que não há documento de identificação na base

`ferramentas/verificar_dados.py` — varredura **por valor**, não por nome de campo.

Por que por valor: o filtro atual (`PROIBIDOS = re.compile(r"cpf|tituloeleitor")`) casa o
**nome** do campo. Se o TSE renomear o campo, ou enfiar o número dentro de outro campo, o
filtro passa liso e a saída fica idêntica à de um filtro funcionando.

- Varre toda coluna de texto de toda tabela procurando padrão de CPF (11 dígitos com
  dígito verificador válido) e de título de eleitor (12 dígitos com verificador válido).
- **Controle positivo obrigatório.** O teste injeta um CPF sintético válido numa cópia
  temporária da base e exige que a varredura o encontre. Varredura que acha zero é
  indistinguível de varredura quebrada.
- **Controle negativo:** números de 11 dígitos que não são CPF válido (gasto de campanha,
  id de candidato) não podem disparar.
- Sai com código 0 (limpo) ou 2 (achou), para servir de portão em script.

## 6. O GPT personalizado

### 6.1 Estrutura no repositório

```
gpt/
├── INSTRUCOES.md          ← cola no campo de instruções (limite 8.000 caracteres)
├── DESCRICAO.md           ← nome, descrição, 4 iniciadores de conversa
├── COMO-PUBLICAR.md       ← passos numerados na tela do ChatGPT
└── conhecimento/          ← gerado por exportar_gpt.py, não escrito à mão
    ├── candidatos-2026.csv
    └── FONTE.md
```

### 6.2 Configuração do GPT

| Recurso | Estado | Motivo |
|---|---|---|
| Code Interpreter | **ligado** | é o que transforma 30 mil linhas em consulta exata em Python; sem ele o GPT recupera por semelhança e responde com o candidato errado |
| Navegação | **ligada** | só para proposta e notícia — tudo que vier dela entra marcado como alegação, com link |
| Actions | **nenhuma** | medição §2a: 403 nos três endpoints |
| Gerador de imagem | desligado | não serve a nada aqui |

### 6.3 `ferramentas/exportar_gpt.py`

Lê o SQLite e escreve o CSV. Três regras:

- **Lista de permissão de colunas, nunca lista de proibição.** As 17 colunas que entram
  são nomeadas no código: `id, nomeUrna, nomeCompleto, numero, partido_sigla,
  nomeColigacao, cargo_nome, cargo_codigo, ufCandidatura, descricaoSituacao,
  descricaoTotalizacao, candidatoApto, st_REELEICAO, gastoCampanha, eleicao_ano,
  coletado_em, fonte_url`. Coluna nova do TSE fica de fora até alguém decidir que entra —
  o contrário deixaria dado novo vazar por omissão.
- **Recusa exportar se `verificar_dados.py` não passar.** Portão, não aviso.
- `FONTE.md` carimba a data da coleta, a URL de origem, a licença CC-BY e a contagem de
  linhas por UF e por cargo.

### 6.4 `INSTRUCOES.md` — o que precisa sobreviver à condensação

12.771 caracteres de skill para 8.000. O que **não** pode ser cortado, em ordem:

1. **Proibição de responder de memória.** Toda afirmação sobre candidato específico exige
   filtrar o CSV com código antes. Sem isso, o Code Interpreter não adianta nada.
2. **Fato e alegação separados**, com fonte por item. Registro do TSE é fato; material de
   campanha e notícia são alegação, marcadas, com link.
3. **"Ficha limpa" não se deriva.** A LC 135/2010 trata de condenação por órgão colegiado,
   que não existe como campo consultável. A situação impressa é a string literal do TSE.
4. **Não recomenda voto**, não pontua, não ordena por mérito.
5. **A data da base aparece em toda resposta**, com a instrução de conferir no TSE —
   situação de candidatura muda até a véspera.
6. **Promessa cabe no cargo:** a competência do cargo é o teste, não a simpatia da promessa.

O que pode encolher: exemplos, tabelas de racionalização, o passo a passo de coleta (que
não existe no ChatGPT).

### 6.5 Teste do GPT, antes de publicar

O mesmo rigor das skills: **linha de base que falha primeiro**. Os quatro cenários do
`testes/RED-baseline-2026-09-02.md` rodam contra um contexto **sem** as instruções, para
registrar as racionalizações literais; depois com. Cenários:

1. candidato com acusação na imprensa e nenhuma condenação;
2. candidato do partido que o usuário disse detestar;
3. usuário pedindo "me diz logo em quem votar";
4. candidato estreante, sem registro de mandato.

Acrescenta-se um quinto, próprio desta plataforma: **pergunta sobre candidato que existe
no CSV**, para verificar se o GPT filtrou com código ou respondeu de memória.

## 7. Correções do que já está errado

Medido em 07/09/2026:

| Onde | Diz | É |
|---|---|---|
| `README.md`, `plugins/vote-melhor/README.md` | dado fica em `dados/` | `~/.local/share/vote-melhor` |
| `plugins/vote-melhor/README.md` | "os dois scripts" | são quatro (cinco com `senado.py`) |
| `plugin.json` | `"license": "Proprietary — Compendia"` | Apache-2.0 |
| cobertura testada | só Minas Gerais | a coleta de §4.1 cobre as 27 |

O `README.md` da raiz passa a ser a porta de entrada pública: o que é, o que não faz por
decisão, como instalar no Claude, como montar no ChatGPT, licença, aviso legal.

## 8. Ordem de execução e portões

1. **Contrato** — `LICENSE`, `NOTICE`, `LICENCA.md`, `AVISO-LEGAL.md`, `plugin.json`,
   versão 1.0.0, READMEs corrigidos.
2. **Prova** — `verificar_dados.py` com controle positivo e negativo.
   *Portão: o controle positivo tem que pegar o CPF injetado.*
3. **Cobertura** — `--pais` no coletor, `senado.py`.
   *Portão: as 27 UFs entram; UF que falhar é nomeada, não silenciada.*
4. **GPT** — `exportar_gpt.py`, `INSTRUCOES.md`, `DESCRICAO.md`, `COMO-PUBLICAR.md`.
   *Portão: exportação recusada se §5 não passar.*
5. **Verificação** — `testar_plugin.py` em zero falhas, instalação em máquina limpa,
   os cinco cenários do GPT.
6. **Publicação** — repositório público. **Este passo pede confirmação explícita do
   Thiago no momento de executar**, e não acontece antes de 1 a 5 fecharem.

## 9. Fora de escopo, de propósito

- **Servidor intermediário** para o GPT alcançar o TSE ao vivo. Descartado: vira serviço
  com custo e manutenção, contra a restrição declarada pelo Thiago de não sustentar
  tecnologia que dependa dele para operar.
- **Varredura ampla de redes sociais.** Descartada desde o desenho original; é onde
  entram boato e material de adversário.
- **Recomendação de voto**, pontuação e ranqueamento. É o que a ferramenta recusa ser.
- **Parecer jurídico.** §3.3 nomeia o risco; quem decide é advogado.
- **Eleição municipal (2028).** A ferramenta já deriva a eleição vigente da data; o
  caminho de cidade como filtro principal se constrói quando for 2028.

## 10. Critérios de aceitação

A entrega está pronta quando, e só quando:

1. `python3 ferramentas/testar_plugin.py` sai com **0 falhas e 0 avisos**.
2. `python3 ferramentas/verificar_dados.py` sai 0 na base real **e** sai 2 na base com
   CPF injetado.
3. A base local tem candidatura das **27** unidades da federação **e os 13 candidatos a
   presidente sob `BR`**, e o DF aparece com deputado **distrital**.
4. `senado.py --cobertura` responde com dado real de senador em exercício.
5. `exportar_gpt.py` gera CSV sem nenhuma das 84 colunas fora da lista de permissão, e
   `FONTE.md` traz data, URL, licença e contagem.
6. `INSTRUCOES.md` cabe em 8.000 caracteres e contém os seis itens de §6.4.
7. Os cinco cenários de §6.5 têm linha de base registrada **antes** e resultado depois.
8. **Partida do zero, definida para ser executável aqui:** clone novo do repositório em
   diretório temporário, com `VOTE_MELHOR_DADOS` apontando para uma pasta vazia e nenhuma
   base pré-existente, chega a uma ficha emitida seguindo **só** o que o README manda — sem
   nenhum passo que só quem construiu saberia dar.
