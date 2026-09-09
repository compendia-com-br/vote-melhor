#!/usr/bin/env python3
"""Confere que toda fonte oficial que o produto cita EXISTE, e gera a lista para o GPT.

COMO RODAR:  python3 ferramentas/verificar_fontes.py
             python3 ferramentas/verificar_fontes.py --autoteste

Por que este script existe: em 09/09/2026 o GPT citou `www2.camara.leg.br` com acento —
`www2.câmara.leg.br` — um dominio que nao existe. A instrucao ja proibia montar URL por
palpite, e ele montou assim mesmo: proibicao sem alternativa nao segura falha de forma.

A correcao em tres camadas, e esta e a primeira:
  1. AQUI: a lista de fontes vive num lugar so, e um script prova que cada uma responde.
  2. O pacote do GPT leva essa lista como dado, entao citar vira consultar arquivo.
  3. O hook do Claude acusa URL de dominio oficial que nao esteja na lista.

Codigos: 0 todas respondem  ·  2 alguma nao responde  ·  1 erro de uso.
"""
import argparse, http.client, os, ssl, sys, urllib.parse

# As paginas que uma PESSOA abre — nao os endpoints de API que as ferramentas usam.
# Cada uma existe para responder uma pergunta que a ficha nao responde.
FONTES = [
    ("https://divulgacandcontas.tse.jus.br",
     "TSE — situacao da candidatura na hora, e a fonte de tudo que esta no CSV"),
    ("https://www.camara.leg.br",
     "Camara dos Deputados — atuacao de quem exerce mandato federal"),
    ("https://www25.senado.leg.br/web/senadores",
     "Senado Federal — senadores em exercicio"),
    ("https://www.tse.jus.br",
     "TSE — portal geral, calendario eleitoral e prestacao de contas"),
]

TEMPO = 20


