#!/usr/bin/env python3
"""Varre TODO o historico do git — nao so a arvore atual — atras de CPF e
titulo de eleitor, por VALOR.

COMO RODAR:  python3 ferramentas/varrer_historico.py
             python3 ferramentas/varrer_historico.py --repo /outro/repositorio
             python3 ferramentas/varrer_historico.py --autoteste

O Passo 4 do plano de distribuicao publica (docs/superpowers/plans/
2026-09-07-distribuicao-publica.md) trazia isto como o portao antes de tornar
o repositorio publico:

    git log --all --numstat --format="%H" | grep -i "cpf|titulo|credencial|senha|token"

--numstat imprime NOME DE ARQUIVO e contagem de linhas adicionadas/removidas —
nunca o CONTEUDO do arquivo. O grep casava o NOME, nao o dado dentro dele: um
arquivo chamado "candidatos.csv" com um CPF de verdade dentro passava liso, e
um arquivo chamado "cpf-antigo.txt" vazio disparava. E uma varredura que nao
varre, rodando bem na frente do portao mais caro do plano.

Este script varre o CONTEUDO de cada blob de cada commit alcancavel por
qualquer ref (branch, tag, remoto rastreado) — inclusive um blob que so
existiu num commit e foi apagado num commit seguinte, que nao aparece em
nenhum grep sobre a arvore atual. Reaproveita cpf_valido() e titulo_valido()
de verificar_dados.py: e a mesma conta que ja prova que o SQLite local esta
limpo, aplicada agora ao historico do git.

Nunca imprime o documento encontrado por extenso — a ferramenta que caça
vazamento nao pode ela mesma virar o vazamento (este projeto ja cometeu esse
erro uma vez, em verificar_dados.py; ver o comentario acima do print em
main() daquele arquivo). Cada achado sai com o valor mascarado, relatado por
commit, caminho e tipo.

DUAS EXCLUSOES ESTRUTURAIS — e por que elas NAO afrouxam a varredura
--------------------------------------------------------------------
Medido em 08/09/2026, no historico real deste repositorio: 121 achados
brutos, ZERO documentos de verdade. 108 eram o `id` publico de candidatura
do TSE, dentro do blob de gpt/conhecimento/candidatos-2026.csv de quando o
CSV ainda era versionado — 60 casando por coincidencia o digito verificador
de CPF e 48 o de titulo. Os outros 13 eram o CPF sintetico que os proprios
controles deste projeto injetam de proposito.

Portao que recusa sempre e portao que alguem aprende a ignorar — e no dia em
que houver um documento de verdade, ele ja nao protege. Por isso este script
ganhou as mesmas exclusoes que exportar_gpt.relatorio_pos_escrita() e
verificar_dados.varrer() ja aplicavam, com tres travas para que exclusao nao
vire valvula de escape:

  1) A exclusao do `id` e POR VALOR DA PROPRIA LINHA, nunca por posicao nem
     por nome de coluna. So vale dentro de um blob que seja CSV com uma
     coluna "id" no cabecalho, e so perdoa a sequencia que for exatamente
     igual ao id daquela linha. A MESMA sequencia, noutra linha ou noutra
     coluna, e achado. Medido naquele blob de 20.005 linhas: as 108
     exclusoes sairam TODAS da coluna "id", uma por linha, e nenhuma das
     outras 16 colunas perdeu uma unica sequencia — a exclusao e exatamente
     do tamanho do problema que resolve, nao uma peneira geral.
  2) A lista de exemplos sinteticos e curta, escrita por extenso e travada
     pelo --autoteste: cresce-la tem que ser uma decisao, nunca um efeito
     colateral.
  3) TODA exclusao e CONTADA e IMPRESSA, por caminho, mesmo quando o
     resultado final e "limpo". Exclusao que ninguem conta e exclusao que
     ninguem audita.

Codigos: 0 limpo · 2 achou documento · 1 erro de uso ou repositorio invalido.
--autoteste sai 0 se os controles passarem, 1 se a varredura nao for confiavel.
"""
import argparse
import csv
import io
import os
import subprocess
import sys
import tempfile

# Importar modulo do plugin escreve .pyc ao lado dele. Bloqueamos antes de
# manipular sys.path e fazer o import — mesmo padrao de testes/teste_*.py.
sys.dont_write_bytecode = True
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_REPO_PADRAO = os.path.dirname(_AQUI)
sys.path.insert(0, os.path.join(_RAIZ_REPO_PADRAO, "plugins", "vote-melhor", "ferramentas"))
import verificar_dados as vd  # noqa: E402  (import depois do sys.path de proposito)


