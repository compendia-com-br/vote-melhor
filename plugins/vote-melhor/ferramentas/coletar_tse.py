#!/usr/bin/env python3
# coletar_tse.py — coletor de candidaturas do TSE (DivulgaCandContas)
#
# O QUE FAZ: baixa a lista de candidatos de um estado (todos os cargos) e, sob pedido,
# a ficha detalhada de UM candidato. Guarda o JSON como veio em dados/bruto/ e monta
# um banco SQLite em dados/tse.sqlite. Cada linha guarda de onde veio e quando.
# COMO RODAR (da raiz de um clone; instalado, use ${CLAUDE_PLUGIN_ROOT}/ferramentas/):
#   python3 plugins/vote-melhor/ferramentas/coletar_tse.py --listar MG
#   python3 plugins/vote-melhor/ferramentas/coletar_tse.py --detalhe 123456789
# CUIDADO: servidor público. Há pausa obrigatória entre requisições e cache em disco.

import argparse, glob, gzip, http.client, json, os, re, ssl, sqlite3, sys, time, zlib
from datetime import datetime, timezone

# Importar um modulo escreve .pyc ao lado dele. Como este diretorio e copiado
# inteiro na distribuicao do plugin, nao pode ter artefatos de build. Bloqueamos.
sys.dont_write_bytecode = True

# Mesmo diretorio: verificar_dados.py reaproveita os digitos verificadores de
# CPF e de titulo de eleitor, para a mascara de valor nao reescrever a conta
# (ver comentario acima de PROIBIDOS, mais abaixo).
import verificar_dados as vd

# Diretorio REAL deste arquivo. As mensagens de recuperacao montam o comando a
# partir daqui, e nao de um caminho escrito a mao: "ferramentas/x.py" nao
# existe a partir da raiz de um clone (os scripts moram em
# plugins/vote-melhor/ferramentas/) nem a partir de um plugin instalado. Uma
# mensagem de recuperacao que manda rodar um caminho inexistente deixa quem
# tropecou sem saida — o erro seguinte e igualzinho ao primeiro.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_IRMAO = lambda nome: os.path.join(_AQUI, nome)

# ---------------------------------------------------------------------------
# CABECALHOS — não mexa sem medir. Medido em 02/09/2026 contra o TSE (Akamai):
#   * A ORDEM importa. urllib.request reordena e normaliza os cabeçalhos e leva 403
#     mesmo mandando exatamente estes valores. Por isso aqui se usa http.client cru,
#     com putrequest(skip_host=True, skip_accept_encoding=True) e putheader na ordem.
#   * Tirar UM cabeçalho de cada vez ainda passa (200), mas o conjunto enxuto de 6
#     falha (403): o Akamai pontua o conjunto inteiro, não confere item por item.
#     Conclusão prática: NÃO ENXUGUE ESTA LISTA. Ela é o mínimo seguro conhecido.
# ---------------------------------------------------------------------------
CABECALHOS = [
    ("Host", None),  # preenchido com o host da vez
    ("Connection", "keep-alive"),
    ("Upgrade-Insecure-Requests", "1"),
    ("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    ("sec-ch-ua", '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"'),
    ("sec-ch-ua-mobile", "?0"),
    ("sec-ch-ua-platform", '"macOS"'),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
               "image/webp,image/apng,*/*;q=0.8"),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "document"),
    ("Accept-Encoding", "gzip, deflate"),
    ("Accept-Language", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"),
]

# O dado NUNCA mora dentro do plugin. Plugin instalado é pacote somente-leitura,
# e escrever ali suja o pacote de quem comprou — além de o cache de plugin ser
# congelado por versão, então o dado sumiria a cada atualização.
# Destino: ~/.local/share/vote-melhor, ou VOTE_MELHOR_DADOS se definido.
RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
DIR_BRUTO = os.path.join(RAIZ, "dados", "bruto")
BANCO = os.path.join(RAIZ, "dados", "tse.sqlite")

HOST = "divulgacandcontas.tse.jus.br"
# --- LINHAS PRESAS A 2026 / ELEIÇÃO GERAL (ver relatório: o que quebra em 2028) ---
ANO = 2026
ID_ELEICAO = "20322002026"     # de rest/v1/eleicao/ordinarias
CARGOS_TENTADOS = [1, 3, 5, 6, 7, 8]  # códigos plausíveis de eleição geral
# -------------------------------------------------------------------------------

# As 27 unidades da federacao MAIS "BR". Medido em 07/09/2026: cargo=1 sob
# UF=BR devolve 13 candidatos a presidente, e sob MG, DF ou UF inexistente
# devolve 200 com lista VAZIA. Varrer so as 27 coletaria o pais inteiro sem a
# eleicao presidencial, e o erro seria invisivel — zeros, nao falha.
ALVOS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG",
         "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR",
         "RS", "SC", "SE", "SP", "TO", "BR"]


def alvo_mudo(por_cargo):
    """True quando o alvo devolveu zero em TODOS os cargos.

    E o unico sinal que separa "essa UF nao elege esse cargo" de "a coleta
    dessa UF falhou calada". Nenhum dos 28 alvos pode ser mudo: as 27 UFs
    elegem ao menos deputado, e BR elege presidente."""
    return all(int(n) == 0 for n in por_cargo.values())


class BloqueioTSE(Exception):
    pass


# O ERRO TEM LADO, e o lado decide quem morre junto. Numa varredura de 28
# alvos, falha de TRANSPORTE de um alvo e' rotina — o DNS oscila, o socket
# cai, o TLS tropeca — e nao pode levar junto os 27 outros nem o bloco que
# diz por onde retomar. DEFEITO DE CODIGO e' o contrario: se o TSE mudar o
# esquema do JSON e este arquivo pedir uma chave que sumiu, isso tem que
# quebrar alto, no primeiro alvo, com o traceback inteiro.
# Por isso a lista nomeia as familias de transporte uma a uma em vez de
# `except Exception`: capturar Exception fecharia o buraco criando um pior —
# todo bug nosso viraria "alvo falhou" em silencio, a coleta nacional
# terminaria com 28 linhas de FALHOU, e quem lesse concluiria "a rede esta
# ruim hoje" e repetiria a coleta a noite inteira sem nunca achar a causa.
FALHAS_DE_TRANSPORTE = (
    BloqueioTSE,                # o TSE respondeu, e respondeu nao (403, HTTP != 200)
    OSError,                    # DNS, timeout, conexao derrubada, TLS, gzip corrompido
    http.client.HTTPException,  # resposta HTTP malformada (truncada, status ilegivel)
    zlib.error,                 # corpo deflate corrompido
    json.JSONDecodeError,       # veio corpo, mas nao era JSON (pagina de erro do CDN)
    UnicodeDecodeError,         # veio corpo, mas nao era utf-8
)
# As duas ultimas sao subclasses de ValueError, e e' de proposito que
# ValueError NAO esta na lista: as duas dizem "o que chegou do outro lado nao
# presta", enquanto ValueError cru engoliria erro de logica nosso. Mesma
# razao para nao usar IOError/EnvironmentError (apelidos de OSError, que ja
# esta ai) nem socket.error (idem).


