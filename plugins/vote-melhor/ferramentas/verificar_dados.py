#!/usr/bin/env python3
"""Prova, por VALOR, que a base nao guarda CPF nem titulo de eleitor.

COMO RODAR:  python3 verificar_dados.py
             python3 verificar_dados.py --banco /caminho/outro.sqlite

O coletor descarta esses dois campos na ingestao, mas o filtro dele casa o
NOME da chave do JSON. Se o TSE renomear o campo, mudar de posicao, ou
mandar o numero dentro de outro campo, aquele filtro passa liso — e passar
liso produz exatamente a mesma saida de funcionar. Este script olha o valor.

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
            for coluna, valor in reg.items():
                if valor is None:
                    continue
                for seq in SEQ.findall(str(valor)):
                    tipo = ("cpf" if cpf_valido(seq)
                            else "titulo" if titulo_valido(seq) else None)
                    if tipo:
                        achados.append({"tabela": tabela, "coluna": coluna,
                                        "id": str(reg.get(chave)),
                                        "tipo": tipo, "valor": seq})
    cx.close()
    return achados


def main():
    ap = argparse.ArgumentParser(
        description="Varre a base atras de CPF e titulo de eleitor, por valor.")
    ap.add_argument("--banco", default=BANCO, help=f"padrao: {BANCO}")
    a = ap.parse_args()
    if not os.path.exists(a.banco):
        print(f"Banco nao encontrado: {a.banco}\n"
              f"Rode antes:  python3 coletar_tse.py --listar <UF>", file=sys.stderr)
        return 1
    achados = varrer(a.banco)
    print(f"Varredura por valor em {a.banco}")
    if not achados:
        print("Nenhum CPF e nenhum titulo de eleitor encontrado.")
        print("Isto e uma varredura por VALOR: nao depende do nome do campo.")
        return 0
    print(f"ACHOU {len(achados)} documento(s) de identificacao:\n")
    for a_ in achados:
        print(f"  {a_['tipo']:>6}  {a_['tabela']}.{a_['coluna']}  "
              f"id={a_['id']}  {a_['valor']}")
    print("\nEsses valores NAO podem sair em ficha, CSV nem pacote do GPT.")
    return 2


if __name__ == "__main__":
    # sys.exit(main()) e nao main(): portao que diz ACHOU e sai 0 nao para
    # script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
