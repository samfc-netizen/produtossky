
import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Sky - Estoque, Giro e Direcionamento", layout="wide")

ARQUIVOS_CANDIDATOS = [
    "Plano de ação sky.xlsx",
    "plano de ação sky.xlsx",
    "sky.xlsx",
]


def localizar_arquivo() -> str:
    base = Path(__file__).resolve().parent
    for nome in ARQUIVOS_CANDIDATOS:
        caminho = base / nome
        if caminho.exists():
            return str(caminho)
    raise FileNotFoundError(
        "Não encontrei a planilha. Deixe o arquivo 'Plano de ação sky.xlsx' na mesma pasta do app.py."
    )


@st.cache_data(show_spinner=False)
def carregar_dados():
    arquivo = localizar_arquivo()
    giro = pd.read_excel(arquivo, sheet_name="giro sky")
    estoque = pd.read_excel(arquivo, sheet_name="estoque sky")

    giro.columns = [str(c).strip() for c in giro.columns]
    estoque.columns = [str(c).strip() for c in estoque.columns]

    giro["DATA"] = pd.to_datetime(giro["DATA"], errors="coerce")
    giro["QTD"] = pd.to_numeric(giro["QTD"], errors="coerce").fillna(0)
    giro["UNIT"] = pd.to_numeric(giro["UNIT"], errors="coerce").fillna(0)
    giro["VR.TOTAL"] = pd.to_numeric(giro["VR.TOTAL"], errors="coerce").fillna(0)
    giro["CÓD"] = pd.to_numeric(giro["CÓD"], errors="coerce").astype("Int64")

    for col in ["LOJA", "CLIENTE", "CIDADE", "VEN", "DESCRIÇÃO"]:
        if col in giro.columns:
            giro[col] = giro[col].astype(str).str.strip()

    estoque["Cód.Item"] = pd.to_numeric(estoque["Cód.Item"], errors="coerce").astype("Int64")
    estoque["Saldo"] = pd.to_numeric(estoque["Saldo"], errors="coerce").fillna(0)

    estoque = estoque.rename(
        columns={
            "Cód.Item": "CODIGO",
            "Descrição": "DESCRICAO",
            "Saldo": "SALDO_UNICA",
        }
    )

    giro_prod = (
        giro.groupby("CÓD", dropna=True)
        .agg(
            QTD_VENDIDA=("QTD", "sum"),
            VALOR_VENDIDO=("VR.TOTAL", "sum"),
            LOJAS_COM_VENDA=("LOJA", "nunique"),
            CLIENTES_COM_COMPRA=("CLIENTE", "nunique"),
            ULTIMA_VENDA=("DATA", "max"),
        )
        .reset_index()
        .rename(columns={"CÓD": "CODIGO"})
    )

    produtos = estoque.merge(giro_prod, on="CODIGO", how="left")

    for col in ["QTD_VENDIDA", "VALOR_VENDIDO", "LOJAS_COM_VENDA", "CLIENTES_COM_COMPRA"]:
        produtos[col] = produtos[col].fillna(0)

    produtos["ULTIMA_VENDA"] = pd.to_datetime(produtos["ULTIMA_VENDA"], errors="coerce")
    produtos["CODIGO_TXT"] = produtos["CODIGO"].astype("Int64").astype(str)
    produtos["LABEL"] = produtos["CODIGO_TXT"] + " - " + produtos["DESCRICAO"].fillna("")

    produtos = produtos.sort_values(
        by=["SALDO_UNICA", "QTD_VENDIDA", "DESCRICAO"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    return giro, produtos


@st.cache_data(show_spinner=False)
def gerar_direcionamento(giro: pd.DataFrame, produtos: pd.DataFrame):
    registros = []
    detalhes_produto = {}

    for _, prod in produtos.iterrows():
        codigo = prod["CODIGO"]
        descricao = prod["DESCRICAO"]
        saldo = prod["SALDO_UNICA"]

        vendas_prod = giro[giro["CÓD"] == codigo].copy()

        if vendas_prod.empty:
            registros.append(
                {
                    "CODIGO": codigo,
                    "DESCRICAO": descricao,
                    "SALDO_UNICA": saldo,
                    "TOP1_LOJA": "Sem venda",
                    "TOP1_RESUMO": "Sem histórico de giro",
                    "TOP2_LOJA": "",
                    "TOP2_RESUMO": "",
                    "TOP3_LOJA": "",
                    "TOP3_RESUMO": "",
                    "QTD_TOTAL": 0,
                    "ULTIMA_VENDA": pd.NaT,
                }
            )
            detalhes_produto[int(codigo) if pd.notna(codigo) else codigo] = []
            continue

        resumo_lojas = (
            vendas_prod.groupby("LOJA", dropna=False)
            .agg(
                QTD_VENDIDA=("QTD", "sum"),
                VALOR_VENDIDO=("VR.TOTAL", "sum"),
                ULTIMA_VENDA=("DATA", "max"),
                CLIENTES=("CLIENTE", "nunique"),
            )
            .reset_index()
            .sort_values(
                by=["QTD_VENDIDA", "ULTIMA_VENDA", "VALOR_VENDIDO", "LOJA"],
                ascending=[False, False, False, True],
            )
            .reset_index(drop=True)
        )

        top_lojas = []
        for idx, loja_row in resumo_lojas.head(3).iterrows():
            loja = loja_row["LOJA"]
            vendas_loja = vendas_prod[vendas_prod["LOJA"] == loja].copy()

            clientes = (
                vendas_loja.groupby("CLIENTE", dropna=False)
                .agg(
                    QTD_CLIENTE=("QTD", "sum"),
                    VALOR_CLIENTE=("VR.TOTAL", "sum"),
                    ULTIMA_COMPRA=("DATA", "max"),
                    PRECO_MEDIO=("UNIT", "mean"),
                )
                .reset_index()
                .sort_values(
                    by=["QTD_CLIENTE", "ULTIMA_COMPRA", "VALOR_CLIENTE", "CLIENTE"],
                    ascending=[False, False, False, True],
                )
                .reset_index(drop=True)
            )

            clientes_top = []
            for _, cli_row in clientes.head(3).iterrows():
                data_txt = (
                    cli_row["ULTIMA_COMPRA"].strftime("%d/%m/%Y")
                    if pd.notna(cli_row["ULTIMA_COMPRA"])
                    else "-"
                )
                clientes_top.append(
                    {
                        "CLIENTE": cli_row["CLIENTE"],
                        "QTD": cli_row["QTD_CLIENTE"],
                        "ULTIMA_COMPRA": cli_row["ULTIMA_COMPRA"],
                        "ULTIMA_COMPRA_TXT": data_txt,
                        "VALOR_TOTAL": cli_row["VALOR_CLIENTE"],
                        "PRECO_MEDIO": cli_row["PRECO_MEDIO"],
                    }
                )

            cliente_resumo = " | ".join(
                [
                    f"{c['CLIENTE']} ({int(c['QTD'])} un | {c['ULTIMA_COMPRA_TXT']} | R$ {c['PRECO_MEDIO']:.2f})"
                    for c in clientes_top
                ]
            )

            top_lojas.append(
                {
                    "RANK": idx + 1,
                    "LOJA": loja,
                    "QTD_VENDIDA": loja_row["QTD_VENDIDA"],
                    "VALOR_VENDIDO": loja_row["VALOR_VENDIDO"],
                    "ULTIMA_VENDA": loja_row["ULTIMA_VENDA"],
                    "ULTIMA_VENDA_TXT": loja_row["ULTIMA_VENDA"].strftime("%d/%m/%Y") if pd.notna(loja_row["ULTIMA_VENDA"]) else "-",
                    "CLIENTES_TOP": clientes_top,
                    "RESUMO": f"{int(loja_row['QTD_VENDIDA'])} un | últ. venda {loja_row['ULTIMA_VENDA'].strftime('%d/%m/%Y') if pd.notna(loja_row['ULTIMA_VENDA']) else '-'} | {cliente_resumo}",
                }
            )

        row = {
            "CODIGO": codigo,
            "DESCRICAO": descricao,
            "SALDO_UNICA": saldo,
            "QTD_TOTAL": vendas_prod["QTD"].sum(),
            "ULTIMA_VENDA": vendas_prod["DATA"].max(),
            "TOP1_LOJA": "",
            "TOP1_RESUMO": "",
            "TOP2_LOJA": "",
            "TOP2_RESUMO": "",
            "TOP3_LOJA": "",
            "TOP3_RESUMO": "",
        }

        for pos, loja_info in enumerate(top_lojas, start=1):
            row[f"TOP{pos}_LOJA"] = loja_info["LOJA"]
            row[f"TOP{pos}_RESUMO"] = loja_info["RESUMO"]

        registros.append(row)
        detalhes_produto[int(codigo) if pd.notna(codigo) else codigo] = top_lojas

    ranking = pd.DataFrame(registros).sort_values(
        by=["QTD_TOTAL", "ULTIMA_VENDA", "SALDO_UNICA", "DESCRICAO"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    ranking["LABEL"] = ranking["CODIGO"].astype("Int64").astype(str) + " - " + ranking["DESCRICAO"].fillna("")
    return ranking, detalhes_produto


def distribuir_inteiros(total: int, pesos: list[float]) -> list[int]:
    if total <= 0 or not pesos:
        return [0] * len(pesos)

    soma = sum(pesos)
    if soma <= 0:
        return [0] * len(pesos)

    quotas = [(total * p) / soma for p in pesos]
    base = [int(q) for q in quotas]
    restante = total - sum(base)

    fracoes = sorted(
        [(i, quotas[i] - base[i]) for i in range(len(quotas))],
        key=lambda x: x[1],
        reverse=True,
    )

    for i in range(restante):
        idx = fracoes[i % len(fracoes)][0]
        base[idx] += 1

    return base


@st.cache_data(show_spinner=False)
def gerar_realocacao(giro: pd.DataFrame, produtos: pd.DataFrame):
    giro = giro.copy()
    giro["LOJA"] = giro["LOJA"].fillna("").astype(str).str.strip()

    produtos_base = produtos[["CODIGO", "DESCRICAO", "SALDO_UNICA", "LABEL"]].copy()

    vendas_loja_sku = (
        giro.groupby(["CÓD", "LOJA"], dropna=False)
        .agg(
            QTD_VENDIDA=("QTD", "sum"),
            VALOR_VENDIDO=("VR.TOTAL", "sum"),
            ULTIMA_VENDA=("DATA", "max"),
        )
        .reset_index()
        .rename(columns={"CÓD": "CODIGO"})
    )

    # lojas elegíveis para receber realocação: todas as lojas que tiveram venda histórica,
    # incluindo a própria ÚNICA quando houver tração nela.
    vendas_loja_sku = vendas_loja_sku[vendas_loja_sku["QTD_VENDIDA"] > 0].copy()

    base = produtos_base.merge(vendas_loja_sku, on="CODIGO", how="left")
    base["QTD_VENDIDA"] = base["QTD_VENDIDA"].fillna(0)
    base["VALOR_VENDIDO"] = base["VALOR_VENDIDO"].fillna(0)

    registros_gerais = []

    for codigo, grp in base.groupby("CODIGO", dropna=False):
        grp = grp.copy()
        saldo = float(grp["SALDO_UNICA"].iloc[0]) if pd.notna(grp["SALDO_UNICA"].iloc[0]) else 0
        saldo_int = int(round(saldo))

        if saldo_int <= 0:
            continue

        grp_valid = grp[grp["LOJA"].notna() & (grp["LOJA"].astype(str).str.strip() != "")]
        grp_valid = grp_valid[grp_valid["QTD_VENDIDA"] > 0].copy()

        if grp_valid.empty:
            continue

        pesos = grp_valid["QTD_VENDIDA"].tolist()
        alocacoes = distribuir_inteiros(saldo_int, pesos)
        grp_valid["SUGESTAO_REALOCAR"] = alocacoes

        total_vendido = grp_valid["QTD_VENDIDA"].sum()
        grp_valid["PCT_PARTICIPACAO"] = grp_valid["QTD_VENDIDA"] / total_vendido if total_vendido > 0 else 0

        # Cliente mais representativo e mais recente por loja/SKU
        # Aqui a ÚNICA também entra quando ela teve tração no histórico.
        vendas_prod = giro[giro["CÓD"] == codigo].copy()
        clientes_loja = (
            vendas_prod.groupby(["LOJA", "CLIENTE"], dropna=False)
            .agg(
                QTD_CLIENTE=("QTD", "sum"),
                VALOR_TOTAL=("VR.TOTAL", "sum"),
                ULTIMA_COMPRA=("DATA", "max"),
                PRECO_MEDIO=("UNIT", "mean"),
            )
            .reset_index()
            .sort_values(
                by=["LOJA", "QTD_CLIENTE", "ULTIMA_COMPRA", "VALOR_TOTAL", "CLIENTE"],
                ascending=[True, False, False, False, True],
            )
        )

        top_clientes = clientes_loja.groupby("LOJA", dropna=False).head(3).copy()
        top_clientes["ULTIMA_COMPRA_TXT"] = pd.to_datetime(top_clientes["ULTIMA_COMPRA"], errors="coerce").dt.strftime("%d/%m/%Y")
        clientes_resumo = (
            top_clientes.groupby("LOJA", dropna=False)
            .apply(
                lambda x: " | ".join(
                    [
                        f"{row['CLIENTE']} ({int(row['QTD_CLIENTE'])} un | {row['ULTIMA_COMPRA_TXT']} | R$ {row['PRECO_MEDIO']:.2f})"
                        for _, row in x.iterrows()
                    ]
                )
            )
            .reset_index(name="CLIENTES_REFERENCIA")
        )

        grp_valid = grp_valid.merge(clientes_resumo, on="LOJA", how="left")

        for _, row in grp_valid.iterrows():
            registros_gerais.append(
                {
                    "CODIGO": row["CODIGO"],
                    "DESCRICAO": row["DESCRICAO"],
                    "LABEL": row["LABEL"],
                    "LOJA": row["LOJA"],
                    "SALDO_UNICA": saldo_int,
                    "QTD_VENDIDA_LOJA": row["QTD_VENDIDA"],
                    "PCT_PARTICIPACAO": row["PCT_PARTICIPACAO"],
                    "SUGESTAO_REALOCAR": row["SUGESTAO_REALOCAR"],
                    "ULTIMA_VENDA_LOJA": row["ULTIMA_VENDA"],
                    "VALOR_VENDIDO_LOJA": row["VALOR_VENDIDO"],
                    "CLIENTES_REFERENCIA": row.get("CLIENTES_REFERENCIA", ""),
                }
            )

    geral = pd.DataFrame(registros_gerais)

    if geral.empty:
        return geral, []

    geral["ULTIMA_VENDA_LOJA"] = pd.to_datetime(geral["ULTIMA_VENDA_LOJA"], errors="coerce")
    geral = geral.sort_values(
        by=["LOJA", "SUGESTAO_REALOCAR", "QTD_VENDIDA_LOJA", "ULTIMA_VENDA_LOJA", "DESCRICAO"],
        ascending=[True, False, False, False, True],
    ).reset_index(drop=True)

    lojas_disponiveis = sorted(geral["LOJA"].dropna().astype(str).unique().tolist())
    return geral, lojas_disponiveis


def brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def int_fmt(v):
    try:
        return f"{float(v):,.0f}".replace(",", ".")
    except Exception:
        return "0"


def render_pagina_estoque(giro: pd.DataFrame, produtos: pd.DataFrame):
    st.title("Sky - Estoque Única + Drill de Giro por Produto")
    st.caption("Consulta dos saldos da Única Atacadista com detalhamento das vendas por loja, cliente e data.")

    with st.sidebar:
        st.header("Filtros")
        busca = st.text_input("Buscar produto por código ou descrição", key="busca_prod")
        somente_com_saldo = st.checkbox("Mostrar apenas produtos com saldo > 0", value=False, key="saldo_prod")
        somente_com_venda = st.checkbox("Mostrar apenas produtos com venda", value=False, key="venda_prod")

    produtos_filtrados = produtos.copy()

    if busca:
        termo = busca.strip().lower()
        produtos_filtrados = produtos_filtrados[
            produtos_filtrados["LABEL"].str.lower().str.contains(termo, na=False)
        ]

    if somente_com_saldo:
        produtos_filtrados = produtos_filtrados[produtos_filtrados["SALDO_UNICA"] > 0]

    if somente_com_venda:
        produtos_filtrados = produtos_filtrados[produtos_filtrados["QTD_VENDIDA"] > 0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Produtos na base", int_fmt(len(produtos_filtrados)))
    col2.metric("Saldo total Única", int_fmt(produtos_filtrados["SALDO_UNICA"].sum()))
    col3.metric("Qtd. vendida (base filtrada)", int_fmt(produtos_filtrados["QTD_VENDIDA"].sum()))
    col4.metric("Valor vendido (base filtrada)", brl(produtos_filtrados["VALOR_VENDIDO"].sum()))

    st.subheader("Produtos e saldos na Única")
    tabela_produtos = produtos_filtrados[
        ["CODIGO", "DESCRICAO", "SALDO_UNICA", "QTD_VENDIDA", "VALOR_VENDIDO", "LOJAS_COM_VENDA", "CLIENTES_COM_COMPRA", "ULTIMA_VENDA"]
    ].copy()

    tabela_produtos["ULTIMA_VENDA"] = tabela_produtos["ULTIMA_VENDA"].dt.strftime("%d/%m/%Y")
    tabela_produtos = tabela_produtos.rename(
        columns={
            "CODIGO": "Código",
            "DESCRICAO": "Descrição",
            "SALDO_UNICA": "Saldo Única",
            "QTD_VENDIDA": "Qtd. Vendida",
            "VALOR_VENDIDO": "Valor Vendido",
            "LOJAS_COM_VENDA": "Lojas",
            "CLIENTES_COM_COMPRA": "Clientes",
            "ULTIMA_VENDA": "Última Venda",
        }
    )

    st.dataframe(
        tabela_produtos,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Código": st.column_config.NumberColumn(format="%d"),
            "Descrição": st.column_config.TextColumn(width="large"),
            "Saldo Única": st.column_config.NumberColumn(format="%.0f"),
            "Qtd. Vendida": st.column_config.NumberColumn(format="%.0f"),
            "Valor Vendido": st.column_config.NumberColumn(format="R$ %.2f"),
            "Lojas": st.column_config.NumberColumn(format="%d"),
            "Clientes": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.markdown("---")
    st.subheader("Drill do produto")

    if produtos_filtrados.empty:
        st.warning("Nenhum produto encontrado com os filtros informados.")
        return

    opcoes = produtos_filtrados["LABEL"].tolist()
    produto_escolhido = st.selectbox("Selecione o produto", options=opcoes, index=0)

    linha_prod = produtos_filtrados.loc[produtos_filtrados["LABEL"] == produto_escolhido].iloc[0]
    codigo_sel = int(linha_prod["CODIGO"])
    descricao_sel = linha_prod["DESCRICAO"]

    vendas_prod = giro[giro["CÓD"] == codigo_sel].copy()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Código", str(codigo_sel))
    c2.metric("Saldo Única", int_fmt(linha_prod["SALDO_UNICA"]))
    c3.metric("Qtd. vendida", int_fmt(vendas_prod["QTD"].sum()))
    c4.metric("Valor vendido", brl(vendas_prod["VR.TOTAL"].sum()))

    st.write(f"**Produto selecionado:** {descricao_sel}")

    if vendas_prod.empty:
        st.info("Esse produto possui saldo/registro na Única, mas não teve vendas nas lojas na aba 'giro sky'.")
        return

    resumo_lojas = (
        vendas_prod.groupby("LOJA", dropna=False)
        .agg(
            QTD_VENDIDA=("QTD", "sum"),
            VALOR_VENDIDO=("VR.TOTAL", "sum"),
            CLIENTES=("CLIENTE", "nunique"),
            ULTIMA_VENDA=("DATA", "max"),
        )
        .reset_index()
        .sort_values(by=["QTD_VENDIDA", "VALOR_VENDIDO", "LOJA"], ascending=[False, False, True])
        .reset_index(drop=True)
    )

    resumo_lojas["RANK_LOJA"] = range(1, len(resumo_lojas) + 1)

    st.markdown("### Lojas que venderam o produto")
    tabela_lojas = resumo_lojas.copy()
    tabela_lojas["ULTIMA_VENDA"] = tabela_lojas["ULTIMA_VENDA"].dt.strftime("%d/%m/%Y")
    tabela_lojas = tabela_lojas.rename(
        columns={
            "RANK_LOJA": "Rank",
            "LOJA": "Loja",
            "QTD_VENDIDA": "Qtd. Vendida",
            "VALOR_VENDIDO": "Valor Vendido",
            "CLIENTES": "Clientes",
            "ULTIMA_VENDA": "Última Venda",
        }
    )

    st.dataframe(
        tabela_lojas[["Rank", "Loja", "Qtd. Vendida", "Valor Vendido", "Clientes", "Última Venda"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            "Qtd. Vendida": st.column_config.NumberColumn(format="%.0f"),
            "Valor Vendido": st.column_config.NumberColumn(format="R$ %.2f"),
            "Clientes": st.column_config.NumberColumn(format="%d"),
        },
    )

    ordem_lojas = resumo_lojas[["LOJA", "RANK_LOJA"]].copy()
    detalhes = vendas_prod.merge(ordem_lojas, on="LOJA", how="left")

    detalhes = detalhes[
        ["RANK_LOJA", "LOJA", "CLIENTE", "DATA", "QTD", "UNIT", "VR.TOTAL", "Nº DOC", "CIDADE", "VEN"]
    ].copy()

    detalhes["DATA"] = pd.to_datetime(detalhes["DATA"], errors="coerce")
    detalhes = detalhes.sort_values(
        by=["RANK_LOJA", "QTD", "VR.TOTAL", "DATA"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)

    st.markdown("### Clientes que compraram o produto")
    st.caption("A ordem abaixo respeita o ranking das lojas: da que mais vendeu para a que menos vendeu.")

    st.dataframe(
        detalhes.rename(
            columns={
                "RANK_LOJA": "Rank Loja",
                "LOJA": "Loja",
                "CLIENTE": "Cliente",
                "DATA": "Data",
                "QTD": "Qtd.",
                "UNIT": "Valor Unit.",
                "VR.TOTAL": "Valor Pago",
                "Nº DOC": "Documento",
                "CIDADE": "Cidade",
                "VEN": "Vendedor",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank Loja": st.column_config.NumberColumn(format="%d"),
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Qtd.": st.column_config.NumberColumn(format="%.0f"),
            "Valor Unit.": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor Pago": st.column_config.NumberColumn(format="R$ %.2f"),
            "Cliente": st.column_config.TextColumn(width="large"),
            "Cidade": st.column_config.TextColumn(width="medium"),
            "Documento": st.column_config.TextColumn(width="medium"),
        },
    )


def render_pagina_direcionamento(giro: pd.DataFrame, produtos: pd.DataFrame):
    ranking, detalhes_produto = gerar_direcionamento(giro, produtos)

    st.title("Sky - Direcionamento Automático por SKU")
    st.caption("Ranking por produto com até 3 lojas prioritárias, baseado em volume vendido, recência e clientes reais da base.")

    with st.sidebar:
        st.header("Filtros do direcionamento")
        busca_dir = st.text_input("Buscar SKU / descrição", key="busca_dir")
        apenas_com_venda_dir = st.checkbox("Somente SKUs com venda", value=True, key="venda_dir")
        apenas_com_saldo_dir = st.checkbox("Somente SKUs com saldo > 0", value=False, key="saldo_dir")

    base = ranking.copy()
    if busca_dir:
        termo = busca_dir.strip().lower()
        base = base[base["LABEL"].str.lower().str.contains(termo, na=False)]
    if apenas_com_venda_dir:
        base = base[base["QTD_TOTAL"] > 0]
    if apenas_com_saldo_dir:
        base = base[base["SALDO_UNICA"] > 0]

    c1, c2, c3 = st.columns(3)
    c1.metric("SKUs no ranking", int_fmt(len(base)))
    c2.metric("Saldo Única", int_fmt(base["SALDO_UNICA"].sum()))
    c3.metric("Qtd. vendida dos SKUs filtrados", int_fmt(base["QTD_TOTAL"].sum()))

    tabela = base[
        [
            "CODIGO",
            "DESCRICAO",
            "SALDO_UNICA",
            "QTD_TOTAL",
            "ULTIMA_VENDA",
            "TOP1_LOJA",
            "TOP1_RESUMO",
            "TOP2_LOJA",
            "TOP2_RESUMO",
            "TOP3_LOJA",
            "TOP3_RESUMO",
        ]
    ].copy()
    tabela["ULTIMA_VENDA"] = pd.to_datetime(tabela["ULTIMA_VENDA"], errors="coerce").dt.strftime("%d/%m/%Y")
    tabela = tabela.rename(
        columns={
            "CODIGO": "Código",
            "DESCRICAO": "Descrição",
            "SALDO_UNICA": "Saldo Única",
            "QTD_TOTAL": "Qtd. Vendida",
            "ULTIMA_VENDA": "Última Venda",
            "TOP1_LOJA": "1ª Loja",
            "TOP1_RESUMO": "Resumo 1",
            "TOP2_LOJA": "2ª Loja",
            "TOP2_RESUMO": "Resumo 2",
            "TOP3_LOJA": "3ª Loja",
            "TOP3_RESUMO": "Resumo 3",
        }
    )

    st.subheader("Tabela geral de direcionamento")
    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Código": st.column_config.NumberColumn(format="%d"),
            "Descrição": st.column_config.TextColumn(width="large"),
            "Saldo Única": st.column_config.NumberColumn(format="%.0f"),
            "Qtd. Vendida": st.column_config.NumberColumn(format="%.0f"),
            "Resumo 1": st.column_config.TextColumn(width="large"),
            "Resumo 2": st.column_config.TextColumn(width="large"),
            "Resumo 3": st.column_config.TextColumn(width="large"),
        },
    )

    csv = tabela.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar direcionamento em CSV",
        data=csv,
        file_name="direcionamento_sky.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("Drill do direcionamento")

    if base.empty:
        st.warning("Nenhum SKU encontrado com os filtros aplicados.")
        return

    sku_escolhido = st.selectbox("Selecione o SKU para detalhar o direcionamento", base["LABEL"].tolist(), index=0)
    linha = base.loc[base["LABEL"] == sku_escolhido].iloc[0]
    codigo = int(linha["CODIGO"])

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Código", str(codigo))
    d2.metric("Saldo Única", int_fmt(linha["SALDO_UNICA"]))
    d3.metric("Qtd. vendida", int_fmt(linha["QTD_TOTAL"]))
    d4.metric("Última venda", linha["ULTIMA_VENDA"].strftime("%d/%m/%Y") if pd.notna(linha["ULTIMA_VENDA"]) else "-")

    st.write(f"**Produto:** {linha['DESCRICAO']}")

    lojas = detalhes_produto.get(codigo, [])
    if not lojas:
        st.info("Esse SKU não possui histórico de venda na aba 'giro sky'.")
        return

    for loja_info in lojas:
        st.markdown(f"### {loja_info['RANK']}º {loja_info['LOJA']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Qtd. vendida na loja", int_fmt(loja_info["QTD_VENDIDA"]))
        c2.metric("Valor vendido na loja", brl(loja_info["VALOR_VENDIDO"]))
        c3.metric("Última venda", loja_info["ULTIMA_VENDA_TXT"])

        clientes_df = pd.DataFrame(loja_info["CLIENTES_TOP"])
        if not clientes_df.empty:
            clientes_df = clientes_df.rename(
                columns={
                    "CLIENTE": "Cliente",
                    "QTD": "Qtd.",
                    "ULTIMA_COMPRA_TXT": "Última Compra",
                    "VALOR_TOTAL": "Valor Total",
                    "PRECO_MEDIO": "Preço Médio",
                }
            )
            st.dataframe(
                clientes_df[["Cliente", "Qtd.", "Última Compra", "Preço Médio", "Valor Total"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Qtd.": st.column_config.NumberColumn(format="%.0f"),
                    "Preço Médio": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Valor Total": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Cliente": st.column_config.TextColumn(width="large"),
                },
            )
        else:
            st.info("Sem clientes para esta loja.")

    with st.expander("Critério do ranking"):
        st.write(
            """
            - O ranking das lojas por SKU considera primeiro a quantidade vendida, depois a data mais recente de venda e, em seguida, o valor vendido.
            - Dentro de cada loja, os clientes são ordenados por quantidade comprada, recência da compra e valor total.
            - O objetivo é sugerir para onde o estoque da Única pode ser direcionado com base no histórico real da planilha.
            """
        )


def render_pagina_realocacao(giro: pd.DataFrame, produtos: pd.DataFrame):
    geral, lojas_disponiveis = gerar_realocacao(giro, produtos)

    st.title("Sky - Sugestão de Realocação por Loja")
    st.caption("Distribuição proporcional do saldo da Única entre as lojas, com base no histórico de quantidade vendida por SKU, incluindo a própria ÚNICA quando ela também teve tração.")

    if geral.empty:
        st.warning("Não encontrei SKUs com saldo na Única e vendas históricas para sugerir realocação.")
        return

    with st.sidebar:
        st.header("Filtros da realocação")
        loja_escolhida = st.selectbox("Selecione a loja", lojas_disponiveis, index=0, key="loja_realoc")
        busca_realoc = st.text_input("Buscar SKU / descrição", key="busca_realoc")
        somente_sugestao = st.checkbox("Mostrar apenas SKUs com sugestão > 0", value=True, key="so_sug_maior_zero")

    base_loja = geral[geral["LOJA"] == loja_escolhida].copy()

    if busca_realoc:
        termo = busca_realoc.strip().lower()
        base_loja = base_loja[base_loja["LABEL"].str.lower().str.contains(termo, na=False)]

    if somente_sugestao:
        base_loja = base_loja[base_loja["SUGESTAO_REALOCAR"] > 0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Loja", loja_escolhida)
    k2.metric("SKUs sugeridos", int_fmt(len(base_loja)))
    k3.metric("Unidades sugeridas", int_fmt(base_loja["SUGESTAO_REALOCAR"].sum()))
    k4.metric("Saldo Única considerado", int_fmt(base_loja["SALDO_UNICA"].sum()))

    st.subheader(f"SKUs sugeridos para {loja_escolhida}")

    tabela = base_loja[
        [
            "CODIGO",
            "DESCRICAO",
            "SALDO_UNICA",
            "QTD_VENDIDA_LOJA",
            "PCT_PARTICIPACAO",
            "SUGESTAO_REALOCAR",
            "ULTIMA_VENDA_LOJA",
            "VALOR_VENDIDO_LOJA",
            "CLIENTES_REFERENCIA",
        ]
    ].copy()

    tabela["ULTIMA_VENDA_LOJA"] = pd.to_datetime(tabela["ULTIMA_VENDA_LOJA"], errors="coerce").dt.strftime("%d/%m/%Y")
    tabela = tabela.rename(
        columns={
            "CODIGO": "Código",
            "DESCRICAO": "Descrição",
            "SALDO_UNICA": "Saldo Única",
            "QTD_VENDIDA_LOJA": "Qtd. Vendida na Loja",
            "PCT_PARTICIPACAO": "% Participação",
            "SUGESTAO_REALOCAR": "Sugestão de Envio",
            "ULTIMA_VENDA_LOJA": "Última Venda",
            "VALOR_VENDIDO_LOJA": "Valor Vendido",
            "CLIENTES_REFERENCIA": "Clientes de Referência",
        }
    )

    st.dataframe(
        tabela.sort_values(by=["Sugestão de Envio", "Qtd. Vendida na Loja", "Última Venda"], ascending=[False, False, False]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Código": st.column_config.NumberColumn(format="%d"),
            "Descrição": st.column_config.TextColumn(width="large"),
            "Saldo Única": st.column_config.NumberColumn(format="%.0f"),
            "Qtd. Vendida na Loja": st.column_config.NumberColumn(format="%.0f"),
            "% Participação": st.column_config.NumberColumn(format="%.2f%%"),
            "Sugestão de Envio": st.column_config.NumberColumn(format="%.0f"),
            "Valor Vendido": st.column_config.NumberColumn(format="R$ %.2f"),
            "Clientes de Referência": st.column_config.TextColumn(width="large"),
        },
    )

    csv_loja = tabela.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        f"Baixar CSV da loja {loja_escolhida}",
        data=csv_loja,
        file_name=f"realocacao_sky_{loja_escolhida.lower().replace(' ', '_')}.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("Resumo geral da metodologia")
    st.write(
        """
        A sugestão é calculada SKU a SKU:
        1. pega o saldo disponível na Única;
        2. busca quanto cada loja vendeu daquele SKU no histórico, incluindo a própria ÚNICA quando ela teve tração;
        3. calcula a participação de cada loja no total vendido;
        4. distribui o saldo da Única proporcionalmente a essa participação, fechando em números inteiros.
        """
    )

    with st.expander("Exemplo de cálculo"):
        st.write(
            """
            Se um SKU tem saldo 18 na Única e o histórico mostra:
            - Gama: 5 unidades
            - Luziânia: 5 unidades

            Então cada loja representa 50% das vendas desse SKU.
            A sugestão fica:
            - Gama: 9 unidades
            - Luziânia: 9 unidades

            Se a própria ÚNICA também vendeu o SKU no histórico, ela entra na divisão proporcional como destino.
            Exemplo:
            - ÚNICA: 6 unidades
            - Gama: 3 unidades
            - Luziânia: 3 unidades

            Participação:
            - ÚNICA: 50%
            - Gama: 25%
            - Luziânia: 25%

            Com saldo 18, a sugestão fica:
            - ÚNICA: 9 unidades
            - Gama: 4 ou 5 unidades
            - Luziânia: 4 ou 5 unidades
                        """
        )

    st.markdown("### Visão geral por loja")
    resumo_lojas = (
        geral.groupby("LOJA", dropna=False)
        .agg(
            SKUS=("CODIGO", "nunique"),
            UNIDADES_SUGERIDAS=("SUGESTAO_REALOCAR", "sum"),
            QTD_HISTORICA=("QTD_VENDIDA_LOJA", "sum"),
        )
        .reset_index()
        .sort_values(by=["UNIDADES_SUGERIDAS", "QTD_HISTORICA", "LOJA"], ascending=[False, False, True])
        .rename(
            columns={
                "LOJA": "Loja",
                "SKUS": "SKUs",
                "UNIDADES_SUGERIDAS": "Unidades Sugeridas",
                "QTD_HISTORICA": "Qtd. Histórica",
            }
        )
    )

    st.dataframe(
        resumo_lojas,
        use_container_width=True,
        hide_index=True,
        column_config={
            "SKUs": st.column_config.NumberColumn(format="%d"),
            "Unidades Sugeridas": st.column_config.NumberColumn(format="%.0f"),
            "Qtd. Histórica": st.column_config.NumberColumn(format="%.0f"),
        },
    )


giro, produtos = carregar_dados()

pagina = st.sidebar.radio(
    "Navegação",
    ["Estoque + Drill", "Direcionamento por SKU", "Realocação por Loja"],
    index=0,
)

if pagina == "Estoque + Drill":
    render_pagina_estoque(giro, produtos)
elif pagina == "Direcionamento por SKU":
    render_pagina_direcionamento(giro, produtos)
else:
    render_pagina_realocacao(giro, produtos)