def descrever_falha(e):
    """Uma linha que diz O QUE aconteceu, nao so QUE aconteceu.

    O nome da classe vem sempre: e' ele que separa "nao resolveu o nome" de
    "conexao recusada" quando as duas viram a mesma palavra FALHOU. E ha'
    excecao de transporte cujo str() e' VAZIO — str(TimeoutError()) e' "" —
    e e' ali que um `str(e)` pelado imprimiria um alvo falho sem nenhuma
    razao, o que e' pior que inutil: parece dado."""
    texto = str(e).strip()
    return f"{type(e).__name__}: {texto}" if texto else type(e).__name__

_requisicoes = 0

def buscar(caminho, pausa):
    """Uma requisição HTTPS ao TSE, com pausa antes. Devolve (status, bytes)."""
    global _requisicoes
    time.sleep(pausa)
    _requisicoes += 1
    ctx = ssl.create_default_context()
    con = http.client.HTTPSConnection(HOST, context=ctx, timeout=45)
    con.putrequest("GET", caminho, skip_host=True, skip_accept_encoding=True)
    if os.environ.get("TSE_SEM_CABECALHOS") == "1":
        # modo de teste do caminho de falha: manda só o Host
        con.putheader("Host", HOST)
    else:
        for chave, valor in CABECALHOS:
            con.putheader(chave, HOST if chave == "Host" else valor)
    con.endheaders()
    resp = con.getresponse()
    corpo = resp.read()
    status = resp.status
    codificacao = resp.headers.get("Content-Encoding", "")
    con.close()
    if codificacao == "gzip":
        corpo = gzip.decompress(corpo)
    elif codificacao == "deflate":
        corpo = zlib.decompress(corpo, -15)
    if status == 403:
        raise BloqueioTSE(
            "o TSE bloqueou; confira os cabeçalhos em CABECALHOS no topo do arquivo\n"
            f"  caminho pedido: https://{HOST}{caminho}\n"
            "  o bloqueio é do Akamai, não do seu computador. A lista de cabeçalhos "
            "não pode ser enxugada e a ORDEM dela importa."
        )
    if status != 200:
        raise BloqueioTSE(f"o TSE respondeu HTTP {status} em https://{HOST}{caminho}")
    return status, corpo

def norm(t):
    """Sem acento e sem caixa. Comparar situacao do TSE sem normalizar acento
    da divergencia falsa: 'Deferido' contra 'DEFERIDO' contra 'Deferido '."""
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def agora():
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()

def caminho_cache(apelido):
    hoje = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(DIR_BRUTO, f"{apelido}__{hoje}.json")

# coletado_em precisa dizer QUANDO O TSE RESPONDEU, nao quando a linha foi
# gravada no SQLite. Quando o dado vem do cache, o instante da resposta e o
# instante em que o ARQUIVO foi escrito — nunca "agora", que so descreve a
# releitura. Duas fontes davam essa data e so uma foi escolhida:
#   * o NOME do arquivo (caminho_cache monta <apelido>__<AAAA-MM-DD>.json):
#     so tem o DIA, sem hora. coletado_em sempre guardou timestamp completo
#     (agora() tem hora, minuto, segundo) — usar so o dia seria trocar um
#     carimbo errado por um carimbo incompleto, e obrigaria a inventar uma
#     hora (meio-dia? meia-noite?) que ninguem mediu.
#   * o MTIME do arquivo: tem dia E hora, no mesmo formato que agora() ja
#     produz. Risco aceito e declarado: muda se algo ALEM desta funcao
#     tocar o arquivo depois de escrito. Conferido: nada neste projeto faz
#     isso — dados/bruto/ so e escrito aqui (obter()), e verificar_dados.py
#     documenta explicitamente que --limpar NUNCA toca dados/bruto/, so o
#     banco. Por isso: MTIME.
def quando_arquivo(caminho):
    """ISO local, no mesmo formato de agora(), a partir do mtime do arquivo.
    E a data verdadeira de um dado que veio do cache — ver comentario acima."""
    ts = os.path.getmtime(caminho)
    return datetime.fromtimestamp(ts).astimezone().replace(microsecond=0).isoformat()

def obter(caminho, apelido, pausa, forcar=False):
    """Cache primeiro. Devolve (objeto, url, de_cache, quando_dado).

    quando_dado e sempre o instante em que O TSE RESPONDEU, nunca o instante
    desta chamada: rede -> agora() (acabamos de receber); cache -> mtime do
    arquivo (ver comentario acima de quando_arquivo). Quem chama obter() NAO
    pode usar agora() por conta propria para carimbar o dado — faria de novo
    o defeito que esta funcao existe para fechar."""
    url = f"https://{HOST}{caminho}"
    arq = caminho_cache(apelido)
    if os.path.exists(arq) and not forcar:
        with open(arq, encoding="utf-8") as f:
            return json.load(f), url, True, quando_arquivo(arq)
    _, corpo = buscar(caminho, pausa)
    texto = corpo.decode("utf-8")
    os.makedirs(DIR_BRUTO, exist_ok=True)
    with open(arq, "w", encoding="utf-8") as f:
        f.write(texto)
    return json.loads(texto), url, False, agora()

# --- achatamento e limpeza ---------------------------------------------------
# NÃO GRAVAMOS CPF NEM TÍTULO DE ELEITOR.
# O detalhe do TSE devolve o CPF do candidato, e a própria listagem já devolve o
# número do título de eleitor. O dossiê não usa nenhum dos dois: ele cita nome de
# urna, número, partido, cargo e a situação literal do registro. Guardar documento
# de identificação criaria um cadastro de dado pessoal sem nenhum uso, e o risco de
# vazamento não se paga. Por isso os dois campos são descartados aqui, na ingestão,
# antes de tocar o SQLite. Regra em uma linha: guarde só o que o dossiê cita.
# O JSON bruto em dados/bruto/ ainda tem o que o TSE mandou — quem quiser sigilo
# total apaga a pasta dados/bruto/ depois de montar o banco.
PROIBIDOS = re.compile(r"cpf|tituloeleitor", re.IGNORECASE)

