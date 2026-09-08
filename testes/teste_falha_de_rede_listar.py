#!/usr/bin/env python3
"""Controles de cmd_listar: falha de rede legivel, e a conexao sempre fechada.

DEFEITO 1 — cmd_listar capturava so BloqueioTSE, como cmd_pais capturava
antes da correcao de 08/09/2026. O custo aqui e' menor que na coleta
nacional (e' um alvo so, nada ja coletado se perde), mas nao e' zero, e a
ironia e' que ele cai justamente em cima do caminho de recuperacao: o bloco
"N alvo(s) falharam. Repita so eles:" que cmd_pais imprime manda a pessoa
rodar `--listar UF`. Se o que derrubou a varredura foi o DNS, e o DNS ainda
esta ruim, o comando SUGERIDO PELA RECUPERACAO responde com um traceback de
socket.gaierror em vez da linha "ERRO: ..." que o codigo obviamente
pretendia. Quem esta tentando se recuperar de uma falha recebe, como
resposta, uma falha pior formatada que a primeira.

DEFEITO 2 — a conexao sqlite so era fechada nos caminhos que os autores
lembraram: o final feliz e o `except BloqueioTSE`. Qualquer outra saida —
uma falha de transporte, um defeito de codigo — pulava o cx.close(). O
processo morrendo logo em seguida esconde o custo na linha de comando, mas
esconder nao e' resolver: cmd_listar tambem e' importado e chamado de dentro
de outro processo, e a unica forma de fechar que nao depende de lembrar de
todas as saidas e' o `finally`. Este arquivo prova as duas coisas: fechada
no sucesso, fechada na falha de rede, e fechada quando um defeito de codigo
sobe (e o defeito continua subindo).

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
ambiente_isolado() redireciona ct.RAIZ/ct.BANCO/ct.DIR_BRUTO para um
diretorio temporario, e ct.buscar — o unico ponto do modulo que abre socket
— e' substituido em todos os controles. Mesmo padrao de
testes/teste_falha_de_rede_pais.py e testes/teste_datas_coleta.py.
"""
import contextlib, http.client, io, json, os, socket, sqlite3, ssl, sys, tempfile

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
def rede_falsa(acao=None):
    """Substitui ct.buscar. `acao` e' None (responde 200 com um candidato de
    mentira), uma Exception (levanta) ou bytes (devolve como corpo, para o
    erro nascer depois, dentro de obter(), como um corpo malformado real)."""
    original = ct.buscar
    def falso(caminho, pausa):
        if isinstance(acao, BaseException):
            raise acao
        if isinstance(acao, bytes):
            return 200, acao
        # O id muda por cargo de proposito: gravar() usa id como chave
        # primaria com INSERT OR REPLACE, entao um id fixo faria os 6 cargos
        # colapsarem numa linha so e o controle contaria 1 achando que
        # media a gravacao. Candidato real tem id proprio em cada cargo.
        cargo = caminho.split("/")[-2]
        corpo = json.dumps({"candidatos": [{
            "id": f"cand-{cargo}", "nome": "FULANO",
            "cargo": {"nome": "DEPUTADO FEDERAL"}}]})
        return 200, corpo.encode("utf-8")
    ct.buscar = falso
    try:
        yield
    finally:
        ct.buscar = original


@contextlib.contextmanager
def espiar_banco():
    """Guarda as conexoes que o comando abriu, para dar para perguntar depois
    se foram fechadas. Sem isto a conexao morre dentro da funcao e nao ha'
    como testemunhar nada sobre ela."""
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
    """Pergunta a propria conexao, em vez de confiar num contador de chamadas
    de close(): conexao fechada acusa sqlite3.ProgrammingError."""
    try:
        cx.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


def rodar_listar(uf="MG"):
    """Executa cmd_listar engolindo stdout/stderr. Devolve (codigo, saida, erro),
    com codigo = o do SystemExit, ou None se a funcao voltou normalmente.
    So SystemExit e' capturado aqui: defeito de codigo TEM que atravessar."""
    saida, erro = io.StringIO(), io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            ct.cmd_listar(uf, pausa=0, forcar=True)
        except SystemExit as e:
            codigo = e.code
    return codigo, saida.getvalue(), erro.getvalue()


# --- CONTROLE 1 — falha de transporte vira ERRO legivel, nao traceback -------
# O caminho que a recuperacao de cmd_pais manda a pessoa percorrer.
print("CONTROLE 1 — falha de transporte em --listar vira ERRO legivel")
with ambiente_isolado():
    erro_dns = socket.gaierror(8, "nodename nor servname provided, or not known")
    with rede_falsa(erro_dns):
        estourou = None
        try:
            codigo, saida, err = rodar_listar()
        except BaseException as e:        # noqa: BLE001 — e' o defeito sob teste
            estourou, codigo, saida, err = e, None, "", ""
    checa("cmd_listar nao deixa a falha de rede subir como traceback",
          estourou is None,
          "voltou por sys.exit" if estourou is None
          else f"subiu {type(estourou).__name__}: {estourou}")
    if estourou is None:
        checa("saiu com codigo 2", codigo == 2, f"codigo={codigo}")
        checa("a mensagem foi para o stderr, com o prefixo ERRO",
              err.strip().startswith("ERRO:"), f"stderr={err.strip()!r}")
        checa("a mensagem diz o que aconteceu",
              "gaierror" in err and "Errno 8" in err, f"stderr={err.strip()!r}")


# --- CONTROLE 2 — a mensagem sobrevive a excecao de texto vazio --------------
print("CONTROLE 2 — a mensagem nomeia a classe mesmo sem texto")
with ambiente_isolado():
    with rede_falsa(TimeoutError()):
        codigo, saida, err = rodar_listar()
    checa("TimeoutError sem texto ainda se identifica",
          "TimeoutError" in err, f"stderr={err.strip()!r}")
    checa("nao imprimiu 'ERRO:' seguido de nada",
          err.strip() != "ERRO:", f"stderr={err.strip()!r}")


