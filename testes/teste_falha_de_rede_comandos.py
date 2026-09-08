#!/usr/bin/env python3
"""Controles dos quatro comandos restantes: --detalhe, --idade, --frescor, --plano.

Fecha a mesma dupla de defeitos que 08/09/2026 fechou em cmd_pais e
cmd_listar, nos quatro comandos que sobraram. Nao e' repeticao por zelo: o
defeito estava em todos, cada um com uma variacao propria.

DEFEITO 1 — a conexao sqlite so fechava nos caminhos que alguem lembrou.
As variacoes, medidas antes de corrigir:
  * cmd_detalhe  — o `except BloqueioTSE` faz sys.exit(2) SEM fechar. Aqui
    nem o caminho tratado fechava, ao contrario de cmd_listar, que fechava.
  * cmd_idade    — tres `cx.close(); return` espalhados. Fecha em toda saida
    que existe hoje; quebra na proxima que alguem acrescentar sem lembrar.
  * cmd_frescor  — dois cx.execute() ANTES do try. Numa base recem-criada nao
    existe tabela candidatura, o SELECT levantava OperationalError e a
    conexao ficava aberta.
  * cmd_plano    — abre conexao em DOIS ramos (inventario e extracao), cada
    um com o SELECT desprotegido, mesma historia do frescor.

Os cenarios de base recem-criada acima DEIXARAM de estourar depois que os
comandos ganharam a guarda base_nao_coletada(): --frescor e --plano <id>
degradam (entregam o que da' para entregar), --plano <UF> recusa com
AVISO_SEM_BASE. Os controles ficaram, com a expectativa trocada — o que eles
medem aqui e' a CONEXAO, e essa exigencia nao mudou. Quem guarda o
"estourou e fechou" e' a secao NEGATIVO, no fim.

DEFEITO 2 — os tres que tocam a rede (detalhe, frescor, plano) capturavam so
BloqueioTSE. Falha de transporte respondia traceback, como cmd_listar
respondia antes. Passam a usar o mesmo FALHAS_DE_TRANSPORTE e o mesmo
descrever_falha() dos outros dois comandos.

O CONTROLE QUE VALE MAIS e' o negativo (secao NEGATIVO, no fim): defeito de
codigo tem que continuar subindo em todos os quatro. Um `except Exception`
faria todo o resto deste arquivo passar e so ele reprovar.

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
ambiente_isolado() redireciona ct.RAIZ/ct.BANCO/ct.DIR_BRUTO para um
diretorio temporario, e ct.buscar / ct.baixar_cdn — os unicos pontos do
modulo que abrem socket — sao substituidos. Mesmo padrao de
testes/teste_falha_de_rede_listar.py e testes/teste_datas_coleta.py.
"""
import contextlib, io, json, os, socket, sqlite3, sys, tempfile, zipfile
from datetime import datetime, timedelta

# Importar um modulo escreve .pyc ao lado dele. Bloqueamos antes de manipular
# sys.path e fazer os imports — mesmo padrao dos outros testes deste projeto.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugins", "vote-melhor", "ferramentas"))
sys.argv = ["coletar_tse"]
import coletar_tse as ct

# Id de candidato de mentira, com codificacao propria para se denunciar como
# falso: os digitos sao pares que dao a posicao da letra no alfabeto —
# 06-01-12-19-15 = F-A-L-S-O. Quem bater o olho e decodificar le "FALSO".
#
# O formato obedece a tres amarras, e nenhuma e' cosmetica:
#   1. SO DIGITOS — cmd_plano acha o PDF no pacote por `re.search(rf"{ANO}
#      {uf_pacote}(\d+)_", nome)`. Texto nao casa, e a extracao nao acharia
#      nada.
#   2. MAIS DE 3 CARACTERES — cmd_plano decide se o argumento e' UF ou id por
#      `len(str(alvo)) <= 3`. Id curto seria lido como UF, e o comando iria
#      procurar um pacote proposta_governo_<ano>_<id>.zip que nao existe.
#   3. NEM 11 NEM 12 DIGITOS — sao os comprimentos de CPF e de titulo de
#      eleitor. O id REAL do TSE tem 12, e era esse o problema: um numero de
#      12 digitos num repositorio publico parece documento de gente, mesmo
#      sendo inventado, e obriga quem le a ir conferir digito verificador
#      para se tranquilizar. Aqui sao 10, e nao parece nada.
#
# O controle logo abaixo nao deixa isto voltar a ser um numero com cara de
# documento. Ele existe porque comentario lembra e portao recusa.
ID_CAND = "0601121915"

