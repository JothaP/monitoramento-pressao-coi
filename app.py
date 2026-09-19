import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import simplekml
from datetime import datetime
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
    """Gera um ID curto e único."""
    return str(uuid.uuid4())[:8].upper()

def normalizar_coluna(nome: str) -> str:
    """Padroniza nomes de colunas."""
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
    """Converte valor para float de forma segura."""
    try:
        if pd.isna(valor):
            return default
        texto = str(valor).strip().replace(",", ".")
        return float(texto)
    except (ValueError, TypeError):
        return default

def normalizar_coordenada(valor, tipo: str = "lat") -> Optional[float]:
    """
    Normaliza coordenadas.
    Corrige casos em que o valor veio sem ponto decimal (ex: -5089200 → -5.089200).
    """
    num = parse_float(valor, None)
    if num is None:
        return None

    if tipo == "lat":
        if abs(num) > 90:
            num = num / 1_000_000 if abs(num) > 1000 else num / 100_000
    else:  # lon
        if abs(num) > 180:
            num = num / 1_000_000 if abs(num) > 1000 else num / 100_000

    # Validação básica para a região do Piauí
    if tipo == "lat" and not (-10.5 <= num <= -2.5):
        return None
    if tipo == "lon" and not (-46.0 <= num <= -40.0):
        return None

    return round(num, 6)

@st.cache_data(ttl=15, show_spinner="Carregando dados...")
def carregar_dados() -> pd.DataFrame:
    """Carrega e normaliza os dados da planilha."""
    try:
        registros = worksheet.get_all_records()
    except Exception as e:
        st.error(f"Erro ao ler planilha: {e}")
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    if not registros:
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    df = pd.DataFrame(registros)
    df.columns = [normalizar_coluna(c) for c in df.columns]

    # Garante colunas obrigatórias
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = None

    # Gera ID para registros antigos que não possuem
    if df["ID"].isna().any() or (df["ID"].astype(str).str.strip() == "").any():
        mask = df["ID"].isna() | (df["ID"].astype(str).str.strip() == "")
        df.loc[mask, "ID"] = [gerar_id() for _ in range(mask.sum())]

    # Normaliza tipos
    df["Latitude"] = df["Latitude"].apply(lambda x: normalizar_coordenada(x, "lat"))
    df["Longitude"] = df["Longitude"].apply(lambda x: normalizar_coordenada(x, "lon"))
    df["Pressao_MCA"] = df["Pressao_MCA"].apply(lambda x: parse_float(x, 0.0))
    df["Data"] = df["Data"].astype(str).str.strip()
    df["Municipio"] = df["Municipio"].astype(str).str.strip().replace("nan", "Teresina")
    df["Bairro"] = df["Bairro"].astype(str).str.strip().replace("nan", "")

    # Remove linhas completamente vazias
    df = df.dropna(how="all")
    df = df[df["Bairro"] != ""]

    return df[COLUNAS_PADRAO].reset_index(drop=True)

def limpar_cache():
    """Limpa o cache de dados."""
    carregar_dados.clear()

def adicionar_ponto(municipio: str, bairro: str, lat: float, lon: float, pressao: float, data: str = None):
    """Adiciona um novo ponto na planilha."""
    if data is None:
        data = datetime.now().strftime("%d/%m/%Y")
    
    novo_id = gerar_id()
    worksheet.append_row([novo_id, data, municipio, bairro, lat, lon, pressao])
    limpar_cache()
    return novo_id

def atualizar_ponto(id_registro: str, municipio: str, bairro: str, lat: float, lon: float, pressao: float, data: str):
    """Atualiza um ponto existente pelo ID."""
    # Busca a linha pelo ID (mais confiável)
    try:
        celula = worksheet.find(id_registro)
        if celula is None:
            return False
        
        linha = celula.row
        worksheet.update(f"A{linha}:G{linha}", [[id_registro, data, municipio, bairro, lat, lon, pressao]])
        limpar_cache()
        return True
    except Exception:
        return False

def excluir_ponto(id_registro: str) -> bool:
    """Exclui um ponto pelo ID."""
    try:
        celula = worksheet.find(id_registro)
        if celula is None:
            return False
        worksheet.delete_rows(celula.row)
        limpar_cache()
        return True
    except Exception:
        return False

