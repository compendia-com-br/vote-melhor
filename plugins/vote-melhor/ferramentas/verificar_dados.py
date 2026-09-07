#!/usr/bin/env python3
"""Prova, por VALOR, que a base nao guarda CPF nem titulo de eleitor.

COMO RODAR:  python3 verificar_dados.py
             python3 verificar_dados.py --banco /caminho/outro.sqlite
             python3 verificar_dados.py --limpar

O coletor descarta esses dois campos na ingestao, mas o filtro dele casa o
NOME da chave do JSON. Se o TSE renomear o campo, mudar de posicao, ou
mandar o numero dentro de outro campo, aquele filtro passa liso — e passar
liso produz exatamente a mesma saida de funcionar. Este script olha o valor.

--limpar mascara, no banco ja gravado, os documentos que a varredura achar.
E explicito: sem essa flag o script so relata. Nao mexe em dados/bruto/.

Codigos: 0 limpo · 2 achou documento · 1 erro de uso.
"""
import argparse, os, re, sqlite3, sys

RAIZ = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
BANCO = os.path.join(RAIZ, "dados", "tse.sqlite")

# Sequencias de digitos com 11 a 13 posicoes, isoladas por nao-digito. O
# recorte e largo de proposito: o custo de olhar um numero a mais e uma
# multiplicacao; o custo de nao olhar e um documento publicado.
SEQ = re.compile(r"(?<!\d)(\d{11,13})(?!\d)")


