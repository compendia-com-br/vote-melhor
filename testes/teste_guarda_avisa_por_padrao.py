#!/usr/bin/env python3
"""O padrao da guarda e AVISAR (decisao do Thiago, 30/09/2026), e quem quiser barrar declara.

Em PostToolUse a saida 2 nunca impediu a gravacao: o arquivo ja foi escrito quando o hook
roda (documentacao de hooks do Claude Code). O aviso que alguem ve sai em JSON no stdout,
com saida 0: `systemMessage` para o usuario, `additionalContext` para o Claude.
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
    ev = json.dumps({"tool_input": {"file_path": "/tmp/vote-melhor/x.md", "content": texto}})
    r = subprocess.run([sys.executable, HOOK], input=ev, capture_output=True, text=True, env=e)
    return r.returncode, r.stderr, r.stdout

RUIM = "O candidato Fulano e ficha limpa e tem o curriculo mais forte dos tres."
BOM  = "Situacao do registro    : Aguardando julgamento"

print("PADRAO — sem variavel nenhuma, a guarda AVISA")
cod, err, out = roda(RUIM)
checa("saida 0 na afirmacao proibida", cod == 0, f"saida={cod}")
try:
    d = json.loads(out)
except Exception:
    d = {}
checa("systemMessage para o usuario", "guarda de neutralidade" in d.get("systemMessage", ""))
hso = d.get("hookSpecificOutput", {})
checa("additionalContext para o Claude", hso.get("hookEventName") == "PostToolUse"
      and "guarda de neutralidade" in hso.get("additionalContext", ""))

print("\nPADRAO — saida legitima passa sem ruido")
cod, err, out = roda(BOM)
checa("saida 0 na ficha correta", cod == 0, f"saida={cod}")
checa("sem mensagem nenhuma", (err + out).strip() == "", f"{len(err + out)} bytes")

print("\nESTRITO — VOTE_MELHOR_ESTRITO=1 volta a recusar")
cod, err, _ = roda(RUIM, {"VOTE_MELHOR_ESTRITO": "1"})
checa("saida 2", cod == 2, f"saida={cod}")
checa("explica no stderr", "guarda de neutralidade" in err)

print("\nCOMPATIBILIDADE — VOTE_MELHOR_AVISAR=1 antigo segue avisando")
cod, _, _ = roda(RUIM, {"VOTE_MELHOR_AVISAR": "1"})
checa("saida 0", cod == 0, f"saida={cod}")

print("\nA GUARDA NAO PODE BARRAR A PROPRIA MANUTENCAO")
for rel in ("gpt/INSTRUCOES.md", "plugins/vote-melhor/hooks/verificar_saida.py",
            "plugins/vote-melhor/skills/fato-e-alegacao/SKILL.md",
            "testes/RED-gpt-2026-09-07.md", "README.md", "AVISO-LEGAL.md"):
    cam = os.path.join(RAIZ, rel)
    if not os.path.exists(cam):
        checa(f"{rel} (ausente)", False, "arquivo nao existe"); continue
    cod, _, out = roda(open(cam, encoding="utf-8").read())
    checa(rel, cod == 0 and not out.strip(), "" if not out.strip() else f"AVISOU: {out[:80]}")

print()
if falhas:
    print(f"REPROVADO: {len(falhas)} controle(s) — {falhas}")
    sys.exit(1)
print("Todos os controles corretos.")
sys.exit(0)
