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

# Configuração da Página
st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide"
)

# Atualização automática a cada 30 segundos
st_autorefresh(interval=30000, key="datarefresh")

# Conexão com Google Sheets usando o ID da planilha e o JSON bruto dos Secrets
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials_dict = json.loads(st.secrets["gcp_json"])
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    spreadsheet_id = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"  # ID da planilha
    sh = gc.open_by_key(spreadsheet_id)
    return sh.sheet1

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# Função para carregar os dados
def carregar_dados():
    data = worksheet.get_all_records()
    if not data:
        return pd.DataFrame(columns=["Data", "Bairro", "Latitude", "Longitude", "Pressao_MCA"])
    return pd.DataFrame(data)

# Título Principal
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.markdown("Visualização em tempo real de ocorrências de baixa pressão e rede de abastecimento.")

# --- BARRA LATERAL ---
st.sidebar.header("➕ Novo Registro de Pressão")

# Formulário com campos limpos (sem valores estáticos pré-preenchidos)
with st.sidebar.form("form_ponto", clear_on_submit=True):
    bairro = st.text_input("Município / Bairro", value="", placeholder="Ex: Teresina - Centro")
    lat = st.number_input("Latitude", format="%.6f", value=0.000000, placeholder="Ex: -5.089200")
    lon = st.number_input("Longitude", format="%.6f", value=0.000000, placeholder="Ex: -42.801900")
    pressao = st.number_input("Pressão (MCA)", format="%.2f", value=0.00, placeholder="Ex: 4.50")
    
    enviado = st.form_submit_button("Cadastrar Ponto")
    if enviado:
        if bairro:
            # Data automática no formato dd/mm/aaaa correspondente ao dia de hoje
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            worksheet.append_row([data_hoje, bairro, lat, lon, pressao])
            st.sidebar.success(f"Ponto em {bairro} adicionado com sucesso!")
            st.rerun()
        else:
            st.sidebar.error("Informe o nome do bairro/município.")

st.sidebar.divider()

# Upload de Planilha em Massa na Barra Lateral
st.sidebar.header("📂 Importação em Massa")
arquivo_upload = st.sidebar.file_uploader("Enviar Planilha (CSV ou XLSX)", type=["csv", "xlsx"])

if arquivo_upload is not None:
    try:
        if arquivo_upload.name.endswith('.csv'):
            df_upload = pd.read_csv(arquivo_upload)
        else:
            df_upload = pd.read_excel(arquivo_upload)
            
        if st.sidebar.button("📤 Processar e Enviar para Planilha"):
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            contador = 0
            for _, row in df_upload.iterrows():
                b = row.get('Bairro', row.get('Município', ''))
                l = row.get('Latitude', 0)
                lg = row.get('Longitude', 0)
                p = row.get('Pressao_MCA', row.get('Pressão', 0))
                if pd.notna(b):
                    worksheet.append_row([data_hoje, str(b), float(l), float(lg), float(p)])
                    contador += 1
            st.sidebar.success(f"{contador} registros importados com sucesso!")
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro ao processar arquivo: {e}")

st.sidebar.divider()

# Botões de Exportação na Barra Lateral (logo abaixo da importação)
st.sidebar.header("💾 Exportação de Dados")

# Carregar e normalizar dados globais para exportação e uso no painel
df = carregar_dados()

