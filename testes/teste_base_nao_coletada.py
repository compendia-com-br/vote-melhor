#!/usr/bin/env python3
"""Controles do que os comandos fazem numa base que nunca foi coletada.

O DEFEITO: --reparar-datas, --frescor e --plano leem a tabela candidatura
sem perguntar se ela existe. Numa instalacao nova ela nao existe — quem cria
e' a primeira gravacao, nao abrir_banco(), que cria so `coleta`. Resultado
medido em 08/09/2026: os tres respondiam traceback de sqlite3, e o
--reparar-datas falhava ainda antes, no proprio sqlite3.connect ("unable to
open database file"), porque sqlite3.connect nao cria o diretorio pai como
abrir_banco cria. Traceback nao e' resposta: quem acabou de instalar nao tem
como saber que a resposta certa era "rode --listar primeiro".

O modelo e' o --idade, que ja fazia certo desde antes: imprime
AVISO_SEM_BASE e devolve 2. A mensagem agora mora num lugar so, e os quatro
comandos apontam para ela.

A CORRECAO NAO E' UNIFORME, e a diferenca e' de proposito. Recusar por
igual apagaria funcao que ja existe:

  RECUSAM (o comando nao tem o que fazer sem base):
    * reparar_datas — nao ha carimbo para reparar.
    * --plano <UF> — a saida INTEIRA e' o cruzamento do pacote com a tabela
      candidatura. Recusa ANTES de baixar o pacote: baixar para depois nao
      ter o que cruzar gasta uma requisicao ao CDN do TSE a toa.

  DEGRADAM (o codigo ja tinha o caminho, e ele entrega valor):
    * --frescor — `if base is None` ja existia e mostra so a consulta da
      hora, que e' justamente o dado mais volatil e o motivo do comando.
      Sem base ele passa a cair ali, dizendo QUAL das duas coisas houve:
      "a base nunca foi coletada" e' fato diferente de "este id nao esta na
      base", e quem le precisa saber qual dos dois.
    * --plano <id> — a extracao do PDF nao depende da tabela; ela so serve
      para mostrar o nome no lugar do id. Continua extraindo.

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
tudo em diretorio temporario, com ct.buscar e ct.baixar_cdn substituidos.
"""
import contextlib, io, json, os, sqlite3, sys, tempfile, zipfile

# Importar um modulo escreve .pyc ao lado dele. Bloqueamos antes de manipular
# sys.path e fazer os imports — mesmo padrao dos outros testes deste projeto.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
sys.argv = ["coletar_tse"]
import coletar_tse as ct

ID_CAND = "280001606090"

falhas = []
def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)


@contextlib.contextmanager
def ambiente_isolado(criar_pasta=True):
    """RAIZ/BANCO/DIR_BRUTO num diretorio temporario. Com criar_pasta=False
    nem a pasta dados/ existe — que e' o estado de quem so instalou."""
    with tempfile.TemporaryDirectory() as d:
        orig = (ct.RAIZ, ct.BANCO, ct.DIR_BRUTO)
        ct.RAIZ = d
        ct.DIR_BRUTO = os.path.join(d, "dados", "bruto")
        ct.BANCO = os.path.join(d, "dados", "tse.sqlite")
        if criar_pasta:
            os.makedirs(ct.DIR_BRUTO, exist_ok=True)
        try:
            yield d
        finally:
            ct.RAIZ, ct.BANCO, ct.DIR_BRUTO = orig


@contextlib.contextmanager
def rede_falsa(corpo_cdn=b"pacote falso"):
    """Substitui ct.buscar e ct.baixar_cdn. baixar_cdn conta as chamadas:
    e' o que prova que a recusa do inventario acontece ANTES do download."""
    buscar_orig, cdn_orig = ct.buscar, ct.baixar_cdn
    chamadas_cdn = []
    def falso(caminho, pausa):
        corpo = json.dumps({"id": ID_CAND, "nomeUrna": "FULANO",
                            "descricaoSituacao": "INDEFERIDO",
                            "cargo": {"nome": "Governador"}})
        return 200, corpo.encode("utf-8")
    def falso_cdn(caminho, pausa=1.5):
        chamadas_cdn.append(caminho)
        return corpo_cdn
    ct.buscar, ct.baixar_cdn = falso, falso_cdn
    try:
        yield chamadas_cdn
    finally:
        ct.buscar, ct.baixar_cdn = buscar_orig, cdn_orig


