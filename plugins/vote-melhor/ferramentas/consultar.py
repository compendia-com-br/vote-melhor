#!/usr/bin/env python3
# consultar.py — lê o banco montado pelo coletar_tse.py. Não acessa a rede, nunca.
#
# O QUE FAZ: procura candidatos no banco local e imprime a ficha em FORMATO FIXO.
# COMO RODAR (da raiz de um clone; instalado, use ${CLAUDE_PLUGIN_ROOT}/ferramentas/):
#   python3 plugins/vote-melhor/ferramentas/consultar.py --uf MG --cargo "DEPUTADO FEDERAL"
#   python3 plugins/vote-melhor/ferramentas/consultar.py --nome "trecho do nome"
#   python3 plugins/vote-melhor/ferramentas/consultar.py --ficha <id>
# A ficha sai sempre com os mesmos campos, na mesma ordem, com "sem dado" onde faltar.
# Esse formato fixo é o contrato: o dossiê se apoia nele e não pode mudar de forma.

import argparse, os, sqlite3, sys, unicodedata

# Diretorio REAL deste arquivo. As mensagens de recuperacao montam o comando a
# partir daqui, e nao de um caminho escrito a mao: "ferramentas/x.py" nao
# existe a partir da raiz de um clone (os scripts moram em
# plugins/vote-melhor/ferramentas/) nem a partir de um plugin instalado. Uma
# mensagem de recuperacao que manda rodar um caminho inexistente deixa quem
# tropecou sem saida — o erro seguinte e igualzinho ao primeiro.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_IRMAO = lambda nome: os.path.join(_AQUI, nome)

# O dado NUNCA mora dentro do plugin. Plugin instalado é pacote somente-leitura,
# e escrever ali suja o pacote de quem comprou — além de o cache de plugin ser
# congelado por versão, então o dado sumiria a cada atualização.
# Destino: ~/.local/share/vote-melhor, ou VOTE_MELHOR_DADOS se definido.
RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
BANCO = os.path.join(RAIZ, "dados", "tse.sqlite")

SEM = "sem dado"

# O que o TSE grava querendo dizer "nao ha dado". Fica em constante de modulo,
# e nao escondido dentro de v(), porque ferramentas/exportar_gpt.py precisa da
# MESMA regra para escrever celula vazia no CSV que sobe para o GPT. Duas
# listas iguais em dois arquivos derivam sem dar erro nenhum: no dia em que uma
# mudasse, o GPT voltaria a afirmar "R$ 0,00" sobre pessoa real e nada acusaria.
VAZIOS = ("", "None", "null", "null-null", "0.0")

def vazio(x):
    """True quando o valor nao carrega informacao nenhuma.

    "0.0" entra na lista porque e o que o TSE grava em gastoCampanha enquanto
    nao ha prestacao de contas publicada — medido em 07/09/2026: 20.005 de
    20.005 candidaturas, 100%. Zero de gasto seria um fato sobre a campanha;
    ausencia de prestacao de contas nao e. Vazio nao e zero."""
    return x is None or str(x).strip() in VAZIOS