# ============================================================
# SESSION STATE
# ============================================================
if "clicked_lat" not in st.session_state:
    st.session_state.clicked_lat = None
if "clicked_lon" not in st.session_state:
    st.session_state.clicked_lon = None
if "modo_adicionar_mapa" not in st.session_state:
    st.session_state.modo_adicionar_mapa = False

# ============================================================
# SIDEBAR - CONTROLES
# ============================================================
with st.sidebar:
    st.title("💧 COI - Controle")
    
    # --- Atualização automática ---
    st.subheader("⏱️ Atualização")
    intervalo = st.select_slider(
        "Intervalo de atualização (segundos)",
        options=[0, 15, 30, 60, 120],
        value=30,
        help="0 = desativado"
    )
    if intervalo > 0:
        st_autorefresh(interval=intervalo * 1000, key="datarefresh")

    st.divider()

    # --- NOVO REGISTRO MANUAL ---
    st.subheader("➕ Novo Registro")

    # Se veio de clique no mapa, pré-preenche
    lat_default = st.session_state.clicked_lat if st.session_state.clicked_lat is not None else 0.0
    lon_default = st.session_state.clicked_lon if st.session_state.clicked_lon is not None else 0.0

    with st.form("form_novo_ponto", clear_on_submit=True):
        municipio = st.text_input("Município *", value="Teresina", placeholder="Ex: Teresina")
        bairro = st.text_input("Bairro *", placeholder="Ex: Centro")
        
        col_lat, col_lon = st.columns(2)
        with col_lat:
            lat = st.number_input("Latitude *", format="%.6f", value=float(lat_default), step=0.000001)
        with col_lon:
            lon = st.number_input("Longitude *", format="%.6f", value=float(lon_default), step=0.000001)
        
        pressao = st.number_input("Pressão (MCA) *", format="%.2f", value=0.00, min_value=0.0, step=0.1)
        
        enviado = st.form_submit_button("Cadastrar Ponto", type="primary", use_container_width=True)
        
        if enviado:
            if not municipio.strip() or not bairro.strip():
                st.error("Município e Bairro são obrigatórios.")
            elif lat == 0.0 and lon == 0.0:
                st.error("Informe coordenadas válidas (ou clique no mapa).")
            else:
                lat_norm = normalizar_coordenada(lat, "lat")
                lon_norm = normalizar_coordenada(lon, "lon")
                
                if lat_norm is None or lon_norm is None:
                    st.error("Coordenadas fora da região válida (Piauí).")
                else:
                    novo_id = adicionar_ponto(municipio.strip(), bairro.strip(), lat_norm, lon_norm, pressao)
                    st.success(f"✅ Ponto cadastrado! ID: {novo_id}")
                    # Limpa o clique do mapa
                    st.session_state.clicked_lat = None
                    st.session_state.clicked_lon = None
                    st.rerun()

    if st.session_state.clicked_lat is not None:
        st.info(f"📍 Coordenadas do mapa:\n`{st.session_state.clicked_lat:.6f}, {st.session_state.clicked_lon:.6f}`")
        if st.button("Limpar coordenadas do mapa", use_container_width=True):
            st.session_state.clicked_lat = None
            st.session_state.clicked_lon = None
            st.rerun()

    st.divider()

    # --- EDIÇÃO ---
    st.subheader("✏️ Editar Registro")
    
    df_edit = carregar_dados()
    
    if not df_edit.empty:
        opcoes = ["— Selecione —"] + [
            f"{row['ID']} | {row['Municipio']} - {row['Bairro']} ({row['Pressao_MCA']} MCA)"
            for _, row in df_edit.iterrows()
        ]
        
        escolha = st.selectbox("Registro:", opcoes, key="select_edicao")
        
        if escolha != "— Selecione —":
            id_sel = escolha.split(" | ")[0]
            registro = df_edit[df_edit["ID"] == id_sel].iloc[0]
            
            with st.form("form_edicao"):
                st.caption(f"Editando ID: **{id_sel}**")
                
                edit_mun = st.text_input("Município", value=registro["Municipio"])
                edit_bairro = st.text_input("Bairro", value=registro["Bairro"])
                edit_lat = st.number_input("Latitude", format="%.6f", value=float(registro["Latitude"] or 0))
                edit_lon = st.number_input("Longitude", format="%.6f", value=float(registro["Longitude"] or 0))
                edit_pressao = st.number_input("Pressão (MCA)", format="%.2f", value=float(registro["Pressao_MCA"]))
                edit_data = st.text_input("Data", value=registro["Data"])
                
                if st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
                    sucesso = atualizar_ponto(
                        id_sel, edit_mun.strip(), edit_bairro.strip(),
                        edit_lat, edit_lon, edit_pressao, edit_data.strip()
                    )
                    if sucesso:
                        st.success("Registro atualizado!")
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar. Tente novamente.")
    else:
        st.caption("Nenhum registro para editar.")

    st.divider()

    # --- IMPORTAÇÃO EM MASSA ---
    st.subheader("📂 Importação em Massa")
    
    # Modelo
    df_modelo = pd.DataFrame([{
        "Data": datetime.now().strftime("%d/%m/%Y"),
        "Municipio": "Teresina",
        "Bairro": "Centro",
        "Latitude": -5.0892,
        "Longitude": -42.8019,
        "Pressao_MCA": 4.5
    }])
    csv_modelo = df_modelo.to_csv(index=False).encode("utf-8")
    
    st.download_button(
        "📥 Baixar Modelo CSV",
        data=csv_modelo,
        file_name="modelo_importacao_coi.csv",
        mime="text/csv",
        use_container_width=True
    )
    
    arquivo = st.file_uploader("Enviar planilha (CSV ou Excel)", type=["csv", "xlsx"])
    
    if arquivo is not None:
        try:
            if arquivo.name.endswith(".csv"):
                df_up = pd.read_csv(arquivo)
            else:
                df_up = pd.read_excel(arquivo)
            
            st.caption(f"Arquivo com **{len(df_up)}** linhas")
            st.dataframe(df_up.head(3), use_container_width=True)
            
            if st.button("📤 Processar e Enviar", type="primary", use_container_width=True):
                contador = 0
                erros = 0
                
                for _, row in df_up.iterrows():
                    mun = str(row.get("Municipio") or row.get("Município") or "Teresina").strip()
                    bairro = str(row.get("Bairro") or "").strip()
                    
                    if not bairro or bairro.lower() == "nan":
                        continue
                    
                    lat = normalizar_coordenada(row.get("Latitude") or row.get("Lat"), "lat")
                    lon = normalizar_coordenada(row.get("Longitude") or row.get("Lon") or row.get("Long"), "lon")
                    pressao = parse_float(row.get("Pressao_MCA") or row.get("Pressão") or row.get("MCA"), 0.0)
                    
                    if lat is None or lon is None:
                        erros += 1
                        continue
                    
                    adicionar_ponto(mun, bairro, lat, lon, pressao)
                    contador += 1
                
                st.success(f"✅ {contador} registros importados." + (f" {erros} ignorados por coordenadas inválidas." if erros else ""))
                st.rerun()
                
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")

    st.divider()

    # --- EXPORTAÇÃO ---
    st.subheader("💾 Exportação")
    
    df_export = carregar_dados()
    
    if not df_export.empty:
        # Excel
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
        
        kmz_buffer = io.BytesIO()
        kml.savekmz(kmz_buffer)  # simplekml aceita file-like em versões recentes
        # Fallback caso a versão não suporte BytesIO diretamente
        try:
            kmz_data = kmz_buffer.getvalue()
        except Exception:
            # Salva temporariamente
            kml.savekmz("temp_pontos.kmz")
            with open("temp_pontos.kmz", "rb") as f:
                kmz_data = f.read()
            if os.path.exists("temp_pontos.kmz"):
                os.remove("temp_pontos.kmz")
        
        st.download_button(
            "🗺️ Baixar KMZ",
            data=kmz_data,
            file_name="pontos_baixa_pressao.kmz",
            mime="application/vnd.google-earth.kmz",
            use_container_width=True
        )
    else:
        st.caption("Nenhum dado para exportar.")

