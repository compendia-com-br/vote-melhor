#!/usr/bin/env python3
"""Controles do pacote do GPT personalizado: o tamanho e as seis guardas.

O CRITERIO 6 da especificacao (§10) diz: `INSTRUCOES.md` cabe em 8.000
caracteres e contem os seis itens de §6.4. Ate' agora isso era conferido por
um trecho de bash DENTRO do documento de plano, que alguem precisava lembrar
de rodar. Medido em 08/09/2026: o arquivo esta em 7.988 caracteres — doze
de folga. Com doze de folga, a proxima frase acrescentada estoura o limite,
e o limite nao e' estetico: o campo de instrucoes do GPT Builder corta em
8.000, entao passar disso significa que a guarda contra recomendar voto vai
para o ChatGPT com o fim cortado, e ninguem percebe pelo texto.

Portao que recusa vence aviso que lembra. Por isso este arquivo.

A ARMADILHA DA MEDICAO, que quase produziu um defeito falso:
`wc -m` NAO conta caracteres nesta maquina. A shell aqui nao tem locale
(LANG e LC_ALL vazios), e sem locale UTF-8 o `wc -m` do BSD cai para bytes —
devolve 8318, identico a `wc -c`, porque o arquivo tem 302 caracteres
multibyte (acento e travessao). Medido: `LC_ALL=en_US.UTF-8 wc -m` devolve
7988, e `len()` do Python sobre o texto decodificado tambem. A contagem que
vale e' a de CARACTERES, que e' como o campo do ChatGPT conta, e a unica
forma confiavel de obter aqui e' decodificar e medir em Python — que e' o
que este teste faz. Quem for conferir pelo terminal precisa exportar o
locale, ou vai ver um numero 4% maior e caçar um problema que nao existe.

As ancoras das seis guardas sao PARES de termos, nao um substring solto. O
medidor antigo procurava por "data" e por "cargo" — palavras que aparecem em
qualquer texto em portugues sobre eleicao, inclusive num arquivo de onde a
guarda tivesse sido removida. Par de termos especificos falha quando o item
sai; substring generico nao falha nunca, e portao que nunca falha nao e'
portao.

Este teste nao toca rede, banco nem a base real: le dois arquivos do repo.
"""
import os, sys

# Importar um modulo escreve .pyc ao lado dele. Bloqueamos antes de qualquer
# import de modulo do plugin — mesmo padrao dos outros testes deste projeto.
sys.dont_write_bytecode = True

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INSTRUCOES = os.path.join(RAIZ, "gpt", "INSTRUCOES.md")
LIMITE = 8000

falhas = []
def checa(nome, condicao, detalhe):
    print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
    if not condicao:
        falhas.append(nome)


def texto():
    """Decodifica explicitamente: e' a contagem de CARACTERES que vale, e ela
    so e' confiavel sobre o texto decodificado (ver a armadilha no topo)."""
    with open(INSTRUCOES, encoding="utf-8") as f:
        return f.read()


print("TAMANHO — o campo do GPT Builder corta em 8.000 caracteres")
t = texto()
n = len(t)
bytes_ = len(t.encode("utf-8"))
checa(f"cabe em {LIMITE} caracteres", n <= LIMITE,
      f"{n} caracteres, sobra {LIMITE - n}")
checa("a contagem foi em caracteres, nao em bytes (a diferenca importa)",
      bytes_ > n,
      f"{n} caracteres = {bytes_} bytes; {bytes_ - n} bytes a mais de multibyte")
# Aviso, nao falha: folga curta ainda cabe, mas quem for editar precisa saber.
if n > LIMITE - 200:
    print(f"  [nota] a folga e de {LIMITE - n} caracteres. Qualquer frase nova "
          f"estoura o limite — corte antes de acrescentar.")


print("AS SEIS GUARDAS — cada uma ancorada em DOIS termos, nao num substring solto")
b = t.lower()
guardas = [
    ("1. nao responder de memoria", ["de memória", "code interpreter"]),
    ("2. fato e alegacao separados", ["alegação", "fato"]),
    ("3. ficha limpa nao se deriva", ["135", "colegiado"]),
    # "recomend" casa recomende/recomendar; "mérito" e' o termo que a guarda
    # usa para o que ela proibe (nota, ranking, superlativo). O par foi
    # conferido contra o arquivo — a primeira tentativa usou "não decide",
    # que eu supus e nao existe la'.
    ("4. nao recomenda voto", ["recomend", "mérito"]),
    ("5. a data da base aparece", ["data da base", "véspera"]),
    ("6. promessa cabe no cargo", ["competência", "cargo"]),
]
for nome, termos in guardas:
    ausentes = [x for x in termos if x not in b]
    checa(nome, not ausentes,
          "presentes: " + ", ".join(repr(x) for x in termos) if not ausentes
          else f"AUSENTES: {ausentes}")


print("ARQUIVOS DO PACOTE — o que o COMO-PUBLICAR manda colar tem que existir")
for rel in ["gpt/INSTRUCOES.md", "gpt/DESCRICAO.md", "gpt/COMO-PUBLICAR.md",
            "gpt/conhecimento/FONTE.md", "gpt/conhecimento/candidatos-2026.csv"]:
    caminho = os.path.join(RAIZ, rel)
    existe = os.path.exists(caminho)
    checa(f"existe {rel}", existe,
          f"{os.path.getsize(caminho)} bytes" if existe else "AUSENTE")


print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