# O filtro acima casa o NOME da chave do JSON — e so isso. Medido em
# 07/09/2026: uma certidao do TCU anexada a uma candidatura carrega o CPF do
# requerente dentro do proprio NOME do arquivo (pratica normal de certidao
# desse tipo), guardado na lista JSON do campo `arquivos`. PROIBIDOS nunca
# olha para DENTRO do valor, entao esse CPF passava liso. Por isso, alem do
# filtro por nome, toda string e toda lista gravada passa por
# mascarar_valor(), que troca por "[documento removido]" qualquer sequencia
# de 11 a 13 digitos que bata o digito verificador de CPF ou de titulo — a
# MESMA conta de verificar_dados.py, nunca reescrita aqui. Mascarar todo
# numero de 11+ digitos destruiria id de arquivo e numero de protocolo
# legitimos; so o checksum decide.
#
# Excecao: uma sequencia IGUAL ao id da propria linha nunca e mascarada — o
# id publico de candidatura do TSE as vezes cai, por acaso, na faixa de UF de
# titulo de eleitor, e isso nao e documento (mesma razao estrutural de
# varrer() em verificar_dados.py).

def achatar(obj, prefixo="", id_linha=None):
    saida = {}
    for chave, valor in obj.items():
        nome = f"{prefixo}{chave}"
        if PROIBIDOS.search(nome):
            continue
        if isinstance(valor, dict):
            saida.update(achatar(valor, nome + "_", id_linha))
        elif isinstance(valor, (list, tuple)):
            bruto = json.dumps(valor, ensure_ascii=False)
            saida[nome] = vd.mascarar_valor(bruto, id_linha)
        elif isinstance(valor, str):
            saida[nome] = vd.mascarar_valor(valor, id_linha)
        else:
            saida[nome] = valor
    return saida

def col(nome):
    return '"' + nome.replace('"', "") + '"'

def garantir_tabela(cx, tabela, colunas):
    existe = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
    ).fetchone()
    if not existe:
        defs = ", ".join(f"{col(c)} TEXT" for c in colunas if c != "id")
        cx.execute(f"CREATE TABLE {tabela} (id TEXT PRIMARY KEY, {defs})")
    else:
        atuais = {r[1] for r in cx.execute(f"PRAGMA table_info({tabela})")}
        for c in colunas:
            if c not in atuais:
                cx.execute(f"ALTER TABLE {tabela} ADD COLUMN {col(c)} TEXT")

def gravar(cx, tabela, linhas):
    if not linhas:
        return 0
    colunas = []
    for l in linhas:
        for c in l:
            if c not in colunas:
                colunas.append(c)
    garantir_tabela(cx, tabela, colunas)
    marcas = ",".join("?" * len(colunas))
    sql = (f"INSERT OR REPLACE INTO {tabela} ({','.join(col(c) for c in colunas)}) "
           f"VALUES ({marcas})")
    cx.executemany(sql, [[
        (None if l.get(c) is None else str(l.get(c))) for c in colunas] for l in linhas])
    return len(linhas)

def abrir_banco():
    os.makedirs(os.path.dirname(BANCO), exist_ok=True)
    cx = sqlite3.connect(BANCO)
    cx.execute("""CREATE TABLE IF NOT EXISTS coleta (
        quando TEXT, alvo TEXT, url TEXT, itens INTEGER, de_cache INTEGER)""")
    return cx

# --- comandos ----------------------------------------------------------------
def coletar_alvo(cx, uf, pausa, forcar, imprimir=True):
    """Coleta os 6 cargos de UM alvo. Devolve {codigo: n_gravados}.

    LEVANTA BloqueioTSE em vez de sair: numa varredura de 28 alvos, sair no
    primeiro tropeco de rede joga fora tudo o que ja entrou. Quem chama decide.
    """
    uf = uf.upper()
    por_cargo = {}
    for codigo in CARGOS_TENTADOS:
        caminho = (f"/divulga/rest/v1/candidatura/listar/{ANO}/{uf}/"
                   f"{ID_ELEICAO}/{codigo}/candidatos")
        apelido = f"listar_{ANO}_{uf}_{codigo}"
        t0 = time.time()
        dados, url, de_cache, quando = obter(caminho, apelido, pausa, forcar)
        dt = time.time() - t0
        cands = dados.get("candidatos") or []
        nome_cargo = "(sem candidato)"
        if cands:
            nome_cargo = (cands[0].get("cargo") or {}).get("nome") or "?"
        linhas = []
        for c in cands:
            id_linha = str(c.get("id"))
            l = achatar(c, id_linha=id_linha)
            l["id"] = id_linha
            l["uf_consultada"] = uf
            l["cargo_codigo"] = str(codigo)
            l["coletado_em"] = quando
            l["fonte_url"] = url
            linhas.append(l)
        n = gravar(cx, "candidatura", linhas)
        cx.execute("INSERT INTO coleta VALUES (?,?,?,?,?)",
                   (quando, f"listar {uf} cargo {codigo}", url, n, int(de_cache)))
        cx.commit()
        por_cargo[str(codigo)] = n
        if imprimir:
            tam = os.path.getsize(caminho_cache(apelido))
            print(f"{nome_cargo:<28} {codigo:>4} {n:>10} {dt:>6.2f}s {tam:>8}B  "
                  f"{'cache' if de_cache else 'rede'}")
    return por_cargo

def cmd_listar(uf, pausa, forcar):
    """Coleta UM alvo. Falha de transporte sai por ERRO legivel e codigo 2.

    Aqui nao ha' 27 alvos para proteger — o motivo de nao deixar o traceback
    subir e' outro: este e' o comando que o bloco de recuperacao de cmd_pais
    manda a pessoa rodar. Se o que derrubou a varredura foi o DNS, e o DNS
    ainda esta ruim, seria justamente o caminho de conserto a responder com
    um traceback."""
    uf = uf.upper()
    cx = abrir_banco()
    try:
        print(f"Listagem de {uf} — eleição {ANO} (id {ID_ELEICAO})")
        print(f"{'cargo':<28} {'cód':>4} {'candidatos':>10} {'tempo':>7} {'tamanho':>9}  origem")
        try:
            por_cargo = coletar_alvo(cx, uf, pausa, forcar)
        except FALHAS_DE_TRANSPORTE as e:
            print(f"\nERRO: {descrever_falha(e)}", file=sys.stderr)
            sys.exit(2)
        total = sum(por_cargo.values())
        if alvo_mudo(por_cargo):
            print(f"\nATENÇÃO: {uf} devolveu ZERO em todos os cargos. Isso é anomalia, "
                  f"não resultado — toda UF elege ao menos deputado.")
        print(f"\nTotal gravado: {total} candidatos. "
              f"Requisições de rede nesta execução: {_requisicoes}.")
        print(f"Banco: {BANCO}")
    finally:
        # Fecha em TODA saida: o fim feliz, o sys.exit(2) acima (SystemExit
        # atravessa o finally) e o defeito de codigo que sobe. O cx.close()
        # solto no fim so cobria o primeiro, e o de dentro do except so o
        # segundo — os dois dependiam de alguem lembrar de cada saida.
        cx.close()

