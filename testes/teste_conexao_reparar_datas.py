#!/usr/bin/env python3
"""Controles da conexao sqlite em reparar_datas() — a ultima da familia.

O DEFEITO: reparar_datas abre DUAS conexoes em sequencia (uma para escanear
e aplicar, outra para a reconferencia depois do commit) e fecha as duas com
`cx.close()` solto, em quatro pontos diferentes. Fecha em toda saida que os
autores enumeraram — e so nelas. As que sobram:

  * escanear_datas() estourando na PRIMEIRA conexao. Nao e' hipotetico: o
    primeiro SELECT dele le a tabela candidatura SEM guarda de tabela_existe
    (a guarda existe so para a tabela `detalhe`, logo abaixo). Numa base que
    ainda nao foi coletada a tabela nao existe, o SELECT levanta
    OperationalError, e a conexao fica aberta. Quem rodar --reparar-datas
    antes da primeira coleta cai exatamente ai.
  * o UPDATE estourando no meio do laco de aplicacao.
  * escanear_datas() estourando na SEGUNDA conexao, a da reconferencia — o
    caminho que so roda depois do commit, e por isso o menos exercitado.

reparar_datas nao toca a rede, entao aqui nao ha a metade de
FALHAS_DE_TRANSPORTE que os seis comandos receberam: o defeito e' so a
conexao, e a correcao e' so o finally.

Este arquivo mede a conexao. O COMPORTAMENTO de reparar_datas (o que ele
corrige, o que ele se recusa a adivinhar, e a idempotencia) ja e medido por
testes/teste_datas_coleta.py, CONTROLE 3 — que serve aqui de rede de
seguranca contra regressao, e continua tendo que passar.

O espiao e' posto em sqlite3.connect, e nao em ct.abrir_banco como nos
outros testes desta serie, porque reparar_datas recebe o CAMINHO do banco e
conecta direto — foi justamente por isso que ele escapou da varredura por
AST que conferiu os seis comandos.

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
tudo acontece em diretorio temporario, e reparar_datas nao abre socket.
"""
import contextlib, io, os, sqlite3, sys, tempfile

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
    """RAIZ/BANCO/DIR_BRUTO num diretorio temporario, restaurados ao sair."""
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
def espiar_conexoes():
    """O espiao vai em sqlite3.connect, nao em ct.abrir_banco: reparar_datas
    recebe o caminho do banco e conecta direto. Restaurado sempre, senao o
    proprio teste sairia com o modulo sqlite3 remendado."""
    criadas = []
    original = sqlite3.connect
    def espiao(*a, **k):
        cx = original(*a, **k)
        criadas.append(cx)
        return cx
    sqlite3.connect = espiao
    try:
        yield criadas
    finally:
        sqlite3.connect = original


def esta_fechada(cx):
    """Pergunta a propria conexao: fechada acusa sqlite3.ProgrammingError."""
    try:
        cx.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


