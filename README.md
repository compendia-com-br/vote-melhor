<img src="assets/marca/assinatura-horizontal.svg" alt="Compendia" width="300">

# Vote Melhor

Monta a ficha de candidatura de eleição brasileira a partir do dado oficial do TSE. O
"melhor" é sobre a decisão de quem vota, não sobre o candidato — a ferramenta reúne o dado
oficial, não classifica, não pontua e não recomenda voto.

Uma coleção **Compendia**.

## O que tem aqui

| Pasta | O que é |
|---|---|
| `plugins/vote-melhor` | o plugin do Claude Code — instalável, com o skill que conduz a consulta |
| `ferramentas` | coleta do TSE e da Câmara, critérios de checagem |
| `testes` | linha de base e sondas de verificação |
| `dados` | cache local de coleta — **nunca versionado** (ver abaixo) |

Detalhe de uso e o que o plugin não faz, por decisão, em
[plugins/vote-melhor/README.md](plugins/vote-melhor/README.md).

## Dado sensível

`dados/` guarda documento de identificação de candidato — o TSE publica título de eleitor
em toda listagem e CPF no detalhe, sob licença Creative Commons Atribuição. É dado público
do TSE, mas ainda assim de terceiro: o `.gitignore` bloqueia essa pasta antes de qualquer
commit.

---

<img src="assets/marca/simbolo-compendia.svg" alt="" width="12"> © 2026 **Compendia** · [compendia.com.br](https://compendia.com.br)
· compendia.com.br@gmail.com · +55 34 98430-9000
