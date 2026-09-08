#!/usr/bin/env python3
"""Controles da promessa de cmd_pais: "Falha de um nao derruba os outros".

O DEFEITO que este arquivo cobre: o `try` dentro do laco de cmd_pais
capturava so BloqueioTSE — a excecao que o PROPRIO codigo levanta quando o
TSE responde 403 ou um HTTP != 200. Qualquer falha de TRANSPORTE (DNS que
nao resolve, timeout, conexao derrubada, handshake TLS) nasce fora dessa
classe e subia inteira, derrubando a varredura nacional no primeiro alvo que
tropecasse. O custo tem tres partes, e a terceira e' a pior:
  1. os alvos ainda nao visitados nao eram visitados;
  2. o rodape ("Total gravado", "Banco:") nunca era impresso;
  3. o bloco "N alvo(s) falharam. Repita so eles:" — que e' EXATAMENTE o
     caminho de recuperacao de quem esta no meio de uma coleta de 28
     unidades — nunca era impresso. Quem levava o traceback ficava sem
     saber por onde retomar.
Medido em 08/09/2026 com HOST apontado para um endereco inalcancavel:
socket.gaierror [Errno 8] subiu ate' o topo, sem nenhuma das tres.

A CORRECAO: o `except` passa a nomear as falhas de TRANSPORTE (ver
FALHAS_DE_TRANSPORTE em coletar_tse.py) em vez de so BloqueioTSE. O erro
tem lado, e o lado importa: falha de rede de um alvo vira linha em
`falharam` e a varredura segue; DEFEITO DE CODIGO (um KeyError numa mudanca
de esquema do TSE, por exemplo) continua estourando. Capturar `Exception`
cru teria fechado o buraco relatado criando um pior — todo bug de
programacao viraria "alvo falhou" em silencio, e a coleta nacional
terminaria com 28 linhas de FALHOU e nenhuma pista. O CONTROLE 4 existe
para provar que isso NAO acontece: e' o controle negativo do arquivo.

Este teste NUNCA toca a base real (~/.local/share/vote-melhor) nem a rede:
todo controle roda dentro de ambiente_isolado(), que redireciona
ct.RAIZ/ct.BANCO/ct.DIR_BRUTO para um diretorio temporario (tempfile) e
restaura os originais ao sair — mesmo padrao de testes/teste_datas_coleta.py.
ct.buscar, o unico ponto do modulo que abre socket, e' substituido em todos
os controles; se algum caminho escapasse da substituicao o teste acusaria
com erro de DNS de verdade, nao com um falso verde.

O ponto de injecao e' o MESMO nos controles positivos e no negativo (sempre
ct.buscar). E' de proposito: se a falha de rede for registrada e o defeito
de codigo estourar tendo nascido no mesmo lugar, dentro do mesmo `try`, o
que separou os dois so pode ter sido o TIPO da excecao — que e' precisamente
a regra sob teste.
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


def fabricar_buscar(roteiro, chamadas):
    """Um ct.buscar falso, dirigido por alvo. NAO abre socket nenhum.

    `roteiro` mapeia UF -> o que a rede faz naquele alvo:
      * instancia de Exception -> a funcao LEVANTA (falha de transporte, que
        no mundo real nasce exatamente aqui, dentro de buscar);
      * bytes -> a funcao DEVOLVE aquilo como corpo, e o erro nasce DEPOIS,
        ja dentro de obter(), ao decodificar/parsear — que e' como um corpo
        malformado do TSE realmente chega.
    UF fora do roteiro responde 200 com um candidato de mentira.
    Cada chamada e' anotada em `chamadas`, que e' a prova de que a varredura
    seguiu (ou nao) para os alvos seguintes."""
    def falso(caminho, pausa):
        # /divulga/rest/v1/candidatura/listar/<ano>/<UF>/<id>/<cargo>/candidatos
        partes = caminho.split("/")
        uf, cargo = partes[-4], partes[-2]
        chamadas.append((uf, cargo))
        acao = roteiro.get(uf)
        if isinstance(acao, BaseException):
            raise acao
        if isinstance(acao, bytes):
            return 200, acao
        corpo = json.dumps({"candidatos": [{
            "id": f"{uf}-{cargo}", "nome": f"FULANO DE {uf}",
            "cargo": {"nome": "DEPUTADO FEDERAL"}}]}).encode("utf-8")
        return 200, corpo
    return falso


@contextlib.contextmanager
def varredura(alvos, roteiro):
    """Fixa ct.ALVOS e substitui ct.buscar pelo falso. Devolve a lista de
    chamadas. Restaura os dois ao sair, sempre."""
    chamadas = []
    alvos_orig, buscar_orig = ct.ALVOS, ct.buscar
    ct.ALVOS = list(alvos)
    ct.buscar = fabricar_buscar(roteiro, chamadas)
    try:
        yield chamadas
    finally:
        ct.ALVOS, ct.buscar = alvos_orig, buscar_orig


def rodar_pais():
    """Executa cmd_pais engolindo o stdout. Devolve (codigo, texto)."""
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = ct.cmd_pais(pausa=0, forcar=True)
    return codigo, saida.getvalue()


def ufs_no_banco():
    """As UFs que realmente entraram na tabela candidatura do banco temporario."""
    cx = sqlite3.connect(ct.BANCO)
    try:
        existe = cx.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='candidatura'").fetchone()
        if not existe:
            return set()
        return {r[0] for r in cx.execute("SELECT DISTINCT uf_consultada "
                                         "FROM candidatura")}
    finally:
        cx.close()


# --- CONTROLE 1 — o defeito relatado: DNS que nao resolve no MEIO da varredura
# E' o controle que reproduz o relato de 08/09/2026 em miniatura. O alvo que
# falha esta' entre dois que dao certo, de proposito: um alvo depois prova a
# continuidade, um alvo antes prova que o que ja tinha entrado no banco NAO
# se perdeu. Com a funcao quebrada (except so BloqueioTSE) este controle nao
# reprova com "FALHA" — ele derruba o arquivo inteiro com o traceback do
# gaierror, que e' o proprio defeito.
print("CONTROLE 1 — falha de DNS vira alvo registrado e a varredura segue")
with ambiente_isolado():
    erro_dns = socket.gaierror(8, "nodename nor servname provided, or not known")
    with varredura(["AC", "AL", "AM"], {"AL": erro_dns}) as chamadas:
        estourou = None
        try:
            codigo, texto = rodar_pais()
        except BaseException as e:            # noqa: BLE001 — e' o defeito sob teste
            estourou = e
            codigo, texto = None, ""

    checa("cmd_pais nao deixa a falha de rede subir",
          estourou is None,
          "voltou normalmente" if estourou is None
          else f"subiu {type(estourou).__name__}: {estourou}")

    if estourou is None:
        visitados = {uf for uf, _ in chamadas}
        checa("o alvo ANTERIOR ao que falhou foi coletado",
              "AC" in visitados, f"visitados={sorted(visitados)}")
        checa("a varredura SEGUIU para o alvo posterior ao que falhou",
              "AM" in visitados, f"visitados={sorted(visitados)}")
        checa("o alvo que falhou parou no primeiro cargo (nao insistiu nos 6)",
              len([1 for uf, _ in chamadas if uf == "AL"]) == 1,
              f"chamadas de AL={[c for u, c in chamadas if u == 'AL']}")
        checa("o que ja tinha sido gravado NAO se perdeu",
              ufs_no_banco() == {"AC", "AM"}, f"no banco={sorted(ufs_no_banco())}")
        checa("imprimiu o bloco de recuperacao",
              "1 alvo(s) falharam. Repita só eles:" in texto,
              repr([l for l in texto.splitlines() if "falharam" in l]))
        checa("o bloco de recuperacao traz o comando do alvo que falhou",
              "--listar AL" in texto,
              repr([l for l in texto.splitlines() if "--listar" in l]))
        checa("imprimiu o rodape (total e banco), que o traceback comia",
              "Total gravado:" in texto and "Banco:" in texto,
              repr([l for l in texto.splitlines() if l.startswith(("Total", "Banco"))]))
        checa("codigo de saida 2 (houve alvo falho)", codigo == 2, f"codigo={codigo}")


# --- CONTROLE 2 — a linha do alvo diz O QUE aconteceu, nao so QUE aconteceu
# Duas metades. A primeira: a mensagem tem que sobreviver a uma excecao de
# texto VAZIO. str(TimeoutError()) e' "" — com um `str(e)` pelado, a linha do
# alvo sairia "AL   FALHOU" e o bloco de recuperacao listaria um alvo sem
# nenhuma razao, que e' pior que inutil: parece dado. Por isso a descricao
# carrega o NOME DA CLASSE. A segunda: quando ha' texto, o texto entra — o
# "[Errno 8]" do DNS e' o que distingue "nao resolveu o nome" de "conexao
# recusada", e e' o que a pessoa vai colar numa busca.
print("CONTROLE 2 — a mensagem do alvo que falhou diz o que aconteceu")
with ambiente_isolado():
    with varredura(["AC", "AL"], {"AL": TimeoutError()}):
        codigo, texto = rodar_pais()
    linha_al = next((l for l in texto.splitlines() if l.startswith("AL")), "")
    checa("excecao de texto vazio ainda se identifica pelo nome da classe",
          "TimeoutError" in linha_al, f"linha={linha_al!r}")

with ambiente_isolado():
    with varredura(["AC", "AL"],
                   {"AL": socket.gaierror(8, "nodename nor servname provided, "
                                             "or not known")}):
        codigo, texto = rodar_pais()
    linha_al = next((l for l in texto.splitlines() if l.startswith("AL")), "")
    checa("o texto da excecao entra na linha do alvo",
          "Errno 8" in linha_al and "gaierror" in linha_al, f"linha={linha_al!r}")


# --- CONTROLE 3 — as outras especies de falha de transporte, uma a uma
# gaierror e' so a que apareceu primeiro. Cada linha abaixo e' uma familia
# que chega por um caminho diferente do codigo, e nenhuma delas e' BloqueioTSE:
# as quatro primeiras nascem dentro de buscar() (socket/TLS/HTTP); as duas
# ultimas nascem dentro de obter(), quando o corpo chega mas nao presta.
print("CONTROLE 3 — toda falha de transporte vira alvo registrado")
especies = [
    ("timeout de socket",        TimeoutError("timed out")),
    ("conexao derrubada",        ConnectionResetError(54, "Connection reset by peer")),
    ("handshake TLS",            ssl.SSLError(1, "sslv3 alert handshake failure")),
    ("resposta HTTP truncada",   http.client.IncompleteRead(b"parcial", 100)),
    ("o TSE respondeu HTML",     b"<html><body>Servico indisponivel</body></html>"),
    ("corpo nao era utf-8",      b"\xff\xfe\x00nao sou utf-8"),
    ("403 do Akamai (BloqueioTSE, que ja era tratado)",
                                 ct.BloqueioTSE("o TSE bloqueou")),
]
for rotulo, acao in especies:
    with ambiente_isolado():
        with varredura(["AC", "AL", "AM"], {"AL": acao}) as chamadas:
            estourou = None
            try:
                codigo, texto = rodar_pais()
            except BaseException as e:        # noqa: BLE001 — e' o defeito sob teste
                estourou = e
                codigo, texto = None, ""
        if estourou is not None:
            checa(f"{rotulo}: registrado em vez de derrubar", False,
                  f"subiu {type(estourou).__name__}: {estourou}")
            continue
        seguiu = "AM" in {uf for uf, _ in chamadas}
        registrou = "1 alvo(s) falharam" in texto and "--listar AL" in texto
        checa(f"{rotulo}: vira alvo registrado e a varredura segue",
              seguiu and registrou and codigo == 2,
              f"seguiu={seguiu} registrou={registrou} codigo={codigo}")


# --- CONTROLE 4 (NEGATIVO) — defeito de CODIGO tem que continuar estourando
# Este controle e' o freio da correcao, e vale mais que os positivos: qualquer
# `except Exception` faria os controles 1 a 3 passarem e este reprovar. Um
# KeyError e' o que aparece quando o TSE muda o esquema do JSON e o nosso
# codigo pede uma chave que deixou de existir — isso e' bug NOSSO, tem que
# quebrar alto e no primeiro alvo, nao virar 28 linhas de "FALHOU" que a
# pessoa vai ler como "a rede esta ruim hoje" e repetir a coleta a noite
# inteira sem nunca descobrir a causa.
print("CONTROLE 4 (negativo) — defeito de codigo AINDA estoura")
defeitos = [
    ("KeyError (esquema do TSE mudou)", KeyError("cargo")),
    ("AttributeError",                  AttributeError("'NoneType' object has no attribute 'get'")),
    ("TypeError",                       TypeError("unsupported operand")),
    ("ValueError generico",             ValueError("valor inesperado")),
    ("NameError",                       NameError("name 'x' is not defined")),
    ("ZeroDivisionError",               ZeroDivisionError("division by zero")),
]
for rotulo, defeito in defeitos:
    with ambiente_isolado():
        with varredura(["AC", "AL", "AM"], {"AL": defeito}):
            estourou = None
            texto = ""
            try:
                codigo, texto = rodar_pais()
            except BaseException as e:        # noqa: BLE001 — e' o comportamento exigido
                estourou = e
        subiu_igual = type(estourou) is type(defeito)
        checa(f"{rotulo}: sobe em vez de virar 'alvo falhou'", subiu_igual,
              "subiu como esperado" if subiu_igual
              else f"foi engolido — saida terminou em {texto.splitlines()[-1:]!r}")
        checa(f"{rotulo}: NAO entrou no bloco de recuperacao",
              "alvo(s) falharam" not in texto,
              repr([l for l in texto.splitlines() if "falharam" in l]))


# --- CONTROLE 5 — varredura em que TODOS os alvos falham
# O caso degenerado tem que terminar tao bem quanto o caso de um so: a
# contagem certa, todo mundo listado no bloco de recuperacao, e saida 2. Se
# o `continue` do laco estivesse errado, este e' o controle que acusaria.
print("CONTROLE 5 — todos os alvos falhando terminam com a lista completa")
with ambiente_isolado():
    erro = ConnectionResetError(54, "Connection reset by peer")
    with varredura(["AC", "AL", "AM"], dict.fromkeys(["AC", "AL", "AM"], erro)):
        estourou = None
        try:
            codigo, texto = rodar_pais()
        except BaseException as e:            # noqa: BLE001 — e' o defeito sob teste
            estourou = e
            codigo, texto = None, ""
    checa("nao derrubou", estourou is None,
          "voltou normalmente" if estourou is None
          else f"subiu {type(estourou).__name__}")
    if estourou is None:
        checa("contou os tres", "3 alvo(s) falharam" in texto,
              repr([l for l in texto.splitlines() if "falharam" in l]))
        checa("listou os tres comandos de repeticao",
              all(f"--listar {u}" in texto for u in ("AC", "AL", "AM")),
              repr([l for l in texto.splitlines() if "--listar" in l]))
        checa("nada foi gravado (nenhum alvo respondeu)", ufs_no_banco() == set(),
              f"no banco={sorted(ufs_no_banco())}")
        checa("codigo de saida 2", codigo == 2, f"codigo={codigo}")


# --- CONTROLE 6 — a conexao sqlite e' fechada em TODOS os caminhos de saida --
# cmd_pais fechava a conexao na ultima linha, que so e' alcancada quando a
# funcao chega ao fim. Um defeito de codigo subindo do laco pula o close.
# Na linha de comando o processo morre em seguida e o custo fica escondido —
# mas cmd_pais tambem e' chamado de dentro de outro processo, e "o sistema
# operacional limpa depois" nao e' fechar. O `finally` e a unica forma que
# nao depende de alguem lembrar de cada saida nova que vier a existir.
print("CONTROLE 6 — a conexao e fechada em todos os caminhos de saida")


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
    """Pergunta a propria conexao, em vez de confiar num contador de chamadas
    de close(): conexao fechada acusa sqlite3.ProgrammingError."""
    try:
        cx.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


caminhos = [
    ("varredura inteira sem falha", {},                              False),
    ("com um alvo falho",           {"AL": TimeoutError("timed out")}, False),
    ("defeito de codigo subindo",   {"AL": KeyError("cargo")},       True),
]
for rotulo, roteiro, espera_estouro in caminhos:
    with ambiente_isolado():
        with espiar_banco() as conexoes, varredura(["AC", "AL", "AM"], roteiro):
            estourou = None
            try:
                rodar_pais()
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


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
