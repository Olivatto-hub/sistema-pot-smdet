def obter_coluna_data_ordenacao(df):
    """Detecta automaticamente a coluna de data para ordenação, considerando múltiplos formatos"""
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'DATA', 'DATA_PAGTO']
    
    for coluna in colunas_data:
        if coluna in df.columns:
            # Tentar converter para datetime se ainda não estiver
            if not pd.api.types.is_datetime64_any_dtype(df[coluna]):
                try:
                    # Tentar diferentes formatos de data
                    df_temp = df.copy()
                    df_temp[coluna] = pd.to_datetime(df_temp[coluna], errors='coerce')
                    # Verificar se a conversão foi bem sucedida (não todos NaT)
                    if not df_temp[coluna].isna().all():
                        return coluna
                except:
                    continue
            else:
                return coluna
    
    # Se não encontrou coluna de data, usar o índice
    return None

# NOVA FUNÇÃO: Ordenar dados por data
def ordenar_por_data(df, coluna_data):
    """Ordena DataFrame por data de forma segura"""
    if coluna_data and coluna_data in df.columns:
        try:
            df_ordenado = df.copy()
            # Converter para datetime se necessário
            if not pd.api.types.is_datetime64_any_dtype(df_ordenado[coluna_data]):
                df_ordenado[coluna_data] = pd.to_datetime(
                    df_ordenado[coluna_data], 
                    dayfirst=True,  # Importante para formato brasileiro
                    errors='coerce'
                )
            
            # Ordenar por data (mais recente primeiro)
            df_ordenado = df_ordenado.sort_values(by=coluna_data, ascending=False)
            return df_ordenado
        except Exception as e:
            st.warning(f"Não foi possível ordenar por data: {str(e)}")
            return df
    else:
        return df
