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

# Configuração da Página
st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide"
)

# Atualização automática a cada 30 segundos
st_autorefresh(interval=10000, key="datarefresh")

# Coordenada Base Fixa (Centro de Teresina - PI)
LAT_BASE = -5.0892
LON_BASE = -42.8019

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
        return pd.DataFrame(columns=["Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"])
    return pd.DataFrame(data)

# Título Principal
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.markdown("Visualização em tempo real de ocorrências de baixa pressão e rede de abastecimento.")

# --- BARRA LATERAL ---
st.sidebar.header("➕ Novo Registro de Pressão")

with st.sidebar.form("form_ponto", clear_on_submit=True):
    municipio = st.text_input("Município", value="", placeholder="Ex: Teresina")
    bairro = st.text_input("Bairro", value="", placeholder="Ex: Centro")
    lat = st.number_input("Latitude", format="%.6f", value=0.000000, placeholder="Ex: -5.089200")
    lon = st.number_input("Longitude", format="%.6f", value=0.000000, placeholder="Ex: -42.801900")
    pressao = st.number_input("Pressão (MCA)", format="%.2f", value=0.00, placeholder="Ex: 4.50")
    
    enviado = st.form_submit_button("Cadastrar Ponto")
    if enviado:
        if municipio and bairro:
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            worksheet.append_row([data_hoje, municipio, bairro, lat, lon, pressao])
            st.sidebar.success(f"Ponto em {municipio} - {bairro} adicionado com sucesso!")
            st.rerun()
        else:
            st.sidebar.error("Informe o Município e o Bairro.")

st.sidebar.divider()

# --- EDIÇÃO DE REGISTROS NA BARRA LATERAL (VERSÃO ROBUSTA POR IDENTIFICADOR) ---
st.sidebar.header("✏️ Editar Registro")

# Força o recarregamento dos dados sem cache para garantir dados frescos
@st.cache_data(ttl=1)
def carregar_dados_frescos():
    return carregar_dados()

df_edit_check = carregar_dados_frescos()

if not df_edit_check.empty:
    df_edit_check.columns = [col.strip() for col in df_edit_check.columns]
    
    # Criamos um identificador único legível para cada linha baseado no conteúdo real
    opcoes_edicao = ["Nenhum"]
    mapa_registros = {}
    
    for idx, row in df_edit_check.iterrows():
        mun = str(row.get('Municipio', ''))
        bairro = str(row.get('Bairro', ''))
        pressao = str(row.get('Pressao_MCA', ''))
        data_reg = str(row.get('Data', ''))
        
        # Chave descritiva única
        chave = f"{mun} | {bairro} | {pressao} MCA ({data_reg})"
        opcoes_edicao.append(chave)
        mapa_registros[chave] = row.to_dict()

    ponto_para_editar = st.sidebar.selectbox("Selecione o registro:", opcoes_edicao, key="select_edicao_robusta")
    
    if ponto_para_editar != "Nenhum":
        dados_selecionados = mapa_registros[ponto_para_editar]
        
        with st.sidebar.form("form_edicao_robusta"):
            st.write(f"Editando: **{dados_selecionados.get('Municipio')} - {dados_selecionados.get('Bairro')}**")
            
            edit_mun = st.text_input("Município", value=str(dados_selecionados.get('Municipio', '')))
            edit_bairro = st.text_input("Bairro", value=str(dados_selecionados.get('Bairro', '')))
            
            def parse_float(val):
                try:
                    return float(str(val).replace(',', '.'))
                except:
                    return 0.0

            edit_lat = st.number_input("Latitude", format="%.6f", value=parse_float(dados_selecionados.get('Latitude', 0.0)))
            edit_lon = st.number_input("Longitude", format="%.6f", value=parse_float(dados_selecionados.get('Longitude', 0.0)))
            edit_pressao = st.number_input("Pressão (MCA)", format="%.2f", value=parse_float(dados_selecionados.get('Pressao_MCA', 0.0)))
            
            salvar_edicao = st.form_submit_button("💾 Salvar Alterações na Nuvem")
            
            if salvar_edicao:
                try:
                    # BUSCA DINÂMICA DA LINHA REAL NO GOOGLE SHEETS PELO CONTEÚDO
                    # Isso elimina qualquer erro de índice desalinhado pela importação em massa
                    celula_encontrada = worksheet.find(dados_selecionados.get('Bairro', ''))
                    
                    if celula_encontrada:
                        linha_real = celula_encontrada.row
                        data_atual = str(dados_selecionados.get('Data', datetime.now().strftime("%d/%m/%Y")))
                        
                        # Atualiza diretamente na linha exata encontrada pelo gspread
                        worksheet.update_cell(linha_real, 1, data_atual)
                        worksheet.update_cell(linha_real, 2, edit_mun)
                        worksheet.update_cell(linha_real, 3, edit_bairro)
                        worksheet.update_cell(linha_real, 4, edit_lat)
                        worksheet.update_cell(linha_real, 5, edit_lon)
                        worksheet.update_cell(linha_real, 6, edit_pressao)
                        
                        # Limpa todos os caches do Streamlit
                        st.cache_data.clear()
                        
                        st.sidebar.success(f"Registro atualizado com sucesso na linha {linha_real}!")
                        st.rerun()
                    else:
                        st.sidebar.error("Erro: O registro não foi encontrado na planilha do Google Sheets.")
                except Exception as e:
                    st.sidebar.error(f"Erro crítico ao atualizar: {e}")