# Numeros que passam na conta de digito verificador e NAO pertencem a
# ninguem: este repositorio os injeta de proposito como controle. Um portao
# que acusa o proprio controle acusa todos os dias, ate alguem parar de ler.
#
# A exclusao e por VALOR EXATO — nunca por caminho de arquivo, nunca por nome
# de coluna. Filtrar por nome e exatamente o defeito que este script veio
# consertar; se ele passasse a perdoar "o que estiver em testes/", herdaria o
# defeito de volta pela porta dos fundos.
#
# Para uma entrada existir aqui, as tres condicoes valem juntas:
#   1) o numero e publicado como exemplo em documentacao publica — nao e de
#      ninguem, e ja circula fora deste repositorio;
#   2) este repositorio o injeta como controle, em codigo ou em plano — nao
#      chegou aqui por acidente de coleta;
#   3) esta escrito abaixo por extenso, com o motivo ao lado.
#
# O --autoteste TRAVA o tamanho desta lista. Crescer a lista reprova o
# autoteste ate alguem mexer no controle de proposito — que e o ponto: um
# terceiro numero perdoado tem que passar por uma decisao, nao por um commit
# distraido.
EXEMPLOS_SINTETICOS = {
    "52998224725": (
        "CPF de exemplo de documentacao publica brasileira (digitos "
        "verificadores corretos, sem dono). Injetado de proposito como "
        "controle positivo em testes/teste_verificar_dados.py e citado no "
        "plano docs/superpowers/plans/2026-09-07-distribuicao-publica.md."
    ),
}

# Rotulos das exclusoes. Ficam em constante porque aparecem em tres lugares
# (contagem, impressao e autoteste) e um erro de digitacao num deles
# esconderia uma coluna inteira do relatorio.
EXC_ID_DA_LINHA = "id da PROPRIA linha (CSV com coluna id)"
EXC_EXEMPLO = "exemplo sintetico declarado"


def _git(repo, *args, entrada=None):
    """Roda git no repositorio `repo`. `entrada`, quando dado, vai para o
    stdin (usado pelo --batch). Devolve stdout em bytes."""
    r = subprocess.run(["git", "-C", repo, *args], input=entrada,
                        capture_output=True)
    if r.returncode != 0:
        erro = r.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} falhou: {erro}")
    return r.stdout


def _objetos_alcancaveis(repo):
    """(sha, caminho) de todo objeto alcancavel por QUALQUER ref — nao so o
    HEAD atual. `--all` e o que torna isto uma varredura de historico e nao
    de arvore: inclui branch abandonado, tag, e commit que só um remoto
    rastreado ainda enxerga. Caminho vem vazio para commit e para a arvore
    raiz; blob e arvore normalmente vem com caminho."""
    saida = _git(repo, "rev-list", "--objects", "--all").decode("utf-8", "replace")
    pares = []
    for linha in saida.splitlines():
        if not linha:
            continue
        partes = linha.split(" ", 1)
        sha = partes[0]
        caminho = partes[1] if len(partes) > 1 else ""
        pares.append((sha, caminho))
    return pares


def _tipos(repo, shas):
    """git cat-file --batch-check: um sha por linha de entrada, um tipo por
    linha de saida, na mesma ordem — sem um subprocesso por objeto."""
    entrada = ("\n".join(shas) + "\n").encode("utf-8") if shas else b""
    saida = _git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype)",
                 entrada=entrada).decode("utf-8", "replace")
    tipos = {}
    for linha in saida.splitlines():
        campos = linha.split(" ")
        if len(campos) >= 2 and campos[1] != "missing":
            tipos[campos[0]] = campos[1]
    return tipos