@contextlib.contextmanager
def espiar_conexoes():
    """As conexoes abertas, para provar que a guarda nova nao reintroduz o
    vazamento que o commit anterior fechou."""
    criadas = []
    # Basta espiar sqlite3.connect: abrir_banco() passa por ele.
    orig_connect = sqlite3.connect
    def espiao(*a, **k):
        cx = orig_connect(*a, **k); criadas.append(cx); return cx
    sqlite3.connect = espiao
    try:
        yield criadas
    finally:
        sqlite3.connect = orig_connect


def esta_fechada(cx):
    try:
        cx.execute("SELECT 1"); return False
    except sqlite3.ProgrammingError:
        return True


def base_coletada():
    """Base com a tabela candidatura ja criada — o estado normal."""
    cx0 = ct.abrir_banco(); cx0.close()
    cx = sqlite3.connect(ct.BANCO)
    try:
        cx.execute("""CREATE TABLE candidatura (id TEXT PRIMARY KEY, nomeUrna TEXT,
            descricaoSituacao TEXT, cargo_nome TEXT, partido_sigla TEXT,
            numero TEXT, uf_consultada TEXT, cargo_codigo TEXT, coletado_em TEXT)""")
        cx.execute("INSERT INTO candidatura (id,nomeUrna,descricaoSituacao,cargo_nome,"
                   "partido_sigla,numero,uf_consultada,cargo_codigo,coletado_em) "
                   "VALUES (?,'FULANO','DEFERIDO','Governador','PX','13','MG','3',?)",
                   (ID_CAND, ct.agora()))
        cx.commit()
    finally:
        cx.close()


def base_so_instalada():
    """abrir_banco cria o arquivo e a tabela `coleta` — e nada mais. E' o
    estado de quem instalou e nunca rodou --listar."""
    cx0 = ct.abrir_banco(); cx0.close()


def criar_zip():
    os.makedirs(ct.DIR_BRUTO, exist_ok=True)
    caminho = os.path.join(ct.DIR_BRUTO, f"proposta_governo_{ct.ANO}_MG.zip")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(f"{ct.ANO}MG{ID_CAND}_proposta.pdf", b"%PDF-1.4 falso")
    return caminho


def rodar(chamada):
    saida, erro = io.StringIO(), io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = chamada()
        except SystemExit as e:
            codigo = e.code
    return codigo, saida.getvalue(), erro.getvalue()


# --- 1. reparar_datas — RECUSA ----------------------------------------------
print("reparar_datas — recusa, porque nao ha carimbo para reparar")
for rotulo, criar_pasta, preparar in [
        ("sem a pasta dados/ (instalacao nova)", False, lambda: None),
        ("com o banco, sem tabela candidatura", True, base_so_instalada)]:
    with ambiente_isolado(criar_pasta=criar_pasta):
        preparar()
        with espiar_conexoes() as conexoes:
            estourou = None
            codigo, saida = None, ""
            try:
                codigo, saida, _ = rodar(lambda: ct.reparar_datas(ct.BANCO, aplicar=False))
            except BaseException as e:      # noqa: BLE001 — e' o defeito sob teste
                estourou = e
        checa(f"{rotulo}: nao estoura", estourou is None,
              "ok" if estourou is None else f"subiu {type(estourou).__name__}: {estourou}")
        if estourou is None:
            checa(f"{rotulo}: diz que a base nao foi coletada",
                  ct.AVISO_SEM_BASE.splitlines()[0] in saida, repr(saida.strip()[:80]))
            checa(f"{rotulo}: codigo 2 (nao 0 — nao olhou, nao e' 'nada a mudar')",
                  codigo == 2, f"codigo={codigo}")
        abertas = [i for i, c in enumerate(conexoes) if not esta_fechada(c)]
        checa(f"{rotulo}: nenhuma conexao ficou aberta", not abertas,
              f"abertas={abertas}")

with ambiente_isolado():
    base_coletada()
    codigo, saida, _ = rodar(lambda: ct.reparar_datas(ct.BANCO, aplicar=False))
    checa("base coletada: a guarda NAO dispara",
          ct.AVISO_SEM_BASE.splitlines()[0] not in saida, repr(saida.strip()[:70]))


