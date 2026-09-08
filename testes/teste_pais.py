#!/usr/bin/env python3
"""Controles da coleta nacional. NAO toca a rede: mede a lista de alvos e o
portao de zero, que sao as duas coisas que falham em silencio."""
import os, sys

# Importar coletar_tse escreve .pyc ao lado dele. O dont_write_bytecode DE
# DENTRO de coletar_tse.py so passa a valer depois que o corpo do modulo
# comeca a executar — e a escrita do .pyc do proprio coletar_tse.py acontece
# ANTES disso, no carregamento do import. Isso protege o que coletar_tse.py
# importa (verificar_dados), mas nao protege coletar_tse.py ser cacheado
# quando e ELE que esta sendo importado por este teste. Bloqueamos aqui,
# antes do import — mesmo padrao de testes/teste_verificar_dados.py.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
sys.argv = ["coletar_tse"]
import coletar_tse as ct

falhas = []
def checa(nome, cond, detalhe):
    print(f"  [{'ok ' if cond else 'FALHA'}] {nome}: {detalhe}")
    if not cond: falhas.append(nome)

print("ALVOS — a cedula presidencial nao mora em UF nenhuma")
checa("sao 28 alvos", len(ct.ALVOS) == 28, f"len={len(ct.ALVOS)}")
checa("BR esta na lista", "BR" in ct.ALVOS, f"BR in ALVOS = {'BR' in ct.ALVOS}")
checa("DF esta na lista", "DF" in ct.ALVOS, f"DF in ALVOS = {'DF' in ct.ALVOS}")
checa("sem repetido", len(set(ct.ALVOS)) == len(ct.ALVOS),
      f"unicos={len(set(ct.ALVOS))}")

print("CARGOS — 7 e 8 parecem redundantes e nao sao")
checa("cargo 7 presente", 7 in ct.CARGOS_TENTADOS, str(ct.CARGOS_TENTADOS))
checa("cargo 8 presente (dep. distrital do DF)", 8 in ct.CARGOS_TENTADOS,
      str(ct.CARGOS_TENTADOS))
checa("cargo 1 presente (presidente, so sob BR)", 1 in ct.CARGOS_TENTADOS,
      str(ct.CARGOS_TENTADOS))

print("PORTAO DE ZERO — alvo mudo tem que ser nomeado")
checa("alvo com tudo zero e anomalia",
      ct.alvo_mudo({"1": 0, "3": 0, "5": 0, "6": 0, "7": 0, "8": 0}) is True,
      "todos zero -> True")
checa("alvo com um cargo preenchido nao e anomalia",
      ct.alvo_mudo({"1": 0, "3": 11, "5": 0, "6": 0, "7": 0, "8": 0}) is False,
      "um preenchido -> False")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