falhas = []
def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)

print("FIXTURE — o id de mentira nao pode parecer documento de gente")
checa("nem 11 nem 12 digitos (CPF e titulo de eleitor)",
      len(ID_CAND) not in (11, 12), f"len={len(ID_CAND)}")
checa("so digitos (a regex de cmd_plano exige)", ID_CAND.isdigit(), ID_CAND)
checa("mais de 3 caracteres (senao cmd_plano le como UF)",
      len(ID_CAND) > 3, f"len={len(ID_CAND)}")
checa("nao valida como CPF", ct.vd.cpf_valido(ID_CAND) is False, ID_CAND)
checa("nao valida como titulo de eleitor",
      ct.vd.titulo_valido(ID_CAND) is False, ID_CAND)
checa("decodifica para FALSO (a codificacao esta documentada acima)",
      "".join(chr(64 + int(ID_CAND[i:i+2])) for i in range(0, len(ID_CAND), 2))
      == "FALSO", ID_CAND)



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
def rede_falsa(acao=None):
    """Substitui ct.buscar E ct.baixar_cdn. `acao` e' None (responde bem),
    uma Exception (levanta) ou bytes (devolve como corpo)."""
    buscar_orig, cdn_orig = ct.buscar, ct.baixar_cdn
    def falso(caminho, pausa):
        if isinstance(acao, BaseException):
            raise acao
        if isinstance(acao, bytes):
            return 200, acao
        corpo = json.dumps({"id": ID_CAND, "nomeUrna": "FULANO",
                            "nomeCompleto": "FULANO DE TAL",
                            "descricaoSituacao": "DEFERIDO",
                            "cargo": {"nome": "DEPUTADO FEDERAL"}})
        return 200, corpo.encode("utf-8")
    def falso_cdn(caminho, pausa=1.5):
        if isinstance(acao, BaseException):
            raise acao
        return b"nao deveria ser usado"
    ct.buscar, ct.baixar_cdn = falso, falso_cdn
    try:
        yield
    finally:
        ct.buscar, ct.baixar_cdn = buscar_orig, cdn_orig


@contextlib.contextmanager
def espiar_banco():
    """Guarda as conexoes que o comando abriu, para dar para perguntar depois
    se foram fechadas."""
    criadas = []
    original = ct.abrir_banco
    def espiao():
        cx = original()
        criadas.append(cx)
        return cx
    ct.abrir_banco = espiao
    try:
        yield criadas
    finally:
        ct.abrir_banco = original


def esta_fechada(cx):
    """Pergunta a propria conexao: fechada acusa sqlite3.ProgrammingError."""
    try:
        cx.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


def criar_candidatura():
    """Tabela candidatura com as colunas que os quatro comandos consultam."""
    cx = sqlite3.connect(ct.BANCO)
    try:
        cx.execute("""CREATE TABLE IF NOT EXISTS candidatura (
            id TEXT PRIMARY KEY, nomeUrna TEXT, descricaoSituacao TEXT,
            cargo_nome TEXT, partido_sigla TEXT, numero TEXT)""")
        cx.execute("INSERT OR REPLACE INTO candidatura VALUES "
                   "(?,'FULANO','DEFERIDO','Governador','PX','13')", (ID_CAND,))
        cx.commit()
    finally:
        cx.close()


def registrar_coleta(dias_atras):
    """Uma linha em coleta com alvo 'listar...', que e' o que cmd_idade le."""
    quando = (datetime.now().astimezone()
              .replace(microsecond=0) - timedelta(days=dias_atras)).isoformat()
    cx = sqlite3.connect(ct.BANCO)
    try:
        cx.execute("""CREATE TABLE IF NOT EXISTS coleta (
            quando TEXT, alvo TEXT, url TEXT, itens INTEGER, de_cache INTEGER)""")
        cx.execute("INSERT INTO coleta VALUES (?,?,?,?,?)",
                   (quando, "listar MG cargo 6", "http://x", 1, 0))
        cx.commit()
    finally:
        cx.close()


