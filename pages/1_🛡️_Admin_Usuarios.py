import os
import streamlit as st
import pandas as pd
from utils.users import add_user, list_users, set_user_active

st.set_page_config(page_title="Admin - Usuários", page_icon="🛡️", layout="wide")

def require_admin():
    auth = st.session_state.get("auth")
    if not auth:
        st.error("Você precisa estar logado para acessar esta página.")
        st.stop()
    if auth.get("role") != "admin":
        st.error("Acesso negado. Apenas administrador.")
        st.stop()

require_admin()

st.title("🛡️ Administração de Usuários")
st.write("Crie, ative/desative e visualize usuários. As senhas são armazenadas com hash seguro (PBKDF2).")

with st.expander("➕ Criar novo usuário", expanded=True):
    with st.form("create_user_form"):
        username = st.text_input("Usuário (sem espaços)")
        password = st.text_input("Senha", type="password")
        role = st.selectbox("Perfil", ["user","admin"], index=0)
        active = st.checkbox("Ativo", value=True)
        submitted = st.form_submit_button("Criar")
    if submitted:
        try:
            uname = username.strip()
            if not uname or " " in uname:
                st.error("Usuário inválido.")
            elif len(password) < 6:
                st.error("Senha muito curta (mínimo 6).")
            else:
                add_user(uname, password, role=role, active=active)
                st.success(f"Usuário '{uname}' criado.")
                st.rerun()
        except Exception as e:
            st.error(str(e))

st.subheader("Usuários cadastrados")
users = pd.DataFrame(list_users()).sort_values(["role","username"])
st.dataframe(users, use_container_width=True)

st.subheader("Ativar / Desativar")
col1, col2 = st.columns([2,1])
with col1:
    alvo = st.selectbox("Selecione o usuário", users["username"].tolist() if not users.empty else [])
with col2:
    novo_status = st.selectbox("Novo status", ["Ativo","Inativo"], index=0)

if st.button("Aplicar status"):
    try:
        set_user_active(alvo, active=(novo_status=="Ativo"))
        st.success("Atualizado.")
        st.rerun()
    except Exception as e:
        st.error(str(e))

st.caption("Em produção, defina ADMIN_USER e ADMIN_PASS via secrets/env e troque a senha padrão imediatamente.")