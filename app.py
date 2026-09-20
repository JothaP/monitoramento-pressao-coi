import streamlit as st

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Plataforma COI - Operações",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CONTROLE DE AUTENTICAÇÃO E PERFIS
# ============================================================
def verificar_login():
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
        st.session_state.perfil = None

    if st.session_state.autenticado:
        return True

    # ---------- Tela de Login ----------
    st.markdown(
        """
        <style>
        .login-container {
            max-width: 420px;
            margin: 80px auto 40px auto;
            padding: 40px 36px;
            background: linear-gradient(145deg, #f0f7ff 0%, #e8f4fd 100%);
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 80, 140, 0.12);
            border: 1px solid #d0e6f7;
            text-align: center;
        }
        .login-icon { font-size: 52px; margin-bottom: 12px; }
        .login-title { font-size: 22px; font-weight: 700; color: #0a4d8c; margin-bottom: 6px; }
        .login-subtitle { font-size: 14px; color: #5a7a9a; margin-bottom: 28px; line-height: 1.4; }
        </style>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown(
            """
            <div class="login-container">
                <div class="login-icon">💧</div>
                <div class="login-title">Plataforma Operacional COI</div>
                <div class="login-subtitle">
                    Centro de Operações Integradas<br>
                    Digite sua senha de acesso
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("form_login"):
            senha_digitada = st.text_input(
                "Senha de acesso",
                type="password",
                placeholder="Digite a senha...",
                label_visibility="collapsed"
            )
            entrar = st.form_submit_button("Acessar Plataforma", type="primary", use_container_width=True)

            if entrar:
                # Busca senhas nos secrets (com fallbacks de segurança caso não configurados)
                senha_admin = st.secrets.get("SENHA_ADMIN", "admin2026")
                senha_usuario = st.secrets.get("SENHA_USUARIO", "coi2026")

                if senha_digitada == senha_admin:
                    st.session_state.autenticado = True
                    st.session_state.perfil = "admin"
                    st.rerun()
                elif senha_digitada == senha_usuario:
                    st.session_state.autenticado = True
                    st.session_state.perfil = "usuario"
                    st.rerun()
                else:
                    st.error("Senha incorreta. Tente novamente.")

    st.stop()
    return False

# Executa verificação
verificar_login()

# ============================================================
# HUB DE SELEÇÃO (TELA PRINCIPAL PÓS-LOGIN)
# ============================================================
st.title("💧 Central de Módulos - COI")
st.markdown(f"Bem-vindo(a)! Perfil conectado: **{st.session_state.perfil.upper()}**")
st.divider()

st.markdown("### Selecione o módulo desejado:")

col_m1, col_m2, col_m3 = st.columns(3)

# --- MÓDULO 1 ---
with col_m1:
    st.markdown("#### 🗺️ Módulo 1")
    st.markdown("**Baixa Pressão**")
    st.caption("Status: **Ativo para todos**")
    if st.button("Acessar Baixa Pressão", type="primary", use_container_width=True):
        st.switch_page("pages/1_Baixa_Pressao.py")

# --- MÓDULO 2 ---
with col_m2:
    st.markdown("#### 📊 Módulo 2")
    st.markdown("**Mapeamento**")
    st.caption("Status: **Em desenvolvimento**")
    
    # Trava de visualização baseada no perfil
    admin_ativo = (st.session_state.perfil == "admin")
    if st.button("Acessar Mapeamento", disabled=not admin_ativo, use_container_width=True):
        st.switch_page("pages/2_Mapeamento.py")
    if not admin_ativo:
        st.caption("🔒 *Restrito a administradores*")

# --- MÓDULO 3 ---
with col_m3:
    st.markdown("#### ⚙️ Módulo 3")
    st.markdown("**Vazão de Poços**")
    st.caption("Status: **Em desenvolvimento**")
    
    if st.button("Acessar Vazão de Poços", disabled=not admin_ativo, use_container_width=True):
        st.switch_page("pages/3_Vazao_Pocos.py")
    if not admin_ativo:
        st.caption("🔒 *Restrito a administradores*")

st.divider()
if st.button("Encerrar Sessão / Sair"):
    st.session_state.autenticado = False
    st.session_state.perfil = None
    st.rerun()