def criar_zip_planos(uf="MG", ident=ID_CAND):
    """Pacote de planos no formato que cmd_plano espera achar em DIR_BRUTO."""
    os.makedirs(ct.DIR_BRUTO, exist_ok=True)
    caminho = os.path.join(ct.DIR_BRUTO, f"proposta_governo_{ct.ANO}_{uf}.zip")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(f"{ct.ANO}{uf}{ident}_proposta.pdf", b"%PDF-1.4 falso")
    return caminho


def rodar(chamada):
    """Executa engolindo stdout/stderr. Devolve (codigo, saida, erro).
    So SystemExit e' capturado: defeito de codigo TEM que atravessar."""
    saida, erro = io.StringIO(), io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = chamada()
        except SystemExit as e:
            codigo = e.code
    return codigo, saida.getvalue(), erro.getvalue()


def caso(rotulo, preparar, acao_rede, chamada, espera_estouro=False,
         espera_codigo="qualquer", espera_erro_stderr=False):
    """Roda um caminho de saida de um comando e responde as tres perguntas:
    a conexao fechou, o estouro aconteceu (ou nao), e o codigo/mensagem
    saiu como devia."""
    with ambiente_isolado():
        preparar()
        with espiar_banco() as conexoes, rede_falsa(acao_rede):
            estourou = None
            codigo, saida, err = None, "", ""
            try:
                codigo, saida, err = rodar(chamada)
            except BaseException as e:      # noqa: BLE001 — e' o defeito sob teste
                estourou = e

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
        if espera_erro_stderr and estourou is None:
            checa(f"{rotulo}: ERRO legivel no stderr, com a razao",
                  err.strip().startswith("ERRO:") and len(err.strip()) > 8,
                  f"stderr={err.strip()[:75]!r}")

        if not conexoes:
            checa(f"{rotulo}: abriu conexao", False, "nenhuma conexao aberta")
        else:
            todas = all(esta_fechada(c) for c in conexoes)
            checa(f"{rotulo}: conexao fechada ({len(conexoes)} aberta(s))", todas,
                  "todas fechadas" if todas else "ALGUMA SEGUE ABERTA")


nada = lambda: None
TIMEOUT = TimeoutError("timed out")
DNS = socket.gaierror(8, "nodename nor servname provided, or not known")

# --- cmd_detalhe -------------------------------------------------------------
print("cmd_detalhe")
caso("caminho feliz", nada, None,
     lambda: ct.cmd_detalhe(ID_CAND, "MG", pausa=0, forcar=True))
caso("falha de transporte", nada, DNS,
     lambda: ct.cmd_detalhe(ID_CAND, "MG", pausa=0, forcar=True),
     espera_codigo=2, espera_erro_stderr=True)
caso("403 do Akamai", nada, ct.BloqueioTSE("o TSE bloqueou"),
     lambda: ct.cmd_detalhe(ID_CAND, "MG", pausa=0, forcar=True),
     espera_codigo=2, espera_erro_stderr=True)

# --- cmd_idade ---------------------------------------------------------------
print("cmd_idade")
caso("base nunca coletada", nada, None, lambda: ct.cmd_idade(), espera_codigo=2)
caso("base fresca", lambda: registrar_coleta(1), None,
     lambda: ct.cmd_idade(), espera_codigo=0)
caso("base velha", lambda: registrar_coleta(30), None,
     lambda: ct.cmd_idade(), espera_codigo=2)

# --- cmd_frescor -------------------------------------------------------------
print("cmd_frescor")
caso("caminho feliz", lambda: (criar_candidatura(), registrar_coleta(1)), None,
     lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0), espera_codigo=0)
caso("falha de transporte", lambda: (criar_candidatura(), registrar_coleta(1)),
     TIMEOUT, lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0),
     espera_codigo=2, espera_erro_stderr=True)
# Base recem-criada: era aqui que o SELECT de fora do try estourava. Hoje o
# comando degrada — mostra so a consulta da hora, que e' o dado que ele
# existe para dar — e a conexao continua tendo que fechar.
caso("base nunca coletada: degrada em vez de estourar", nada, None,
     lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0), espera_codigo=0)