# ============================================================
# ÁREA PRINCIPAL
# ============================================================
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.caption("Visualização em tempo real de ocorrências de baixa pressão e rede de abastecimento.")

df = carregar_dados()

# --- FILTROS ---
if not df.empty:
    st.subheader("🔍 Filtros")
    
    f1, f2, f3, f4 = st.columns(4)
    
    with f1:
        datas = ["Todas"] + sorted(df["Data"].dropna().unique().tolist())
        data_sel = st.selectbox("Data", datas)
    
    with f2:
        municipios = ["Todos"] + sorted(df["Municipio"].dropna().unique().tolist())
        mun_sel = st.selectbox("Município", municipios)
    
    with f3:
        bairros = ["Todos"] + sorted(df["Bairro"].dropna().unique().tolist())
        bairro_sel = st.selectbox("Bairro", bairros)
    
    with f4:
        faixa = st.selectbox("Pressão", ["Todas", "Críticos (0 MCA)", "Atenção (≤ 5 MCA)", "Normais (> 5 MCA)"])
    
    # Aplica filtros
    df_filtrado = df.copy()
    
    if data_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado["Data"] == data_sel]
    if mun_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Municipio"] == mun_sel]
    if bairro_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Bairro"] == bairro_sel]
    
    if faixa == "Críticos (0 MCA)":
        df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] == 0]
    elif faixa == "Atenção (≤ 5 MCA)":
        df_filtrado = df_filtrado[(df_filtrado["Pressao_MCA"] > 0) & (df_filtrado["Pressao_MCA"] <= 5)]
    elif faixa == "Normais (> 5 MCA)":
        df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] > 5]