if not df.empty:
    df.columns = [col.strip() for col in df.columns]
    
    col_map = {}
    for c in df.columns:
        c_lower = c.lower()
        if 'data' in c_lower:
            col_map[c] = 'Data'
        elif 'bairro' in c_lower or 'município' in c_lower:
            col_map[c] = 'Bairro'
        elif 'lat' in c_lower:
            col_map[c] = 'Latitude'
        elif 'lon' in c_lower:
            col_map[c] = 'Longitude'
        elif 'pressao' in c_lower or 'mca' in c_lower:
            col_map[c] = 'Pressao_MCA'
            
    df = df.rename(columns=col_map)
    
    # Garantir coluna de data caso não exista na planilha antiga
    if 'Data' not in df.columns:
        df['Data'] = datetime.now().strftime("%d/%m/%Y")

    # Conversão robusta de coordenadas
    for col in ['Latitude', 'Longitude']:
        if col in df.columns:
            s = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.strip()
            valores_num = pd.to_numeric(s, errors='coerce')
            if col == 'Latitude':
                valores_num = valores_num.apply(lambda x: x / 100000.0 if abs(x) > 90 else x)
            if col == 'Longitude':
                valores_num = valores_num.apply(lambda x: x / 100000.0 if abs(x) > 180 else x)
            df[col] = valores_num

    if 'Pressao_MCA' in df.columns:
        df['Pressao_MCA'] = pd.to_numeric(df['Pressao_MCA'].astype(str).str.replace(',', '.', regex=False).str.strip(), errors='coerce')

    # Botões na barra lateral
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button("📁 Baixar Planilha (CSV)", data=csv_data, file_name="pontos_baixa_pressao.csv", mime="text/csv")

    kml = simplekml.Kml()
    for _, row in df.iterrows():
        if pd.notna(row.get('Longitude')) and pd.notna(row.get('Latitude')):
            kml.newpoint(name=f"{row.get('Bairro', '')} - {row.get('Pressao_MCA', '')} MCA", coords=[(row['Longitude'], row['Latitude'])])
    kmz_path = "pontos.kmz"
    kml.savekmz(kmz_path)
    with open(kmz_path, "rb") as f:
        st.sidebar.download_button("🗺️ Baixar Arquivo KMZ", data=f, file_name="pontos_baixa_pressao.kmz", mime="application/vnd.google-earth.kmz")

# --- FILTROS NA ÁREA PRINCIPAL ---
if not df.empty:
    st.subheader("🔍 Filtros de Visualização")
    f_col1, f_col2 = st.columns(2)
    
    # Filtro por Data
    datas_disponiveis = sorted(df['Data'].dropna().unique().tolist())
    data_selecionada = f_col1.selectbox("Filtrar por Data", ["Todas"] + datas_disponiveis)
    
    # Filtro por Município / Bairro
    municipios_disponiveis = sorted(df['Bairro'].dropna().unique().tolist())
    municipio_selecionado = f_col2.selectbox("Filtrar por Município / Bairro", ["Todos"] + municipios_disponiveis)
    
    # Aplicar filtros
    df_filtrado = df.copy()
    if data_selecionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Data'] == data_selecionada]
    if municipio_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Bairro'] == municipio_selecionado]
else:
    df_filtrado = df.copy()

# --- MÉTRICAS RÁPIDAS (KPIs) ---
if not df_filtrado.empty:
    total_pontos = len(df_filtrado)
    criticos_zero = len(df_filtrado[df_filtrado['Pressao_MCA'] == 0])
    atencao = len(df_filtrado[(df_filtrado['Pressao_MCA'] > 0) & (df_filtrado['Pressao_MCA'] <= 5)])
    normais = len(df_filtrado[df_filtrado['Pressao_MCA'] > 5])
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total de Ocorrências", total_pontos)
    kpi2.metric("Críticos (0 MCA)", criticos_zero, delta_color="inverse")
    kpi3.metric("Em Atenção (≤ 5 MCA)", atencao)
    kpi4.metric("Normais (> 5 MCA)", normais)
    
    # Alerta Automático de Pontos Críticos (0 MCA)
    if criticos_zero > 0:
        st.error(f"🚨 **ALERTA COI:** Existem {criticos_zero} ocorrência(s) com pressão zerada (0 MCA) exigindo ação imediata da equipe técnica!")

st.divider()

# --- VISUALIZAÇÃO DE TABELA E EXCLUSÃO ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📋 Registro de Pontos do Plantão")
    if not df_filtrado.empty:
        # Ajustar índice da tabela para começar em 1 em vez de 0
        df_exibicao = df_filtrado.reset_index(drop=True)
        df_exibicao.index = df_exibicao.index + 1
        st.dataframe(df_exibicao, use_container_width=True)
    else:
        st.info("Nenhum ponto encontrado com os filtros selecionados.")

