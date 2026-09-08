#!/usr/bin/env python3
"""Controles do carimbo de data da coleta (coletado_em / coleta.quando).

O DEFEITO que este arquivo cobre: coletar_alvo() e cmd_detalhe() carimbavam
coletado_em com agora() mesmo quando obter() devolvia do CACHE — o carimbo
dizia "agora" para um dado que podia ter horas (ou dias) de idade. Medido na
base real em 07/09/2026: as 20.005 linhas de candidatura carimbadas num
intervalo de 3 segundos, enquanto o arquivo bruto de origem tinha sido
escrito antes daquele intervalo. Uma data errada, aqui, nao e cosmetico: e
o proprio campo que existe para avisar que o dado envelhece (--frescor,
--idade, a ficha de consultar.py e o FONTE.md do exportador leem esta data).

A CORRECAO: obter() agora devolve (objeto, url, de_cache, quando_dado), e
quando_dado e SEMPRE o instante em que o TSE respondeu — agora() se veio da
rede, o mtime do arquivo de cache se veio do cache (ver comentario acima de
quando_arquivo() em coletar_tse.py, que justifica mtime sobre o nome do
arquivo). Este arquivo prova as duas metades: o carimbo novo (controles 1 e
2) e o reparo do que ja estava gravado errado (controle 3).

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
todo controle roda dentro de ambiente_isolado(), que redireciona
ct.RAIZ/ct.BANCO/ct.DIR_BRUTO para um diretorio temporario (tempfile) e
restaura os valores originais ao sair — mesmo padrao de monkeypatch usado em
testes/teste_exportar_gpt.py. Onde a rede entraria (ct.buscar), ela e
substituida por uma funcao falsa; no controle de cache, a funcao falsa
ESTOURA se for chamada, provando que aquele caminho nao foi a rede.
"""
import contextlib, io, json, os, sqlite3, sys, tempfile, time
from datetime import datetime

# Importar um modulo escreve .pyc ao lado dele. Bloqueamos antes de manipular
# sys.path e fazer os imports — mesmo padrao dos outros testes deste projeto.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
sys.argv = ["coletar_tse"]
import coletar_tse as ct

falhas = []
def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)


@contextlib.contextmanager
def ambiente_isolado():
    """RAIZ/BANCO/DIR_BRUTO apontando para um diretorio temporario, restaurados
    ao sair. Nunca a base real, nunca dados/bruto/ real."""
    with tempfile.TemporaryDirectory() as d:
        raiz_orig, banco_orig, bruto_orig = ct.RAIZ, ct.BANCO, ct.DIR_BRUTO
        ct.RAIZ = d
        ct.DIR_BRUTO = os.path.join(d, "dados", "bruto")
        ct.BANCO = os.path.join(d, "dados", "tse.sqlite")
        os.makedirs(ct.DIR_BRUTO, exist_ok=True)
        try:
            yield d
        finally:
            ct.RAIZ, ct.BANCO, ct.DIR_BRUTO = raiz_orig, banco_orig, bruto_orig


@contextlib.contextmanager
def sem_rede():
    """Troca ct.buscar por uma versao que ESTOURA se for chamada. Usado nos
    controles em que o cache deveria bastar — se a rede for tocada mesmo
    assim, o teste acusa em vez de mascarar o defeito com uma resposta
    falsa que pareceria dar certo."""
    original = ct.buscar
    def bomba(*a, **k):
        raise AssertionError("foi a rede: o cache deveria ter bastado")
    ct.buscar = bomba
    try:
        yield
    finally:
        ct.buscar = original


