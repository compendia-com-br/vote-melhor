#!/usr/bin/env python3
"""Controles do exportador do pacote do GPT (ferramentas/exportar_gpt.py).

Dois portoes protegem o CSV que sobe para dentro de um GPT publico: um confere
a base ANTES de escrever (varrer()), outro RELE o arquivo JA GRAVADO em disco
depois de escrever (relatorio_pos_escrita()). Nenhum dos dois tinha teste
commitado — a verificacao foi manual, descrita em prosa num relatorio, e uma
mudanca futura podia quebrar o pareamento entre linha e id em silencio, sem
que nada acusasse.

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem grava nos
arquivos versionados gpt/conhecimento/*: toda chamada usa banco, CSV e
FONTE.md temporarios, e main() e chamado com BANCO/CSV_SAIDA/FONTE_SAIDA
redirecionados por monkeypatch ANTES de rodar — mesmo que o codigo tivesse um
defeito que o fizesse escrever fora do lugar certo, o redirecionamento
acontece primeiro.
"""
import contextlib, csv, io, os, sqlite3, sys, tempfile

# Importar modulo escreve .pyc ao lado dele. Bloqueamos antes de manipular
# sys.path e fazer os imports — mesmo padrao de teste_verificar_dados.py.
sys.dont_write_bytecode = True
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "plugins", "vote-melhor", "ferramentas"))
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))
import verificar_dados as vd
import exportar_gpt as eg

falhas = []

def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)


def linha_generica(prefixo, **overrides):
    """Um dict com um valor generico e identificavel para cada uma das 17
    colunas da lista de permissao, com os campos de `overrides` sobrescritos
    (inclusive campos que nao estao na lista, para simular coluna extra)."""
    v = {c: f"{prefixo}_{c}" for c in eg.COLUNAS}
    v.update(overrides)
    return v


def montar_banco(caminho, colunas, linhas):
    """Cria uma tabela `candidatura` com as `colunas` dadas, na ordem dada, e
    insere uma linha por dict em `linhas` (cada dict precisa ter todas as
    `colunas` como chave)."""
    cx = sqlite3.connect(caminho)
    defs = ", ".join(f'"{c}" TEXT' for c in colunas)
    cx.execute(f"CREATE TABLE candidatura ({defs})")
    marcadores = ", ".join("?" for _ in colunas)
    for v in linhas:
        cx.execute(f"INSERT INTO candidatura VALUES ({marcadores})",
                   [v[c] for c in colunas])
    cx.commit()
    cx.close()


def escrever_csv_manual(caminho, linhas):
    """Escreve um CSV com o cabecalho das 17 colunas permitidas, direto em
    disco, SEM passar por eg.exportar(). Simula o cenario que o portao da
    releitura existe para cobrir: um documento que so existe no ARQUIVO
    gravado (por exemplo por um erro de escrita ou de concatenacao de
    campos), nunca nos dados que estavam em memoria."""
    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(eg.COLUNAS)
        for v in linhas:
            w.writerow([v[c] for c in eg.COLUNAS])


def rodar_main_isolado(banco, csv_saida, fonte_saida):
    """Chama eg.main() com BANCO/CSV_SAIDA/FONTE_SAIDA redirecionados para
    caminhos temporarios, capturando stdout/stderr. O redirecionamento
    acontece ANTES da chamada e e desfeito depois, em `finally` — assim os
    arquivos reais do repositorio nunca sao tocados, mesmo que main() tenha
    um defeito que o fizesse escrever no lugar errado."""
    banco_orig, csv_orig, fonte_orig = eg.BANCO, eg.CSV_SAIDA, eg.FONTE_SAIDA
    eg.BANCO, eg.CSV_SAIDA, eg.FONTE_SAIDA = banco, csv_saida, fonte_saida
    saida_out, saida_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(saida_out), \
             contextlib.redirect_stderr(saida_err):
            codigo = eg.main()
    finally:
        eg.BANCO, eg.CSV_SAIDA, eg.FONTE_SAIDA = banco_orig, csv_orig, fonte_orig
    return codigo, saida_out.getvalue(), saida_err.getvalue()