def bater(url, tempo=TEMPO):
    """Devolve (codigo, detalhe). Sem biblioteca de terceiro, e sem seguir redirecionamento
    em silencio: 301/302 e resposta valida — o dominio existe, que e o que se afirma."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return 0, "esquema invalido"
    try:
        if p.scheme == "https":
            c = http.client.HTTPSConnection(p.netloc, timeout=tempo,
                                            context=ssl.create_default_context())
        else:
            c = http.client.HTTPConnection(p.netloc, timeout=tempo)
        c.request("GET", p.path or "/", headers={"User-Agent": "Mozilla/5.0"})
        r = c.getresponse()
        cod = r.status
        c.close()
        return cod, ""
    except Exception as e:
        return 0, f"{type(e).__name__}"


def esta_viva(cod):
    """A pergunta e "este endereco existe?", nao "eu consigo baixar?".

    Contam como VIVA: 2xx, 3xx (redireciona, logo o dominio serve) e 401/403 — recusa
    prova que ha servidor ali respondendo. Medido: tse.jus.br devolve 403 ao cliente comum,
    o mesmo anti-bot do resto do TSE, e o endereco e obviamente valido.

    NAO contam: 0 (o nome nao resolve — foi o caso do dominio acentuado) e 404 (o caminho
    nao existe), que sao exatamente as duas formas de inventar endereco.
    """
    return (200 <= cod < 400) or cod in (401, 403)


CAMINHO_ABSURDO = "/isto-nao-existe-em-lugar-nenhum-2026-vote-melhor"


def discrimina(host, tempo=TEMPO):
    """O dominio distingue caminho que existe de caminho inventado?

    Medido em 09/09/2026, e o resultado nao e uniforme:
      camara.leg.br e senado.leg.br  -> raiz 200, caminho inventado 404  = distingue
      tse.jus.br e divulgacandcontas -> 403 para tudo (anti-bot)         = nao distingue
      dadosabertos.camara.leg.br     -> 200 para tudo (API)              = nao distingue

    Onde nao distingue, verificar caminho e teatro: o servidor responde igual para o
    endereco certo e para o inventado. A saida honesta nao e "esta ok", e "so a raiz".
    """
    raiz, _ = bater(f"https://{host}/", tempo)
    absurdo, _ = bater(f"https://{host}{CAMINHO_ABSURDO}", tempo)
    return esta_viva(raiz) and not esta_viva(absurdo), raiz, absurdo


def escrever_lista(caminho, resultados):
    linhas = ["# Fontes oficiais — as unicas URLs que esta ferramenta cita", "",
              "Cada endereco abaixo foi buscado e respondeu no dia da geracao. **Nao cite URL",
              "que nao esteja nesta lista, e nao monte caminho dentro destes dominios:** o",
              "endereco muda, e o que voce inventa da 404 para quem confiou em voce.", ""]
    for url, porque, cod, disc in resultados:
        linhas.append(f"- {url}")
        linhas.append(f"  {porque} (respondeu {cod})")
        if disc:
            linhas.append("  Caminho interno pode ser conferido neste dominio.")
        else:
            linhas.append("  **Cite so este endereco, sem caminho depois dele.** Este servidor")
            linhas.append("  responde igual para rota certa e rota inventada — nao da para conferir.")
    linhas.append("")
    linhas.append("Para qualquer outra coisa, diga que nao tem a fonte — nunca invente o endereco.")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


def autoteste():
    """Controle positivo e negativo. Varredura que so aprova e indistinguivel de quebrada."""
    ok = True
    print("CONTROLE NEGATIVO — dominio que nao existe tem de reprovar")
    # o erro real medido: 'camara' com acento
    cod, det = bater("https://www2.xn--cmara-9ta.leg.br", tempo=8)
    passou = not esta_viva(cod)
    print(f"  [{'ok ' if passou else 'FALHA'}] dominio acentuado da Camara: codigo={cod} {det}")
    ok &= passou

    print("CONTROLE POSITIVO — dominio que existe tem de passar")
    cod, det = bater("https://www.tse.jus.br", tempo=TEMPO)
    passou = esta_viva(cod)
    print(f"  [{'ok ' if passou else 'FALHA'}] tse.jus.br: codigo={cod} {det}")
    ok &= passou

    print("CONTROLE NEGATIVO 2 — caminho que nao existe tem de reprovar")
    cod, det = bater("https://www.camara.leg.br/isto-nao-existe-em-lugar-nenhum-2026", tempo=15)
    passou = not esta_viva(cod)
    print(f"  [{'ok ' if passou else 'FALHA'}] caminho inventado: codigo={cod} {det}")
    ok &= passou

    print("CONTROLE DE FORMA — esquema invalido nao vira 'viva'")
    cod, _ = bater("ftp://exemplo.invalido")
    passou = not esta_viva(cod)
    print(f"  [{'ok ' if passou else 'FALHA'}] ftp:// recusado: codigo={cod}")
    ok &= passou
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser(description="Confere que as fontes oficiais existem.")
    ap.add_argument("--autoteste", action="store_true",
                    help="prova que o verificador acha o que precisa achar")
    ap.add_argument("--saida", default="gpt/conhecimento/FONTES.md",
                    help="onde gravar a lista para o pacote do GPT")
    a = ap.parse_args()
    if a.autoteste:
        return autoteste()

    print(f"Conferindo {len(FONTES)} fonte(s) oficial(is):\n")
    resultados, quebradas = [], []
    for url, porque in FONTES:
        cod, det = bater(url)
        viva = esta_viva(cod)
        print(f"  [{'ok ' if viva else 'FALHOU'}] {url:46} {cod if cod else det}")
        if viva:
            host = urllib.parse.urlparse(url).netloc
            disc, r_, a_ = discrimina(host)
            print(f"         distingue caminho inventado? {'sim' if disc else f'nao (raiz {r_}, inventado {a_})'}")
            resultados.append((url, porque, cod, disc))
        else:
            quebradas.append((url, cod or det))

    if quebradas:
        print(f"\n{len(quebradas)} fonte(s) nao responderam. A lista NAO foi gravada —")
        print("publicar endereco que nao abre e pior do que nao dar endereco nenhum.")
        for u, d in quebradas:
            print(f"  {u}  ->  {d}")
        return 2

    escrever_lista(a.saida, resultados)
    print(f"\nTodas responderam. Lista gravada em {a.saida}")
    print("Rode --autoteste antes de confiar: verificador que so aprova nao prova nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
