#!/usr/bin/env python3
# exportar_gpt.py — gera o pacote de conhecimento do GPT personalizado.
#
# O QUE FAZ: lê o SQLite montado por coletar_tse.py e escreve dois arquivos em
# gpt/conhecimento/: candidatos-2026.csv (lista de permissão de 17 colunas) e
# FONTE.md (data da coleta, URL de origem, licença, contagem por UF e cargo).
# COMO RODAR:  python3 ferramentas/exportar_gpt.py
#
# NÃO EMBARCA NO PLUGIN: é ferramenta de quem mantém a base, não de quem usa
# o plugin. Roda uma vez por atualização de dado, e o CSV gerado é o arquivo
# que sobe para dentro do GPT — por isso vive em gpt/conhecimento/, gerado a
# cada rodada, NÃO versionado (.gitignore) — instalar o plugin clona o
# repositório inteiro, e quem só queria o plugin não pediu o dado. Também não
# fica em plugins/vote-melhor/ (o validador reprova dado embarcado no plugin).
#
# PORTÃO, NÃO AVISO. O ChatGPT não alcança o TSE — medido: 403 nos três
# endpoints, a cliente HTTP comum — então a base tem que ir como arquivo, e
# arquivo publicado dentro de um GPT público é IRREVERSÍVEL: não volta atrás.
# Por isso este script recusa (sai != 0) em dois pontos:
#   1) antes de tocar o banco, se verificar_dados.varrer() achar documento;
#   2) depois de escrever o CSV, relendo o ARQUIVO JÁ GRAVADO em disco com as
#      mesmas cpf_valido/titulo_valido — porque verificar a origem (o SQLite)
#      não é verificar a saída (o arquivo), e um erro de escrita poderia
#      concatenar campos de um jeito que a leitura do banco nunca revelaria.
#
# Códigos de saída: 0 gerado e limpo · 2 recusado (documento achado, na base
# ou no CSV recém-escrito) · 1 erro de uso (banco não encontrado, ou coluna
# da lista de permissão não existe mais na tabela).
import csv, os, sqlite3, sys

# Importar um módulo escreve .pyc ao lado dele. verificar_dados.py mora DENTRO
# do plugin (plugins/vote-melhor/ferramentas/), e o validador reprova qualquer
# artefato de build ali. Isto tem que vir ANTES do sys.path.insert e do
# import — este mesmo defeito já aconteceu nesta série (commit 9a612ca).
sys.dont_write_bytecode = True

RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ_REPO, "plugins", "vote-melhor", "ferramentas"))
import verificar_dados as vd
# consultar.vazio() e a MESMA regra que a ficha do plugin usa para imprimir
# "sem dado". Importada, nao copiada: se o CSV do GPT tivesse uma copia da
# regra, as duas derivariam em silencio. consultar.py e importavel — todo o
# codigo de CLI dele esta atras de `if __name__ == "__main__"`.
import consultar as cs

# O dado nunca mora dentro do plugin nem deste repositório: mesma resolução de
# consultar.py e coletar_tse.py. VOTE_MELHOR_DADOS sobrescreve — é o que o
# controle negativo deste script usa, para apontar a uma base própria e
# nunca tocar a base real ao provar que o portão recusa.
RAIZ_DADOS = os.environ.get("VOTE_MELHOR_DADOS") or os.path.join(
    os.path.expanduser("~"), ".local", "share", "vote-melhor")
BANCO = os.path.join(RAIZ_DADOS, "dados", "tse.sqlite")

DESTINO = os.path.join(RAIZ_REPO, "gpt", "conhecimento")
CSV_SAIDA = os.path.join(DESTINO, "candidatos-2026.csv")
FONTE_SAIDA = os.path.join(DESTINO, "FONTE.md")
CAMPOS_SAIDA = os.path.join(DESTINO, "CAMPOS.md")

URL_ORIGEM = "https://divulgacandcontas.tse.jus.br"
LICENCA = "Creative Commons Atribuição (CC BY)"
FRASE_VALIDADE = "Situação de candidatura muda até a véspera da eleição. Confira no TSE."