# --- cmd_plano ---------------------------------------------------------------
print("cmd_plano")
caso("inventario da UF", lambda: (criar_candidatura(), criar_zip_planos()), None,
     lambda: ct.cmd_plano("MG", "MG", pausa=0), espera_codigo=0)
caso("inventario sem base: recusa em vez de estourar", lambda: criar_zip_planos(),
     None, lambda: ct.cmd_plano("MG", "MG", pausa=0), espera_codigo=2)
caso("extracao do PDF de um candidato",
     lambda: (criar_candidatura(), criar_zip_planos()), None,
     lambda: ct.cmd_plano(ID_CAND, "MG", pausa=0))
caso("extracao sem base: extrai o PDF assim mesmo", lambda: criar_zip_planos(),
     None, lambda: ct.cmd_plano(ID_CAND, "MG", pausa=0), espera_codigo=0)

# O download do pacote acontece antes de qualquer conexao existir, entao aqui
# nao ha vazamento a medir — o que se mede e' a outra metade: transporte tem
# que virar mensagem, nao traceback.
# A base COLETADA aqui nao e' decoracao: sem ela a guarda base_nao_coletada()
# recusa antes do download, e este controle mediria o caminho errado —
# passaria com codigo 2 sem nunca tocar a rede.
print("cmd_plano — download do pacote")
with ambiente_isolado():
    criar_candidatura()
    with rede_falsa(DNS):
        estourou = None
        try:
            codigo, saida, err = rodar(lambda: ct.cmd_plano("MG", "MG", pausa=0))
        except BaseException as e:          # noqa: BLE001 — e' o defeito sob teste
            estourou, codigo, err = e, None, ""
    checa("download com DNS quebrado nao vira traceback", estourou is None,
          "ok" if estourou is None else f"subiu {type(estourou).__name__}")
    if estourou is None:
        checa("sai com codigo 2 e ERRO legivel", codigo == 2 and "ERRO:" in err,
              f"codigo={codigo} stderr={err.strip()[:70]!r}")


# --- NEGATIVO — defeito de codigo tem que continuar subindo nos quatro -------
# Vale mais que tudo acima: um `except Exception` em qualquer um dos quatro
# faria todo o resto deste arquivo passar e so esta secao reprovar.
print("NEGATIVO — defeito de codigo AINDA estoura nos quatro comandos")
DEFEITO = KeyError("cargo")

def quebrar_idade_da_base():
    """cmd_idade nao toca a rede, entao o defeito tem que nascer no unico
    lugar que ele chama: idade_da_base()."""
    def bomba(cx):
        raise DEFEITO
    ct.idade_da_base = bomba

original_idade = ct.idade_da_base
caso("cmd_detalhe: KeyError sobe", nada, DEFEITO,
     lambda: ct.cmd_detalhe(ID_CAND, "MG", pausa=0, forcar=True), espera_estouro=True)
caso("cmd_frescor: KeyError sobe", lambda: (criar_candidatura(), registrar_coleta(1)),
     DEFEITO, lambda: ct.cmd_frescor(ID_CAND, "MG", pausa=0), espera_estouro=True)
try:
    caso("cmd_idade: KeyError sobe",
         lambda: (registrar_coleta(1), quebrar_idade_da_base()), None,
         lambda: ct.cmd_idade(), espera_estouro=True)
finally:
    ct.idade_da_base = original_idade
# cmd_plano: o defeito vem do zip corrompido, que nao e' falha de transporte
# nenhuma — e' arquivo local ilegivel, e tem que subir.
def zip_corrompido():
    criar_candidatura()
    os.makedirs(ct.DIR_BRUTO, exist_ok=True)
    with open(os.path.join(ct.DIR_BRUTO,
                           f"proposta_governo_{ct.ANO}_MG.zip"), "wb") as f:
        f.write(b"isto nao e um zip")
with ambiente_isolado():
    zip_corrompido()
    with espiar_banco(), rede_falsa(None):
        estourou = None
        try:
            rodar(lambda: ct.cmd_plano("MG", "MG", pausa=0))
        except BaseException as e:          # noqa: BLE001 — e' o comportamento exigido
            estourou = e
    checa("cmd_plano: zip ilegivel sobe (nao vira 'falha de rede')",
          estourou is not None and isinstance(estourou, zipfile.BadZipFile),
          f"estourou={type(estourou).__name__ if estourou else None}")


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
