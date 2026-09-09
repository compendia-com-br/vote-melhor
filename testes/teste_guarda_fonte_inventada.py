#!/usr/bin/env python3
"""URL de dominio oficial que nao esta na lista verificada e endereco inventado.

Medido em 09/09/2026: o GPT citou `www2.câmara.leg.br` — com acento — para mandar o eleitor
conferir a atuacao parlamentar. O dominio nao existe (o nome nem resolve), e a instrucao ja
proibia montar URL por palpite. Proibicao sem alternativa nao segura falha de forma.

Esta e a terceira camada da correcao: o dado (FONTES.md, gerado e verificado por
ferramentas/verificar_fontes.py), a instrucao que manda consultar esse dado, e AQUI o
portao que acusa quando o endereco sai fora da lista.

O discriminador e estrutural, nao uma lista de erros: dominio que TERMINA em .leg.br,
.jus.br ou .gov.br carrega autoridade — se nao for um dos verificados, foi inventado.
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

print("INVENTADAS — tem de acusar")
for nome, txt in [
 ("o erro medido: dominio com acento",
  "Confira em https://www2.câmara.leg.br/deputados a atuacao dele."),
 ("subdominio que nao existe",
  "Veja https://consulta.tse.jus.br/candidato/12345 para a ficha completa."),
 ("orgao inventado com cara de oficial",
  "A fonte e https://transparencia.eleicoes.gov.br/relatorio."),
]:
    checa(nome, bool(g.achar(txt)))

print("\nVERIFICADAS — nao pode acusar")
for nome, txt in [
 ("TSE, consulta de candidatura", "Confira em https://divulgacandcontas.tse.jus.br antes de decidir."),
 ("Camara",                        "A atuacao esta em https://www.camara.leg.br."),
 ("Senado",                        "Veja https://www25.senado.leg.br/web/senadores."),
 ("API que as ferramentas usam",   "fonte: https://dadosabertos.camara.leg.br/api/v2/deputados"),
 ("API do Senado",                 "fonte: https://legis.senado.leg.br/dadosabertos/senador/lista/atual"),
 ("dominio que nao finge ser oficial", "Leia mais em https://exemplo.com.br/materia."),
]:
    ach = g.achar(txt)
    checa(nome, not ach, "" if not ach else f"pegou {ach[0][2]!r}")

print("\nOS DOCUMENTOS DO PROJETO CONTINUAM EDITAVEIS")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
for rel in ("gpt/INSTRUCOES.md", "README.md", "AVISO-LEGAL.md", "NOTICE",
            "plugins/vote-melhor/hooks/verificar_saida.py",
            "plugins/vote-melhor/skills/fontes-externas/SKILL.md"):
    cam = os.path.join(RAIZ, rel)
    if not os.path.exists(cam):
        checa(f"{rel} (ausente)", False); continue
    ach = g.achar(open(cam, encoding="utf-8").read())
    checa(rel, not ach, "" if not ach else f"{len(ach)} achado(s), 1o = {ach[0][2]!r}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
