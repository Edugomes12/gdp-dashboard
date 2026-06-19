import streamlit as st
import requests
import pandas as pd
import re
import time
from io import BytesIO

# ==========================================
# BACKEND: REGRAS DE NEGÓCIO E APIs
# ==========================================

def limpar_cep(cep) -> str:
    """Extrai apenas números e garante 8 dígitos com zeros à esquerda."""
    cep_str = str(cep)
    cep_limpo = re.sub(r'\D', '', cep_str)
    if not cep_limpo:
        return None
    return cep_limpo.zfill(8)

def buscar_viacep(cep: str) -> dict:
    """Consulta o endereço no ViaCEP."""
    url = f"https://viacep.com.br/ws/{cep}/json/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
        if dados.get("erro"):
            return None
        return dados
    except:
        return None

def buscar_lat_long(logradouro: str, cidade: str, estado: str) -> tuple:
    """
    Consulta o OpenStreetMap (Nominatim) para converter o endereço em Coordenadas.
    Retorna (Latitude, Longitude).
    """
    # O Nominatim exige um User-Agent válido para solicitações gratuitas
    headers = {'User-Agent': 'BuscadorLatLongApp/1.0 (seu_email@exemplo.com)'}
    
    # Montamos a query com os dados do ViaCEP
    query = f"{logradouro}, {cidade}, {estado}, Brazil"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': query,
        'format': 'json',
        'limit': 1
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        dados = response.json()
        if dados:
            return dados[0].get('lat'), dados[0].get('lon')
        return None, None
    except:
        return None, None

# ==========================================
# FRONTEND: INTERFACE STREAMLIT
# ==========================================

def main():
    st.set_page_config(page_title="Processador em Lote de CEPs", page_icon="📍", layout="wide")
    
    st.title("📍 Enriquecedor de Planilhas: CEP para Lat/Long")
    st.markdown("Faça o upload da sua planilha. O sistema irá ler todos os CEPs, buscar o endereço no ViaCEP e obter a Latitude e Longitude exatas no OpenStreetMap.")
    st.divider()

    # 1. Upload do Arquivo
    arquivo_upload = st.file_uploader("Carregue seu arquivo CSV ou Excel (ex: Edu.xlsx)", type=["csv", "xlsx"])

    if arquivo_upload is not None:
        try:
            # Tenta ler o arquivo de forma robusta
            if arquivo_upload.name.endswith('.csv'):
                df = pd.read_csv(arquivo_upload, sep=None, engine='python', encoding='utf-8-sig')
            else:
                df = pd.read_excel(arquivo_upload)
            
            st.success(f"✅ Arquivo carregado com {len(df)} linhas!")
            st.dataframe(df.head(5), use_container_width=True) # Mostra uma prévia

            # Identifica a coluna de CEP
            colunas_cep = [col for col in df.columns if 'CEP' in col.upper()]
            
            if not colunas_cep:
                st.error("❌ Não encontrei nenhuma coluna chamada 'CEP' na planilha.")
                return
            
            nome_col_cep = colunas_cep[0]

            # Se as colunas Lat/Long não existirem, cria-as
            if 'Latitude' not in df.columns:
                df['Latitude'] = ""
            if 'Longitude' not in df.columns:
                df['Longitude'] = ""
            if 'Logradouro_Encontrado' not in df.columns:
                df['Logradouro_Encontrado'] = ""

            st.info("Pressione o botão abaixo para começar a pesquisar as coordenadas para cada CEP da planilha.")
            
            # 2. Botão de Processamento
            if st.button("🚀 Processar todos os CEPs", type="primary"):
                
                barra_progresso = st.progress(0)
                texto_status = st.empty()
                total_linhas = len(df)
                
                # Prepara cópia do dataframe para atualizar
                df_resultado = df.copy()

                for index, row in df_resultado.iterrows():
                    cep_atual = limpar_cep(row[nome_col_cep])
                    texto_status.text(f"Processando linha {index + 1} de {total_linhas}... (CEP: {cep_atual})")
                    
                    if cep_atual:
                        # Passo A: ViaCEP
                        dados_endereco = buscar_viacep(cep_atual)
                        
                        if dados_endereco:
                            logradouro = dados_endereco.get('logradouro', '')
                            cidade = dados_endereco.get('localidade', '')
                            estado = dados_endereco.get('uf', '')
                            
                            df_resultado.at[index, 'Logradouro_Encontrado'] = f"{logradouro}, {cidade} - {estado}"
                            
                            # Passo B: Nominatim (Lat e Long)
                            if logradouro and cidade and estado:
                                lat, lon = buscar_lat_long(logradouro, cidade, estado)
                                df_resultado.at[index, 'Latitude'] = lat
                                df_resultado.at[index, 'Longitude'] = lon
                                
                                # Pausa obrigatória de 1 segundo (Regra do OpenStreetMap para evitar bloqueio)
                                time.sleep(1)
                    
                    # Atualiza a barra de progresso
                    progresso_atual = (index + 1) / total_linhas
                    barra_progresso.progress(progresso_atual)

                texto_status.success("🎉 Processamento concluído com sucesso!")
                
                # 3. Exibição do Resultado
                st.subheader("📊 Planilha Atualizada")
                st.dataframe(df_resultado, use_container_width=True)
                
                # 4. Exportação (Download)
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_resultado.to_excel(writer, index=False, sheet_name='CEPs_Processados')
                dados_excel = output.getvalue()
                
                st.download_button(
                    label="📥 Baixar Planilha com Latitude e Longitude",
                    data=dados_excel,
                    file_name="base_com_coordenadas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )

        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")

if __name__ == "__main__":
    main()
