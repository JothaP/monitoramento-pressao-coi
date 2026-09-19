import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import simplekml
from datetime import datetime, date
from streamlit_autorefresh import st_autorefresh
import io
import uuid
from typing import Optional

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CONSTANTES
# ============================================================
LAT_BASE = -5.0892
LON_BASE = -42.8019
SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"
COLUNAS_PADRAO = ["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"]

# ============================================================
# AUTENTICAÇÃO
# ============================================================
def verificar_senha() -> bool:
    """Tela de login com senha. Retorna True se autenticado."""
    def senha_correta():
        if "senha_acesso" in st.secrets:
            return st.session_state.get("senha_digitada") == st.secrets["senha_acesso"]
        # Fallback para desenvolvimento (remova em produção)
        return st.session_state.get("senha_digitada") == "coi2026"

    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

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
        .login-icon {
            font-size: 52px;
            margin-bottom: 12px;
        }
        .login-title {
            font-size: 22px;
            font-weight: 700;
            color: #0a4d8c;
            margin-bottom: 6px;
        }
        .login-subtitle {
            font-size: 14px;
            color: #5a7a9a;
            margin-bottom: 28px;
            line-height: 1.4;
        }
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
                <div class="login-title">Monitoramento de Baixa Pressão</div>
                <div class="login-subtitle">
                    Centro de Operações Integradas (COI)<br>
                    Digite a senha de acesso para continuar
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("form_login"):
            senha = st.text_input(
                "Senha de acesso",
                type="password",
                placeholder="Digite a senha...",
                label_visibility="collapsed"
            )
            st.session_state.senha_digitada = senha
            entrar = st.form_submit_button("Acessar Painel", type="primary", use_container_width=True)

            if entrar:
                if senha_correta():
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.error("Senha incorreta. Tente novamente.")

    st.stop()
    return False


# Executa a verificação de senha
verificar_senha()

# ============================================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================================
@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = json.loads(st.secrets["gcp_json"])
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.sheet1

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"❌ Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# ============================================================
# FUNÇÕES DE DADOS
# ============================================================
def gerar_id() -> str:
    return str(uuid.uuid4())[:8].upper()


def normalizar_coluna(nome: str) -> str:
    nome = str(nome).strip().lower()
    mapeamento = {
        "id": "ID",
        "data": "Data",
        "municipio": "Municipio",
        "município": "Municipio",
        "bairro": "Bairro",
        "latitude": "Latitude",
        "lat": "Latitude",
        "longitude": "Longitude",
        "lon": "Longitude",
        "long": "Longitude",
        "pressao_mca": "Pressao_MCA",
        "pressão_mca": "Pressao_MCA",
        "pressao": "Pressao_MCA",
        "pressão": "Pressao_MCA",
        "mca": "Pressao_MCA",
    }
    return mapeamento.get(nome, nome.title())


def parse_float(valor, default: float = 0.0) -> float:
    try:
        if pd.isna(valor):
            return default
        texto = str(valor).strip().replace(",", ".")
        return float(texto)
    except (ValueError, TypeError):
        return default


def normalizar_coordenada(valor, tipo: str = "lat") -> Optional[float]:
    num = parse_float(valor, None)
    if num is None:
        return None

    if tipo == "lat":
        if abs(num) > 90:
            num = num / 1_000_000 if abs(num) > 1000 else num / 100_000
    else:
        if abs(num) > 180:
            num = num / 1_000_000 if abs(num) > 1000 else num / 100_000

    if tipo == "lat" and not (-10.5 <= num <= -2.5):
        return None
    if tipo == "lon" and not (-46.0 <= num <= -40.0):
        return None

    return round(num, 6)


