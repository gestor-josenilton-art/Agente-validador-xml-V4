import os
import streamlit as st

from utils.users import require_admin
from utils.base_legal import get_status, save_uploaded_table

st.set_page_config(page_title="Admin - Base Legal", page_icon="📚", layout="wide")

require_admin()

st.title("📚 Admin — Base Legal (CFOP / NCM / CST/CSOSN)")
st.caption("Aqui você faz upload das planilhas que serão usadas como **fonte da verdade** nas validações. Apenas ADMIN pode acessar.")

status = get_status()

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("NCM")
    st.write(f"Status: {'✅' if status['ncm'].ok else '❌'} {status['ncm'].message}")
    st.write(f"Linhas: {status['ncm'].rows}")
    up_ncm = st.file_uploader("Upload ncm_regras.xlsx", type=["xlsx"], key="up_ncm")
    if up_ncm is not None:
        res = save_uploaded_table("ncm", up_ncm.read())
        st.success(res.message) if res.ok else st.error(res.message)

with col2:
    st.subheader("CFOP")
    st.write(f"Status: {'✅' if status['cfop'].ok else '❌'} {status['cfop'].message}")
    st.write(f"Linhas: {status['cfop'].rows}")
    up_cfop = st.file_uploader("Upload cfop_regras.xlsx", type=["xlsx"], key="up_cfop")
    if up_cfop is not None:
        res = save_uploaded_table("cfop", up_cfop.read())
        st.success(res.message) if res.ok else st.error(res.message)

with col3:
    st.subheader("CST / CSOSN")
    st.write(f"Status: {'✅' if status['cst'].ok else '❌'} {status['cst'].message}")
    st.write(f"Linhas: {status['cst'].rows}")
    up_cst = st.file_uploader("Upload cst_csosn_regras.xlsx", type=["xlsx"], key="up_cst")
    if up_cst is not None:
        res = save_uploaded_table("cst", up_cst.read())
        st.success(res.message) if res.ok else st.error(res.message)

st.divider()
st.markdown("""
### Colunas obrigatórias

**ncm_regras.xlsx**
- `ncm`
- `descricao`

**cfop_regras.xlsx**
- `cfop`
- `descricao`

**cst_csosn_regras.xlsx**
- `codigo`
- `tipo` (CST ou CSOSN)
- `descricao`

> Dica: você pode manter outras colunas extras (ex.: observações). O app ignora o que não precisa.
""")
