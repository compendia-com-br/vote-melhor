#!/usr/bin/env python3
"""O padrao da guarda e BARRAR, e existe saida declarada para quem precisar so do aviso.

Por que mudou: o padrao era avisar, e o motivo escrito era que falso positivo em hook que
barra faz o usuario desligar o hook. Medido em 09/09/2026, esse motivo caiu:

  - a guarda nao dispara em saida legitima — tres fichas e o panorama de 24 KB, zero achados;
  - o que ela acusava eram documentos do proprio projeto que CITAM a construcao proibida, e
    isso foi corrigido em 3e313a9 (citar deixou de ser tratado como afirmar);
  - a ferramenta virou publica, e quem instala nao descobre sozinho uma variavel de ambiente.

O escape continua existindo, e de proposito: hook que nao deixa trabalhar e hook que o
usuario desinstala. VOTE_MELHOR_AVISAR=1 devolve o comportamento antigo, e tem de estar
escrito na propria mensagem — senao quem for barrado nao sabe o que fazer.
"""
import json, os, subprocess, sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOK = os.path.join(RAIZ, "plugins", "vote-melhor", "hooks", "verificar_saida.py")

falhas = []
def checa(nome, cond, detalhe=""):
    print(f"  [{'ok ' if cond else 'FALHA'}] {nome}{': ' + detalhe if detalhe else ''}")
    if not cond: falhas.append(nome)

def roda(texto, env=None):
    e = dict(os.environ); e.pop("VOTE_MELHOR_ESTRITO", None); e.pop("VOTE_MELHOR_AVISAR", None)
    e.update(env or {})
    ev = json.dumps({"tool_input": {"file_path": "/tmp/x.md", "content": texto}})
    r = subprocess.run([sys.executable, HOOK], input=ev, capture_output=True, text=True, env=e)
    return r.returncode, r.stderr

RUIM = "O candidato Fulano e ficha limpa e tem o curriculo mais forte dos tres."
BOM  = "Situacao do registro    : Aguardando julgamento"

print("PADRAO — sem variavel nenhuma, a guarda BARRA")
cod, err = roda(RUIM)
checa("saida 2 na afirmacao proibida", cod == 2, f"saida={cod}")
checa("a explicacao continua saindo", "guarda de neutralidade" in err, f"{len(err)} bytes")
checa("a mensagem ensina como seguir mesmo assim", "VOTE_MELHOR_AVISAR" in err,
      "" if "VOTE_MELHOR_AVISAR" in err else "quem for barrado nao sabe o que fazer")

print("\nPADRAO — saida legitima passa sem ruido")
cod, err = roda(BOM)
checa("saida 0 na ficha correta", cod == 0, f"saida={cod}")
checa("sem mensagem nenhuma", err.strip() == "", f"{len(err)} bytes")

print("\nESCAPE — VOTE_MELHOR_AVISAR=1 devolve o comportamento antigo")
cod, err = roda(RUIM, {"VOTE_MELHOR_AVISAR": "1"})
checa("saida 0 (avisa e deixa passar)", cod == 0, f"saida={cod}")
checa("mas continua explicando", "guarda de neutralidade" in err)

print("\nCOMPATIBILIDADE — quem ja usava VOTE_MELHOR_ESTRITO=1 nao quebra")
cod, _ = roda(RUIM, {"VOTE_MELHOR_ESTRITO": "1"})
checa("continua barrando", cod == 2, f"saida={cod}")

print("\nA GUARDA NAO PODE BARRAR A PROPRIA MANUTENCAO")
for rel in ("gpt/INSTRUCOES.md", "plugins/vote-melhor/hooks/verificar_saida.py",
            "plugins/vote-melhor/skills/fato-e-alegacao/SKILL.md",
            "testes/RED-gpt-2026-09-07.md", "README.md", "AVISO-LEGAL.md"):
    cam = os.path.join(RAIZ, rel)
    if not os.path.exists(cam):
        checa(f"{rel} (ausente)", False, "arquivo nao existe"); continue
    cod, err = roda(open(cam, encoding="utf-8").read())
    checa(rel, cod == 0, "" if cod == 0 else f"BARRADO: {err.splitlines()[1].strip()[:60]}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