with col2:
    st.subheader("⚙️ Excluir Ponto")
    if not df.empty and 'Bairro' in df.columns and 'Pressao_MCA' in df.columns:
        opcoes = [f"Linha {idx+2}: {row['Bairro']} ({row['Pressao_MCA']} MCA - {row.get('Data', '')})" for idx, row in df.iterrows()]
        ponto_selecionado = st.selectbox("Selecione para remover:", opcoes)
        
        if st.button("🗑️ Confirmar Exclusão", type="primary"):
            linha_index = int(ponto_selecionado.split(":")[0].replace("Linha ", ""))
            worksheet.delete_rows(linha_index)
            st.success("Registro removido!")
            st.rerun()

st.divider()

# --- MAPA INTERATIVO COM FOLIUM ---
st.subheader("🗺️ Mapa de Baixa Pressão em Tempo Real")

mostrar_rotulos = st.checkbox("🔍 Exibir Rótulos", value=False)

if not df_filtrado.empty and 'Latitude' in df_filtrado.columns and 'Longitude' in df_filtrado.columns:
    valid_df = df_filtrado.dropna(subset=['Latitude', 'Longitude'])
    if not valid_df.empty:
        centro_lat = valid_df['Latitude'].mean()
        centro_lon = valid_df['Longitude'].mean()
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=12, tiles="OpenStreetMap")
        
        if os.path.exists("bairros.geojson"):
            with open("bairros.geojson", "r", encoding="utf-8") as f:
                geojson_bairros = json.load(f)
            folium.GeoJson(
                geojson_bairros,
                name="Limites dos Bairros",
                style_function=lambda feature: {'fillColor': '#3186cc', 'color': '#2b2b2b', 'weight': 1.5, 'fillOpacity': 0.1},
                highlight_function=lambda feature: {'weight': 3, 'fillOpacity': 0.3}
            ).add_to(m)

        for _, row in valid_df.iterrows():
            pressao = row.get('Pressao_MCA', 0.0)
            bairro_nome = row.get('Bairro', 'Desconhecido')
            data_reg = row.get('Data', '')
            
            # Regra de Cores: Vermelho (==0), Amarelo (<=5), Azul (>5)
            if pressao == 0:
                cor = "red"
            elif pressao <= 5:
                cor = "orange"
            else:
                cor = "blue"
            
            popup_html = f"<b>Data:</b> {data_reg}<br><b>Bairro:</b> {bairro_nome}<br><b>Pressão:</b> {pressao} MCA"
            
            if mostrar_rotulos:
                icon_html = f"""
                <div style="position: relative; display: flex; flex-direction: column; align-items: center; transform: translate(-50%, -100%);">
                    <div style="background: white; padding: 3px 8px; border: 1.5px solid {cor}; border-radius: 4px; font-size: 12px; font-weight: bold; white-space: nowrap; box-shadow: 0 1px 3px rgba(0,0,0,0.3); color: #222; margin-bottom: 2px;">
                        {bairro_nome} ({pressao} MCA)
                    </div>
                    <div style="background-color: {cor}; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 3px rgba(0,0,0,0.7);"></div>
                </div>
                """
                custom_icon = folium.DivIcon(html=icon_html, icon_size=(1, 1), icon_anchor=(0, 0))
                folium.Marker(
                    location=[row['Latitude'], row['Longitude']],
                    icon=custom_icon
                ).add_to(m)
            else:
                folium.Marker(
                    location=[row['Latitude'], row['Longitude']],
                    popup=folium.Popup(popup_html, max_width=250),
                    tooltip=f"{bairro_nome} ({pressao} MCA)",
                    icon=folium.Icon(color=cor, icon="tint", prefix="fa")
                ).add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, width="100%", height=550, returned_objects=[])
    else:
        st.info("Coordenadas válidas não encontradas para exibir no mapa.")
else:
   st.info("Nenhum ponto registrado para exibir no mapa.")