# --- 2. cmd_frescor — DEGRADA -----------------------------------------------
# O comando existe para mostrar a situacao DA HORA. Sem base ele ainda pode
# fazer isso — e faz, pelo caminho `base is None` que ja existia.
print("cmd_frescor — degrada: mostra a consulta da hora, sem a comparacao")
with ambiente_isolado():
    base_so_instalada()
    with rede_falsa():
        estourou = None
        codigo, saida = None, ""
        try:
            codigo, saida, _ = rodar(lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0))
        except BaseException as e:          # noqa: BLE001 — e' o defeito sob teste
            estourou = e
    checa("nao estoura", estourou is None,
          "ok" if estourou is None else f"subiu {type(estourou).__name__}: {estourou}")
    if estourou is None:
        checa("mostrou a situacao da hora, que e o dado que ele existe para dar",
              "INDEFERIDO" in saida, repr([l for l in saida.splitlines() if "agora" in l]))
        checa("diz que a BASE nunca foi coletada",
              "foi coletada" in saida,
              repr([l for l in saida.splitlines() if "base" in l.lower()][:2]))
        checa("NAO diz 'este id nao esta na base' — e outro fato",
              "Este id nao esta na base local" not in saida,
              "mensagem de id ausente usada no lugar da de base ausente")
        checa("codigo 0 (entregou o que podia entregar)", codigo == 0, f"codigo={codigo}")

with ambiente_isolado():
    base_coletada()
    with rede_falsa():
        codigo, saida, _ = rodar(lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0))
    checa("base coletada: comparacao normal, com as duas linhas",
          "base   (" in saida and "agora  (" in saida and "DIVERGEM" in saida,
          repr([l for l in saida.splitlines() if "(" in l][:3]))


# --- 3. cmd_plano <UF> — RECUSA, e antes de baixar --------------------------
print("cmd_plano <UF> — recusa, e sem gastar o download")
with ambiente_isolado():
    base_so_instalada()
    with rede_falsa() as chamadas_cdn:
        estourou = None
        codigo, saida = None, ""
        try:
            codigo, saida, _ = rodar(lambda: ct.cmd_plano("MG", "MG", pausa=0))
        except BaseException as e:          # noqa: BLE001 — e' o defeito sob teste
            estourou = e
    checa("nao estoura", estourou is None,
          "ok" if estourou is None else f"subiu {type(estourou).__name__}: {estourou}")
    if estourou is None:
        checa("diz que a base nao foi coletada",
              ct.AVISO_SEM_BASE.splitlines()[0] in saida, repr(saida.strip()[:80]))
        checa("codigo 2", codigo == 2, f"codigo={codigo}")
    checa("NAO baixou o pacote do CDN (recusa antes do download)",
          chamadas_cdn == [], f"chamadas ao CDN={chamadas_cdn}")

with ambiente_isolado():
    base_coletada(); criar_zip()
    with rede_falsa():
        codigo, saida, _ = rodar(lambda: ct.cmd_plano("MG", "MG", pausa=0))
    checa("base coletada: inventario normal", codigo == 0 and "FULANO" in saida,
          f"codigo={codigo}")


# --- 4. cmd_plano <id> — DEGRADA --------------------------------------------
# A extracao do PDF nao depende da tabela: ela so da o nome no lugar do id.
print("cmd_plano <id> — degrada: extrai o PDF assim mesmo")
with ambiente_isolado():
    base_so_instalada(); criar_zip()
    with rede_falsa():
        estourou = None
        codigo, saida = None, ""
        try:
            codigo, saida, _ = rodar(lambda: ct.cmd_plano(ID_CAND, "MG", pausa=0))
        except BaseException as e:          # noqa: BLE001 — e' o defeito sob teste
            estourou = e
    checa("nao estoura", estourou is None,
          "ok" if estourou is None else f"subiu {type(estourou).__name__}: {estourou}")
    if estourou is None:
        checa("extraiu o PDF mesmo sem base", "arquivo:" in saida,
              repr([l for l in saida.splitlines() if "arquivo" in l]))
        checa("mostrou o id no lugar do nome", ID_CAND in saida, "id ausente da saida")
        checa("explica por que nao mostra o nome",
              "foi coletada" in saida,
              repr([l for l in saida.splitlines() if "coletada" in l]))
        checa("codigo 0 (o PDF saiu)", codigo == 0, f"codigo={codigo}")


# --- 5. a mensagem mora num lugar so ----------------------------------------
print("AVISO_SEM_BASE — uma fonte, quatro comandos")
with ambiente_isolado():
    base_so_instalada()
    codigo_idade, saida_idade, _ = rodar(lambda: ct.cmd_idade())
checa("--idade usa a mesma constante que os outros",
      ct.AVISO_SEM_BASE.splitlines()[0] in saida_idade, repr(saida_idade.strip()[:80]))
checa("a constante diz o que fazer, nao so o que faltou",
      "--listar" in ct.AVISO_SEM_BASE, repr(ct.AVISO_SEM_BASE))


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
