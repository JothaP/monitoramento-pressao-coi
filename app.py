import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import simplekml
import matplotlib.pyplot as plt
import folium
import json
import os
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

# Configuração da página
st.set_page_config(page_title="Monitoramento de Pressão COI", page_icon="💧", layout="wide")

# Temporizador de recarregamento automático (a cada 30 segundos)
count = st_autorefresh(interval=30000, key="counter_pressao")

# Conexão com Google Sheets usando Secrets em formato JSON bruto
@st.cache_resource
# Conexão com Google Sheets usando o ID da planilha e o JSON bruto
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials_dict = json.loads(st.secrets["gcp_json"])
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    # Substitua "COLE_O_ID_DA_SUA_PLANILHA_AQUI" pelo ID real da sua planilha
    spreadsheet_id = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"
    sh = gc.open_by_key(spreadsheet_id)
    return sh.sheet1

worksheet = conectar_google_sheets()

def carregar_dados():
    registros = worksheet.get_all_records()
    return pd.DataFrame(registros)

# Título do Painel
st.title("💧 COI - Lançamento e Monitoramento de Baixa Pressão")
st.caption(f"Painel colaborativo em tempo real | Recarregamento automático ativo (30s) - Ciclo: {count}")

# Sidebar - Formulário de Entrada
st.sidebar.header("📍 Adicionar Novo Ponto")
with st.sidebar.form(key="form_ponto", clear_on_submit=True):
    bairro = st.text_input("Nome do Bairro")
    lat = st.number_input("Latitude", value=-5.0892, format="%.5f")
    lon = st.number_input("Longitude", value=-42.8016, format="%.5f")
    mca = st.number_input("Pressão Aferida (MCA)", value=5.0, min_value=0.0, step=0.1)
    
    submit = st.form_submit_button(label="➕ Salvar Ponto")

if submit:
    if bairro.strip():
        nova_linha = [bairro.strip(), float(lat), float(lon), float(mca)]
        worksheet.append_row(nova_linha)
        st.sidebar.success(f"Ponto em **{bairro}** ({mca} MCA) gravado!")
        st.rerun()
    else:
        st.sidebar.error("Preencha o nome do bairro!")

# Botão manual de atualização
if st.button("🔄 Atualizar Dados Agora"):
    st.rerun()

df = carregar_dados()

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
    if not df.empty:
        opcoes = [f"Linha {idx+2}: {row['Bairro']} ({row['Pressao_MCA']} MCA)" for idx, row in df.iterrows()]
        ponto_selecionado = st.selectbox("Selecione para remover:", opcoes)
        
        if st.button("🗑️ Confirmar Exclusão", type="primary"):
            linha_index = int(ponto_selecionado.split(":")[0].replace("Linha ", ""))
            worksheet.delete_rows(linha_index)
            st.success("Registro removido!")
            st.rerun()

st.divider()

# Mapa Interativo com Folium
st.subheader("🗺️ Mapa de Baixa Pressão em Tempo Real")

if not df.empty:
    centro_lat = df['Latitude'].mean()
    centro_lon = df['Longitude'].mean()
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=12, tiles="OpenStreetMap")
    
    # Adicionar polígonos de bairros (se o arquivo bairros.geojson existir no repositório)
    if os.path.exists("bairros.geojson"):
        with open("bairros.geojson", "r", encoding="utf-8") as f:
            geojson_bairros = json.load(f)
        folium.GeoJson(
            geojson_bairros,
            name="Limites dos Bairros",
            style_function=lambda feature: {'fillColor': '#3186cc', 'color': '#2b2b2b', 'weight': 1.5, 'fillOpacity': 0.1},
            highlight_function=lambda feature: {'weight': 3, 'fillOpacity': 0.3}
        ).add_to(m)

    # Marcadores dos pontos
    for _, row in df.iterrows():
        pressao = row['Pressao_MCA']
        cor = "red" if pressao < 5.0 else "orange" if pressao < 10.0 else "blue"
        
        popup_html = f"<b>Bairro:</b> {row['Bairro']}<br><b>Pressão:</b> {pressao} MCA"
        
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{row['Bairro']} ({pressao} MCA)",
            icon=folium.Icon(color=cor, icon="tint", prefix="fa")
        ).add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=500, returned_objects=[])
else:
    st.info("Nenhum ponto registrado para exibir no mapa.")

st.divider()

# Seção de Exportação
st.subheader("💾 Arquivamento e Exportação")
col_ex1, col_ex2, col_ex3 = st.columns(3)

if not df.empty:
    # CSV / Excel
    csv_data = df.to_csv(index=False).encode('utf-8')
    col_ex1.download_button("📁 Baixar Planilha (CSV)", data=csv_data, file_name="pontos_baixa_pressao.csv", mime="text/csv")

    # KMZ
    kml = simplekml.Kml()
    for _, row in df.iterrows():
        kml.newpoint(name=f"{row['Bairro']} - {row['Pressao_MCA']} MCA", coords=[(row['Longitude'], row['Latitude'])])
    kmz_path = "pontos.kmz"
    kml.savekmz(kmz_path)
    with open(kmz_path, "rb") as f:
        col_ex2.download_button("🗺️ Baixar Arquivo KMZ", data=f, file_name="pontos_baixa_pressao.kmz", mime="application/vnd.google-earth.kmz")

    # PNG
    fig, ax = plt.subplots(figsize=(8, 5))
    sc = ax.scatter(df['Longitude'], df['Latitude'], c=df['Pressao_MCA'], cmap='autumn', s=120, edgecolors='black')
    plt.colorbar(sc, label='Pressão (MCA)')
    for _, row in df.iterrows():
        ax.annotate(f"{row['Bairro']}\n({row['Pressao_MCA']} MCA)", (row['Longitude'], row['Latitude']), xytext=(0, 6), textcoords="offset points", ha='center', fontsize=8)
    plt.title('Pontos de Baixa Pressão Registrados')
    plt.grid(True, linestyle='--', alpha=0.6)
    png_path = "mapa_pressao.png"
    plt.savefig(png_path, bbox_inches='tight', dpi=150)
    plt.close()

    with open(png_path, "rb") as f:
        col_ex3.download_button("🖼️ Baixar Mapa PNG", data=f, file_name="mapa_pressao.png", mime="image/png")