def _conteudo_dos_blobs(repo, shas_blob):
    """git cat-file --batch: le o CONTEUDO de cada blob pedido, num so
    processo. Cada objeto sai como '<sha> blob <tamanho>\\n<tamanho bytes>\\n'.
    O parsing usa o primeiro '\\n' para achar o fim do cabecalho (o
    cabecalho e sempre texto puro, o conteudo binario vem depois dele, nunca
    misturado)."""
    if not shas_blob:
        return {}
    entrada = ("\n".join(shas_blob) + "\n").encode("utf-8")
    bruto = _git(repo, "cat-file", "--batch", entrada=entrada)
    conteudos = {}
    i = 0
    while i < len(bruto):
        fim_cab = bruto.index(b"\n", i)
        cabecalho = bruto[i:fim_cab].decode("utf-8", "replace").split(" ")
        sha, tamanho = cabecalho[0], int(cabecalho[2])
        inicio = fim_cab + 1
        conteudos[sha] = bruto[inicio:inicio + tamanho]
        i = inicio + tamanho + 1  # +1 pula o '\n' que o git acrescenta apos cada bloco
    return conteudos


def _commits_de(repo, caminho, sha_blob):
    """So chamado para um achado: em quais commits este blob aparece neste
    caminho. Caro (um `ls-tree` por commit candidato) de proposito restrito
    aos poucos achados — nunca ao historico inteiro, que e varrido uma vez
    so via _conteudo_dos_blobs."""
    if not caminho:
        return ["(objeto sem caminho — arvore ou commit solto)"]
    saida = _git(repo, "log", "--all", "--format=%H", "--", caminho).decode(
        "utf-8", "replace")
    commits = [c for c in saida.splitlines() if c]
    achados_em = []
    for c in commits:
        r = subprocess.run(["git", "-C", repo, "ls-tree", c, "--", caminho],
                            capture_output=True, text=True)
        if sha_blob in r.stdout:
            achados_em.append(c[:12])
    return achados_em or ["(commit nao identificado)"]


def _classificar(seq):
    """cpf, titulo, ou None. Mesma conta de verificar_dados.varrer()."""
    return ("cpf" if vd.cpf_valido(seq)
            else "titulo" if vd.titulo_valido(seq) else None)


def csv_com_coluna_id(texto):
    """Reconhece um blob em formato CSV cujo cabecalho tenha uma coluna "id",
    e devolve (cabecalho, linhas de dados). Devolve None quando o blob NAO e
    esse formato — e None e o caminho ESTRITO: o chamador volta a varrer o
    texto cru e nenhuma sequencia e perdoada.

    Toda duvida aqui devolve None de proposito. Errar para o lado estrito
    custa um alarme falso a conferir; errar para o outro lado custa um
    documento publicado. Por isso as guardas sao todas de reconhecimento, e
    nenhuma delas tenta "consertar" um arquivo torto:

      · byte nulo => nao e texto, nao e CSV;
      · cabecalho com menos de 2 campos => e um arquivo de texto qualquer,
        nao uma tabela (a linha 1 de quase todo arquivo vira "um campo so");
      · sem um campo exatamente "id" => nao ha coluna de identificador
        publico para excluir, entao nao se exclui nada. "ID" em maiuscula nao
        casa de proposito: o preco de nao casar e um alarme falso, e a
        alternativa (casar por aproximacao) e voltar a filtrar por nome;
      · menos da metade das linhas com a largura do cabecalho => nao e
        tabela, e um arquivo que por acaso comeca com uma linha parecida com
        cabecalho de CSV (codigo-fonte, por exemplo).
    """
    texto = texto.lstrip("\ufeff")  # CSV gravado com BOM ainda e CSV
    if "\x00" in texto:
        return None
    try:
        leitor = csv.reader(io.StringIO(texto, newline=""))
        cabecalho = next(leitor)
        linhas = [l for l in leitor if l]
    except (csv.Error, StopIteration):
        return None
    if len(cabecalho) < 2 or "id" not in cabecalho:
        return None
    if not linhas:
        return None
    casam = sum(1 for l in linhas if len(l) == len(cabecalho))
    if casam * 2 < len(linhas):
        return None
    return cabecalho, linhas