@st.cache_data(ttl=15, show_spinner="Carregando dados...")
def carregar_dados() -> pd.DataFrame:
    try:
        registros = worksheet.get_all_records()
    except Exception as e:
        st.error(f"Erro ao ler planilha: {e}")
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    if not registros:
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    df = pd.DataFrame(registros)
    df.columns = [normalizar_coluna(c) for c in df.columns]

    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = None

    # Gera ID temporário para registros antigos (não grava de volta automaticamente)
    mask = df["ID"].isna() | (df["ID"].astype(str).str.strip() == "") | (df["ID"].astype(str).str.lower() == "nan")
    if mask.any():
        df.loc[mask, "ID"] = [gerar_id() for _ in range(mask.sum())]

    df["Latitude"] = df["Latitude"].apply(lambda x: normalizar_coordenada(x, "lat"))
    df["Longitude"] = df["Longitude"].apply(lambda x: normalizar_coordenada(x, "lon"))
    df["Pressao_MCA"] = df["Pressao_MCA"].apply(lambda x: parse_float(x, 0.0))
    df["Data"] = df["Data"].apply(normalizar_data)
    df["Municipio"] = df["Municipio"].astype(str).str.strip().replace({"nan": "Teresina", "None": "Teresina"})
    df["Bairro"] = df["Bairro"].astype(str).str.strip().replace({"nan": "", "None": ""})

    df = df.dropna(how="all")
    df = df[df["Bairro"] != ""]

    return df[COLUNAS_PADRAO].reset_index(drop=True)


def limpar_cache():
    carregar_dados.clear()


def adicionar_ponto(municipio: str, bairro: str, lat: float, lon: float, pressao: float, data_str: str):
    novo_id = gerar_id()
    worksheet.append_row([novo_id, data_str, municipio, bairro, lat, lon, pressao])
    limpar_cache()
    return novo_id


def atualizar_ponto(id_registro: str, municipio: str, bairro: str, lat: float, lon: float, pressao: float, data_str: str) -> bool:
    try:
        celula = worksheet.find(str(id_registro))
        if celula is None:
            return False
        linha = celula.row
        worksheet.update(f"A{linha}:G{linha}", [[id_registro, data_str, municipio, bairro, lat, lon, pressao]])
        limpar_cache()
        return True
    except Exception:
        return False


def excluir_ponto(id_registro: str) -> bool:
    try:
        celula = worksheet.find(str(id_registro))
        if celula is None:
            return False
        worksheet.delete_rows(celula.row)
        limpar_cache()
        return True
    except Exception:
        return False