def cmd_pais(pausa, forcar):
    """Varre os 28 alvos. Falha de REDE de um nao derruba os outros.

    Falha de transporte (ver FALHAS_DE_TRANSPORTE) vira linha em `falharam`
    e a varredura segue; defeito de codigo sobe inteiro, de proposito. O
    que se perderia sem isso nao e' so o resto da varredura: e' o bloco de
    recuperacao do fim, que e' a unica coisa que diz por onde retomar."""
    cx = abrir_banco()
    try:
        print(f"Coleta nacional — eleição {ANO} (id {ID_ELEICAO}) — {len(ALVOS)} alvos")
        print("BR é a cédula presidencial: cargo 1 só devolve candidato ali.\n")
        print(f"{'alvo':<6} {'candidatos':>11}  detalhe por cargo")
        falharam, mudos, total = [], [], 0
        for uf in ALVOS:
            try:
                por_cargo = coletar_alvo(cx, uf, pausa, forcar, imprimir=False)
            except FALHAS_DE_TRANSPORTE as e:
                descricao = descrever_falha(e)
                falharam.append((uf, descricao))
                print(f"{uf:<6} {'FALHOU':>11}  {descricao}")
                continue
            n = sum(por_cargo.values())
            total += n
            if alvo_mudo(por_cargo):
                mudos.append(uf)
            detalhe = " ".join(f"{c}:{v}" for c, v in por_cargo.items() if v)
            print(f"{uf:<6} {n:>11}  {detalhe or '(tudo zero)'}")
        print(f"\nTotal gravado: {total} candidaturas. "
              f"Requisições de rede: {_requisicoes}.")
        print(f"Banco: {BANCO}")
        if mudos:
            print(f"\nANOMALIA: {len(mudos)} alvo(s) devolveram zero em todos os cargos: "
                  f"{', '.join(mudos)}. Isso não é resultado — é coleta que falhou calada.")
        if falharam:
            print(f"\n{len(falharam)} alvo(s) falharam. Repita só eles:")
            for uf, _ in falharam:
                print(f"  python3 {_IRMAO('coletar_tse.py')} --listar {uf}")
        return 2 if (falharam or mudos) else 0
    finally:
        # Fecha inclusive quando um defeito de codigo sobe do laco — o
        # `return` acima passa pelo finally, e a excecao tambem.
        cx.close()

def cmd_detalhe(ident, uf, pausa, forcar):
    uf = uf.upper()
    cx = abrir_banco()
    caminho = (f"/divulga/rest/v1/candidatura/buscar/{ANO}/{uf}/"
               f"{ID_ELEICAO}/candidato/{ident}")
    apelido = f"detalhe_{ANO}_{uf}_{ident}"
    try:
        dados, url, de_cache, quando = obter(caminho, apelido, pausa, forcar)
    except BloqueioTSE as e:
        print(f"\nERRO: {e}", file=sys.stderr)
        sys.exit(2)
    id_linha = str(dados.get("id") or ident)
    l = achatar(dados, id_linha=id_linha)
    l["id"] = id_linha
    l["uf_consultada"] = uf
    l["coletado_em"] = quando
    l["fonte_url"] = url
    gravar(cx, "detalhe", [l])
    cx.execute("INSERT INTO coleta VALUES (?,?,?,?,?)",
               (l["coletado_em"], f"detalhe {ident}", url, 1, int(de_cache)))
    cx.commit()
    print(f"Detalhe gravado: {l['id']} — {l.get('nomeUrna') or l.get('nomeCompleto')}")
    print(f"  campos guardados: {len(l)}  |  origem: {'cache' if de_cache else 'rede'}")
    print(f"  requisições de rede nesta execução: {_requisicoes}")
    cx.close()

# --- frescor -----------------------------------------------------------------
# A situacao do registro e o campo mais volatil no momento mais decisivo:
# deferido vira indeferido, indeferido vai a recurso, e isso muda ate a vespera.
# Uma base local envelhece exatamente ai.
#
# Por isso duas coisas, e as duas importam:
#   1. divergencia se EXIBE, nunca se sobrescreve. "Base 27/08: DEFERIDO ·
#      consulta 02/09: INDEFERIDO COM RECURSO" e a informacao, nao o ruido.
#   2. base velha RECUSA, nao avisa. Aviso que depende da mao apodrece.
#
# IDADE_MAXIMA nao foi medida. O certo seria baixar duas vezes com N dias de
# intervalo e contar quantas linhas mudaram de situacao — isso da o N honesto.
# Ate la, 7 dias e escolha conservadora e esta declarada como escolha.
IDADE_MAXIMA_DIAS = int(os.environ.get("VOTE_MELHOR_IDADE_MAXIMA", "7"))


def idade_da_base(cx):
    """Devolve (dias, quando) da coleta de listagem mais recente, ou (None, None)."""
    r = cx.execute("SELECT MAX(quando) FROM coleta WHERE alvo LIKE 'listar%'").fetchone()
    if not r or not r[0]:
        return None, None
    from datetime import datetime as _dt
    try:
        q = _dt.fromisoformat(r[0])
        agora_ = _dt.now(q.tzinfo) if q.tzinfo else _dt.now()
        return (agora_ - q).days, r[0]
    except Exception:
        return None, r[0]


def cmd_idade(_pausa=None, _forcar=None):
    cx = abrir_banco()
    dias, quando = idade_da_base(cx)
    if dias is None:
        print("Base ainda nao coletada. Rode:  coletar_tse.py --listar <UF>")
        cx.close(); return 2
    print(f"Base coletada em {quando}")
    print(f"Idade: {dias} dia(s)  |  limite: {IDADE_MAXIMA_DIAS} dia(s)")
    if dias > IDADE_MAXIMA_DIAS:
        print()
        print("RECUSADO: a base passou do limite.")
        print(f"  Rode:  coletar_tse.py --listar <UF> --forcar")
        cx.close(); return 2
    print("Dentro do limite.")
    cx.close(); return 0


