# Licença

**Vote Melhor** (`vote-melhor`) — ficha de candidatura a partir do dado oficial do TSE

© 2026 **Compendia**. Licenciado sob **Apache License, Version 2.0**. O texto integral está
em [`LICENSE`](../../LICENSE), na raiz do repositório.

## O que a licença permite

Usar, estudar, modificar, redistribuir e usar comercialmente — de graça, sem pedir
permissão. Fork, cópia, embutir num produto maior, vender serviço em cima: tudo permitido,
contanto que a atribuição e o aviso de copyright do `LICENSE` viajem junto.

## A reserva de marca — e por que ela existe

O valor desta ferramenta está na guarda que a impede de recomendar voto. Um fork que remova
essa guarda e passe a recomendar candidatos é o cenário que esta cláusula existe para impedir
de acontecer com o nosso nome. O código é livre; o nome não acompanha. Quem redistribuir
modificado troca o nome.

Em termos práticos: o §6 do Apache-2.0 concede direito sobre o código e, no mesmo parágrafo,
nega direito sobre marca. "Vote Melhor" e "Compendia" continuam marcas da Compendia mesmo
depois de um fork. Um fork sem essa guarda pode existir — a licença permite — mas não pode se
chamar Vote Melhor nem usar o nome Compendia.

## A procedência do dado

**Este software não embarca dado nenhum.** Ele coleta, na máquina de quem usa, de fontes
públicas oficiais:

- **Tribunal Superior Eleitoral (TSE)** — DivulgaCandContas
  (https://divulgacandcontas.tse.jus.br) e Portal de Dados Abertos
  (https://dadosabertos.tse.jus.br), sob licença Creative Commons Atribuição (CC BY).
- **Câmara dos Deputados** — Dados Abertos (https://dadosabertos.camara.leg.br).
- **Senado Federal** — Dados Abertos (https://legis.senado.leg.br/dadosabertos).

A atribuição ao TSE (URL e data da coleta) é impressa em toda ficha de candidatura emitida
(`consultar.py --ficha`). A atribuição à Câmara e ao Senado aparece quando o registro de
mandato federal é consultado (`camara.py --registro` / `senado.py --registro`), cada um com
a própria URL e data da coleta.
A propriedade da Compendia é sobre o **código, o método e a forma da ficha** — nunca sobre o
dado público, que é do TSE, da Câmara, do Senado e de quem quiser usá-lo.

## O que este software não faz

Não classifica candidato, não deriva elegibilidade, não emite veredito de "ficha limpa", não
ordena por mérito e não recomenda voto. A ficha traz a string literal do TSE e a fonte de
cada campo. A decisão é de quem vota.

## Sem garantia

O software é fornecido "como está". A Compendia não garante disponibilidade nem exatidão do
dado publicado por terceiros, e não responde por decisão tomada com base nele. Situação de
candidatura muda até a véspera da eleição: confira a data de coleta impressa na ficha.