def cpf_valido(d):
    """Os dois digitos verificadores do CPF. Repeticao total (00000000000,
    11111111111...) passa na conta e NAO e CPF: e recusada antes."""
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * ((n + 1) - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def _dv_titulo(soma):
    """Resto 10 vira 0. SP (01) e MG (02) tem a variante em que resto 0 vira
    1; as duas sao aceitas, porque aqui falso positivo custa uma conferencia
    e falso negativo custa um documento publicado."""
    r = soma % 11
    return {0, 1} if r == 0 else ({0} if r == 10 else {r})


def titulo_valido(d):
    """Titulo de eleitor: 8 digitos de sequencial, 2 de UF (01 a 28), 2 de
    verificador. Aceita 12 ou 13 digitos (alguns estados grafam com zero a
    esquerda)."""
    if len(d) not in (12, 13):
        return False
    d = d[-12:]
    uf = int(d[8:10])
    if not 1 <= uf <= 28:
        return False
    if int(d[10]) not in _dv_titulo(sum(int(d[i]) * (i + 2) for i in range(8))):
        return False
    soma2 = int(d[8]) * 7 + int(d[9]) * 8 + int(d[10]) * 9
    return int(d[11]) in _dv_titulo(soma2)


def montar_titulo_sintetico(sequencial8, uf2):
    """Fabrica um titulo valido para servir de CONTROLE POSITIVO no teste.
    Existe aqui, e nao no teste, para que a mesma conta gere e verifique — um
    controle montado por outra conta nao prova nada sobre esta."""
    d = sequencial8 + uf2
    dv1 = min(_dv_titulo(sum(int(d[i]) * (i + 2) for i in range(8))))
    dv2 = min(_dv_titulo(int(d[8]) * 7 + int(d[9]) * 8 + dv1 * 9))
    return f"{d}{dv1}{dv2}"


MASCARA = "[documento removido]"


def mascarar_valor(texto, valor_chave):
    """Troca por MASCARA cada sequencia de 11 a 13 digitos que seja CPF ou
    titulo de eleitor validos dentro de `texto`, preservando o resto do
    valor em volta (por exemplo o nome do arquivo, fora do numero).

    Nunca mascara uma sequencia IGUAL a `valor_chave` — mesma regra
    estrutural usada em varrer(): a chave primaria da propria linha nao e
    documento, seja qual for a coluna onde o valor aparece. Esta funcao e
    compartilhada por coletar_tse.py (mascara na ingestao) e por --limpar
    (mascara o que ja esta gravado), para que as duas rotas apliquem
    exatamente a mesma regra em vez de reescrever a conta duas vezes."""
    def trocar(m):
        seq = m.group(1)
        if seq == valor_chave:
            return seq
        if cpf_valido(seq) or titulo_valido(seq):
            return MASCARA
        return seq
    return SEQ.sub(trocar, str(texto))


def _prever_mascara(texto, valor_chave):
    """Mesmo criterio de mascarar_valor, mas so para IMPRESSAO do --limpar:
    mostra 2+2 digitos do documento, nunca o numero inteiro na tela, e o
    resultado e visivelmente diferente da mascara real gravada no banco —
    para nao confundir a previa do 'antes' com o resultado do 'depois'."""
    def trocar(m):
        seq = m.group(1)
        if seq == valor_chave:
            return seq
        if cpf_valido(seq) or titulo_valido(seq):
            return seq[:2] + "*" * (len(seq) - 4) + seq[-2:]
        return seq
    return SEQ.sub(trocar, str(texto))


def _identificador_sql(nome):
    """Escapa nome de tabela/coluna para SQL (mesmo truque de coletar_tse.py:
    aspas duplas, sem aceitar aspas dentro do nome)."""
    return '"' + str(nome).replace('"', "") + '"'


def varrer(banco):
    """Devolve a lista de achados. Lista vazia = base limpa."""
    achados = []
    cx = sqlite3.connect(banco)
    cx.text_factory = lambda b: b.decode("utf-8", "replace")
    tabelas = [r[0] for r in cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for tabela in tabelas:
        cols = [r[1] for r in cx.execute(f"PRAGMA table_info({tabela})")]
        if not cols:
            continue
        chave = "id" if "id" in cols else cols[0]
        for linha in cx.execute(f"SELECT * FROM {tabela}"):
            reg = dict(zip(cols, linha))
            valor_chave = str(reg.get(chave))
            for coluna, valor in reg.items():
                if valor is None:
                    continue
                for seq in SEQ.findall(str(valor)):
                    # Um valor IGUAL a chave primaria da propria linha nao e
                    # documento vazado: e o id publico de candidatura do TSE
                    # (por exemplo candidatura.id), que este projeto grava e
                    # imprime de proposito em toda ficha. O teste compara o
                    # VALOR achado com o VALOR da chave desta linha — nunca
                    # o NOME da coluna. Filtrar por nome de campo e
                    # exatamente a fraqueza que este scanner existe para
                    # cobrir: se ele mesmo passasse a filtrar por nome de
                    # coluna, herdaria o defeito que veio consertar.
                    if seq == valor_chave:
                        continue
                    tipo = ("cpf" if cpf_valido(seq)
                            else "titulo" if titulo_valido(seq) else None)
                    if tipo:
                        achados.append({"tabela": tabela, "coluna": coluna,
                                        "id": str(reg.get(chave)),
                                        "tipo": tipo, "valor": seq})
    cx.close()
    return achados


def limpar(banco):
    """Mascara, no banco JA GRAVADO, os documentos que varrer() encontrar.

    Explicito, nunca automatico: so roda quando chamado com --limpar. Antes
    de alterar qualquer linha, imprime tabela, coluna, id e o valor antes e
    depois — com o documento tambem oculto na propria impressao, porque
    tela de terminal e saida, e a regra de nunca imprimir documento inteiro
    vale igual aqui.

    NUNCA toca dados/bruto/: o JSON como o TSE mandou fica ali de proposito
    (coletar_tse.py ja documenta que quem quiser sigilo total apaga essa
    pasta). Por isso, ao terminar, esta funcao sempre avisa que o bruto
    continua intacto — limpar o banco e deixar o bruto do jeito que estava
    e meia limpeza, e quem nao for avisado disso acha que acabou.
    """
    achados = varrer(banco)
    if not achados:
        print("--limpar: a varredura nao achou nada. Nada para mudar.")
        return 0

    celulas = sorted({(a["tabela"], a["coluna"], a["id"]) for a in achados})
    cx = sqlite3.connect(banco)
    cx.text_factory = lambda b: b.decode("utf-8", "replace")

    print(f"--limpar vai alterar {len(celulas)} celula(s):\n")
    alteradas = 0
    for tabela, coluna, id_linha in celulas:
        cols = [r[1] for r in cx.execute(f"PRAGMA table_info({tabela})")]
        chave = "id" if "id" in cols else cols[0]
        t_i = _identificador_sql(tabela)
        c_i = _identificador_sql(coluna)
        k_i = _identificador_sql(chave)
        linha = cx.execute(
            f"SELECT {c_i} FROM {t_i} WHERE {k_i} = ?", (id_linha,)).fetchone()
        if not linha or linha[0] is None:
            continue
        original = str(linha[0])
        depois = mascarar_valor(original, id_linha)
        if depois == original:
            continue
        antes_tela = _prever_mascara(original, id_linha)
        print(f"  {tabela}.{coluna}  id={id_linha}")
        print(f"    antes : {antes_tela}")
        print(f"    depois: {depois}")
        cx.execute(f"UPDATE {t_i} SET {c_i} = ? WHERE {k_i} = ?", (depois, id_linha))
        alteradas += 1
    cx.commit()
    cx.close()

    print(f"\n{alteradas} celula(s) alterada(s).")
    print("Conferindo de novo...")
    restantes = varrer(banco)
    if restantes:
        print(f"AINDA HA {len(restantes)} achado(s) apos a limpeza — nao ficou limpo.")
    else:
        print("Varredura de novo: limpo.")
    print()
    print("ATENCAO: dados/bruto/ NAO foi tocado. O JSON como o TSE mandou continua")
    print("la, com o documento original — isto e SO METADE da limpeza. Quem quiser")
    print("sigilo total precisa apagar dados/bruto/ tambem (coletar_tse.py ja")
    print("documenta esse caminho, no comentario acima de PROIBIDOS).")
    return 2 if restantes else 0


def main():
    ap = argparse.ArgumentParser(
        description="Varre a base atras de CPF e titulo de eleitor, por valor.")
    ap.add_argument("--banco", default=BANCO, help=f"padrao: {BANCO}")
    ap.add_argument("--limpar", action="store_true",
                     help="mascara os documentos ja gravados (explicito — sem isso so relata)")
    a = ap.parse_args()
    if not os.path.exists(a.banco):
        print(f"Banco nao encontrado: {a.banco}\n"
              f"Rode antes:  python3 coletar_tse.py --listar <UF>", file=sys.stderr)
        return 1
    if a.limpar:
        return limpar(a.banco)
    achados = varrer(a.banco)
    print(f"Varredura por valor em {a.banco}")
    if not achados:
        print("Nenhum CPF e nenhum titulo de eleitor encontrado.")
        print("Isto e uma varredura por VALOR: nao depende do nome do campo.")
        return 0
    print(f"ACHOU {len(achados)} documento(s) de identificacao:\n")
    for a_ in achados:
        # NUNCA a_['valor'] cru aqui: uma ferramenta que denuncia vazamento
        # nao pode ela mesma ser o vazamento. Medido: essa mesma linha, sem
        # mascara, botou um CPF real na tela e dali para dentro do relatorio
        # da tarefa, por inteiro, duas vezes. _prever_mascara mostra so 2
        # digitos no comeco e 2 no fim — da para LOCALIZAR o achado (tabela,
        # coluna, id, tipo) sem reconstituir o documento.
        print(f"  {a_['tipo']:>6}  {a_['tabela']}.{a_['coluna']}  "
              f"id={a_['id']}  {_prever_mascara(a_['valor'], a_['id'])}")
    print("\nEsses valores NAO podem sair em ficha, CSV nem pacote do GPT.")
    return 2


if __name__ == "__main__":
    # sys.exit(main()) e nao main(): portao que diz ACHOU e sai 0 nao para
    # script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