def data_para_str(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def normalizar_data(valor) -> str:
    """
    Converte qualquer formato de data para o padrão DD/MM/YYYY.
    Aceita: datetime, date, string nos formatos mais comuns, e serial do Excel.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""

    # Já é date ou datetime
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")

    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", "nat"):
        return ""

    # Tenta vários formatos comuns
    formatos = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%m/%d/%Y",   # formato americano
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]

    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    # Tenta serial do Excel (número)
    try:
        num = float(texto)
        if 30000 < num < 60000:  # faixa típica de datas Excel
            from datetime import timedelta
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=num)).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        pass

    # Se nada funcionou, devolve o texto original limpo
    return texto


def str_para_data(s: str) -> Optional[date]:
    try:
        normalizado = normalizar_data(s)
        if not normalizado:
            return None
        return datetime.strptime(normalizado, "%d/%m/%Y").date()
    except Exception:
        return None


# ============================================================
# SESSION STATE
# ============================================================
hoje = date.today()

if "data_selecionada" not in st.session_state:
    st.session_state.data_selecionada = hoje
if "clicked_lat" not in st.session_state:
    st.session_state.clicked_lat = None
if "clicked_lon" not in st.session_state:
    st.session_state.clicked_lon = None
if "modo_adicionar_mapa" not in st.session_state:
    st.session_state.modo_adicionar_mapa = False
if "registro_selecionado_id" not in st.session_state:
    st.session_state.registro_selecionado_id = None
if "modo_edicao" not in st.session_state:
    st.session_state.modo_edicao = False

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### 💧 COI - Monitoramento")
    st.caption("Baixa Pressão • Tempo Real")

    # ---------- CALENDÁRIO ----------
    st.markdown("#### 📅 Selecionar Data")
    data_escolhida = st.date_input(
        "Data",
        value=st.session_state.data_selecionada,
        format="DD/MM/YYYY",
        label_visibility="collapsed",
        key="calendario_principal"
    )
    st.session_state.data_selecionada = data_escolhida
    data_str_selecionada = data_para_str(data_escolhida)

    # Destaque se for hoje
    if data_escolhida == hoje:
        st.success("Exibindo dados de **hoje**")
    else:
        st.info(f"Exibindo dados de **{data_str_selecionada}**")

    st.divider()

    # ---------- FILTROS ----------
    st.markdown("#### 🔍 Filtros")

    df_all = carregar_dados()

    # Filtra primeiro pela data para popular as opções dos outros filtros
    df_data = df_all[df_all["Data"] == data_str_selecionada] if not df_all.empty else df_all

    municipios_opts = ["Todos"] + sorted(df_data["Municipio"].dropna().unique().tolist()) if not df_data.empty else ["Todos"]
    mun_sel = st.selectbox("Município", municipios_opts, key="filtro_municipio")

    if mun_sel != "Todos" and not df_data.empty:
        bairros_base = df_data[df_data["Municipio"] == mun_sel]
    else:
        bairros_base = df_data

    bairros_opts = ["Todos"] + sorted(bairros_base["Bairro"].dropna().unique().tolist()) if not bairros_base.empty else ["Todos"]
    bairro_sel = st.selectbox("Bairro", bairros_opts, key="filtro_bairro")

    faixa_sel = st.selectbox(
        "Faixa de Pressão",
        ["Todas", "Críticos (0 MCA)", "Atenção (≤ 5 MCA)", "Normais (> 5 MCA)"],
        key="filtro_pressao"
    )

    st.divider()

    # ---------- NOVO REGISTRO (somente hoje) ----------
    st.markdown("#### ➕ Novo Ponto")
    if data_escolhida != hoje:
        st.warning("Cadastro manual disponível apenas para a **data de hoje**. Use o upload para datas anteriores.")
    else:
        lat_default = st.session_state.clicked_lat if st.session_state.clicked_lat is not None else 0.0
        lon_default = st.session_state.clicked_lon if st.session_state.clicked_lon is not None else 0.0

        with st.form("form_novo_ponto", clear_on_submit=True):
            municipio = st.text_input("Município *", value="Teresina")
            bairro = st.text_input("Bairro *", placeholder="Ex: Centro")

            c1, c2 = st.columns(2)
            with c1:
                lat = st.number_input("Latitude *", format="%.6f", value=float(lat_default), step=0.000001)
            with c2:
                lon = st.number_input("Longitude *", format="%.6f", value=float(lon_default), step=0.000001)

            pressao = st.number_input("Pressão (MCA) *", format="%.2f", value=0.00, min_value=0.0, step=0.1)

            enviado = st.form_submit_button("Cadastrar Ponto", type="primary", use_container_width=True)

            if enviado:
                if not municipio.strip() or not bairro.strip():
                    st.error("Município e Bairro são obrigatórios.")
                elif lat == 0.0 and lon == 0.0:
                    st.error("Informe coordenadas válidas ou clique no mapa.")
                else:
                    lat_n = normalizar_coordenada(lat, "lat")
                    lon_n = normalizar_coordenada(lon, "lon")
                    if lat_n is None or lon_n is None:
                        st.error("Coordenadas fora da região válida (Piauí).")
                    else:
                        novo_id = adicionar_ponto(
                            municipio.strip(), bairro.strip(),
                            lat_n, lon_n, pressao,
                            data_para_str(hoje)
                        )
                        st.success(f"Ponto cadastrado! ID: {novo_id}")
                        st.session_state.clicked_lat = None
                        st.session_state.clicked_lon = None
                        st.rerun()

        if st.session_state.clicked_lat is not None:
            st.caption(f"📍 {st.session_state.clicked_lat:.6f}, {st.session_state.clicked_lon:.6f}")
            if st.button("Limpar coordenadas", use_container_width=True):
                st.session_state.clicked_lat = None
                st.session_state.clicked_lon = None
                st.rerun()

    st.divider()

    # ---------- IMPORTAÇÃO ----------
    st.markdown("#### 📂 Importação em Massa")
    st.caption("Permite cadastrar pontos em qualquer data.")

    df_modelo = pd.DataFrame([{
        "Data": data_para_str(hoje),
        "Municipio": "Teresina",
        "Bairro": "Centro",
        "Latitude": -5.0892,
        "Longitude": -42.8019,
        "Pressao_MCA": 4.5
    }])
    st.download_button(
        "📥 Baixar Modelo CSV",
        data=df_modelo.to_csv(index=False).encode("utf-8"),
        file_name="modelo_importacao_coi.csv",
        mime="text/csv",
        use_container_width=True
    )

    arquivo = st.file_uploader("Enviar planilha (CSV / Excel)", type=["csv", "xlsx"])

    if arquivo is not None:
        try:
            if arquivo.name.endswith(".csv"):
                df_up = pd.read_csv(arquivo)
            else:
                df_up = pd.read_excel(arquivo)

            st.caption(f"{len(df_up)} linhas detectadas")
            st.dataframe(df_up.head(3), use_container_width=True)

            if st.button("📤 Processar e Enviar", type="primary", use_container_width=True):
                contador = 0
                erros = 0
                for _, row in df_up.iterrows():
                    # Data - normaliza para DD/MM/YYYY
                    data_raw = row.get("Data") or row.get("data")
                    data_reg = normalizar_data(data_raw)
                    if not data_reg:
                        data_reg = data_para_str(hoje)

                    mun = str(row.get("Municipio") or row.get("Município") or "Teresina").strip()
                    bairro = str(row.get("Bairro") or "").strip()
                    if not bairro or bairro.lower() in ("nan", "none"):
                        continue

                    lat = normalizar_coordenada(row.get("Latitude") or row.get("Lat"), "lat")
                    lon = normalizar_coordenada(row.get("Longitude") or row.get("Lon") or row.get("Long"), "lon")
                    pressao = parse_float(row.get("Pressao_MCA") or row.get("Pressão") or row.get("MCA"), 0.0)

                    if lat is None or lon is None:
                        erros += 1
                        continue

                    adicionar_ponto(mun, bairro, lat, lon, pressao, data_reg)
                    contador += 1

                msg = f"✅ {contador} registros importados."
                if erros:
                    msg += f" {erros} ignorados (coordenadas inválidas)."
                st.success(msg)
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao processar: {e}")

    st.divider()

    # ---------- EXPORTAÇÃO ----------
    st.markdown("#### 💾 Exportação")
    df_export = carregar_dados()

    if not df_export.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Plantao_COI")
        st.download_button(
            "📁 Baixar Excel",
            data=output.getvalue(),
            file_name=f"pontos_baixa_pressao_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        # KMZ
        kml = simplekml.Kml()
        for _, row in df_export.iterrows():
            if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                nome = f"{row['Municipio']} - {row['Bairro']} ({row['Pressao_MCA']} MCA)"
                kml.newpoint(name=nome, coords=[(row["Longitude"], row["Latitude"])])

        try:
            kmz_buffer = io.BytesIO()
            # simplekml savekmz espera path; usamos arquivo temporário
            temp_kmz = "temp_export.kmz"
            kml.savekmz(temp_kmz)
            with open(temp_kmz, "rb") as f:
                kmz_data = f.read()
            if os.path.exists(temp_kmz):
                os.remove(temp_kmz)
        except Exception:
            kmz_data = b""

        if kmz_data:
            st.download_button(
                "🗺️ Baixar KMZ",
                data=kmz_data,
                file_name="pontos_baixa_pressao.kmz",
                mime="application/vnd.google-earth.kmz",
                use_container_width=True
            )
    else:
        st.caption("Nenhum dado para exportar.")

    st.divider()

    # Atualização automática
    st.markdown("#### ⏱️ Atualização")
    intervalo = st.select_slider(
        "Intervalo (segundos)",
        options=[0, 15, 30, 60, 120],
        value=30,
        help="0 = desativado"
    )
    if intervalo > 0:
        st_autorefresh(interval=intervalo * 1000, key="autorefresh")

# ============================================================
# ÁREA PRINCIPAL
# ============================================================
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.caption(f"Visualizando: **{data_str_selecionada}**" + (" (hoje)" if data_escolhida == hoje else ""))

# Aplica filtros
df = carregar_dados()
df_filtrado = df[df["Data"] == data_str_selecionada].copy() if not df.empty else df.copy()

if mun_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Municipio"] == mun_sel]
if bairro_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Bairro"] == bairro_sel]

if faixa_sel == "Críticos (0 MCA)":
    df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] == 0]
elif faixa_sel == "Atenção (≤ 5 MCA)":
    df_filtrado = df_filtrado[(df_filtrado["Pressao_MCA"] > 0) & (df_filtrado["Pressao_MCA"] <= 5)]
elif faixa_sel == "Normais (> 5 MCA)":
    df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] > 5]

# ---------- KPIs ----------
if not df_filtrado.empty:
    total = len(df_filtrado)
    criticos = len(df_filtrado[df_filtrado["Pressao_MCA"] == 0])
    atencao = len(df_filtrado[(df_filtrado["Pressao_MCA"] > 0) & (df_filtrado["Pressao_MCA"] <= 5)])
    normais = len(df_filtrado[df_filtrado["Pressao_MCA"] > 5])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de Ocorrências", total)
    k2.metric("Críticos (0 MCA)", criticos, delta_color="inverse")
    k3.metric("Em Atenção (≤ 5 MCA)", atencao)
    k4.metric("Normais (> 5 MCA)", normais)

    if criticos > 0:
        st.error(f"🚨 **ALERTA COI:** Existem **{criticos}** ocorrência(s) com pressão zerada (0 MCA) exigindo ação imediata!")
else:
    st.info("Nenhum ponto registrado para a data e filtros selecionados.")

st.divider()

# ============================================================
# MAPA (PRIORIDADE VISUAL)
# ============================================================
st.subheader("🗺️ Mapa de Baixa Pressão")

c_map1, c_map2 = st.columns([1, 4])
with c_map1:
    mostrar_rotulos = st.checkbox("Exibir rótulos", value=False)
    if data_escolhida == hoje:
        st.session_state.modo_adicionar_mapa = st.checkbox(
            "📍 Modo adicionar ponto",
            value=st.session_state.modo_adicionar_mapa,
            help="Clique no mapa para capturar coordenadas (somente hoje)"
        )
    else:
        st.session_state.modo_adicionar_mapa = False
        st.caption("Adicionar pelo mapa disponível apenas na data de hoje.")

# Centro do mapa
if not df_filtrado.empty and df_filtrado["Latitude"].notna().any():
    centro_lat = float(df_filtrado["Latitude"].mean())
    centro_lon = float(df_filtrado["Longitude"].mean())
    zoom = 13
else:
    centro_lat, centro_lon = LAT_BASE, LON_BASE
    zoom = 12

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles="OpenStreetMap")

# GeoJSON opcional
if os.path.exists("bairros.geojson"):
    try:
        with open("bairros.geojson", "r", encoding="utf-8") as f:
            geojson_bairros = json.load(f)
        folium.GeoJson(
            geojson_bairros,
            name="Limites dos Bairros",
            style_function=lambda x: {
                "fillColor": "#3186cc",
                "color": "#2b2b2b",
                "weight": 1.5,
                "fillOpacity": 0.1
            },
            highlight_function=lambda x: {"weight": 3, "fillOpacity": 0.3}
        ).add_to(m)
    except Exception:
        pass

# Marcadores
if not df_filtrado.empty:
    validos = df_filtrado.dropna(subset=["Latitude", "Longitude"])
    for _, row in validos.iterrows():
        pressao = row["Pressao_MCA"]
        cor = "red" if pressao == 0 else ("orange" if pressao <= 5 else "blue")

        popup = f"""
        <b>ID:</b> {row['ID']}<br>
        <b>Data:</b> {row['Data']}<br>
        <b>Município:</b> {row['Municipio']}<br>
        <b>Bairro:</b> {row['Bairro']}<br>
        <b>Pressão:</b> {pressao} MCA
        """

        if mostrar_rotulos:
            icon_html = f"""
            <div style="transform: translate(-50%, -100%); text-align: center;">
                <div style="background:white;padding:2px 6px;border:1.5px solid {cor};
                            border-radius:4px;font-size:11px;font-weight:bold;
                            white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,0.3);">
                    {row['Bairro']} ({pressao} MCA)
                </div>
                <div style="background:{cor};width:12px;height:12px;border-radius:50%;
                            border:2px solid white;margin:2px auto 0;
                            box-shadow:0 0 3px rgba(0,0,0,0.6);"></div>
            </div>
            """
            icon = folium.DivIcon(html=icon_html, icon_size=(1, 1), icon_anchor=(0, 0))
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                icon=icon,
                popup=folium.Popup(popup, max_width=250)
            ).add_to(m)
        else:
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=folium.Popup(popup, max_width=250),
                tooltip=f"{row['Municipio']} - {row['Bairro']} ({pressao} MCA)",
                icon=folium.Icon(color=cor, icon="tint", prefix="fa")
            ).add_to(m)

folium.LayerControl().add_to(m)

map_data = st_folium(
    m,
    width="100%",
    height=520,
    returned_objects=["last_clicked"],
    key="mapa_principal"
)

# Captura clique (somente se modo ativo e data = hoje)
if (
    st.session_state.modo_adicionar_mapa
    and data_escolhida == hoje
    and map_data
    and map_data.get("last_clicked")
):
    clicked = map_data["last_clicked"]
    if clicked:
        st.session_state.clicked_lat = round(clicked["lat"], 6)
        st.session_state.clicked_lon = round(clicked["lng"], 6)
        st.success(f"📍 Coordenadas capturadas: {st.session_state.clicked_lat}, {st.session_state.clicked_lon}")
        st.info("Preencha Município, Bairro e Pressão na barra lateral e clique em **Cadastrar Ponto**.")
        st.rerun()

if df_filtrado.empty or df_filtrado.dropna(subset=["Latitude", "Longitude"]).empty:
    st.caption("Nenhum ponto com coordenadas válidas para esta data/filtros.")

st.divider()

# ============================================================
# TABELA DE REGISTROS + AÇÕES (abaixo do mapa)
# ============================================================
st.subheader("📋 Registro de Pontos")

if not df_filtrado.empty:
    df_show = df_filtrado[["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"]].copy()
    df_show = df_show.reset_index(drop=True)
    df_show.index = df_show.index + 1

    st.dataframe(df_show, use_container_width=True, height=280)

    st.markdown("##### Ações sobre o registro")
    opcoes = [
        f"{row['ID']} | {row['Municipio']} - {row['Bairro']} ({row['Pressao_MCA']} MCA)"
        for _, row in df_filtrado.iterrows()
    ]
    escolha = st.selectbox(
        "Selecione um registro:",
        ["— Nenhum —"] + opcoes,
        key="select_acao"
    )

    if escolha != "— Nenhum —":
        id_sel = escolha.split(" | ")[0]
        registro = df_filtrado[df_filtrado["ID"] == id_sel].iloc[0]

        col_a, col_b, col_c = st.columns([1, 1, 4])
        with col_a:
            if st.button("✏️ Editar", use_container_width=True, key="btn_editar"):
                st.session_state.registro_selecionado_id = id_sel
                st.session_state.modo_edicao = True
                st.rerun()
        with col_b:
            if st.button("🗑️ Excluir", use_container_width=True, key="btn_excluir"):
                if excluir_ponto(id_sel):
                    st.success("Registro excluído com sucesso.")
                    st.session_state.registro_selecionado_id = None
                    st.session_state.modo_edicao = False
                    st.rerun()
                else:
                    st.error("Erro ao excluir o registro.")

        # Formulário de edição (aparece quando clica no lápis)
        if st.session_state.modo_edicao and st.session_state.registro_selecionado_id == id_sel:
            st.markdown("---")
            st.markdown(f"**Editando registro:** `{id_sel}`")

            with st.form("form_edicao_inline"):
                e_mun = st.text_input("Município", value=registro["Municipio"])
                e_bairro = st.text_input("Bairro", value=registro["Bairro"])
                e1, e2 = st.columns(2)
                with e1:
                    e_lat = st.number_input("Latitude", format="%.6f", value=float(registro["Latitude"] or 0))
                with e2:
                    e_lon = st.number_input("Longitude", format="%.6f", value=float(registro["Longitude"] or 0))
                e_pressao = st.number_input("Pressão (MCA)", format="%.2f", value=float(registro["Pressao_MCA"]))
                e_data = st.text_input("Data (DD/MM/AAAA)", value=registro["Data"])

                c_save, c_cancel = st.columns(2)
                with c_save:
                    salvar = st.form_submit_button("💾 Salvar alterações", type="primary", use_container_width=True)
                with c_cancel:
                    cancelar = st.form_submit_button("Cancelar", use_container_width=True)

                if salvar:
                    ok = atualizar_ponto(
                        id_sel,
                        e_mun.strip(),
                        e_bairro.strip(),
                        e_lat,
                        e_lon,
                        e_pressao,
                        e_data.strip()
                    )
                    if ok:
                        st.success("Registro atualizado!")
                        st.session_state.modo_edicao = False
                        st.session_state.registro_selecionado_id = None
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar. Verifique se o ID existe na planilha.")
                if cancelar:
                    st.session_state.modo_edicao = False
                    st.session_state.registro_selecionado_id = None
                    st.rerun()
else:
    st.info("Nenhum ponto encontrado para a data e filtros selecionados.")