def analisar_blob(dado):
    """Varre o conteudo de UM blob. Devolve (achados, excluidos).

    achados:   [{"tipo", "seq", "coluna", "linha"}] — o que sobrou depois das
               exclusoes estruturais. "coluna" e "" fora de CSV.
    excluidos: {rotulo: quantidade} — o que foi perdoado, contado. O chamador
               imprime esses numeros mesmo num resultado limpo.
    """
    texto = dado.decode("utf-8", "replace")
    achados = []
    excluidos = {EXC_ID_DA_LINHA: 0, EXC_EXEMPLO: 0}

    def olhar(valor, coluna, num_linha, id_legitimo):
        """id_legitimo=None significa SEM PERDAO nesta linha."""
        for seq in vd.SEQ.findall(valor):
            tipo = _classificar(seq)
            if not tipo:
                continue
            # Igualdade EXATA com o id desta linha — a mesma regra de
            # exportar_gpt.relatorio_pos_escrita(). "12345678901" numa celula
            # que vale "id: 12345678901" nao e o id da linha: e um numero
            # dentro de outro texto, e continua sendo achado.
            if id_legitimo is not None and seq == id_legitimo:
                excluidos[EXC_ID_DA_LINHA] += 1
                continue
            if seq in EXEMPLOS_SINTETICOS:
                excluidos[EXC_EXEMPLO] += 1
                continue
            achados.append({"tipo": tipo, "seq": seq,
                            "coluna": coluna, "linha": num_linha})

    tabela = csv_com_coluna_id(texto)
    if tabela is None:
        olhar(texto, "", 0, None)
        return achados, excluidos

    cabecalho, linhas = tabela
    pos_id = cabecalho.index("id")
    for valor in cabecalho:  # o cabecalho tambem se varre, e sem perdao
        olhar(valor, "(cabecalho)", 1, None)
    for i, campos in enumerate(linhas):
        num_linha = i + 2  # 1 = cabecalho
        if len(campos) != len(cabecalho):
            # Linha que nao casa com a largura do cabecalho nao e linha de
            # tabela confiavel. Sem id_legitimo, nada nela e perdoado.
            for valor in campos:
                olhar(valor, "(linha fora do formato)", num_linha, None)
            continue
        id_legitimo = campos[pos_id]
        for pos, valor in enumerate(campos):
            olhar(valor, cabecalho[pos], num_linha, id_legitimo)
    return achados, excluidos


def varrer_historico(repo):
    """Devolve (achados, exclusoes) do historico inteiro do repositorio git
    em `repo`. Lista de achados vazia = historico limpo.

    Cada achado: {"commits", "caminho", "linha", "coluna", "tipo",
    "valor_mascarado"} — nunca o documento por extenso.
    exclusoes: {rotulo: {caminho: quantidade}} — o que foi perdoado e onde.
    """
    pares = _objetos_alcancaveis(repo)
    tipos = _tipos(repo, [sha for sha, _ in pares])
    shas_blob = sorted({sha for sha, _ in pares if tipos.get(sha) == "blob"})
    conteudos = _conteudo_dos_blobs(repo, shas_blob)

    achados = []
    exclusoes = {EXC_ID_DA_LINHA: {}, EXC_EXEMPLO: {}}
    cache_por_blob = {}  # sha -> (achados, excluidos) — um blob identico repetido
    # em varios caminhos/commits (arquivo copiado, ou nunca mudou) e analisado
    # uma vez so, nao uma vez por aparicao.
    for sha, caminho in pares:
        dado = conteudos.get(sha)
        if dado is None:
            continue  # nao e blob (commit ou arvore) — ja filtrado por _tipos
        if sha not in cache_por_blob:
            cache_por_blob[sha] = analisar_blob(dado)
        do_blob, excluidos = cache_por_blob[sha]
        onde = caminho or "(sem caminho — objeto solto)"
        for rotulo, quantos in excluidos.items():
            if quantos:
                exclusoes[rotulo][onde] = exclusoes[rotulo].get(onde, 0) + quantos
        for a in do_blob:
            achados.append({
                "commits": _commits_de(repo, caminho, sha),
                "caminho": onde,
                "linha": a["linha"],
                "coluna": a["coluna"],
                "tipo": a["tipo"],
                "valor_mascarado": vd._prever_mascara(a["seq"], ""),
            })
    return achados, exclusoes


def _imprimir_exclusoes(exclusoes):
    """Imprime SEMPRE, inclusive num historico limpo. Exclusao silenciosa e
    valvula de escape: quem le "limpo" precisa ver, na mesma tela, quanta
    coisa foi perdoada e por que — do contrario a proxima pessoa a mexer
    nestas regras nao tem como notar que elas cresceram."""
    total = sum(sum(por_caminho.values()) for por_caminho in exclusoes.values())
    if not total:
        print("Exclusoes estruturais aplicadas: nenhuma.\n")
        return
    print(f"Exclusoes estruturais aplicadas: {total} sequencia(s) perdoada(s), "
          f"contadas abaixo.")
    for rotulo, por_caminho in exclusoes.items():
        soma = sum(por_caminho.values())
        if not soma:
            continue
        print(f"  {soma:>5}  {rotulo}")
        for caminho, quantos in sorted(por_caminho.items(),
                                       key=lambda kv: (-kv[1], kv[0])):
            print(f"         {quantos:>5}  {caminho}")
    print("Estes numeros TEM que ser explicaveis um a um, como qualquer "
          "achado.\n")