def limpar(texto):
    """minúsculas, sem acento e sem espaço duplicado — mesmo comportamento
    de limpar() em camara.py e senado.py. Faltava o .split()/" ".join() aqui:
    medido, "--cargo \"Deputado  Federal\"" (dois espaços) não casava
    "DEPUTADO FEDERAL" do banco e saía "Nenhum candidato encontrado." com
    código 0 — zero calado, não erro de sintaxe."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(sem_acento.split())

def abrir():
    if not os.path.exists(BANCO):
        print(f"Banco não encontrado em {BANCO}.\n"
              f"Rode antes:  python3 {_IRMAO('coletar_tse.py')} --listar MG",
              file=sys.stderr)
        sys.exit(1)
    cx = sqlite3.connect(BANCO)
    cx.row_factory = sqlite3.Row
    cx.create_function("limpar", 1, limpar)
    return cx

def colunas(cx, tabela):
    return {r[1] for r in cx.execute(f"PRAGMA table_info({tabela})")}

def v(linha, campo):
    """valor da coluna, ou o marcador de ausência. Nunca inventa, nunca interpreta."""
    if linha is None:
        return SEM
    try:
        x = linha[campo]
    except (IndexError, KeyError):
        return SEM
    return SEM if vazio(x) else str(x)

# ---------------------------------------------------------------------------
# FORMATO FIXO DA FICHA. Ordem e rótulos ficam aqui, no código, de propósito:
# quem chama o script não monta a forma. Campo novo entra nesta lista, e passa a
# valer para todas as fichas de uma vez. Situação sai com a string literal do TSE.
# ---------------------------------------------------------------------------
FICHA = [
    ("Nome de urna",           "l:nomeUrna"),
    ("Nome completo",          "l:nomeCompleto"),
    ("Número na urna",         "l:numero"),
    ("Cargo",                  "l:cargo_nome"),
    ("UF da candidatura",      "l:ufCandidatura"),
    ("Partido",                "l:partido_sigla"),
    ("Coligação/federação",    "l:nomeColigacao"),
    ("Situação do registro",   "l:descricaoSituacao"),
    ("Situação na totalização","l:descricaoTotalizacao"),
    ("Concorre à reeleição",   "l:st_REELEICAO"),
    ("Data de nascimento",     "d:dataDeNascimento"),
    ("Naturalidade",           "d:nomeMunicipioNascimento"),
    ("UF de nascimento",       "d:sgUfNascimento"),
    ("Sexo",                   "d:descricaoSexo"),
    ("Cor/raça",               "d:descricaoCorRaca"),
    ("Estado civil",           "d:descricaoEstadoCivil"),
    ("Grau de instrução",      "d:grauInstrucao"),
    ("Ocupação declarada",     "d:ocupacao"),
    ("Total de bens declarado","d:totalDeBens"),
    ("Gasto de campanha",      "d:gastoCampanha"),
    ("Motivo da situação",     "d:motivoSituacao"),
    ("Registro de mandato",    "m:cargo_nome"),
]

# A ausencia se declara por CATEGORIA, nunca em branco. Celula vazia num
# quadro comparativo e lida como "nao fez nada" — que e uma afirmacao, e uma
# que esta ferramenta nao pode sustentar.
COBERTURA_MANDATO = {
    "DEPUTADO FEDERAL": "Camara dos Deputados — use: camara.py --buscar",
    "SENADOR": "Senado Federal — use: senado.py --buscar",
    "GOVERNADOR": "sem fonte de registro de mandato para este cargo",
    "PRESIDENTE": "sem fonte de registro de mandato para este cargo",
    "DEPUTADO ESTADUAL": "sem fonte de registro de mandato para este cargo",
    "DEPUTADO DISTRITAL": "sem fonte de registro de mandato para este cargo",
}
SEM_FONTE = "sem fonte de registro de mandato para este cargo"

def cobertura_mandato(cargo):
    """Fonte do registro de mandato para o cargo, ou o texto de ausência
    declarada quando o cargo não tem fonte — nunca uma célula em branco.
    Normaliza acento e caixa dos dois lados com limpar(): "Deputado
    Distrital" vindo do banco não casa "DEPUTADO DISTRITAL" da tabela sem
    isso, e a falha cairia calada em SEM_FONTE sem ninguém perceber que
    caiu por defeito de comparação, e não por desenho."""
    alvo = limpar(cargo)
    for chave, fonte in COBERTURA_MANDATO.items():
        if limpar(chave) == alvo:
            return fonte
    return SEM_FONTE

def imprimir_ficha(lst, det):
    if lst is None and det is None:
        print("Candidato não encontrado no banco local.")
        return
    largura = max(len(r) for r, _ in FICHA)
    print("=" * 66)
    print("FICHA DE CANDIDATURA — dado do TSE, sem interpretação")
    print("=" * 66)
    for rotulo, chave in FICHA:
        onde, campo = chave.split(":", 1)
        if onde == "m":
            valor = cobertura_mandato(v(lst, campo))
        else:
            valor = v(lst if onde == "l" else det, campo)
            if valor == SEM and onde == "d" and det is None:
                valor = SEM + " (detalhe não coletado)"
        print(f"{rotulo:<{largura}} : {valor}")
    print("-" * 66)
    print("Fonte e data da coleta")
    print(f"  listagem : {v(lst,'fonte_url')}")
    print(f"             coletado em {v(lst,'coletado_em')}")
    print(f"  detalhe  : {v(det,'fonte_url')}")
    print(f"             coletado em {v(det,'coletado_em')}")
    print("  A situação acima é a string literal do TSE. Este script não classifica")
    print("  candidato, não deriva elegibilidade e não recomenda voto.")
    print("=" * 66)

def cmd_ficha(cx, ident):
    lst = cx.execute("SELECT * FROM candidatura WHERE id=?", (str(ident),)).fetchone()
    det = None
    if "detalhe" in {r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}:
        det = cx.execute("SELECT * FROM detalhe WHERE id=?", (str(ident),)).fetchone()
    imprimir_ficha(lst, det)

def linhas_tabela(rows):
    if not rows:
        print("Nenhum candidato encontrado.")
        return
    print(f"{'id':<14} {'nome de urna':<32} {'nº':>6} {'partido':<14} situação")
    for r in rows:
        print(f"{v(r,'id'):<14} {v(r,'nomeUrna')[:32]:<32} {v(r,'numero'):>6} "
              f"{v(r,'partido_sigla')[:14]:<14} {v(r,'descricaoSituacao')}")
    print(f"({len(rows)} linhas)")

def main():
    p = argparse.ArgumentParser(description="Consulta o banco local de candidaturas.")
    p.add_argument("--uf")
    p.add_argument("--cargo")
    p.add_argument("--nome")
    p.add_argument("--ficha")
    a = p.parse_args()
    cx = abrir()
    if a.ficha:
        cmd_ficha(cx, a.ficha)
    elif a.nome:
        alvo = limpar(a.nome)
        rows = cx.execute(
            "SELECT * FROM candidatura WHERE limpar(nomeUrna) LIKE ? "
            "OR limpar(nomeCompleto) LIKE ? ORDER BY nomeUrna",
            (f"%{alvo}%", f"%{alvo}%")).fetchall()
        linhas_tabela(rows)
    elif a.uf or a.cargo:
        sql = "SELECT * FROM candidatura WHERE 1=1"
        par = []
        if a.uf:
            sql += " AND uf_consultada = ?"; par.append(a.uf.upper())
        if a.cargo:
            sql += " AND limpar(cargo_nome) = ?"; par.append(limpar(a.cargo))
        rows = cx.execute(sql + " ORDER BY nomeUrna", par).fetchall()
        linhas_tabela(rows)
    else:
        p.print_help()
    cx.close()

if __name__ == "__main__":
    # sys.exit(main()) e nao main(): um portao que diz RECUSADO e sai com
    # codigo 0 nao para script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