# --- CONTROLE 3 — as outras especies de falha de transporte ------------------
print("CONTROLE 3 — toda falha de transporte sai por codigo 2, nao por traceback")
especies = [
    ("timeout de socket",      TimeoutError("timed out")),
    ("conexao derrubada",      ConnectionResetError(54, "Connection reset by peer")),
    ("handshake TLS",          ssl.SSLError(1, "sslv3 alert handshake failure")),
    ("resposta HTTP truncada", http.client.IncompleteRead(b"parcial", 100)),
    ("o TSE respondeu HTML",   b"<html><body>Servico indisponivel</body></html>"),
    ("corpo nao era utf-8",    b"\xff\xfe\x00nao sou utf-8"),
    ("403 do Akamai (BloqueioTSE, que ja era tratado)",
                               ct.BloqueioTSE("o TSE bloqueou")),
]
for rotulo, acao in especies:
    with ambiente_isolado():
        with rede_falsa(acao):
            estourou = None
            try:
                codigo, saida, err = rodar_listar()
            except BaseException as e:    # noqa: BLE001 — e' o defeito sob teste
                estourou, codigo, err = e, None, ""
        if estourou is not None:
            checa(f"{rotulo}: sai por codigo 2", False,
                  f"subiu {type(estourou).__name__}: {estourou}")
            continue
        checa(f"{rotulo}: sai por codigo 2 com ERRO no stderr",
              codigo == 2 and err.strip().startswith("ERRO:"),
              f"codigo={codigo} stderr={err.strip()[:70]!r}")


# --- CONTROLE 4 (NEGATIVO) — defeito de codigo tem que continuar estourando --
# Mesmo freio do controle 4 de teste_falha_de_rede_pais.py, pelo mesmo motivo:
# um `except Exception` aqui faria os controles 1 a 3 passarem e este reprovar.
print("CONTROLE 4 (negativo) — defeito de codigo AINDA estoura em --listar")
defeitos = [
    ("KeyError (esquema do TSE mudou)", KeyError("cargo")),
    ("AttributeError",                  AttributeError("'NoneType' has no attribute 'get'")),
    ("TypeError",                       TypeError("unsupported operand")),
    ("ValueError generico",             ValueError("valor inesperado")),
    ("ZeroDivisionError",               ZeroDivisionError("division by zero")),
]
for rotulo, defeito in defeitos:
    with ambiente_isolado():
        with rede_falsa(defeito):
            estourou = None
            err = ""
            try:
                codigo, saida, err = rodar_listar()
            except BaseException as e:    # noqa: BLE001 — e' o comportamento exigido
                estourou = e
        subiu_igual = type(estourou) is type(defeito)
        checa(f"{rotulo}: sobe em vez de virar 'ERRO:'", subiu_igual,
              "subiu como esperado" if subiu_igual
              else f"foi engolido — stderr={err.strip()[:70]!r}")


# --- CONTROLE 5 — a conexao sqlite e' fechada em TODOS os caminhos de saida --
# Tres saidas, tres respostas. A terceira e' a que hoje reprova: quando um
# defeito de codigo sobe, o cx.close() do fim nunca e' alcancado. O `finally`
# e' a unica forma que nao depende de alguem lembrar de cada saida nova.
print("CONTROLE 5 — a conexao e fechada em todos os caminhos de saida")
caminhos = [
    ("caminho feliz",       None,                       False),
    ("falha de transporte", TimeoutError("timed out"),   False),
    ("defeito de codigo",   KeyError("cargo"),           True),
]
for rotulo, acao, espera_estouro in caminhos:
    with ambiente_isolado():
        with espiar_banco() as conexoes, rede_falsa(acao):
            estourou = None
            try:
                rodar_listar()
            except BaseException as e:    # noqa: BLE001
                estourou = e
        abriu = len(conexoes) == 1
        checa(f"{rotulo}: abriu exatamente uma conexao", abriu,
              f"conexoes={len(conexoes)}")
        if espera_estouro:
            checa(f"{rotulo}: o defeito subiu (nao foi engolido)",
                  estourou is not None,
                  f"estourou={type(estourou).__name__ if estourou else None}")
        if abriu:
            checa(f"{rotulo}: a conexao foi fechada", esta_fechada(conexoes[0]),
                  "fechada" if esta_fechada(conexoes[0]) else "SEGUE ABERTA")


# --- CONTROLE 6 — o caminho feliz continua fazendo o que fazia ---------------
# Um `finally` mal colocado engole o `return`, come a saida ou fecha a conexao
# cedo demais. Este controle e' o que percebe.
print("CONTROLE 6 — o caminho feliz de --listar nao regrediu")
with ambiente_isolado():
    with rede_falsa(None):
        codigo, saida, err = rodar_listar("MG")
    checa("nao saiu por erro", codigo is None, f"codigo={codigo}")
    checa("stderr limpo", err == "", f"stderr={err!r}")
    checa("imprimiu o cabecalho da listagem", "Listagem de MG" in saida,
          repr(saida.splitlines()[:1]))
    checa("imprimiu o rodape com total e banco",
          "Total gravado:" in saida and "Banco:" in saida,
          repr([l for l in saida.splitlines() if l.startswith(("Total", "Banco"))]))
    cx = sqlite3.connect(ct.BANCO)
    try:
        n = cx.execute("SELECT COUNT(*) FROM candidatura").fetchone()[0]
    finally:
        cx.close()
    checa("gravou os 6 cargos no banco temporario", n == 6, f"linhas={n}")


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
