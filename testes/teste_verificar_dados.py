#!/usr/bin/env python3
"""Controles do portao de documento de identificacao.

Um portao que acha zero e indistinguivel de um portao quebrado. Por isso o
teste injeta um documento sintetico e EXIGE que a varredura o encontre.
"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
import verificar_dados as vd

falhas = []

def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)

# --- CONTROLE POSITIVO: um CPF sintetico valido tem que ser achado ----------
# 529.982.247-25 e um CPF com digitos verificadores corretos, usado em
# documentacao publica brasileira justamente como exemplo. Nao pertence a
# ninguem neste banco: ele e INJETADO aqui de proposito.
CPF_EXEMPLO = "52998224725"
# Titulo de eleitor sintetico: 8 digitos sequenciais + UF 01 + 2 verificadores.
TITULO_EXEMPLO = vd.montar_titulo_sintetico("00000001", "01")

print("CONTROLE POSITIVO — documento injetado tem que ser achado")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "sujo.sqlite")
    cx = sqlite3.connect(banco)
    cx.execute("CREATE TABLE candidatura (id TEXT PRIMARY KEY, nomeUrna TEXT, apelido TEXT)")
    cx.execute("INSERT INTO candidatura VALUES (?,?,?)",
               ("1", "FULANO", CPF_EXEMPLO))
    cx.execute("INSERT INTO candidatura VALUES (?,?,?)",
               ("2", "BELTRANO", f"documento {TITULO_EXEMPLO} anotado"))
    cx.commit(); cx.close()
    achados = vd.varrer(banco)
    tipos = sorted({a["tipo"] for a in achados})
    checa("acha CPF em coluna de nome inocente", "cpf" in tipos, f"tipos={tipos}")
    checa("acha titulo no meio de uma frase", "titulo" in tipos, f"tipos={tipos}")
    checa("aponta a coluna certa",
          all(a["coluna"] == "apelido" for a in achados),
          f"colunas={[a['coluna'] for a in achados]}")

# --- CONTROLE NEGATIVO: numero que NAO e documento nao pode disparar --------
print("CONTROLE NEGATIVO — numero que nao e documento tem que passar")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "limpo.sqlite")
    cx = sqlite3.connect(banco)
    cx.execute("CREATE TABLE candidatura (id TEXT PRIMARY KEY, gasto TEXT, tel TEXT)")
    # id real de candidato do TSE (12 digitos), gasto de campanha, telefone.
    cx.execute("INSERT INTO candidatura VALUES (?,?,?)",
               ("130002539775", "12345678901", "5534984309000"))
    cx.execute("INSERT INTO candidatura VALUES (?,?,?)",
               ("130002539776", "11111111111", "00000000000"))
    cx.commit(); cx.close()
    achados = vd.varrer(banco)
    checa("id de candidato do TSE nao vira documento", not achados,
          f"achados={achados}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
