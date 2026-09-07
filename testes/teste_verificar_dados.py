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

# --- CONTROLE ESTRUTURAL: Achado A e Achado B, medidos na base real --------
# Achado A (falso positivo): 6 ids de candidatura.id passavam em titulo_valido
# por coincidencia de checksum — sao a PROPRIA chave primaria da linha, nunca
# um titulo de eleitor de fato guardado. Achado B (vazamento real): um CPF
# valido estava embutido no NOME de um arquivo de certidao do TCU, dentro da
# lista JSON de `detalhe.arquivos` — outra linha, id diferente do CPF.
print("CONTROLE ESTRUTURAL — Achado A (id igual a chave) e Achado B (documento "
      "dentro de nome de arquivo)")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "estrutural.sqlite")
    cx = sqlite3.connect(banco)
    # Achado A: o id da linha, por coincidencia, bate o checksum de titulo.
    ID_QUE_PARECE_TITULO = vd.montar_titulo_sintetico("00000002", "05")
    cx.execute("CREATE TABLE candidatura (id TEXT PRIMARY KEY, apelido TEXT)")
    cx.execute("INSERT INTO candidatura VALUES (?,?)",
               (ID_QUE_PARECE_TITULO, "candidato qualquer"))
    # Achado B: o CPF de exemplo embutido no nome de um arquivo anexado,
    # dentro de uma lista serializada — o mesmo formato de detalhe.arquivos.
    cx.execute("CREATE TABLE detalhe (id TEXT PRIMARY KEY, arquivos TEXT)")
    cx.execute("INSERT INTO detalhe VALUES (?,?)",
               ("999", f'["CertidaoTCUContasIrregulares{CPF_EXEMPLO}.pdf"]'))
    cx.commit(); cx.close()
    achados = vd.varrer(banco)
    achados_candidatura = [a for a in achados if a["tabela"] == "candidatura"]
    achados_detalhe = [a for a in achados if a["tabela"] == "detalhe"]
    checa("Achado A: valor igual ao proprio id NAO e reportado",
          not achados_candidatura, f"achados={achados_candidatura}")
    checa("Achado B: documento dentro de nome de arquivo E reportado",
          any(a["tipo"] == "cpf" and a["coluna"] == "arquivos"
              for a in achados_detalhe),
          f"achados={achados_detalhe}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