def _autoteste():
    """Controle positivo E negativo, num repositorio git temporario — nunca
    no repositorio de verdade. Varredura que acha zero e indistinguivel de
    varredura quebrada; por isso este modo PROVA que a varredura acharia um
    documento se houvesse um, antes de confiar no resultado "limpo" do
    repositorio real.

    O controle positivo commita um CPF sintetico e depois o REMOVE num
    segundo commit — a arvore atual do repositorio de teste fica limpa, e
    so o historico guarda o documento. E o cenario exato que --numstat sobre
    a arvore atual nunca pegaria, e a razao de este script existir.

    Desde que a varredura ganhou exclusoes estruturais, metade destes
    controles existe para vigiar as EXCLUSOES, nao a deteccao: uma exclusao
    larga demais reprova o mesmo portao que ela veio destravar, so que em
    silencio e do lado que custa caro.
    """
    falhas = []

    def checa(nome, condicao, detalhe):
        print(f"  [{'ok ' if condicao else 'FALHA'}] {nome}: {detalhe}")
        if not condicao:
            falhas.append(nome)

    # Controles positivos GERADOS, nunca escritos por extenso: um numero
    # escrito no codigo pode acabar em EXEMPLOS_SINTETICOS, e controle
    # perdoado pela exclusao que ele deveria vigiar nao vigia nada.
    cpf_apagado = vd.montar_cpf_sintetico("123456789")     # controle do historico
    cpf_em_coluna = vd.montar_cpf_sintetico("111444777")   # controle do CSV
    cpf_no_id = vd.montar_cpf_sintetico("222333444")       # simula o id do TSE
    cpf_sem_coluna_id = vd.montar_cpf_sintetico("987654321")
    declarado = sorted(EXEMPLOS_SINTETICOS)[0]

    gerados = [cpf_apagado, cpf_em_coluna, cpf_no_id, cpf_sem_coluna_id]
    masc = lambda v: vd._prever_mascara(v, "")

    with tempfile.TemporaryDirectory() as d:
        def git(*args):
            subprocess.run(["git", "-C", d, *args], capture_output=True, check=True)

        def escrever(nome, conteudo, mensagem):
            with open(os.path.join(d, nome), "w", encoding="utf-8") as fh:
                fh.write(conteudo)
            git("add", nome)
            git("commit", "-q", "-m", mensagem)

        git("init", "-q")
        git("config", "user.email", "autoteste@local")
        git("config", "user.name", "Autoteste varrer_historico")

        # 1) Documento commitado e DEPOIS apagado: some da arvore, fica no
        #    historico.
        caminho_sujo = os.path.join(d, "vazado.txt")
        escrever("vazado.txt", f"cpf do candidato anotado a mao: {cpf_apagado}\n",
                 "commit com documento sintetico (autoteste)")
        os.remove(caminho_sujo)
        git("add", "vazado.txt")
        git("commit", "-q", "-m", "remove o arquivo — some da arvore, nao do historico")

        # 2) Numeros que NAO sao documento: gasto de campanha (11 digitos, CPF
        #    invalido) e id de candidato do TSE (12 digitos, título invalido —
        #    a faixa de UF de "130002539775" e 97, fora de 01-28). Mesmos dois
        #    casos do controle negativo de testes/teste_verificar_dados.py.
        escrever("limpo.txt",
                 "gasto de campanha: 12345678901\nid candidato: 130002539775\n",
                 "commit sem documento (autoteste)")

        # 3) O CSV com coluna "id" — o formato do pacote do GPT. Tres linhas
        #    montadas para separar as tres coisas que a exclusao NAO pode
        #    confundir:
        #      linha 2: o id da propria linha bate CPF por coincidencia (e o
        #               caso real: 108 achados de 2026-09-08) => perdoado;
        #      linha 3: id limpo, documento numa OUTRA coluna => achado —
        #               este e o controle que impede a correcao de virar
        #               valvula de escape geral;
        #      linha 4: id limpo, e na coluna "anotacao" o MESMO numero que
        #               foi perdoado na linha 2 => achado, porque a exclusao
        #               e por linha e por valor, nunca por valor global.
        escrever("tabela.csv",
                 "id,nomeUrna,anotacao\n"
                 f"{cpf_no_id},FULANO,concorrendo\n"
                 f"10002544540,BELTRANO,{cpf_em_coluna}\n"
                 f"10002544541,CICRANO,{cpf_no_id}\n",
                 "commit com CSV no formato do pacote do GPT (autoteste)")

        # 4) CSV SEM coluna "id": nao ha identificador publico declarado,
        #    entao nao se perdoa nada — nem o primeiro campo.
        escrever("sem-id.csv",
                 "chave,nome\n"
                 f"{cpf_sem_coluna_id},FULANO\n",
                 "commit com CSV sem coluna id (autoteste)")

        # 5) O exemplo sintetico declarado, e ao lado dele um CPF que NAO
        #    esta declarado — no MESMO arquivo. A lista de exemplos nao pode
        #    virar um perdao por arquivo.
        escrever("exemplo.md",
                 f"CPF de exemplo publico: {declarado}\n"
                 f"outro numero qualquer: {cpf_em_coluna}\n",
                 "commit citando o exemplo sintetico declarado (autoteste)")

        achados, exclusoes = varrer_historico(d)

        def de(caminho):
            return [a for a in achados if a["caminho"] == caminho]

        tipos_achados = sorted({a["tipo"] for a in achados})
        arvore_atual_limpa = not os.path.exists(caminho_sujo)
        na_tabela = de("tabela.csv")
        colunas_na_tabela = sorted({a["coluna"] for a in na_tabela})
        mascaras_na_tabela = sorted({a["valor_mascarado"] for a in na_tabela})
        no_exemplo = de("exemplo.md")
        exc_id = exclusoes[EXC_ID_DA_LINHA]
        exc_ex = exclusoes[EXC_EXEMPLO]

        print("AUTOTESTE — prova que a varredura acharia um documento real\n")
        checa("controle positivo: acha o CPF sintetico mesmo apagado da arvore atual",
              "cpf" in tipos_achados, f"tipos achados={tipos_achados}")
        checa("a arvore ATUAL do repositorio de teste esta limpa "
              "(prova que o achado veio do historico, nao da arvore)",
              arvore_atual_limpa, f"arquivo ainda existe? {not arvore_atual_limpa}")
        checa("controle negativo: numero que nao e documento nao dispara",
              not de("limpo.txt"), f"achados em limpo.txt={len(de('limpo.txt'))}")

        print("\n  --- exclusao do id publico de candidatura (CSV com coluna id) ---")
        checa("o id da PROPRIA linha e perdoado (o caso dos 108 achados reais)",
              exc_id.get("tabela.csv") == 1,
              f"perdoados em tabela.csv={exc_id.get('tabela.csv')} (esperado 1)")
        checa("AINDA acha documento numa coluna que NAO e o id do CSV",
              "anotacao" in colunas_na_tabela,
              f"colunas com achado={colunas_na_tabela}")
        checa("o documento achado na coluna anotacao e o injetado ali "
              "(nao um id reclassificado)",
              masc(cpf_em_coluna) in mascaras_na_tabela,
              f"mascaras achadas={mascaras_na_tabela}")
        checa("o MESMO valor perdoado como id da linha 2 e ACHADO na coluna "
              "anotacao da linha 4 (exclusao e por linha, nao por valor global)",
              any(a["coluna"] == "anotacao" and a["linha"] == 4
                  and a["valor_mascarado"] == masc(cpf_no_id) for a in na_tabela),
              f"achados em tabela.csv={[(a['linha'], a['coluna']) for a in na_tabela]}")
        checa("exatamente 2 achados no CSV — nem o id perdoado a mais, nem "
              "um dos dois documentos a menos",
              len(na_tabela) == 2, f"achados em tabela.csv={len(na_tabela)}")
        checa("CSV SEM coluna id nao ganha perdao nenhum",
              len(de("sem-id.csv")) == 1 and "sem-id.csv" not in exc_id,
              f"achados={len(de('sem-id.csv'))} perdoados={exc_id.get('sem-id.csv', 0)}")

        print("\n  --- exclusao dos exemplos sinteticos declarados ---")
        checa("o exemplo declarado e perdoado",
              exc_ex.get("exemplo.md") == 1,
              f"perdoados em exemplo.md={exc_ex.get('exemplo.md')} (esperado 1)")
        checa("um CPF NAO declarado no MESMO arquivo continua sendo achado "
              "(a lista nao perdoa por arquivo)",
              len(no_exemplo) == 1
              and no_exemplo[0]["valor_mascarado"] == masc(cpf_em_coluna),
              f"achados em exemplo.md={[a['valor_mascarado'] for a in no_exemplo]}")
        checa("nenhum controle positivo deste autoteste esta na lista de "
              "exemplos perdoados (controle perdoado nao vigia nada)",
              not [c for c in gerados if c in EXEMPLOS_SINTETICOS],
              f"gerados={len(gerados)}, na lista={len([c for c in gerados if c in EXEMPLOS_SINTETICOS])}")
        checa("a lista de exemplos e curta e travada — crescer exige mexer "
              "aqui de proposito",
              len(EXEMPLOS_SINTETICOS) == 1,
              f"entradas={len(EXEMPLOS_SINTETICOS)} (travado em 1)")
        checa("toda entrada da lista e mesmo um documento valido e tem "
              "motivo escrito (entrada morta nao protege nada)",
              all(_classificar(v) and len(str(m)) > 40
                  for v, m in EXEMPLOS_SINTETICOS.items()),
              f"entradas conferidas={len(EXEMPLOS_SINTETICOS)}")

        print("\n  --- as exclusoes sao contadas, nunca silenciosas ---")
        total_exc = sum(sum(p.values()) for p in exclusoes.values())
        checa("a varredura devolve a contagem das exclusoes para o relatorio",
              total_exc == 2, f"total de exclusoes contadas={total_exc} (esperado 2)")

    print()
    if falhas:
        print(f"AUTOTESTE REPROVADO: {len(falhas)} controle(s) — {falhas}")
        print("A varredura NAO esta confiavel. Nao use o resultado dela no "
              "portao de publicacao ate corrigir.")
        return 1
    print("AUTOTESTE OK — a varredura acha o que precisa achar, e as "
          "exclusoes nao abriram porta.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Varre TODO o historico do git (nao so a arvore atual) "
                     "atras de CPF e titulo de eleitor, por valor.")
    ap.add_argument("--repo", default=_RAIZ_REPO_PADRAO,
                     help=f"repositorio a varrer (padrao: {_RAIZ_REPO_PADRAO})")
    ap.add_argument("--autoteste", action="store_true",
                     help="controle positivo e negativo, num repositorio git "
                          "temporario — nunca no repositorio real")
    a = ap.parse_args()

    if a.autoteste:
        return _autoteste()

    repo = os.path.abspath(a.repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"Nao e um repositorio git (sem .git): {repo}", file=sys.stderr)
        return 1

    print(f"Varredura por valor do HISTORICO INTEIRO em {repo}")
    print("(todo blob de todo commit alcancavel por qualquer ref — nao so a arvore atual)\n")
    try:
        achados, exclusoes = varrer_historico(repo)
    except RuntimeError as e:
        print(f"Erro ao rodar git: {e}", file=sys.stderr)
        return 1

    _imprimir_exclusoes(exclusoes)

    if not achados:
        print("Nenhum CPF e nenhum titulo de eleitor encontrado em nenhum "
              "commit alcancavel.")
        print("Rode com --autoteste antes de confiar neste resultado: "
              "varredura que acha zero e indistinguivel de varredura quebrada.")
        return 0

    print(f"ACHOU {len(achados)} documento(s) de identificacao no historico:\n")
    for a_ in achados:
        commits = ", ".join(a_["commits"])
        onde = (f"  linha={a_['linha']} coluna={a_['coluna']}"
                if a_["coluna"] else "")
        print(f"  {a_['tipo']:>6}  {a_['caminho']}{onde}  commit(s)={commits}  "
              f"{a_['valor_mascarado']}")
    print("\nEsses valores estao no historico do git, nao so na arvore atual.")
    print("Tornar o repositorio publico agora clonaria e indexaria isso para sempre.")
    return 2


if __name__ == "__main__":
    # sys.exit(main() or 0), nao main() solto: portao que diz ACHOU e sai 0
    # nao para script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