else:
    df_filtrado = df.copy()

# --- KPIs ---
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

st.divider()

# --- TABELA + EXCLUSÃO ---
col_tab, col_exc = st.columns([3, 1])

with col_tab:
    st.subheader("📋 Registro de Pontos")
    if not df_filtrado.empty:
        df_show = df_filtrado.copy()
        df_show.index = range(1, len(df_show) + 1)
        st.dataframe(
            df_show[["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"]],
            use_container_width=True,
            height=300
        )
    else:
        st.info("Nenhum ponto encontrado com os filtros selecionados.")

with col_exc:
    st.subheader("🗑️ Excluir")
    if not df.empty:
        opcoes_exc = [
            f"{row['ID']} | {row['Municipio']} - {row['Bairro']}"
            for _, row in df.iterrows()
        ]
        ponto_exc = st.selectbox("Selecione:", opcoes_exc, key="select_exclusao")
        
        if st.button("Confirmar Exclusão", type="primary", use_container_width=True):
            id_exc = ponto_exc.split(" | ")[0]
            if excluir_ponto(id_exc):
                st.success("Registro excluído!")
                st.rerun()
            else:
                st.error("Erro ao excluir.")
    else:
        st.caption("Nada para excluir.")

st.divider()

# ============================================================
# MAPA INTERATIVO
# ============================================================
st.subheader("🗺️ Mapa de Baixa Pressão em Tempo Real")

col_map1, col_map2 = st.columns([1, 3])
with col_map1:
    mostrar_rotulos = st.checkbox("Exibir rótulos nos pontos", value=False)
    st.session_state.modo_adicionar_mapa = st.checkbox(
        "📍 Modo adicionar ponto (clique no mapa)",
        value=st.session_state.modo_adicionar_mapa,
        help="Ative e clique no mapa para capturar coordenadas"
    )

# Centro do mapa
if not df_filtrado.empty and df_filtrado["Latitude"].notna().any():
    centro_lat = df_filtrado["Latitude"].mean()
    centro_lon = df_filtrado["Longitude"].mean()
    zoom = 13
else:
    centro_lat, centro_lon = LAT_BASE, LON_BASE
    zoom = 12

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles="OpenStreetMap")

# GeoJSON de bairros (se existir)
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

# Renderiza o mapa e captura cliques
map_data = st_folium(
    m,
    width="100%",
    height=550,
    returned_objects=["last_clicked"],
    key="mapa_principal"
)

# Captura clique no mapa
if st.session_state.modo_adicionar_mapa and map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    if clicked:
        st.session_state.clicked_lat = round(clicked["lat"], 6)
        st.session_state.clicked_lon = round(clicked["lng"], 6)
        st.success(f"📍 Coordenadas capturadas: {st.session_state.clicked_lat}, {st.session_state.clicked_lon}")
        st.info("Preencha Município, Bairro e Pressão na barra lateral e clique em **Cadastrar Ponto**.")
        st.rerun()

if df_filtrado.empty or df_filtrado.dropna(subset=["Latitude", "Longitude"]).empty:
    st.info("Nenhum ponto com coordenadas válidas para exibir no mapa.")
