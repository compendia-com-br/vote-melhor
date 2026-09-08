# Como publicar o GPT personalizado — Vote Melhor

Passo a passo na tela do ChatGPT (chatgpt.com/gpts/editor, aba "Configure"). Precisa de
conta ChatGPT Plus, Team ou Enterprise — GPT personalizado não existe no plano gratuito.

Cada passo diz o que fazer e o que deve aparecer depois, para dar para conferir sem
adivinhar.

## 1. Criar o GPT

Em chatgpt.com/gpts/editor, aba "Configure". Preencha **Name** com `Vote Melhor` (de
`gpt/DESCRICAO.md`) e **Description** com o texto do mesmo arquivo. Depois disso a tela
mostra os campos Instructions, Conversation starters, Knowledge e Capabilities — é neles
que os próximos passos mexem.

## 2. Colar as instruções

Copie o conteúdo inteiro de `gpt/INSTRUCOES.md` (sem o front-matter, que ele não tem) e
cole em **Instructions**. Depois de colar, o contador de caracteres da própria tela do
ChatGPT deve mostrar um número abaixo de 8.000 — se mostrar acima, o campo trunca sem
avisar, e o corte cai onde o ChatGPT decidir, não onde a guarda pede. Se isso acontecer,
pare e encurte antes de seguir.

## 3. Colar os iniciadores de conversa

Cole as quatro frases de `gpt/DESCRICAO.md` em **Conversation starters**, uma por campo.
Depois de colar, os quatro devem aparecer como botões na pré-visualização à direita da
tela.

## 4. Subir a base de conhecimento

Em **Knowledge**, clique "Upload files" e suba os dois arquivos de
`gpt/conhecimento/`: `candidatos-2026.csv` e `FONTE.md`. Depois de subir, os dois devem
aparecer listados nessa seção com o tamanho do arquivo ao lado — confira que o CSV
aparece com uns 5-6 MB (20 mil linhas), não com 0 bytes.

## 5. Ligar Code Interpreter — obrigatório

Em **Capabilities**, marque **Code Interpreter & Data Analysis**. Sem isso, o item 1 das
instruções (nunca responder de memória, sempre filtrar o CSV com código) não tem como se
cumprir: o ChatGPT passa a recuperar do arquivo por semelhança de texto, e em 20 mil
linhas isso devolve o candidato errado com confiança. Depois de marcar, peça ao GPT (na
pré-visualização) "lista os 3 primeiros candidatos do arquivo" — a resposta certa vem
com uma célula de código executada, visível na conversa. Se não aparecer código nenhum,
a marcação não pegou.

## 6. Ligar navegação — obrigatório

Marque **Web Browsing** (ou **Web Search**, dependendo da versão da tela). É o que
sustenta a skill de fontes externas: proposta de governo, atuação parlamentar e notícia
não estão no CSV, e sem navegação o GPT teria que inventar ou recusar toda pergunta sobre
esses três assuntos.

## 7. NÃO criar Action — decisão medida, não esquecimento

Não marque **Actions**. Não crie nenhuma. Motivo medido em 07/09/2026: uma requisição
`curl` pura, sem nenhum enfeite, levou **403** nos três endpoints do TSE testados
(`divulgacandcontas.tse.jus.br`, `cdn.tse.jus.br`, `dadosabertos.tse.jus.br`). O que
passa é o cliente local do plugin, com a ordem exata de cabeçalhos do Chrome — e uma
Action de GPT personalizado é, para o servidor do TSE, um cliente HTTP comum como
qualquer outro. Ela levaria o mesmo 403. **Se alguém no futuro achar isso estranho e
quiser "consertar" adicionando uma Action, o teste é rodar `curl` contra qualquer um dos
três endpoints acima e ler o código de resposta antes de escrever uma linha** — evita
perder um dia inteiro atrás de uma Action que nunca vai passar.

## 8. Desligar o gerador de imagem

Desmarque **DALL·E Image Generation**. O Vote Melhor não gera imagem — ligado, ele só
soma uma capacidade que nunca é usada e pode confundir quem testar o GPT perguntando por
uma arte.

## 9. Publicar

No canto superior direito, "Create" (ou "Update", se já existir) → escolha quem pode ver
(recomendado: "Anyone with a link" ou "Public", conforme o alcance decidido para a
distribuição) → confirme. Depois de publicar, abra o link em uma aba anônima e repita o
teste do passo 5 — se o código não aparecer para um visitante sem login na conta que
criou o GPT, o link publicado não é o mesmo GPT configurado, e vale conferir de novo os
passos 2 e 5.

## Como atualizar a base depois

A base tem data e envelhece — situação de candidatura muda até a véspera da eleição (4 de
outubro de 2026). Para atualizar:

1. `python3 ferramentas/coletar_tse.py --pais` — recoleta as 27 UFs mais BR do TSE.
2. `python3 ferramentas/exportar_gpt.py` — regrava `gpt/conhecimento/candidatos-2026.csv`
   e `gpt/conhecimento/FONTE.md` com a nova data de coleta.
3. Na tela **Configure** do GPT (mesmo link do passo 1), em **Knowledge**, remova o CSV
   antigo e suba o novo — o ChatGPT não atualiza arquivo já subido sozinho, é preciso
   trocar. Suba também o `FONTE.md` novo.
4. Clique "Update" para publicar a base nova no GPT que já está no ar.

Repita isso perto da eleição, porque a divergência entre a base e o TSE ao vivo é
justamente a informação que o item 5 das instruções pede para o GPT declarar — uma base
muito velha aumenta a chance de o GPT precisar admitir "não sei se isso mudou" em vez de
responder com segurança.