# --- CONTROLE 1: lista de permissao fechada -------------------------------
print("CONTROLE 1 — lista de permissao fechada: coluna extra nao vaza")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "tse.sqlite")
    # A tabela tem as 17 colunas permitidas MAIS 2 que o TSE poderia
    # acrescentar sem avisar.
    colunas_tabela = eg.COLUNAS + ["campoNovoDoTse", "cpfCandidato"]
    linha = linha_generica("c1", id="1",
                            campoNovoDoTse="NAO_DEVE_APARECER_1",
                            cpfCandidato="NAO_DEVE_APARECER_2")
    montar_banco(banco, colunas_tabela, [linha])

    csv_saida = os.path.join(d, "saida.csv")
    total, ids = eg.exportar(banco, csv_saida)
    with open(csv_saida, encoding="utf-8") as fh:
        cabecalho = next(csv.reader(fh))
    conteudo = open(csv_saida, encoding="utf-8").read()

    checa("exportar() le a linha da tabela com colunas extras", total == 1,
          f"total={total}")
    checa("cabecalho do CSV tem exatamente as 17 colunas permitidas, na ordem",
          cabecalho == eg.COLUNAS, f"cabecalho={cabecalho}")
    checa("coluna fora da lista de permissao nao aparece em nenhuma celula",
          "NAO_DEVE_APARECER" not in conteudo,
          "vazou valor de coluna que nao esta na lista de permissao")

# --- CONTROLE 2: coluna que sumiu e detectada -----------------------------
print("CONTROLE 2 — coluna que sumiu e detectada, nao vira coluna vazia")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "tse.sqlite")
    colunas_tabela = [c for c in eg.COLUNAS if c != "fonte_url"]  # falta 1
    linha = {c: f"c2_{c}" for c in colunas_tabela}
    linha["id"] = "1"
    montar_banco(banco, colunas_tabela, [linha])

    cx = sqlite3.connect(banco)
    faltando = eg.colunas_faltando(cx)
    cx.close()
    checa("colunas_faltando() nomeia exatamente a coluna que sumiu",
          faltando == ["fonte_url"], f"faltando={faltando}")

    csv_temp = os.path.join(d, "saida.csv")
    fonte_temp = os.path.join(d, "FONTE.md")
    codigo, saida_out, saida_err = rodar_main_isolado(banco, csv_temp, fonte_temp)
    checa("main() recusa (codigo != 0) quando falta coluna da lista de permissao",
          codigo != 0, f"codigo={codigo}")
    checa("mensagem de recusa nomeia a coluna que falta",
          "fonte_url" in saida_err, f"stderr={saida_err!r}")
    checa("CSV nao foi escrito quando falta coluna",
          not os.path.exists(csv_temp),
          "arquivo apareceu mesmo com coluna faltando na tabela")

# --- CONTROLE 3: o portao da base recusa ----------------------------------
print("CONTROLE 3 — base com documento sintetico: recusa e NAO escreve o CSV")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "tse.sqlite")
    titulo = vd.montar_titulo_sintetico("00000031", "02")
    linha = linha_generica("c3", id="1",
                            nomeColigacao=f"documento {titulo} anotado")
    montar_banco(banco, eg.COLUNAS, [linha])

    csv_temp = os.path.join(d, "saida.csv")
    fonte_temp = os.path.join(d, "FONTE.md")
    codigo, saida_out, saida_err = rodar_main_isolado(banco, csv_temp, fonte_temp)
    checa("main() recusa (codigo != 0) com documento sintetico na base",
          codigo != 0, f"codigo={codigo}")
    checa("mensagem de recusa e RECUSADO (portao 1, antes de exportar())",
          "RECUSADO" in saida_err, f"stderr={saida_err!r}")
    checa("CSV nao foi escrito quando a base tem documento",
          not os.path.exists(csv_temp),
          "arquivo foi escrito mesmo com o portao da base ativo")

# --- CONTROLE 4: o portao da releitura recusa -----------------------------
# O mais importante: prova que a checagem le o ARQUIVO ESCRITO, nao a
# memoria. O CSV abaixo e montado a mao, sem nunca passar por eg.exportar() —
# simula um documento que so existe no disco, do jeito que um erro de
# achatamento/concatenacao na escrita poderia produzir.
print("CONTROLE 4 — releitura acha documento que so existe no ARQUIVO gravado")
with tempfile.TemporaryDirectory() as d:
    csv_temp = os.path.join(d, "saida.csv")
    titulo = vd.montar_titulo_sintetico("00000041", "03")
    linha_suja = linha_generica("c4", id="42",
                                 nomeColigacao=f"certidao anexo {titulo} tcu")
    escrever_csv_manual(csv_temp, [linha_suja])

    achados = eg.relatorio_pos_escrita(csv_temp, ids_por_linha=["42"])
    checa("acha o documento que so existe no arquivo escrito "
          "(nunca passou por eg.exportar())",
          len(achados) == 1, f"len(achados)={len(achados)}")
    if achados:
        checa("aponta a coluna certa", achados[0]["coluna"] == "nomeColigacao",
              f"coluna={achados[0]['coluna']}")
        checa("classifica como titulo de eleitor", achados[0]["tipo"] == "titulo",
              f"tipo={achados[0]['tipo']}")

    # Controle negativo no mesmo mecanismo: arquivo limpo nao dispara nada.
    csv_limpo = os.path.join(d, "limpo.csv")
    escrever_csv_manual(csv_limpo, [linha_generica("c4limpo", id="43")])
    achados_limpos = eg.relatorio_pos_escrita(csv_limpo, ids_por_linha=["43"])
    checa("arquivo sem documento nao dispara nada", not achados_limpos,
          f"achados_limpos={achados_limpos}")