def escrever_cache(apelido, dia, conteudo, mtime):
    """Cria um arquivo no formato de caminho_cache() (<apelido>__<dia>.json),
    com mtime controlado — simula um arquivo escrito ha' horas ou dias."""
    caminho = os.path.join(ct.DIR_BRUTO, f"{apelido}__{dia}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f)
    os.utime(caminho, (mtime, mtime))
    return caminho


# --- CONTROLE 1 — dado vindo da REDE carimba a hora da RESPOSTA -------------
# Isto continuaria passando mesmo sem o bug de cache (o caminho de rede
# sempre usou agora() e sempre esteve certo): existe para proteger a NOVA
# assinatura de obter() — que quando_dado exista, venha na posicao certa, e
# corresponda ao INSTANTE DESTA CHAMADA quando nao ha cache.
print("CONTROLE 1 — dado vindo da rede carimba a hora da resposta")
with ambiente_isolado():
    ct.buscar = lambda caminho, pausa: (200, json.dumps({"ok": True}).encode("utf-8"))
    antes = time.time()
    dados, url, de_cache, quando = ct.obter("/caminho/qualquer", "apelido_rede", pausa=0)
    depois = time.time()

    checa("nao veio do cache", de_cache is False, f"de_cache={de_cache}")
    ts_quando = datetime.fromisoformat(quando).timestamp()
    checa("quando_dado cai dentro da janela desta chamada",
          antes - 1 <= ts_quando <= depois + 1,
          f"quando={quando}  janela=[{antes:.0f}, {depois:.0f}]")
    checa("o arquivo de cache foi escrito (proxima leitura pode usa-lo)",
          os.path.exists(os.path.join(ct.DIR_BRUTO, "apelido_rede__" +
                                       datetime.now().strftime("%Y-%m-%d") + ".json")),
          "arquivo de cache ausente apos fetch de rede")


# --- CONTROLE 2 — dado vindo do CACHE carimba a data do CACHE, nao a de agora
# Este e' o controle que PROVA o defeito relatado: um arquivo de cache
# escrito ha' 4 horas, lido agora. Com a funcao QUEBRADA (agora() tambem no
# caminho de cache), quando_dado seria "agora" — este controle reprovaria.
# Com a funcao corrigida, quando_dado tem que ser o mtime do arquivo. A
# demonstracao de que ele REALMENTE reprova a versao quebrada esta registrada
# no relatorio da tarefa (rodada a parte, contra uma copia revertida).
print("CONTROLE 2 — dado vindo do cache carimba a data do arquivo, nao a de agora")
with ambiente_isolado():
    dia_hoje = datetime.now().strftime("%Y-%m-%d")
    mtime_4h_atras = time.time() - 4 * 3600
    caminho = escrever_cache("listar_2026_MG_7", dia_hoje,
                             {"candidatos": []}, mtime_4h_atras)

    with sem_rede():
        dados, url, de_cache, quando = ct.obter(
            "/caminho/qualquer", "listar_2026_MG_7", pausa=0)

    correto = ct.quando_arquivo(caminho)
    agora_str = ct.agora()
    checa("veio do cache", de_cache is True, f"de_cache={de_cache}")
    checa("quando_dado bate com o mtime do arquivo de cache",
          quando == correto, f"quando={quando}  mtime_arquivo={correto}")
    checa("quando_dado NAO e 'agora' (o arquivo tem 4h de idade)",
          quando != agora_str, f"quando={quando}  agora={agora_str}")


# --- CONTROLE 3 — --reparar-datas corrige o que ja esta gravado, e e idempotente
# Reproduz o cenario medido na base real em miniatura: linhas de candidatura
# e uma entrada de coleta.quando carimbadas com "agora" (a hora da gravacao),
# enquanto o arquivo de cache correspondente foi escrito antes. Inclui uma
# linha ORFA (arquivo de cache ausente, como apos "sigilo total" apagar
# dados/bruto/) para provar que o reparo nunca adivinha: relata e pula.
print("CONTROLE 3 — reparar_datas corrige linhas erradas e e idempotente")
with ambiente_isolado():
    dia_hoje = datetime.now().strftime("%Y-%m-%d")
    mtime_6h_atras = time.time() - 6 * 3600
    caminho = escrever_cache("listar_2026_XX_3", dia_hoje,
                             {"candidatos": []}, mtime_6h_atras)
    correto_esperado = ct.quando_arquivo(caminho)
    carimbo_errado = ct.agora()  # o carimbo tipico do defeito: "agora" da gravacao

    cx0 = ct.abrir_banco()  # cria o banco e a tabela `coleta`
    cx0.close()
    cx = sqlite3.connect(ct.BANCO)
    cx.execute("""CREATE TABLE candidatura (id TEXT PRIMARY KEY, uf_consultada TEXT,
                  cargo_codigo TEXT, coletado_em TEXT)""")
    for i in range(3):
        cx.execute("INSERT INTO candidatura VALUES (?,?,?,?)",
                   (f"id{i}", "XX", "3", carimbo_errado))
    # linha ORFA: mesmo carimbo errado, mas sem arquivo de cache correspondente.
    cx.execute("INSERT INTO candidatura VALUES (?,?,?,?)",
               ("orfa", "ZZ", "9", carimbo_errado))
    cx.execute("INSERT INTO coleta VALUES (?,?,?,?,?)",
               (carimbo_errado, "listar XX cargo 3", "http://x", 3, 1))
    cx.commit(); cx.close()

    saida1 = io.StringIO()
    with contextlib.redirect_stdout(saida1):
        codigo1 = ct.reparar_datas(ct.BANCO, aplicar=True)

    cx = sqlite3.connect(ct.BANCO)
    valores_xx = [r[0] for r in cx.execute(
        "SELECT coletado_em FROM candidatura WHERE uf_consultada='XX'")]
    valor_log = cx.execute(
        "SELECT quando FROM coleta WHERE alvo='listar XX cargo 3'").fetchone()[0]
    valor_orfa = cx.execute(
        "SELECT coletado_em FROM candidatura WHERE id='orfa'").fetchone()[0]
    cx.close()

    checa("as 3 linhas de XX foram corrigidas para o mtime do arquivo",
          valores_xx == [correto_esperado] * 3, f"valores={valores_xx}")
    checa("coleta.quando tambem foi corrigido (--idade le esta coluna)",
          valor_log == correto_esperado, f"quando={valor_log}")
    checa("linha ORFA (sem arquivo) NAO foi tocada — nunca adivinhada",
          valor_orfa == carimbo_errado, f"valor_orfa={valor_orfa}")
    checa("reparo com pendencia (a orfa) sai != 0", codigo1 != 0,
          f"codigo={codigo1}")
    checa("relatorio mostra o antes e o depois, nao so o depois",
          carimbo_errado in saida1.getvalue() and correto_esperado in saida1.getvalue(),
          "relatorio nao imprimiu antes/depois")

    # idempotencia: repetir nao muda mais nada que ja esta certo, e continua
    # relatando (nao escondendo) a orfa que segue sem arquivo.
    saida2 = io.StringIO()
    with contextlib.redirect_stdout(saida2):
        codigo2 = ct.reparar_datas(ct.BANCO, aplicar=True)
    cx = sqlite3.connect(ct.BANCO)
    valores_xx_2 = [r[0] for r in cx.execute(
        "SELECT coletado_em FROM candidatura WHERE uf_consultada='XX'")]
    cx.close()

    checa("segunda rodada: linhas de XX continuam iguais (idempotente)",
          valores_xx_2 == valores_xx, f"valores2={valores_xx_2}")
    checa("segunda rodada: nao ha mais nada 'a corrigir' (grupo XX ja resolvido)",
          "XX_3" not in saida2.getvalue(),
          "grupo ja corrigido reaparecendo como pendente de correcao")
    checa("segunda rodada continua sinalizando a orfa pendente (nao esconde)",
          codigo2 != 0, f"codigo2={codigo2}")


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