# --- reparo de datas -----------------------------------------------------------
# O defeito: ANTES desta correcao, coletar_alvo() e cmd_detalhe() carimbavam
# coletado_em (e coleta.quando — MESMA variavel `quando`) com agora() mesmo
# quando obter() vinha do CACHE. O carimbo dizia "agora" para um dado que
# podia ter horas de idade. Medido em 07/09/2026: a base inteira (20.005
# linhas de candidatura) carimbada num intervalo de 3 segundos, enquanto o
# arquivo bruto correspondente foi escrito antes — a coleta de um pais
# inteiro nao acontece em 3 segundos; a base so mentiu que sim.
#
# A correcao em obter() so vale PARA A FRENTE. O que ja esta gravado precisa
# de reparo explicito — mesmo padrao de verificar_dados.py --limpar: relata
# ANTES de alterar, nunca em silencio, e diz o que mudou.
#
# Reparado: candidatura.coletado_em, detalhe.coletado_em E coleta.quando —
# --idade le coleta.quando, nao candidatura.coletado_em. Corrigir uma tabela
# e deixar a outra mentindo quebraria --idade sem que nada aqui acusasse.
#
# COMO se acha o valor certo de uma linha ja gravada: o DIA do carimbo
# errado e confiavel (agora() e quando_arquivo() sempre caem no mesmo dia,
# porque caminho_cache() usa "hoje" tanto para nomear o arquivo na escrita
# quanto para acha-lo na leitura — so a HORA dentro do dia mente). Por isso
# o reparo usa esse dia para achar o arquivo de cache exato e le o mtime
# dele. Se o arquivo de dados/bruto/ ja foi apagado (por exemplo, sigilo
# total — coletar_tse.py documenta esse caminho acima de PROIBIDOS), a
# linha fica SEM_ARQUIVO: relatada, nunca adivinhada.

def apelido_listar(uf, cargo):
    return f"listar_{ANO}_{uf}_{cargo}"

def apelido_detalhe(uf, ident):
    return f"detalhe_{ANO}_{uf}_{ident}"

def tabela_existe(cx, nome):
    return cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (nome,)).fetchone() is not None

def quando_correto_de(apelido, carimbo_atual):
    """O coletado_em CORRETO para este apelido, lido do arquivo de cache.

    ANTES: montava <apelido>__<dia-do-carimbo-atual>.json e so aceitava esse
    nome exato. Premissa (valida so da PRIMEIRA vez): agora() e mtime nascem
    do MESMO evento de escrita, entao caem no mesmo dia. Na SEGUNDA rodada o
    carimbo examinado ja e o mtime reparado — e mtime perto da meia-noite
    pode cair num dia diferente do dia gravado NO NOME do arquivo (que fica
    fixo desde a escrita original). Medido: reprovava teste_datas_coleta.py
    toda vez que rodava entre 00h e 06h, jogando um grupo JA corrigido em
    SEM_ARQUIVO na rodada seguinte — alarme falso na propria ferramenta que
    existe para a data ser honesta.

    AGORA: busca por PADRAO (apelido__*.json), nao pelo dia extraido do
    carimbo. Um so arquivo bate -> usa ele, sem depender de dia nenhum. Mais
    de um (apelido recoletado em dias diferentes ao longo do tempo) -> so
    aceita o que casa com o dia do carimbo; sem casar, nao adivinha (mesma
    politica de sempre: relatar SEM_ARQUIVO em vez de escolher errado).
    None = nao reparavel."""
    candidatos = sorted(glob.glob(os.path.join(DIR_BRUTO, f"{apelido}__*.json")))
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return quando_arquivo(candidatos[0])
    dia = (carimbo_atual or "")[:10]
    exato = os.path.join(DIR_BRUTO, f"{apelido}__{dia}.json")
    if exato in candidatos:
        return quando_arquivo(exato)
    return None

def escanear_datas(cx):
    """Devolve (grupos, log, sem_arquivo) — nunca altera o banco.

    grupos: candidatura/detalhe agrupados por (uf, cargo-ou-id, coletado_em)
    — toda linha de UMA chamada listar/detalhe carimba o MESMO coletado_em,
    entao reparar por grupo (nao linha a linha) mantem o relatorio legivel.
    log: coleta.quando, linha a linha (rowid) — e um LOG, o mesmo alvo pode
    ter uma entrada por dia diferente ao longo do tempo.
    sem_arquivo: grupos cujo arquivo de cache sumiu — fora da conta de
    'corrigido', para nunca virar acerto por omissao.
    """
    grupos, log, sem_arquivo = [], [], []

    for uf, cargo, atual, n in cx.execute(
            "SELECT uf_consultada, cargo_codigo, coletado_em, COUNT(*) FROM candidatura "
            "GROUP BY uf_consultada, cargo_codigo, coletado_em"):
        apelido = apelido_listar(uf, cargo)
        correto = quando_correto_de(apelido, atual)
        item = {"tabela": "candidatura", "apelido": apelido,
                "where_sql": "uf_consultada = ? AND cargo_codigo = ? AND coletado_em = ?",
                "where_val": (uf, cargo, atual), "n": n, "atual": atual, "correto": correto}
        if correto is None:
            sem_arquivo.append(item)
        elif correto != atual:
            grupos.append(item)

    if tabela_existe(cx, "detalhe"):
        for uf, ident, atual in cx.execute(
                "SELECT uf_consultada, id, coletado_em FROM detalhe"):
            apelido = apelido_detalhe(uf, ident)
            correto = quando_correto_de(apelido, atual)
            item = {"tabela": "detalhe", "apelido": apelido,
                    "where_sql": "uf_consultada = ? AND id = ?",
                    "where_val": (uf, ident), "n": 1, "atual": atual, "correto": correto}
            if correto is None:
                sem_arquivo.append(item)
            elif correto != atual:
                grupos.append(item)

    for rid, alvo, atual in cx.execute("SELECT rowid, alvo, quando FROM coleta"):
        m = re.match(r"^listar (\S+) cargo (\d+)$", alvo or "")
        if not m:
            continue  # "detalhe <id>" e "eleicoes_ordinarias": fora do escopo
                      # medido (candidatura e' quem tem as 20.005 linhas erradas)
        apelido = apelido_listar(m.group(1), m.group(2))
        correto = quando_correto_de(apelido, atual)
        if correto is not None and correto != atual:
            log.append({"rowid": rid, "apelido": apelido, "atual": atual, "correto": correto})

    return grupos, log, sem_arquivo

