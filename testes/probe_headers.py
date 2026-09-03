import urllib.request, urllib.error, gzip, zlib, io, time, json, os, sys

CONTADOR = "/Users/thiagoluz/claude/projetos/vote-melhor/testes/contador_requisicoes.txt"
def conta(url):
    n = 0
    if os.path.exists(CONTADOR):
        n = int(open(CONTADOR).read().strip() or 0)
    n += 1
    open(CONTADOR, "w").write(str(n))
    print(f"   [requisicao TSE #{n}] {url}")
    return n

COMPLETO = {
 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
 "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
 "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
 "Accept-Encoding": "gzip, deflate, br",
 "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
 "sec-ch-ua-mobile": "?0",
 "sec-ch-ua-platform": '"macOS"',
 "Sec-Fetch-Dest": "document",
 "Sec-Fetch-Mode": "navigate",
 "Sec-Fetch-Site": "none",
 "Sec-Fetch-User": "?1",
 "Upgrade-Insecure-Requests": "1",
 "Connection": "keep-alive",
}

URL = "https://dadosabertos.tse.jus.br/api/3/action/status_show"

def testa(rotulo, headers, pausa=1.5):
    time.sleep(pausa)
    conta(URL)
    req = urllib.request.Request(URL, headers=headers)
    # sem redirect handler custom; queremos so o codigo
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo = r.read()
            cod = r.status
            tam = len(corpo)
    except urllib.error.HTTPError as e:
        cod = e.code
        tam = len(e.read())
    except Exception as e:
        cod = f"ERRO {type(e).__name__}"
        tam = 0
    dt = time.time()-t0
    print(f"{cod:>6} | {tam:>7}B | {dt:5.2f}s | {rotulo}")
    return cod

if __name__ == "__main__":
    casos = json.loads(sys.argv[1])
    for rotulo, h in casos:
        testa(rotulo, h)
