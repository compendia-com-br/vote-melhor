#!/usr/bin/env python3
"""Controles do portao de documento de identificacao.

Um portao que acha zero e indistinguivel de um portao quebrado. Por isso o
teste injeta um documento sintetico e EXIGE que a varredura o encontre.
"""
import contextlib, io, os, sqlite3, sys, tempfile

# Importar modulos do plugin escreve .pyc ao lado deles. Bloqueamos antes de
# manipular sys.path e fazer os imports.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
import verificar_dados as vd
import coletar_tse as ct

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

# --- CONTROLE DA MASCARA — mascarar_valor(), achatar() e limpar() ----------
# As tres pecas mais arriscadas do modulo nao tinham teste commitado: a que
# altera o dado na ingestao (mascarar_valor), o ponto onde a mascara entra
# de verdade no banco (achatar, em coletar_tse.py) e a que faz UPDATE na
# base ja gravada (limpar). Uma verificacao manual dessas tres foi descrita
# em relatorio antes, mas sem codigo commitado ninguem conseguia repetir.
print("CONTROLE DA MASCARA — mascarar_valor(), achatar() e limpar()")

# 1) numero que NAO e documento sobrevive intacto a mascara ------------------
# Mesmo valor usado la em cima como "gasto de campanha" no controle
# negativo — 11 digitos que ja nao batiam o digito verificador de CPF.
# Confirmado de novo aqui, na propria conta que a mascara usa: se essa
# premissa quebrar em silencio, o teste abaixo provaria a coisa errada.
NUM_NAO_DOCUMENTO = "12345678901"
checa("premissa: numero de controle realmente nao e CPF valido",
      not vd.cpf_valido(NUM_NAO_DOCUMENTO),
      "troque NUM_NAO_DOCUMENTO — ele passou a bater o digito verificador")
texto_protocolo = f"protocolo {NUM_NAO_DOCUMENTO} anexado ao processo"
resultado = vd.mascarar_valor(texto_protocolo, "id-generico-1")
checa("numero sem digito verificador (protocolo/id de arquivo) sobrevive intacto",
      resultado == texto_protocolo, f"resultado={resultado!r}")

# 2) CPF valido num nome de arquivo vira a mascara VISIVEL, nao truncamento --
NOME_ARQUIVO = f"CertidaoTCUContasIrregularescomImplicacoesEleitorais{CPF_EXEMPLO}.pdf"
resultado = vd.mascarar_valor(NOME_ARQUIVO, "id-generico-2")
esperado = NOME_ARQUIVO.replace(CPF_EXEMPLO, vd.MASCARA)
checa("CPF em nome de arquivo vira a mascara visivel, nao truncamento",
      resultado == esperado and vd.MASCARA in resultado
      and CPF_EXEMPLO not in resultado,
      f"resultado={resultado!r}")

# 3) documento IGUAL ao id da propria linha sobrevive (mesma excecao de varrer) -
resultado = vd.mascarar_valor(CPF_EXEMPLO, CPF_EXEMPLO)
checa("documento igual ao id da propria linha sobrevive a mascara",
      resultado == CPF_EXEMPLO, f"resultado={resultado!r}")

# 4) achatar() (coletar_tse.py) — o ponto onde a mascara entra no banco de fato
# Este e' o que importa de verdade: nao a conta isolada, mas o lugar onde o
# coletor de fato aplica a mascara antes de gravar.
obj_tse = {"arquivos": [{"nome": NOME_ARQUIVO, "tipo": "pdf"}]}
achatado = ct.achatar(obj_tse, id_linha="130002550464")
checa("achatar() mascara o CPF dentro da lista serializada antes de gravar",
      vd.MASCARA in achatado["arquivos"] and CPF_EXEMPLO not in achatado["arquivos"],
      f"arquivos={achatado['arquivos']!r}")

# 5) limpar() numa base temporaria: relata, altera, e a 2a passagem nao acha nada
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "para_limpar.sqlite")
    cx = sqlite3.connect(banco)
    cx.execute("CREATE TABLE candidatura (id TEXT PRIMARY KEY, apelido TEXT)")
    cx.execute("INSERT INTO candidatura VALUES (?,?)", ("1", CPF_EXEMPLO))
    cx.commit(); cx.close()

    antes = vd.varrer(banco)
    checa("antes de --limpar, a varredura acha o documento", len(antes) == 1,
          f"antes={antes}")

    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = vd.limpar(banco)
    relato = saida.getvalue()
    checa("limpar() devolve 0 na primeira passagem (ficou limpo)", codigo == 0,
          f"codigo={codigo}")
    checa("limpar() nunca imprime o documento completo no proprio relato",
          CPF_EXEMPLO not in relato,
          "CPF completo apareceu na saida de --limpar")

    depois = vd.varrer(banco)
    checa("depois de --limpar, a varredura nao acha mais nada", not depois,
          f"depois={depois}")

    saida2 = io.StringIO()
    with contextlib.redirect_stdout(saida2):
        codigo2 = vd.limpar(banco)
    checa("segunda passagem de --limpar nao acha nada para mudar (idempotente)",
          codigo2 == 0, f"codigo2={codigo2}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