def reparar_datas(banco, aplicar):
    """Corrige coletado_em/coleta.quando gravados com o defeito acima.

    Sem `aplicar`, so relata — nunca altera o banco. Mesmo padrao de
    verificar_dados.py --limpar: relata ANTES de alterar, nunca em
    silencio, diz o que mudou, e confere de novo depois de aplicar.

    Codigos: 0 nada a corrigir, ou tudo corrigido e confirmado na
    reconferencia · 2 sem --aplicar havendo o que corrigir, ou sobrou algo
    sem arquivo de cache (nao reparavel) apos aplicar.
    """
    cx = sqlite3.connect(banco)
    grupos, log, sem_arquivo = escanear_datas(cx)

    if not grupos and not log:
        print("--reparar-datas: nenhum carimbo errado encontrado. Nada para mudar.")
        cx.close()
        if sem_arquivo:
            # Repetir isso a cada chamada e de proposito: o gap (arquivo
            # sumido) nao desaparece so porque nao ha mais nada NOVO para
            # corrigir. "Nada para mudar" nao pode virar "esta tudo certo".
            print(f"\n{len(sem_arquivo)} grupo(s) continuam SEM arquivo de cache — "
                  f"nao entram nesta conta porque ja foram avisados antes, mas "
                  f"continuam com coletado_em errado.")
            for item in sem_arquivo:
                print(f"  {item['tabela']:<11} {item['apelido']:<26} {item['n']:>6} linha(s)")
            return 2
        return 0

    total_linhas = sum(g["n"] for g in grupos)
    print(f"--reparar-datas {'vai corrigir' if aplicar else 'encontrou'} "
          f"{len(grupos)} grupo(s) de candidatura/detalhe ({total_linhas} linha(s)) "
          f"e {len(log)} entrada(s) do log de coleta:\n")
    for g in grupos:
        print(f"  {g['tabela']:<11} {g['apelido']:<26} {g['n']:>6} linha(s)  "
              f"{g['atual']}  ->  {g['correto']}")
    for item in log:
        print(f"  coleta      {item['apelido']:<26} {'1':>6} linha(s)  "
              f"{item['atual']}  ->  {item['correto']}  (rowid={item['rowid']})")

    if sem_arquivo:
        print(f"\n{len(sem_arquivo)} grupo(s) SEM arquivo de cache correspondente — "
              f"NAO reparados (nunca adivinhados):")
        for item in sem_arquivo:
            print(f"  {item['tabela']:<11} {item['apelido']:<26} {item['n']:>6} linha(s)")

    if not aplicar:
        print("\nSem --aplicar: nada foi alterado. Repita com --aplicar para gravar.")
        cx.close()
        return 2

    for g in grupos:
        cx.execute(f"UPDATE {g['tabela']} SET coletado_em = ? WHERE {g['where_sql']}",
                   (g["correto"],) + g["where_val"])
    for item in log:
        cx.execute("UPDATE coleta SET quando = ? WHERE rowid = ?",
                   (item["correto"], item["rowid"]))
    cx.commit()
    cx.close()

    print(f"\n{total_linhas} linha(s) de candidatura/detalhe corrigida(s), "
          f"{len(log)} entrada(s) de coleta corrigida(s).")
    print("Conferindo de novo...")
    cx = sqlite3.connect(banco)
    grupos2, log2, _sem2 = escanear_datas(cx)
    cx.close()
    if grupos2 or log2:
        print(f"AINDA HA {len(grupos2)} grupo(s) e {len(log2)} entrada(s) de log "
              f"errados apos o reparo — nao ficou correto.")
        return 2
    print("Conferencia de novo: nenhuma data reparavel continua errada.")
    if sem_arquivo:
        print(f"\n{len(sem_arquivo)} grupo(s) continuam SEM arquivo de cache — o "
              f"coletado_em deles NAO foi tocado, e continua dizendo o instante da "
              f"gravacao, nao o da resposta do TSE.")
        return 2
    return 0

def cmd_reparar_datas(aplicar):
    return reparar_datas(BANCO, aplicar)


def cmd_frescor(ident, uf, pausa, forcar=True):
    """Compara a situacao gravada com a situacao da hora, e mostra as DUAS."""
    uf = uf.upper()
    cx = abrir_banco()
    cx.row_factory = sqlite3.Row
    base = cx.execute(
        "SELECT nomeUrna, descricaoSituacao, cargo_nome, partido_sigla FROM candidatura "
        "WHERE id = ?", (str(ident),)).fetchone()
    cx.row_factory = None
    quando_base = cx.execute(
        "SELECT MAX(quando) FROM coleta WHERE alvo LIKE 'listar%'").fetchone()[0]

    caminho = (f"/divulga/rest/v1/candidatura/buscar/{ANO}/{uf}/"
               f"{ID_ELEICAO}/candidato/{ident}")
    try:
        dados, url, de_cache, quando_ag = obter(
            caminho, f"frescor_{ANO}_{uf}_{ident}", pausa, forcar)
    except BloqueioTSE as e:
        print(f"\nERRO: {e}", file=sys.stderr)
        cx.close(); sys.exit(2)

    nome  = dados.get("nomeUrna") or dados.get("nomeCompleto") or "sem dado"
    ag    = dados.get("descricaoSituacao") or "sem dado"
    # forcar=True por padrao (assinatura acima): --frescor pede a situacao
    # DA HORA de proposito, entao de_cache aqui deveria ser sempre False e
    # quando_ag deveria ser sempre agora(). Se um dia alguem chamar com
    # forcar=False, quando_ag continua correto (mtime do cache), porque vem
    # do mesmo obter() que candidatura/detalhe usam — nao ha calculo em
    # duplicata para divergir.

    L = 66
    print("=" * L)
    print("FRESCOR DO REGISTRO — a base e a consulta da hora, lado a lado")
    print("=" * L)
    print(f"{nome}  ({dados.get('cargo',{}).get('nome','sem dado')})")
    print()
    if base is None:
        print("  Este id nao esta na base local. Mostro so a consulta da hora.")
        print(f"  agora  ({quando_ag[:19]}): {ag}")
    else:
        ant = base["descricaoSituacao"] or "sem dado"
        print(f"  base   ({str(quando_base)[:19]}): {ant}")
        print(f"  agora  ({quando_ag[:19]}): {ag}")
        print()
        if norm(ant) == norm(ag):
            print("  IGUAL — a situacao nao mudou desde a coleta da base.")
        else:
            print("  *** DIVERGEM ***")
            print("  A base local esta desatualizada PARA ESTE CANDIDATO.")
            print("  As duas linhas ficam. A ferramenta nao sobrescreve em silencio:")
            print("  a mudanca de situacao e o fato mais relevante que esta ficha traz hoje.")
    print()
    print(f"  fonte: {url}  [{'cache' if de_cache else 'rede'}]")
    print(f"  requisicoes de rede nesta execucao: {_requisicoes}")
    print("=" * L)
    cx.close()
    return 0