# --- IMPORTAÇÃO EM MASSA E MODELO ---
st.sidebar.header("📂 Importação em Massa")

df_modelo = pd.DataFrame(columns=["Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"])
df_modelo.loc[0] = [datetime.now().strftime("%d/%m/%Y"), "Teresina", "Centro", -5.0892, -42.8019, 4.5]
csv_modelo = df_modelo.to_csv(index=False).encode('utf-8')

st.sidebar.download_button(
    "📥 Baixar Modelo de Planilha",
    data=csv_modelo,
    file_name="modelo_importacao_coi.csv",
    mime="text/csv",
    help="Baixe este arquivo para preencher com a estrutura correta antes de fazer o upload."
)

arquivo_upload = st.sidebar.file_uploader("Enviar Planilha Preenchida", type=["csv", "xlsx"])

if arquivo_upload is not None:
    try:
        if arquivo_upload.name.endswith('.csv'):
            df_upload = pd.read_csv(arquivo_upload)
        else:
            df_upload = pd.read_excel(arquivo_upload)
            
        if st.sidebar.button("📤 Processar e Enviar para Planilha"):
            df_upload.columns = [str(col).strip() for col in df_upload.columns]
            
            contador = 0
            for _, row in df_upload.iterrows():
                mun_val, bairro_val, lat_val, lon_val, pressao_val = "Teresina", "", 0.0, 0.0, 0.0
                
                for col in df_upload.columns:
                    c_lower = col.lower()
                    val = row[col]
                    if pd.isna(val):
                        continue
                        
                    if 'município' in c_lower or 'municipio' in c_lower:
                        mun_val = str(val)
                    elif 'bairro' in c_lower:
                        bairro_val = str(val)
                    elif 'lat' in c_lower:
                        lat_val = val
                    elif 'lon' in c_lower or 'long' in c_lower:
                        lon_val = val
                    elif 'pressao' in c_lower or 'pressão' in c_lower or 'mca' in c_lower:
                        pressao_val = val
                
                if not bairro_val:
                    for col in df_upload.columns:
                        if 'bairro' in col.lower() or 'local' in col.lower():
                            texto = str(row[col])
                            if " - " in texto:
                                partes = texto.split(" - ", 1)
                                mun_val, bairro_val = partes[0], partes[1]
                            else:
                                bairro_val = texto

                if bairro_val and bairro_val.lower() != 'nan':
                    data_hoje = datetime.now().strftime("%d/%m/%Y")
                    try:
                        lat_num = float(str(lat_val).replace(',', '.'))
                        lon_num = float(str(lon_val).replace(',', '.'))
                        if abs(lat_num) > 90: lat_num /= 100000.0
                        if abs(lon_num) > 180: lon_num /= 100000.0
                        pressao_num = float(str(pressao_val).replace(',', '.'))
                    except:
                        lat_num, lon_num, pressao_num = 0.0, 0.0, 0.0
                        
                    worksheet.append_row([data_hoje, mun_val, bairro_val, lat_num, lon_num, pressao_num])
                    contador += 1
                    
            st.sidebar.success(f"{contador} registros importados com sucesso!")
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro ao processar arquivo: {e}")

st.sidebar.divider()

# --- EXPORTAÇÃO DE DADOS NA BARRA LATERAL (EXCEL) ---
st.sidebar.header("💾 Exportação de Dados")

df = carregar_dados()

