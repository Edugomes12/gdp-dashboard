import streamlit as st
import requests
import re
import pandas as pd
from io import BytesIO

# ==========================================
# BACKEND: REGRAS DE NEGÓCIO E REQUISIÇÕES
# ==========================================

def limpar_e_validar_cep(cep: str) -> str:
    """Remove caracteres não numéricos. Retorna o CEP se tiver 8 dígitos, senão None."""
    cep_limpo = re.sub(r'\D', '', cep)
    return cep_limpo if len(cep_limpo) == 8 else None

def buscar_viacep(cep: str) -> dict:
    """Consulta a API gratuita do ViaCEP e trata erros de ligação."""
    url = f"https://viacep.com.br/ws/{cep}/json/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        dados = response.json()
        
        if dados.get("erro"):
            return {"erro": "CEP não encontrado na base dos Correios."}
        return dados
        
    except requests.exceptions.Timeout:
        return {"erro": "A ligação excedeu o tempo limite. Tente novamente."}
    except requests.exceptions.RequestException as e:
        return {"erro": f"Erro de comunicação com o ViaCEP: {str(e)}"}

def normalizar_coluna_cep(df: pd.DataFrame) -> pd.Series:
    """Garante que a coluna de CEPs do dataframe seja tratada, reconstruindo zeros perdidos."""
    # Procura a coluna de forma flexível, ignorando espaços invisíveis (BOM)
    coluna_cep = [col for col in df.columns if 'CEP' in col.upper()]
    
    if coluna_cep:
        nome_col = coluna_cep[0]
        # 1. Converte para texto
        # 2. Extrai estritamente os números
        ceps_limpos = df[nome_col].astype(str).str.replace(r'\D', '', regex=True)
        # 3. Adiciona os zeros perdidos à esquerda até formar os 8 dígitos necessários (.zfill)
        return ceps_limpos.apply(lambda x: x.zfill(8) if len(x) > 0 else x)
        
    return pd.Series(dtype=str)

def inicializar_estado():
    """Inicializa o histórico de pesquisas na sessão atual."""
    if 'historico' not in st.session_state:
        st.session_state.historico = pd.DataFrame(columns=[
            'CEP', 'Logradouro', 'Bairro', 'Localidade', 'UF', 'Latitude', 'Longitude'
        ])

# ==========================================
# FRONTEND: LAYOUT E INTERFACE (STREAMLIT)
# ==========================================

def main():
    st.set_page_config(page_title="Geocoding & CEP Analyzer", page_icon="🌍", layout="wide")
    inicializar_estado()

    st.title("🌍 Hub do Pesquisador: Pesquisa e Validação de CEPs")
    st.markdown("Interface otimizada para cruzamento de endereços com a sua base de coordenadas.")
    st.divider()

    # --- BARRA LATERAL (SIDEBAR) ---
    with st.sidebar:
        st.header("📂 Gerir Base de Dados")
        st.write("Carregue o seu ficheiro `Edu` (CSV ou Excel) para cruzar dados.")
        
        arquivo_upload = st.file_uploader("Selecione a sua base", type=["csv", "xlsx"])
        df_base = None
        
        if arquivo_upload is not None:
            try:
                # Motor super robusto: deteta vírgulas/ponto-e-vírgula e codificações problemáticas automaticamente
                if arquivo_upload.name.endswith('.csv'):
                    df_base = pd.read_csv(arquivo_upload, sep=None, engine='python', encoding='utf-8-sig')
                else:
                    df_base = pd.read_excel(arquivo_upload)
                
                st.success("✅ Base carregada com sucesso!")
                st.metric(label="Total de Registos", value=len(df_base))
            except Exception as e:
                st.error(f"Erro ao ler o ficheiro: {e}")

    # --- ESTRUTURA DE ABAS PRINCIPAIS ---
    aba_busca, aba_base, aba_exportacao = st.tabs([
        "🔍 1. Nova Pesquisa", 
        "📊 2. Visualizar Base Carregada", 
        "💾 3. Histórico e Exportação"
    ])

    with aba_busca:
        st.subheader("Consultar ViaCEP")
        
        col_input, col_btn, _ = st.columns([2, 1, 3])
        
        with col_input:
            cep_input = st.text_input("Digite o CEP:", placeholder="Ex: 01001-000", label_visibility="collapsed")
        with col_btn:
            btn_buscar = st.button("Pesquisar Endereço", type="primary", use_container_width=True)

        if btn_buscar:
            cep_valido = limpar_e_validar_cep(cep_input)
            
            if not cep_valido:
                st.warning("⚠️ Formato inválido. O CEP deve conter exatamente 8 dígitos numéricos.")
            else:
                with st.spinner("A consultar a base dos Correios via ViaCEP..."):
                    resultado = buscar_viacep(cep_valido)
                
                if "erro" in resultado:
                    st.error(f"❌ {resultado['erro']}")
                else:
                    st.success(f"✅ Endereço localizado para o CEP {resultado.get('cep')}")
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("UF", resultado.get('uf', '-'))
                    c2.metric("Cidade", resultado.get('localidade', '-'))
                    c3.metric("Bairro", resultado.get('bairro', '-'))
                    c4.metric("Logradouro", resultado.get('logradouro', '-'))
                    
                    # --- CRUZAMENTO COM O SEU FICHEIRO EDU ---
                    if df_base is not None:
                        ceps_base = normalizar_coluna_cep(df_base)
                        if cep_valido in ceps_base.values:
                            st.info("📌 **Aviso:** Este CEP **JÁ CONSTA** na sua base importada.")
                        else:
                            st.info("✨ **Aviso:** Este é um **NOVO CEP** e não está na sua base.")
                    else:
                        st.info("Nenhuma base de dados carregada para comparação.")

                    novo_registro = {
                        'CEP': resultado.get('cep'),
                        'Logradouro': resultado.get('logradouro'),
                        'Bairro': resultado.get('bairro'),
                        'Localidade': resultado.get('localidade'),
                        'UF': resultado.get('uf'),
                        'Latitude': '',  
                        'Longitude': ''  
                    }
                    
                    historico_atualizado = pd.concat([
                        st.session_state.historico, 
                        pd.DataFrame([novo_registro])
                    ], ignore_index=True)
                    st.session_state.historico = historico_atualizado.drop_duplicates(subset=['CEP'], keep='last')

    with aba_base:
        if df_base is not None:
            st.subheader(f"Base Original: {arquivo_upload.name}")
            st.dataframe(df_base, use_container_width=True, height=400)
        else:
            st.info("Utilize a barra lateral para carregar a sua folha de cálculo.")

    with aba_exportacao:
        st.subheader("CEPs Processados nesta Sessão")
        
        if st.session_state.historico.empty:
            st.write("Nenhum CEP foi pesquisado com sucesso ainda.")
        else:
            st.dataframe(st.session_state.historico, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                st.session_state.historico.to_excel(writer, index=False, sheet_name='Novos_Enderecos')
            dados_excel = output.getvalue()
            
            st.download_button(
                label="📥 Descarregar 'novos_enderecos.xlsx'",
                data=dados_excel,
                file_name="novos_enderecos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

if __name__ == "__main__":
    main()