# --- plano de governo --------------------------------------------------------
# Proposta de governo e o UNICO documento oficial de conteudo que existe numa
# candidatura — e so para cargo EXECUTIVO: presidente, governador, prefeito.
# Senador e deputado nao tem, por lei. Para eles, o que existir e material de
# campanha, ou seja, alegacao.
#
# Duas licoes medidas em 02/09/2026, que este trecho encarna:
#
# 1. NAO se descobre o plano pelo nome do arquivo anexado a candidatura. Fiz isso
#    e errei: procurei "PLANO"/"GOVERNO" no campo `arquivos` do detalhe e conclui
#    que 3 dos 11 candidatos a governador de MG nao tinham anexado. O pacote
#    oficial mostra que so 1 nao tem — os outros 2 nomearam o arquivo de outro
#    jeito. Nome de arquivo mente; o pacote do TSE e a fonte.
#
# 2. O CDN do TSE responde 200 para o MESMO conjunto e ordem de cabecalhos que
#    a API aceita. A crenca anterior de que ele exigia navegador veio de testar
#    com curl — que falha por outro motivo, e nao por politica do TSE.
HOST_CDN = "cdn.tse.jus.br"
CAMINHO_PLANOS = "/estatistica/sead/odsele/proposta_governo/proposta_governo_{ano}_{uf}.zip"


def baixar_cdn(caminho, pausa=1.5):
    """GET no CDN do TSE, com o mesmo conjunto e ORDEM de cabecalhos da API."""
    global _requisicoes
    ctx = ssl.create_default_context()
    cx = http.client.HTTPSConnection(HOST_CDN, 443, context=ctx, timeout=120)
    cx.putrequest("GET", caminho, skip_host=True, skip_accept_encoding=True)
    for k, v in CABECALHOS:
        cx.putheader(k, HOST_CDN if k.lower() == "host" else v)
    if not any(k.lower() == "host" for k, _ in CABECALHOS):
        cx.putheader("Host", HOST_CDN)
    cx.endheaders()
    time.sleep(pausa)
    r = cx.getresponse()
    corpo = r.read()
    _requisicoes += 1
    if r.status != 200:
        raise BloqueioTSE(f"o CDN do TSE respondeu HTTP {r.status} em "
                          f"https://{HOST_CDN}{caminho}")
    return corpo


def cmd_plano(alvo, uf, pausa, forcar=False):
    """--plano <UF> baixa o pacote; --plano <id> extrai o PDF de um candidato."""
    import zipfile
    uf_pacote = (uf if len(str(alvo)) > 3 else str(alvo)).upper()
    zipe = os.path.join(DIR_BRUTO, f"proposta_governo_{ANO}_{uf_pacote}.zip")

    if not os.path.exists(zipe) or forcar:
        caminho = CAMINHO_PLANOS.format(ano=ANO, uf=uf_pacote)
        print(f"Baixando os planos de governo de {uf_pacote}...")
        try:
            dados = baixar_cdn(caminho, pausa)
        except BloqueioTSE as e:
            print(f"\nERRO: {e}", file=sys.stderr); return 2
        os.makedirs(DIR_BRUTO, exist_ok=True)
        open(zipe, "wb").write(dados)
        print(f"  {len(dados):,} bytes".replace(",", "."))
        quando_zip = agora()
    else:
        print(f"Pacote ja em disco: {zipe}")
        # Mesmo defeito de coletar_alvo(), mesma correcao: o pacote pode
        # estar em disco de uma execucao de dias atras. "coletado em" tem
        # que dizer quando o CDN respondeu, nao quando esta chamada rodou.
        quando_zip = quando_arquivo(zipe)

    z = zipfile.ZipFile(zipe)
    mapa = {}
    for n in z.namelist():
        m = re.search(rf"{ANO}{uf_pacote}(\d+)_", n)
        if m:
            mapa.setdefault(m.group(1), []).append(n)

    # --plano <UF>: so o inventario
    if len(str(alvo)) <= 3:
        cx = abrir_banco(); cx.row_factory = sqlite3.Row
        print(f"\nPlanos de governo em {uf_pacote}: {len(mapa)} documento(s)\n")
        print(f"  {'nº':<5}{'candidato':<28}{'cargo':<16}plano")
        print("  " + "-" * 62)
        cargos = ("Presidente", "Governador", "Prefeito")
        linhas = cx.execute(
            "SELECT id, nomeUrna, numero, cargo_nome FROM candidatura "
            "WHERE cargo_nome IN (?,?,?) ORDER BY CAST(numero AS INTEGER)", cargos).fetchall()
        for r in linhas:
            tem = r["id"] in mapa
            print(f"  {r['numero'] or '?':<5}{(r['nomeUrna'] or '')[:26]:<28}"
                  f"{(r['cargo_nome'] or '')[:14]:<16}{'sim' if tem else 'NAO ENTREGOU'}")
        print()
        print("  Nao entregar plano de governo e informacao, nao juizo: a lei exige")
        print("  o documento de candidato a cargo executivo.")
        print()
        print("  ATENCAO ao metodo: nao descubra isso pelo NOME do arquivo anexado")
        print("  a candidatura. Medido em 02/09/2026: essa via errou 2 de 11 em MG,")
        print("  porque candidato nomeia o proprio arquivo como quer.")
        cx.close(); return 0

    # --plano <id>: extrai o PDF daquele candidato
    ident = str(alvo)
    if ident not in mapa:
        print(f"\n{ident}: sem plano de governo no pacote de {uf_pacote}.")
        print("  Se ele e candidato a cargo executivo, isso significa que nao entregou.")
        print("  Se e candidato a deputado ou senador, o cargo NAO tem esse documento:")
        print("  a lei so exige de executivo.")
        return 1
    destino = os.path.join(RAIZ, "dados", "planos", uf_pacote)
    os.makedirs(destino, exist_ok=True)
    saidas = []
    for n in mapa[ident]:
        alvo_pdf = os.path.join(destino, os.path.basename(n))
        with z.open(n) as f, open(alvo_pdf, "wb") as g:
            g.write(f.read())
        saidas.append(alvo_pdf)
    cx = abrir_banco(); cx.row_factory = sqlite3.Row
    r = cx.execute("SELECT nomeUrna, numero, cargo_nome FROM candidatura WHERE id = ?",
                   (ident,)).fetchone()
    cx.close()
    print()
    print(f"Plano de governo — {r['nomeUrna'] if r else ident}")
    if r: print(f"  cargo: {r['cargo_nome']}  |  numero na urna: {r['numero']}")
    for x in saidas:
        tam = os.path.getsize(x)
        print(f"  arquivo: {x}")
        print(f"  tamanho: {tam:,} bytes".replace(",", "."))
    print(f"  fonte  : https://{HOST_CDN}{CAMINHO_PLANOS.format(ano=ANO, uf=uf_pacote)}")
    print(f"  coletado em {quando_zip}")
    print()
    print("  O conteudo e PROMESSA DE CAMPANHA, nao registro oficial de fato.")
    print("  E fato que o documento foi protocolado; o que esta escrito nele e o")
    print("  que o candidato se compromete a fazer, e a ferramenta nao resume,")
    print("  nao avalia e nao compara promessa.")
    return 0