# LISTA DE PERMISSAO, nunca lista de proibicao. A tabela tem 101 colunas e o
# TSE acrescenta campo sem avisar. Uma lista de proibicao deixa passar por
# omissao tudo o que ainda nao foi nomeado — e o que passa por omissao aqui
# vai publicado num arquivo que qualquer pessoa baixa.
COLUNAS = ["id", "nomeUrna", "nomeCompleto", "numero", "partido_sigla",
           "nomeColigacao", "cargo_nome", "cargo_codigo", "ufCandidatura",
           "descricaoSituacao", "descricaoTotalizacao", "candidatoApto",
           "st_REELEICAO", "gastoCampanha", "eleicao_ano", "coletado_em",
           "fonte_url"]


def colunas_faltando(cx):
    """Confere as 17 colunas contra PRAGMA table_info ANTES de montar a
    query. Nome de coluna que não existe mais na tabela — o TSE renomeou, ou
    a lista foi digitada errado — não pode virar coluna vazia no CSV: isso
    aconteceria em silêncio se este código lesse a linha como dict e usasse
    .get(coluna, ""), e ninguém notaria uma coluna sempre vazia numa
    planilha de 20 mil linhas. A query explícita com SELECT "col1", "col2"
    já falharia com OperationalError nesse caso, mas com um traceback cru;
    esta checagem dá o nome da coluna que falta, antes de tentar."""
    existentes = {r[1] for r in cx.execute("PRAGMA table_info(candidatura)")}
    return [c for c in COLUNAS if c not in existentes]


def exportar(banco, destino_csv):
    """Lê candidatura pela lista de permissão e escreve o CSV. Devolve o
    total de linhas e a lista de ids na MESMA ordem em que foram escritas —
    usada só para a exclusão estrutural do id público na releitura abaixo,
    nunca para decidir o que entra no arquivo.

    CÉLULA VAZIA, NÃO VALOR FALSO. Todo valor passa por consultar.vazio() —
    a mesma regra que faz a ficha do plugin imprimir "sem dado" — e o que ela
    reprova sai como célula vazia. O caso que obriga isto: `gastoCampanha`
    vale "0.0" em 20.005 de 20.005 candidaturas (medido em 07/09/2026), porque
    o TSE ainda não publicou prestação de contas. O GPT lia esse zero como
    fato e imprimia "Gasto declarado de campanha: R$ 0,00" sobre pessoa real —
    medido, não suposto, no cenário 2 de testes/RED-gpt-2026-09-07.md.

    O conserto é aqui e não na prosa das instruções de propósito: regra que o
    modelo tem que lembrar é mais fraca que valor que não está no arquivo.

    A coluna FICA no cabeçalho — ela se preenche sozinha quando o TSE publicar
    as contas, e tirá-la agora obrigaria a mexer na lista de permissão depois.
    Medido nesta base: a regra esvazia 20.005 células, todas de gastoCampanha,
    e nenhuma célula de nenhuma das outras 16 colunas — ela é exatamente do
    tamanho do problema que resolve, não uma peneira geral."""
    cx = sqlite3.connect(banco)
    cx.row_factory = sqlite3.Row
    campos = ", ".join(f'"{c}"' for c in COLUNAS)
    linhas = cx.execute(
        f"SELECT {campos} FROM candidatura "
        f"ORDER BY ufCandidatura, cargo_nome, nomeUrna, id"
    ).fetchall()
    cx.close()

    os.makedirs(os.path.dirname(destino_csv), exist_ok=True)
    ids_por_linha = []
    with open(destino_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUNAS)
        for linha in linhas:
            w.writerow(["" if cs.vazio(linha[c]) else linha[c] for c in COLUNAS])
            ids_por_linha.append(str(linha["id"]))
    return len(linhas), ids_por_linha


