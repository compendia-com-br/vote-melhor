#!/usr/bin/env python3
# teste_juncao_por_nome.py — nome parecido nao pode ligar um candidato ao
# registro de OUTRA pessoa.
#
# Medido em 03/10/2026, cruzando os 944 candidatos aptos a deputado estadual de
# MG com os 77 deputados em exercicio da ALMG: dos 10 casamentos PARCIAIS, varios
# eram de outra pessoa — "SILVA" ia para Arnaldo Silva, "MARIA" para Maria Clara
# Marra, "LUIZINHO ABACAXI" e "LUIZINHO DO RETIRO" para Luizinho (PT), que tem
# candidatura propria com nome identico. No --cruzar, o eleitor veria as
# proposicoes de um deputado debaixo do nome de outro candidato.
#
# Na Camara e no Senado era pior: o parcial era por PEDACO de texto, nao por
# palavra — "ANA" casava dentro de "MARIANA".
#
# A regra: so nome IDENTICO liga registro. Nome parecido vira "parcial": aparece
# como possibilidade, nunca puxa registro. Nome de uma palavra so nao casa por
# semelhanca. Sem rede: tudo aqui e offline.
import os, sys
sys.dont_write_bytecode = True
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "plugins", "vote-melhor", "ferramentas"))
import almg
import criterios

falhas = []
def checa(nome, cond, detalhe=""):
    print(f"  [{'ok ' if cond else 'FALHA'}] {nome}{': ' + detalhe if detalhe else ''}")
    if not cond:
        falhas.append(nome)

def dep(i, nome):
    return {"id": i, "nome": nome, "partido": "X", "situacoes": []}

print("ALMG — casos reais de 03/10/2026")
ALMG = [dep(1, "Arnaldo Silva"), dep(2, "Maria Clara Marra"), dep(3, "Luizinho"),
        dep(4, "Leandro Genaro"), dep(5, "Mário Henrique Caixa")]
for nome in ("SILVA", "MARIA", "LUIZINHO ABACAXI", "LUIZINHO DO RETIRO"):
    e, a, m = almg.casar(nome, ALMG)
    checa(f"{nome!r} nao liga registro de ninguem", e != "achei", f"{e} — {m}")
e, a, m = almg.casar("LEANDRO GENARO JUNTOS SOMOS +", ALMG)
checa("nome mais longo que contem o deputado -> parcial, nao achei",
      e == "parcial" and [x["id"] for x in a] == [4], f"{e} — {m}")
e, a, m = almg.casar("MÁRIO HENRIQUE CAIXA", ALMG)
checa("nome identico continua ligando (controle positivo)", e == "achei" and a[0]["id"] == 5, m)
e, a, m = almg.casar("LUIZINHO", ALMG)
checa("nome identico de uma palavra liga (Luizinho e Luizinho)", e == "achei" and a[0]["id"] == 3, m)

print("\nCAMARA — o parcial era por pedaco de texto")
CAMARA = {"dados": [{"id": 10, "nome": "Mariana Exemplo"}, {"id": 11, "nome": "Fulano de Teste"}]}
original_get = criterios._get
try:
    criterios._get = lambda url: CAMARA
    reg, m = criterios.achar_deputado("ANA", "MG")
    checa("'ANA' nao casa dentro de 'MARIANA'", reg is None, m)
    reg, m = criterios.achar_deputado("FULANO DE TESTE JUNIOR", "MG")
    checa("parecido nao liga registro na Camara", reg is None and "Fulano de Teste" in m, m)
    reg, m = criterios.achar_deputado("FULANO DE TESTE", "MG")
    checa("identico liga na Camara (controle positivo)", reg is not None and reg["id"] == 11, m)
finally:
    criterios._get = original_get

print("\nSENADO — mesma regra")
SEN = {"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar": [
    {"IdentificacaoParlamentar": {"NomeParlamentar": "Mariana Exemplo", "CodigoParlamentar": "20"}},
    {"IdentificacaoParlamentar": {"NomeParlamentar": "Fulano de Teste", "CodigoParlamentar": "21"}}]}}}
original_pegar = criterios._senado.pegar
try:
    criterios._senado.pegar = lambda *a, **k: (SEN, "url", False, "agora")
    reg, m = criterios.achar_senador("ANA", "MG")
    checa("'ANA' nao casa dentro de 'MARIANA' no Senado", reg is None, m)
    reg, m = criterios.achar_senador("FULANO DE TESTE JUNIOR", "MG")
    checa("parecido nao liga registro no Senado", reg is None, m)
    reg, m = criterios.achar_senador("FULANO DE TESTE", "MG")
    checa("identico liga no Senado (controle positivo)",
          reg is not None and reg["IdentificacaoParlamentar"]["CodigoParlamentar"] == "21", m)
finally:
    criterios._senado.pegar = original_pegar

print()
if falhas:
    print(f"{len(falhas)} controle(s) falharam: {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
