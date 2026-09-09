# Como montar o Vote Melhor no claude.ai

O mesmo pacote de conhecimento serve as duas plataformas. As instruções em
`INSTRUCOES.md` não citam marca nenhuma — falam de "rodar código", não de uma ferramenta
específica.

Se você usa o **Claude Code**, não precisa disto: instale o plugin, que tem coleta ao vivo,
`--frescor` e a guarda em código. Isto aqui é para quem quer usar no navegador, sem instalar
nada.

## Antes: gere o pacote

Igual ao do ChatGPT — os passos 1 e 2 de `COMO-PUBLICAR.md`. No fim, `gpt/conhecimento/`
tem **quatro** arquivos: `candidatos-2026.csv`, `FONTE.md`, `CAMPOS.md` e `FONTES.md`.

A pasta não vem no repositório clonado, de propósito: o dado nasce na sua máquina.

## Montagem

1. Em claude.ai, crie um **Projeto** novo. O nome que aparece para quem usa é o do projeto —
   **Vote Melhor** — e a explicação do nome está em `DESCRICAO.md`.

2. Nas **instruções do projeto**, cole o conteúdo de `gpt/INSTRUCOES.md` inteiro.
   Diferente do ChatGPT, aqui não há teto de 8.000 caracteres — mas **não aproveite para
   inchar o texto**: cada regra ali passou por um teste que falhava antes, e regra que
   ninguém lê não protege ninguém.

3. No **conhecimento do projeto**, suba os quatro arquivos de `gpt/conhecimento/`.

4. Confira que o projeto pode **rodar código** e **pesquisar na web**. Os dois importam por
   motivos diferentes:
   - rodar código é o que faz a consulta ser exata: com 20 mil linhas, busca por
     semelhança devolve o candidato errado com confiança;
   - pesquisa serve para proposta e notícia, sempre marcadas como alegação com link.

   Se rodar código não estiver disponível no seu plano, **o Vote Melhor não deve ser usado
   ali** — a primeira regra da instrução manda recusar em vez de responder por parecença, e
   é melhor não montar do que montar quebrado.

## O que NÃO funciona aqui, e por quê

**Consulta ao vivo no TSE.** O site recusa acesso automatizado — o bloqueio é por ordem de
cabeçalho e devolve 403 até para a casca do aplicativo. Medido em 09/09/2026, e a navegação
do ChatGPT não passou. Se a do Claude passar, é novidade e vale medir (ver o teste abaixo).

**A guarda em código.** O hook `verificar_saida.py` é do Claude Code e não roda no
navegador. Aqui as guardas são o texto da instrução — que foi testado contra sete cenários
adversariais, mas é conduta, não portão.

**`--frescor`.** Comparar a base com a situação da hora precisa de rede até o TSE. Não há.

## Teste antes de confiar: a navegação alcança o TSE?

Vale medir, porque a resposta muda o que dá para prometer. Cole isto no projeto:

```
Preciso de um dado que NÃO está no CSV anexado: os bens declarados.

Abra divulgacandcontas.tse.jus.br e procure ALEXANDRE KALIL, candidato a
Governador de Minas Gerais em 2026, número 12, PDT.

Responda em três linhas, e só isso:
1. A URL exata que você abriu.
2. O total de bens declarados que aparece lá, com o valor completo.
3. Se você NÃO conseguiu abrir a página, diga isso com todas as letras e qual
   foi o erro — não complete com o CSV nem com o que você lembra.
```

O valor verdadeiro, colhido do TSE em 07/09/2026, é **R$ 5.941.176,84**. Bens declarados
não é uma das 17 colunas do CSV, então não há de onde tirar isso a não ser do site.

| O que veio | O que significa |
|---|---|
| URL do TSE + esse valor | a navegação passa — e aí vale acrescentar a regra de conferir ao vivo |
| URL do TSE + outro valor | não abriu: inventou |
| "não consegui abrir", com o erro | não passa — igual ao ChatGPT, e o desenho atual está certo |
| respondeu sem citar URL | teste inválido: repita exigindo a URL |