def relatorio_pos_escrita(caminho_csv, ids_por_linha):
    """Rele o CSV JÁ GRAVADO EM DISCO, linha a linha — não os dados em
    memória — e testa toda sequência de 11 a 13 dígitos com cpf_valido/
    titulo_valido, exatamente como verificar_dados.varrer() testa o banco.

    Mesma exceção estrutural de varrer() (e de coletar_tse.py, commit
    f861440): uma sequência IGUAL ao "id" da PRÓPRIA linha não é documento
    vazado — é o identificador público de candidatura do TSE, que este
    projeto grava e imprime de propósito (é a primeira coluna da lista de
    permissão). Comparação por VALOR da linha, nunca por posição de coluna.

    Medido nesta base (20.005 candidaturas, 07/09/2026): sem esta exceção,
    60 ids batem por coincidência o dígito verificador de CPF e 48 o de
    título de eleitor (~0,5% do total, sem sobreposição entre os dois) — e
    a exportação seria recusada TODA VEZ, mesmo com a base limpa. Testado
    também: com a exceção aplicada, zero sequência sobra em qualquer uma
    das 17 colunas desta base — a exceção não é uma válvula de escape geral,
    ela é exatamente do tamanho do problema que resolve.

    Devolve achados como {arquivo, linha, coluna, id, tipo} — nunca o valor:
    uma ferramenta que denuncia vazamento não pode ela mesma ser o
    vazamento (a mesma razão do comentário em verificar_dados.main()).
    """
    achados = []
    with open(caminho_csv, encoding="utf-8") as fh:
        leitor = csv.reader(fh)
        cabecalho = next(leitor)
        for i, campos in enumerate(leitor):
            id_legitimo = ids_por_linha[i]
            for pos, valor in enumerate(campos):
                for seq in vd.SEQ.findall(str(valor)):
                    if seq == id_legitimo:
                        continue
                    tipo = ("cpf" if vd.cpf_valido(seq)
                             else "titulo" if vd.titulo_valido(seq) else None)
                    if tipo:
                        achados.append({
                            "arquivo": caminho_csv,
                            "linha": i + 2,  # 1 = cabeçalho
                            "coluna": cabecalho[pos],
                            "id": id_legitimo,
                            "tipo": tipo,
                        })
    return achados