# --- CONTROLE 5: a exclusao do id e estrutural, nao afrouxada -------------
# Par de controle: o MESMO valor sobrevive numa linha e e achado na outra —
# separa "exclusao correta" (por VALOR da linha) de "valvula de escape"
# (por exemplo excluir qualquer valor que apareca como id de QUALQUER linha
# do arquivo, nao so da propria linha).
print("CONTROLE 5 — exclusao do id e por VALOR da linha, nao valvula de escape geral")
with tempfile.TemporaryDirectory() as d:
    csv_temp = os.path.join(d, "saida.csv")
    titulo = vd.montar_titulo_sintetico("00000051", "04")
    linha_a = linha_generica("c5a", id=titulo)  # o proprio id "e" um titulo valido
    linha_b = linha_generica("c5b", id="7000099",
                              nomeColigacao=f"mesmo numero {titulo} em linha diferente")
    escrever_csv_manual(csv_temp, [linha_a, linha_b])

    achados = eg.relatorio_pos_escrita(csv_temp, ids_por_linha=[titulo, "7000099"])
    achados_a = [a for a in achados if a["id"] == titulo]
    achados_b = [a for a in achados if a["id"] == "7000099"]
    checa("valor igual ao PROPRIO id da linha sobrevive (nao e reportado)",
          not achados_a, f"len(achados_a)={len(achados_a)}")
    checa("o MESMO valor, numa linha cujo id e outro, E reportado",
          len(achados_b) == 1 and achados_b[0]["coluna"] == "nomeColigacao",
          f"achados_b={achados_b}")

# --- CONTROLE 6: o FONTE.md conta o que existe ----------------------------
print("CONTROLE 6 — FONTE.md conta o que existe na base (nao numero fixo)")
with tempfile.TemporaryDirectory() as d:
    banco = os.path.join(d, "tse.sqlite")
    # Quantidades escolhidas para nao coincidir por acaso com nenhum numero
    # da base real (que este teste nunca toca).
    combinacoes = [("AC", "Governador", 2), ("AC", "Senador", 1),
                   ("SP", "Governador", 3)]
    linhas = []
    i = 0
    for uf, cargo, qtd in combinacoes:
        for _ in range(qtd):
            i += 1
            linhas.append(linha_generica(
                f"c6-{i}", id=str(i), ufCandidatura=uf, cargo_nome=cargo,
                coletado_em=f"2026-09-0{1 + (i % 2)}T10:00:00-03:00"))
    montar_banco(banco, eg.COLUNAS, linhas)

    fonte_temp = os.path.join(d, "FONTE.md")
    eg.escrever_fonte(banco, fonte_temp, total=len(linhas))
    texto = open(fonte_temp, encoding="utf-8").read()

    checa("total bate com o numero de linhas da base",
          f"**Total de candidaturas:** {len(linhas)}" in texto,
          f"total esperado={len(linhas)}")
    checa("contagem por UF bate (AC = 2+1)", "| AC | 3 |" in texto,
          "linha '| AC | 3 |' nao encontrada em FONTE.md")
    checa("contagem por UF bate (SP = 3)", "| SP | 3 |" in texto,
          "linha '| SP | 3 |' nao encontrada em FONTE.md")
    checa("contagem por cargo bate (Governador = 2+3)", "| Governador | 5 |" in texto,
          "linha '| Governador | 5 |' nao encontrada em FONTE.md")
    checa("contagem por cargo bate (Senador = 1)", "| Senador | 1 |" in texto,
          "linha '| Senador | 1 |' nao encontrada em FONTE.md")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
