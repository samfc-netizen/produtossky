
import os
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Sky - Estoque e Giro", layout="wide")

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

    # Normalização básica
    giro.columns = [str(c).strip() for c in giro.columns]
    estoque.columns = [str(c).strip() for c in estoque.columns]

    giro["DATA"] = pd.to_datetime(giro["DATA"], errors="coerce")
    giro["QTD"] = pd.to_numeric(giro["QTD"], errors="coerce").fillna(0)
    giro["UNIT"] = pd.to_numeric(giro["UNIT"], errors="coerce").fillna(0)
    giro["VR.TOTAL"] = pd.to_numeric(giro["VR.TOTAL"], errors="coerce").fillna(0)
    giro["CÓD"] = pd.to_numeric(giro["CÓD"], errors="coerce").astype("Int64")

    estoque["Cód.Item"] = pd.to_numeric(estoque["Cód.Item"], errors="coerce").astype("Int64")
    estoque["Saldo"] = pd.to_numeric(estoque["Saldo"], errors="coerce").fillna(0)

    estoque = estoque.rename(
        columns={
            "Cód.Item": "CODIGO",
            "Descrição": "DESCRICAO",
            "Saldo": "SALDO_UNICA",
        }
    )

    # Agregados de giro por produto
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
        ascending=[False, False, True]
    ).reset_index(drop=True)

    return giro, produtos

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

giro, produtos = carregar_dados()

st.title("Sky - Estoque Única + Drill de Giro por Produto")
st.caption("Consulta dos saldos da Única Atacadista com detalhamento das vendas por loja, cliente e data.")

with st.sidebar:
    st.header("Filtros")
    busca = st.text_input("Buscar produto por código ou descrição")
    somente_com_saldo = st.checkbox("Mostrar apenas produtos com saldo > 0", value=False)
    somente_com_venda = st.checkbox("Mostrar apenas produtos com venda", value=False)

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
    st.stop()

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
    st.stop()

# Resumo por loja - ordenar da que mais vendeu para a que menos vendeu
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

# Detalhamento por cliente/data respeitando a ordem das lojas
ordem_lojas = resumo_lojas[["LOJA", "RANK_LOJA"]].copy()
detalhes = vendas_prod.merge(ordem_lojas, on="LOJA", how="left")

detalhes = detalhes[
    ["RANK_LOJA", "LOJA", "CLIENTE", "DATA", "QTD", "UNIT", "VR.TOTAL", "Nº DOC", "CIDADE", "VEN"]
].copy()

detalhes["DATA"] = pd.to_datetime(detalhes["DATA"], errors="coerce")
detalhes = detalhes.sort_values(
    by=["RANK_LOJA", "QTD", "VR.TOTAL", "DATA"],
    ascending=[True, False, False, False]
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

with st.expander("Ver observações"):
    st.write(
        """
        - A tabela superior mostra os produtos e os saldos da aba **estoque sky**.
        - O drill usa a aba **giro sky** para mostrar as lojas que venderam o produto.
        - As lojas estão ordenadas da maior para a menor quantidade vendida do produto.
        - O detalhamento final mostra cliente, data da compra e valor pago.
        """
    )