def escrever_fonte(banco, caminho_md, total):
    """FONTE.md é GERADO, não escrito à mão: data mínima e máxima de coleta
    (que não são iguais — a coleta de 28 unidades levou tempo, com pausa
    obrigatória entre requisições), URL de origem, licença, e a contagem por
    UF e por cargo — a mesma prova por CONTEÚDO que este script confere,
    só que em formato de leitura.

    Conta também, coluna a coluna, quantas células saem VAZIAS no CSV — pela
    mesma consultar.vazio() que exportar() aplica. Isso é contado, não
    escrito à mão: no dia em que o TSE publicar a prestação de contas,
    `gastoCampanha` deixa de aparecer nesta seção sozinho, sem ninguém
    lembrar de editar o texto."""
    cx = sqlite3.connect(banco)
    minimo, maximo = cx.execute(
        "SELECT MIN(coletado_em), MAX(coletado_em) FROM candidatura").fetchone()
    cx.row_factory = sqlite3.Row
    campos = ", ".join(f'"{c}"' for c in COLUNAS)
    vazias = {c: 0 for c in COLUNAS}
    for linha in cx.execute(f"SELECT {campos} FROM candidatura"):
        for c in COLUNAS:
            if cs.vazio(linha[c]):
                vazias[c] += 1
    cx.row_factory = None
    por_uf = cx.execute(
        "SELECT ufCandidatura, COUNT(*) FROM candidatura "
        "GROUP BY ufCandidatura ORDER BY ufCandidatura").fetchall()
    por_cargo = cx.execute(
        "SELECT cargo_nome, COUNT(*) FROM candidatura "
        "GROUP BY cargo_nome ORDER BY cargo_nome").fetchall()
    cx.close()

    linhas = [
        "# Fonte dos dados — candidatos-2026.csv",
        "",
        "Gerado por `ferramentas/exportar_gpt.py`. Não editar à mão — para atualizar,",
        "rode `coletar_tse.py --pais` e depois `exportar_gpt.py` de novo.",
        "",
        f"- **Total de candidaturas:** {total}",
        f"- **Coleta:** de `{minimo}` até `{maximo}` (não é o mesmo instante — a "
        f"coleta cobre 28 unidades da federação, com pausa mínima obrigatória de "
        f"1,5 s entre requisições ao TSE)",
        f"- **Fonte:** Tribunal Superior Eleitoral (TSE), DivulgaCandContas — {URL_ORIGEM}",
        f"- **Licença:** {LICENCA}",
        "",
        f"> {FRASE_VALIDADE}",
        "",
        "## Candidaturas por UF",
        "",
        "| UF | candidaturas |",
        "|---|---:|",
    ]
    for uf, n in por_uf:
        linhas.append(f"| {uf} | {n} |")
    linhas += [
        "",
        "## Candidaturas por cargo",
        "",
        "| Cargo | candidaturas |",
        "|---|---:|",
    ]
    for cargo, n in por_cargo:
        linhas.append(f"| {cargo} | {n} |")

    # --- Célula vazia: o que ela quer dizer -------------------------------
    com_vazio = [(c, n) for c, n in vazias.items() if n]
    linhas += [
        "",
        "## Colunas que vêm vazias — vazio NÃO é zero",
        "",
        "**Célula vazia significa que o dado não existe nesta base.** Não é o valor zero,",
        "não é \"nenhum\", não é \"não declarou\". Nunca reporte célula vazia como valor,",
        "e nunca a use para comparar candidatos: o que falta aqui falta para todo mundo,",
        "e não diz nada sobre nenhuma pessoa em particular.",
        "",
    ]
    if com_vazio:
        linhas += [
            f"Contado nesta coleta, sobre as {total} candidaturas:",
            "",
            "| Coluna | células vazias |",
            "|---|---:|",
        ]
        for c, n in com_vazio:
            marca = " (100%)" if n == total else ""
            linhas.append(f"| `{c}` | {n}{marca} |")
        if vazias.get("gastoCampanha") == total and total:
            linhas += [
                "",
                "`gastoCampanha` vem vazia em **todas** as linhas porque o TSE ainda não",
                "publicou a prestação de contas desta eleição. A coluna fica no arquivo e se",
                "preenche sozinha quando as contas saírem. Enquanto isso, ela não é eixo de",
                "comparação: não existe candidato que gastou mais nem candidato que gastou",
                "menos nesta base — existe uma prestação de contas que ainda não foi publicada.",
            ]
    else:
        linhas.append("Nesta coleta, nenhuma das 17 colunas tem célula vazia.")
    linhas.append("")

    with open(caminho_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")


def escrever_campos(caminho, cx):
    """Grava a referencia dos tres campos de situacao, com as contagens VINDAS DA BASE.

    Por que gerado e nao escrito na instrucao: os numeros mudam a cada recoleta, e numero
    embutido em prosa apodrece calado — o proprio plano ja tinha esse risco anotado. E a
    instrucao tem teto de 8.000 caracteres; referencia nao disputa espaco com regra.

    O terceiro campo entrou depois de um caso real, em 09/09/2026: o dono do projeto abriu o
    site do TSE, leu "Concorrendo" e entendeu que a situacao do registro tinha mudado. Nao
    tinha — sao perguntas diferentes na mesma tela, e a instrucao so explicava duas delas.
    """
    def conta(sql, *a):
        return cx.execute(sql, a).fetchone()[0]

    total = conta("SELECT COUNT(*) FROM candidatura")
    linhas = [
        "# Os tres campos de situacao — o que cada um responde", "",
        f"Contagens medidas nesta base ({total} candidaturas). Sao TRES perguntas diferentes,",
        "e o site do TSE mostra as tres na mesma tela. Confundi-las e o erro mais facil aqui.",
        "",
        "## descricaoSituacao — o registro da candidatura ja foi julgado?", "",
    ]
    for sit, n in cx.execute(
            "SELECT descricaoSituacao, COUNT(*) FROM candidatura "
            "GROUP BY 1 ORDER BY 2 DESC"):
        linhas.append(f"- {n} — {sit}")
    linhas += ["", "## descricaoTotalizacao — os votos dele serao contados?", "",
               "**Nao e a mesma pergunta.** Uma candidatura pode estar aguardando julgamento e",
               "ainda assim aparecer como concorrendo: o registro nao foi decidido, e enquanto",
               "isso os votos contam. Ler `Concorrendo` como se fosse a situacao do registro e",
               "o erro que este arquivo existe para evitar.", ""]
    for tot, n in cx.execute(
            "SELECT descricaoTotalizacao, COUNT(*) FROM candidatura "
            "GROUP BY 1 ORDER BY 2 DESC"):
        linhas.append(f"- {n} — {tot}")
    linhas += ["", "## candidatoApto — o registro segue valendo agora?", "",
               "Soa em portugues como \"apto a ser eleito\". **Nao e isso.** Nao mede",
               "elegibilidade, nao mede vida pregressa, nao autoriza nenhum veredito.", ""]
    for sit, apto, n in cx.execute(
            "SELECT descricaoSituacao, candidatoApto, COUNT(*) FROM candidatura "
            "GROUP BY 1,2 ORDER BY 3 DESC"):
        linhas.append(f"- {n} — situacao \"{sit}\" com candidatoApto={apto}")
    linhas += ["",
               "Imprima sempre o valor literal dos tres, com a data de coleta. Nunca traduza",
               "nenhum deles para \"pode ser eleito\", \"esta elegivel\" ou o contrario disso."]
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return total


def main():
    if not os.path.exists(BANCO):
        print(f"Banco não encontrado: {BANCO}\n"
              f"Rode antes: python3 plugins/vote-melhor/ferramentas/coletar_tse.py --pais",
              file=sys.stderr)
        return 1

    # PORTAO, nao aviso. Exportar com documento dentro e irreversivel: o
    # arquivo vai para dentro de um GPT publico e sai do nosso alcance.
    achados = vd.varrer(BANCO)
    if achados:
        print(f"RECUSADO: {len(achados)} documento(s) de identificacao na base.",
              file=sys.stderr)
        print("Rode verificar_dados.py e trate antes de exportar.", file=sys.stderr)
        return 2

    cx = sqlite3.connect(BANCO)
    faltando = colunas_faltando(cx)
    cx.close()
    if faltando:
        print(f"RECUSADO: coluna(s) da lista de permissão não existem mais em "
              f"candidatura: {faltando}", file=sys.stderr)
        print("A tabela mudou desde que COLUNAS foi escrita. Confira o nome antes "
              "de ajustar a lista de permissão em exportar_gpt.py.", file=sys.stderr)
        return 1

    total, ids_por_linha = exportar(BANCO, CSV_SAIDA)

    # Releitura do ARQUIVO JA ESCRITO — verificar a origem nao e verificar a
    # saida. Se algo vazou, o arquivo dirty nao pode ficar no disco: arquivo
    # publicado nao volta atras, e deixa-lo ali e um commit de distancia de
    # sair para sempre.
    achados_csv = relatorio_pos_escrita(CSV_SAIDA, ids_por_linha)
    if achados_csv:
        linhas_achadas = sorted({a["linha"] for a in achados_csv})
        print(f"RECUSADO: {len(achados_csv)} documento(s) de identificacao no CSV "
              f"recem-escrito.", file=sys.stderr)
        for a in achados_csv[:10]:
            print(f"  {a['tipo']:>6}  {os.path.basename(a['arquivo'])}:linha={a['linha']}  "
                  f"coluna={a['coluna']}  id={a['id']}", file=sys.stderr)
        os.remove(CSV_SAIDA)
        print(f"{CSV_SAIDA} removido — arquivo publicado nao volta atras, nao pode "
              "ficar em disco com documento dentro.", file=sys.stderr)
        print(f"Linhas afetadas: {linhas_achadas[:10]}", file=sys.stderr)
        return 2

    escrever_fonte(BANCO, FONTE_SAIDA, total)


    cx = sqlite3.connect(BANCO)

    try:

        escrever_campos(CAMPOS_SAIDA, cx)

    finally:

        cx.close()

    print(f"Referencia dos campos: {CAMPOS_SAIDA}")
    print(f"Exportado: {total} candidatura(s) -> {CSV_SAIDA}")
    print(f"Fonte escrita em {FONTE_SAIDA}")
    return 0


if __name__ == "__main__":
    # sys.exit(main()) e nao main(): portao que diz RECUSADO e sai 0 nao
    # para script nenhum — e aviso fantasiado de recusa.
    sys.exit(main() or 0)