if not df.empty:
    df.columns = [col.strip() for col in df.columns]
    
    col_map = {}
    for c in df.columns:
        c_lower = c.lower()
        if 'data' in c_lower:
            col_map[c] = 'Data'
        elif 'município' in c_lower or 'municipio' in c_lower:
            col_map[c] = 'Municipio'
        elif 'bairro' in c_lower:
            col_map[c] = 'Bairro'
        elif 'lat' in c_lower:
            col_map[c] = 'Latitude'
        elif 'lon' in c_lower:
            col_map[c] = 'Longitude'
        elif 'pressao' in c_lower or 'mca' in c_lower:
            col_map[c] = 'Pressao_MCA'
            
    df = df.rename(columns=col_map)
    
    if 'Data' not in df.columns:
        df['Data'] = datetime.now().strftime("%d/%m/%Y")
    if 'Municipio' not in df.columns:
        df['Municipio'] = "Teresina"

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

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantao_COI')
    excel_data = output.getvalue()

    st.sidebar.download_button(
        "📁 Baixar Planilha (Excel / XLS)", 
        data=excel_data, 
        file_name="pontos_baixa_pressao.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    kml = simplekml.Kml()
    for _, row in df.iterrows():
        if pd.notna(row.get('Longitude')) and pd.notna(row.get('Latitude')):
            kml.newpoint(name=f"{row.get('Municipio', '')} - {row.get('Bairro', '')} ({row.get('Pressao_MCA', '')} MCA)", coords=[(row['Longitude'], row['Latitude'])])
    kmz_path = "pontos.kmz"
    kml.savekmz(kmz_path)
    with open(kmz_path, "rb") as f:
        st.sidebar.download_button("🗺️ Baixar Arquivo KMZ", data=f, file_name="pontos_baixa_pressao.kmz", mime="application/vnd.google-earth.kmz")

# --- FILTROS NA ÁREA PRINCIPAL ---
if not df.empty:
    st.subheader("🔍 Filtros de Visualização")
    f_col1, f_col2, f_col3 = st.columns(3)
    
    datas_disponiveis = sorted(df['Data'].dropna().unique().tolist())
    data_selecionada = f_col1.selectbox("Filtrar por Data", ["Todas"] + datas_disponiveis)
    
    municipios_disponiveis = sorted(df['Municipio'].dropna().unique().tolist())
    municipio_selecionado = f_col2.selectbox("Filtrar por Município", ["Todos"] + municipios_disponiveis)
    
    bairros_disponiveis = sorted(df['Bairro'].dropna().unique().tolist())
    bairro_selecionado = f_col3.selectbox("Filtrar por Bairro", ["Todos"] + bairros_disponiveis)
    
    df_filtrado = df.copy()
    if data_selecionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Data'] == data_selecionada]
    if municipio_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Municipio'] == municipio_selecionado]
    if bairro_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Bairro'] == bairro_selecionado]
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
    
    if criticos_zero > 0:
        st.error(f"🚨 **ALERTA COI:** Existem {criticos_zero} ocorrência(s) com pressão zerada (0 MCA) exigindo ação imediata da equipe técnica!")

st.divider()

# --- VISUALIZAÇÃO DE TABELA E EXCLUSÃO ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📋 Registro de Pontos do Plantão")
    if not df_filtrado.empty:
        df_exibicao = df_filtrado.reset_index(drop=True)
        df_exibicao.index = df_exibicao.index + 1
        st.dataframe(df_exibicao, use_container_width=True)
    else:
        st.info("Nenhum ponto encontrado com os filtros selecionados.")

with col2:
    st.subheader("⚙️ Excluir Ponto")
    if not df.empty and 'Municipio' in df.columns and 'Bairro' in df.columns and 'Pressao_MCA' in df.columns:
        opcoes = [f"Linha {idx+2}: {row['Municipio']} - {row['Bairro']} ({row['Pressao_MCA']} MCA - {row.get('Data', '')})" for idx, row in df.iterrows()]
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

# O mapa sempre é inicializado centralizado fixo no Centro de Teresina
m = folium.Map(location=[LAT_BASE, LON_BASE], zoom_start=12, tiles="OpenStreetMap")

# Carrega o GeoJSON dos bairros, caso exista
if os.path.exists("bairros.geojson"):
    with open("bairros.geojson", "r", encoding="utf-8") as f:
        geojson_bairros = json.load(f)
    folium.GeoJson(
        geojson_bairros,
        name="Limites dos Bairros",
        style_function=lambda feature: {'fillColor': '#3186cc', 'color': '#2b2b2b', 'weight': 1.5, 'fillOpacity': 0.1},
        highlight_function=lambda feature: {'weight': 3, 'fillOpacity': 0.3}
    ).add_to(m)

# Adiciona os marcadores se houver pontos filtrados válidos
if not df_filtrado.empty and 'Latitude' in df_filtrado.columns and 'Longitude' in df_filtrado.columns:
    valid_df = df_filtrado.dropna(subset=['Latitude', 'Longitude'])
    if not valid_df.empty:
        for _, row in valid_df.iterrows():
            pressao = row.get('Pressao_MCA', 0.0)
            mun_nome = row.get('Municipio', '')
            bairro_nome = row.get('Bairro', 'Desconhecido')
            data_reg = row.get('Data', '')
            
            if pressao == 0:
                cor = "red"
            elif pressao <= 5:
                cor = "orange"
            else:
                cor = "blue"
            
            popup_html = f"<b>Data:</b> {data_reg}<br><b>Município:</b> {mun_nome}<br><b>Bairro:</b> {bairro_nome}<br><b>Pressão:</b> {pressao} MCA"
            
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
                    tooltip=f"{mun_nome} - {bairro_nome} ({pressao} MCA)",
                    icon=folium.Icon(color=cor, icon="tint", prefix="fa")
                ).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, width="100%", height=550, returned_objects=[])

if df_filtrado.empty or df_filtrado.dropna(subset=['Latitude', 'Longitude']).empty:
    st.info("Nenhum ponto com coordenadas válidas encontrado para exibir no mapa.")
