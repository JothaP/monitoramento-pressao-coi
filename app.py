import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import simplekml
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
    
    spreadsheet_id = "1O3R4w8x-l6LqW0p6cQzX5N8t9R2v4Q7m1Z3x5N8t9R2"  # Substitua se necessário pelo ID exato da sua planilha
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
        return pd.DataFrame(columns=["Bairro", "Latitude", "Longitude", "Pressao_MCA"])
    return pd.DataFrame(data)

# Título Principal
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.markdown("Visualização em tempo real de ocorrências de baixa pressão e rede de abastecimento.")

# Barra lateral para cadastro rápido via formulário integrado
st.sidebar.header("➕ Novo Registro de Pressão")
with st.sidebar.form("form_ponto", clear_on_submit=True):
    bairro = st.text_input("Município / Bairro")
    lat = st.number_input("Latitude", format="%.6f", value=-5.0892)
    lon = st.number_input("Longitude", format="%.6f", value=-42.8019)
    pressao = st.number_input("Pressão (MCA)", format="%.2f", value=4.5)
    
    enviado = st.form_submit_button("Cadastrar Ponto")
    if enviado:
        if bairro:
            worksheet.append_row([bairro, lat, lon, pressao])
            st.sidebar.success(f"Ponto em {bairro} adicionado com sucesso!")
            st.rerun()
        else:
            st.sidebar.error("Informe o nome do bairro/município.")

# Carregar e normalizar dados
df = carregar_dados()

if not df.empty:
    df.columns = [col.strip() for col in df.columns]
    
    col_map = {}
    for c in df.columns:
        c_lower = c.lower()
        if 'bairro' in c_lower or 'município' in c_lower:
            col_map[c] = 'Bairro'
        elif 'lat' in c_lower:
            col_map[c] = 'Latitude'
        elif 'lon' in c_lower:
            col_map[c] = 'Longitude'
        elif 'pressao' in c_lower or 'mca' in c_lower:
            col_map[c] = 'Pressao_MCA'
            
    df = df.rename(columns=col_map)
    
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

# Visualização de Tabela e Exclusão
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📋 Registro de Pontos do Dia")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum ponto registrado no momento.")

with col2:
    st.subheader("⚙️ Excluir Ponto")
    if not df.empty and 'Bairro' in df.columns and 'Pressao_MCA' in df.columns:
        opcoes = [f"Linha {idx+2}: {row['Bairro']} ({row['Pressao_MCA']} MCA)" for idx, row in df.iterrows()]
        ponto_selecionado = st.selectbox("Selecione para remover:", opcoes)
        
        if st.button("🗑️ Confirmar Exclusão", type="primary"):
            linha_index = int(ponto_selecionado.split(":")[0].replace("Linha ", ""))
            worksheet.delete_rows(linha_index)
            st.success("Registro removido!")
            st.rerun()

st.divider()

# Controles do Mapa
st.subheader("🗺️ Mapa de Baixa Pressão em Tempo Real")

# Botão compacto "Exibir Rótulos"
mostrar_rotulos = st.checkbox("🔍 Exibir Rótulos", value=False)

if not df.empty and 'Latitude' in df.columns and 'Longitude' in df.columns:
    valid_df = df.dropna(subset=['Latitude', 'Longitude'])
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
            
            # Cores conforme regra solicitada:
            # Vermelho == 0
            # Amarelo <= 5
            # Azul > 5
            if pressao == 0:
                cor = "red"
            elif pressao <= 5:
                cor = "orange"
            else:
                cor = "blue"
            
            popup_html = f"<b>Bairro:</b> {bairro_nome}<br><b>Pressão:</b> {pressao} MCA"
            
            if mostrar_rotulos:
                # Estilização compacta em DivIcon para evitar sobreposição excessiva e manter proporção no zoom
                icon_html = f"""
                <div style="position: relative; display: flex; flex-direction: column; align-items: center; transform: translate(-50%, -100%);">
                    <div style="background: white; padding: 2px 6px; border: 1.5px solid {cor}; border-radius: 4px; font-size: 10px; font-weight: bold; white-space: nowrap; box-shadow: 0 1px 3px rgba(0,0,0,0.3); color: #222; margin-bottom: 2px;">
                        {bairro_nome} ({pressao} MCA)
                    </div>
                    <div style="background-color: {cor}; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 3px rgba(0,0,0,0.7);"></div>
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

st.divider()

# Seção de Exportação (CSV e KMZ)
st.subheader("💾 Exportação de Dados")
col_ex1, col_ex2 = st.columns(2)

if not df.empty:
    csv_data = df.to_csv(index=False).encode('utf-8')
    col_ex1.download_button("📁 Baixar Planilha (CSV)", data=csv_data, file_name="pontos_baixa_pressao.csv", mime="text/csv")

    kml = simplekml.Kml()
    for _, row in df.iterrows():
        if pd.notna(row.get('Longitude')) and pd.notna(row.get('Latitude')):
            kml.newpoint(name=f"{row.get('Bairro', '')} - {row.get('Pressao_MCA', '')} MCA", coords=[(row['Longitude'], row['Latitude'])])
    kmz_path = "pontos.kmz"
    kml.savekmz(kmz_path)
    with open(kmz_path, "rb") as f:
        col_ex2.download_button("🗺️ Baixar Arquivo KMZ", data=f, file_name="pontos_baixa_pressao.kmz", mime="application/vnd.google-earth.kmz")