def cmd_eleicoes(pausa, forcar=False):
    """Lista as eleicoes ordinarias que o TSE conhece.

    Existe para que ninguem deduza a eleicao vigente pela data nem pelo ano.
    O id NAO e derivavel do ano: 2016 tem id 2, 2014 tem 680, 2026 tem
    20322002026. Deduzir aqui e errar com confianca.
    """
    dados, url, de_cache, _quando = obter("/divulga/rest/v1/eleicao/ordinarias",
                                          "eleicoes_ordinarias", pausa, forcar)
    itens = dados if isinstance(dados, list) else dados.get("eleicoes", [])
    hoje = datetime.now().strftime("%Y-%m-%d")
    print(f"Eleições ordinárias conhecidas pelo TSE (hoje: {hoje})")
    print(f"fonte: {url}  [{'cache' if de_cache else 'rede'}]\n")
    print(f"{'id':<14} {'ano':<6} {'data':<12} {'abrang':<8} descricao")
    futuras = []
    for e in sorted(itens, key=lambda x: str(x.get("dataEleicao") or ""), reverse=True):
        did = str(e.get("id", ""))
        ano = str(e.get("ano", ""))
        dt  = str(e.get("dataEleicao") or "")[:10]
        ab  = {"F": "federal", "M": "municipal"}.get(e.get("tipoAbrangencia"), e.get("tipoAbrangencia") or "?")
        marca = ""
        if dt >= hoje:
            futuras.append((dt, ano, ab, did)); marca = "  <- ainda nao aconteceu"
        print(f"{did:<14} {ano:<6} {dt:<12} {ab:<8} {e.get('nomeEleicao','')}{marca}")
    print()
    if futuras:
        dt, ano, ab, did = sorted(futuras)[0]
        print(f"VIGENTE: {ano}, {ab}, em {dt} (id {did})")
        if ab == "federal":
            print("  Abrangencia federal: a cedula e definida pela UF, nao pela cidade.")
            print("  Cargos: presidente, governador, senador, deputado federal e estadual.")
        elif ab == "municipal":
            print("  Abrangencia municipal: a cedula e definida pelo MUNICIPIO.")
            print("  Cargos: prefeito e vereador.")
    else:
        print("CALENDARIO VENCIDO: nenhuma eleicao futura neste arquivo.")
        print("  Nao deduza a proxima. Confira em tse.jus.br antes de seguir.")
    return 0


def main():
    p = argparse.ArgumentParser(description="Coletor de candidaturas do TSE.")
    p.add_argument("--plano", metavar="UF_OU_ID",
                   help=("UF: inventário de quem entregou plano de governo | ID: extrai o PDF. "
                         "Códigos: 0 achou, 1 candidato não entregou (é resposta, não erro), "
                         "2 falha de rede ou bloqueio."))
    p.add_argument("--frescor", metavar="ID",
                   help="compara a situação gravada com a situação da hora")
    p.add_argument("--idade", action="store_true",
                   help="diz a idade da base e RECUSA se passou do limite")
    p.add_argument("--reparar-datas", action="store_true",
                   help=("mostra coletado_em/coleta.quando gravados com o carimbo da "
                         "GRAVACAO em vez do da resposta do TSE (bug de cache corrigido "
                         "em 07/09/2026). Sozinho, so relata. Some com --aplicar para gravar."))
    p.add_argument("--eleicoes", action="store_true",
                   help="lista as eleições ordinárias e diz qual está vigente")
    p.add_argument("--pais", action="store_true",
                   help="coleta os 28 alvos (27 UFs + BR, a cédula presidencial). "
                        "Sai 2 se algum alvo falhar ou devolver tudo zero.")
    p.add_argument("--listar", metavar="UF", help="baixa a listagem de todos os cargos da UF")
    p.add_argument("--detalhe", metavar="ID", help="baixa a ficha de UM candidato")
    p.add_argument("--uf", default="MG", help="UF do --detalhe (padrão MG)")
    p.add_argument("--pausa", type=float, default=1.5,
                   help="segundos entre requisições (padrão 1.5; não baixe disso)")
    p.add_argument("--forcar", action="store_true", help="ignora o cache do dia")
    p.add_argument("--aplicar", action="store_true",
                   help="usado com --reparar-datas: grava a correcao (sem ele, so relata)")
    a = p.parse_args()
    if a.pausa < 1.5:
        print("AVISO: pausa abaixo de 1,5 s. Servidor público. Elevando para 1,5 s.")
        a.pausa = 1.5
    if a.reparar_datas:
        return cmd_reparar_datas(a.aplicar)
    if a.idade:
        return cmd_idade()
    if a.plano:
        return cmd_plano(a.plano, a.uf, a.pausa, a.forcar)
    if a.frescor:
        return cmd_frescor(a.frescor, a.uf, a.pausa)
    if a.eleicoes:
        return cmd_eleicoes(a.pausa, a.forcar) or 0
    if a.pais:
        return cmd_pais(a.pausa, a.forcar)
    if a.listar:
        cmd_listar(a.listar, a.pausa, a.forcar); return 0
    if a.detalhe:
        cmd_detalhe(a.detalhe, a.uf, a.pausa, a.forcar); return 0
    p.print_help()
    return 0

if __name__ == "__main__":
    # sys.exit(main()) e nao main(): um portao que diz RECUSADO e sai com
    # codigo 0 nao para script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
