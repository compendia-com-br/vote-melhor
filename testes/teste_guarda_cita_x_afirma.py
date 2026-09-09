#!/usr/bin/env python3
"""A guarda tem de separar AFIRMAR de CITAR — e nao pode ficar cega no caminho.

Por que este teste existe: com o padrao estrito, a guarda BARRAVA a edicao de quatro
documentos do proprio projeto (as instrucoes do GPT, a skill fato-e-alegacao, o registro
RED e ela mesma). A guarda impedia manter a guarda. Medido em 09/09/2026.

Duas causas distintas, e o teste cobre as duas:
  A) mencao — o documento CITA a construcao proibida para proibi-la, e a guarda casava
     igual a quem AFIRMA. A regra do produto ja resolvia isso: alegacao citada COM FONTE
     e saida legitima; afirmacao nua nao e.
  B) prosa comum — "o erro mais comum e o mais caro" nao compara candidato nenhum. O
     regex aceitava qualquer palavra depois de "e o mais".

O perigo desta correcao e afrouxar demais. Por isso o bloco POSITIVO vem primeiro e traz
uma tentativa de EVASAO: aspas sem atribuicao nao podem esconder nada.
"""
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "plugins", "vote-melhor", "hooks"))
import verificar_saida as g

falhas = []
def checa(nome, cond, detalhe=""):
    print(f"  [{'ok ' if cond else 'FALHA'}] {nome}{': ' + detalhe if detalhe else ''}")
    if not cond: falhas.append(nome)

print("POSITIVOS — a guarda TEM de continuar pegando")
POS = [
 ("afirmacao nua de ficha limpa", "O candidato Fulano e ficha limpa e pode ser eleito."),
 ("comparativo entre os tres",    "O curriculo mais forte dos tres e o dele."),
 ("superlativo de qualidade",     "Ele e o mais preparado dos candidatos."),
 ("percentual de aderencia",      "Aderencia de 82% ao seu eixo."),
 ("veredito de elegibilidade",    "Fulano esta inelegivel."),
 ("superlativo solto, mas com candidato por perto",
                                  "Entre os candidatos a governador, ele e o mais consistente."),
]
for nome, txt in POS:
    checa(nome, bool(g.achar(txt)))

print("\nNEGATIVOS — a guarda TEM de parar de pegar")
NEG = [
 ("prosa: 'o erro mais comum e o mais caro'",
  "Confundir dois degraus e o erro mais comum e o mais caro:"),
 ("conector: 'E o mais importante:'",
  "E o mais importante: diga isso na ficha."),
 ("prosa sobre ficha, sem comparar candidato",
  "Uma ficha que omite em silencio o que o eleitor mais quer saber e armadilha."),
 ("mencao para PROIBIR, entre aspas",
  'Nunca escreva "e ficha limpa" na saida.'),
 ("alegacao citada COM fonte",
  'A campanha afirma que ele "e o mais preparado" (fonte: site oficial).'),
 ("construcao dentro de bloco de codigo",
  "Exemplo do que nao fazer:\n```\nFulano e ficha limpa\n```\n"),
 ("construcao em codigo de linha",
  "O regex casa `e ficha limpa` e devolve o achado."),
]
for nome, txt in NEG:
    ach = g.achar(txt)
    checa(nome, not ach, "" if not ach else f"pegou {ach[0][2]!r}")

print("\nOS QUATRO DOCUMENTOS DO PROJETO — a guarda nao pode barrar a propria manutencao")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
for rel in ("gpt/INSTRUCOES.md",
            "plugins/vote-melhor/hooks/verificar_saida.py",
            "plugins/vote-melhor/skills/fato-e-alegacao/SKILL.md",
            "testes/RED-gpt-2026-09-07.md"):
    cam = os.path.join(RAIZ, rel)
    if not os.path.exists(cam):
        checa(f"{rel} (ausente)", False, "arquivo nao existe"); continue
    ach = g.achar(open(cam, encoding="utf-8").read())
    checa(rel, not ach, "" if not ach else f"{len(ach)} achado(s), 1o = {ach[0][2]!r}")

print("\nLIMITES CONHECIDOS — o que este desenho NAO pega, dito de proposito")
# Nao sao falhas: sao o preco medido do discriminador ser ESTRUTURAL (marcacao) e nao
# lexical (lista de verbos). A lista foi tentada e furou em 3 casos reais do proprio
# projeto — "Nunca de ... superlativo (", "Assim nao:", "- Escrever". Lista de palavras da
# confianca falsa; a marcacao nao. Estes controles fixam o comportamento ATUAL, para que
# uma mudanca futura apareca em vez de passar calada.
LIMITES = [
 ("aspas sem atribuicao escondem a afirmacao",
  'Fulano "e ficha limpa".',
  "quem quiser fechar precisa de analise de sujeito, nao de mais uma lista"),
 ("negacao explicativa fora de aspas ainda dispara",
  "Esse campo nao diz se a pessoa esta elegivel.",
  "a guarda le a construcao, nao a negacao que a cerca"),
]
for nome, txt, porque in LIMITES:
    ach = bool(g.achar(txt))
    print(f"  [limite] {nome}: guarda {'acusa' if ach else 'NAO acusa'} — {porque}")

print("\nA GUARDA NAO PODE FICAR CEGA — a afirmacao real da linha de base")
checa("afirmacao nua no cenario real (base-1)",
      bool(g.achar("Excelente noticia: **Alexandre Kalil e ficha limpa**.")))
checa("pergunta do eleitor em bloco de citacao NAO e saida da ferramenta",
      not g.achar("> Vi uma reportagem. Ele e ficha limpa? Posso votar tranquilo?"))

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