def base_com_carimbo_errado(com_arquivo=True):
    """Reproduz o defeito de data em miniatura: linhas carimbadas com 'agora'
    e um arquivo de cache escrito antes. Mesma fixture de
    teste_datas_coleta.py CONTROLE 3, reduzida ao que a conexao precisa."""
    import json, time
    from datetime import datetime
    dia = datetime.now().strftime("%Y-%m-%d")
    carimbo_errado = ct.agora()
    if com_arquivo:
        caminho = os.path.join(ct.DIR_BRUTO, f"listar_{ct.ANO}_XX_3__{dia}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"candidatos": []}, f)
        antes = time.time() - 5 * 3600
        os.utime(caminho, (antes, antes))
    cx0 = ct.abrir_banco(); cx0.close()          # cria o banco e a tabela coleta
    cx = sqlite3.connect(ct.BANCO)
    try:
        cx.execute("""CREATE TABLE candidatura (id TEXT PRIMARY KEY,
                      uf_consultada TEXT, cargo_codigo TEXT, coletado_em TEXT)""")
        cx.execute("INSERT INTO candidatura VALUES ('id0','XX','3',?)",
                   (carimbo_errado,))
        cx.execute("INSERT INTO coleta VALUES (?,?,?,?,?)",
                   (carimbo_errado, "listar XX cargo 3", "http://x", 1, 1))
        cx.commit()
    finally:
        cx.close()


def base_vazia():
    """Banco recem-criado: tem a tabela coleta, nao tem candidatura. E' o
    estado de quem instalou e ainda nao coletou nada."""
    cx0 = ct.abrir_banco(); cx0.close()


def caso(rotulo, preparar, aplicar, espera_estouro=False, espera_codigo="qualquer",
         adulterar=None):
    with ambiente_isolado():
        preparar()
        restaurar = adulterar() if adulterar else None
        try:
            with espiar_conexoes() as conexoes:
                estourou, codigo = None, None
                saida = io.StringIO()
                try:
                    with contextlib.redirect_stdout(saida):
                        codigo = ct.reparar_datas(ct.BANCO, aplicar=aplicar)
                except BaseException as e:   # noqa: BLE001 — e' o defeito sob teste
                    estourou = e
        finally:
            if restaurar:
                restaurar()

        if espera_estouro:
            checa(f"{rotulo}: o defeito subiu (nao foi engolido)",
                  estourou is not None,
                  f"estourou={type(estourou).__name__ if estourou else None}")
        else:
            checa(f"{rotulo}: nao estourou", estourou is None,
                  "ok" if estourou is None
                  else f"subiu {type(estourou).__name__}: {estourou}")
        if espera_codigo != "qualquer" and estourou is None:
            checa(f"{rotulo}: codigo {espera_codigo}", codigo == espera_codigo,
                  f"codigo={codigo}")
        if not conexoes:
            checa(f"{rotulo}: abriu conexao", False, "nenhuma conexao aberta")
        else:
            abertas = [i for i, c in enumerate(conexoes) if not esta_fechada(c)]
            checa(f"{rotulo}: as {len(conexoes)} conexao(oes) fecharam",
                  not abertas,
                  "todas fechadas" if not abertas
                  else f"seguem abertas: indices {abertas}")


# --- caminhos normais — passam hoje, e existem para nao regredirem ----------
def base_ja_reparada():
    """Base montada e ja reparada: a chamada que o controle mede nao encontra
    nada para mudar. O relatorio da preparacao e' engolido para nao se
    misturar com a saida do proprio teste."""
    base_com_carimbo_errado()
    with contextlib.redirect_stdout(io.StringIO()):
        ct.reparar_datas(ct.BANCO, aplicar=True)

print("reparar_datas — caminhos que ja fechavam")
caso("nada a corrigir", base_ja_reparada, aplicar=True, espera_codigo=0)
caso("ha o que corrigir, sem --aplicar", base_com_carimbo_errado, aplicar=False,
     espera_codigo=2)
caso("ha o que corrigir, com --aplicar", base_com_carimbo_errado, aplicar=True,
     espera_codigo=0)

# --- o vazamento real: base nunca coletada ----------------------------------
# O primeiro SELECT de escanear_datas le candidatura sem guarda. Numa base
# recem-criada a tabela nao existe. Isto e' o que acontece com quem roda
# --reparar-datas antes da primeira coleta.
print("reparar_datas — base nunca coletada (candidatura nao existe)")
caso("SELECT estoura na primeira conexao", base_vazia, aplicar=False,
     espera_estouro=True)


# --- o UPDATE estourando no meio da aplicacao -------------------------------
# escanear_datas devolve um grupo apontando para uma tabela que nao existe.
# O laco de UPDATE estoura, depois do escaneamento e antes do commit.
print("reparar_datas — UPDATE estourando no meio da aplicacao")
def grupo_com_tabela_inexistente():
    original = ct.escanear_datas
    def falso(cx):
        return ([{"tabela": "tabela_que_nao_existe", "apelido": "x",
                  "where_sql": "id = ?", "where_val": ("1",), "n": 1,
                  "atual": "a", "correto": "b"}], [], [])
    ct.escanear_datas = falso
    return lambda: setattr(ct, "escanear_datas", original)

caso("UPDATE em tabela inexistente", base_com_carimbo_errado, aplicar=True,
     espera_estouro=True, adulterar=grupo_com_tabela_inexistente)


# --- a SEGUNDA conexao, a da reconferencia ----------------------------------
# So roda depois do commit, entao e' o caminho menos exercitado do arquivo.
# O escaneamento estoura na segunda chamada, nao na primeira.
print("reparar_datas — defeito na reconferencia (segunda conexao)")
def quebrar_so_a_reconferencia():
    original = ct.escanear_datas
    chamadas = []
    def falso(cx):
        chamadas.append(1)
        if len(chamadas) >= 2:
            raise KeyError("esquema mudou")
        return original(cx)
    ct.escanear_datas = falso
    return lambda: setattr(ct, "escanear_datas", original)

caso("reconferencia estoura", base_com_carimbo_errado, aplicar=True,
     espera_estouro=True, adulterar=quebrar_so_a_reconferencia)


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
