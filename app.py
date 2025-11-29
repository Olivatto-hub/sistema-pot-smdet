# NOVA FUNÇÃO: Processar CPF para manter apenas números
def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''  # Manter como string vazia para campos em branco
    
    cpf_str = str(cpf).strip()
    
    # Remover TODOS os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Se ficou vazio após limpeza, retornar vazio
    if cpf_limpo == '':
        return ''
    
    # Completar com zeros à esquerda se tiver menos de 11 dígitos
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

# FUNÇÃO ATUALIZADA: Padronizar documentos - CPF apenas números
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, CPF apenas números"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'CPF':
                    # Para CPF: manter apenas números
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                elif coluna == 'RG':
                    # Para RG: manter números e letras (podem ter letras em RGs)
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                else:
                    # Para outros documentos: tratamento genérico
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^\w]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

# NOVA FUNÇÃO: Identificar CPFs problemáticos
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas de formatação"""
    problemas_cpf = {
        'cpfs_com_caracteres_invalidos': [],
        'cpfs_com_tamanho_incorreto': [],
        'cpfs_vazios': [],
        'total_problemas_cpf': 0,
        'detalhes_cpfs_problematicos': pd.DataFrame()
    }
    
    if 'CPF' not in df.columns:
        return problemas_cpf
    
    # Adicionar coluna com número da linha original
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    # Identificar problemas
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) else ''
        problemas = []
        
        # CPF vazio
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
        
        # CPF com caracteres não numéricos (após processamento não deveria ter, mas verifica)
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
        
        # CPF com tamanho incorreto (deve ter 11 dígitos)
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
        
        # Se há problemas, adicionar aos detalhes
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas': ', '.join(problemas)
            }
            
            # Adicionar informações adicionais para identificação
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in row:
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in row:
                info_problema['Nome'] = row[coluna_nome]
            
            problemas_cpf['detalhes_cpfs_problematicos'] = pd.concat([
                problemas_cpf['detalhes_cpfs_problematicos'],
                pd.DataFrame([info_problema])
            ], ignore_index=True)
    
    problemas_cpf['total_problemas_cpf'] = len(problemas_cpf['cpfs_com_caracteres_invalidos']) + \
                                         len(problemas_cpf['cpfs_com_tamanho_incorreto']) + \
                                         len(problemas_cpf['cpfs_vazios'])
    
    return problemas_cpf

# NOVA FUNÇÃO: Gerar planilha com ajustes realizados
def gerar_planilha_ajustes(dados_originais, dados_processados, metrics):
    """Gera planilha com os ajustes realizados nos dados"""
    try:
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba 1: Dados Originais vs Processados
            if 'pagamentos' in dados_originais and not dados_originais['pagamentos'].empty:
                df_original = dados_originais['pagamentos'].copy()
                df_processado = dados_processados['pagamentos'].copy()
                
                # Criar comparação para CPF
                if 'CPF' in df_original.columns:
                    df_comparacao = df_original[['CPF']].copy()
                    df_comparacao['CPF_Original'] = df_original['CPF'].fillna('')
                    df_comparacao['CPF_Processado'] = df_processado['CPF'].fillna('')
                    df_comparacao['Alteracao_CPF'] = df_comparacao['CPF_Original'] != df_comparacao['CPF_Processado']
                    
                    # Adicionar outras colunas importantes para contexto
                    coluna_conta = obter_coluna_conta(df_original)
                    if coluna_conta:
                        df_comparacao['Numero_Conta'] = df_original[coluna_conta]
                    
                    coluna_nome = obter_coluna_nome(df_original)
                    if coluna_nome:
                        df_comparacao['Nome'] = df_original[coluna_nome]
                    
                    df_comparacao.to_excel(writer, sheet_name='Ajustes_CPF', index=False)
            
            # Aba 2: Resumo de Ajustes
            resumo_ajustes = []
            
            # Contar ajustes de CPF
            if 'CPF' in df_original.columns:
                cpfs_alterados = len(df_comparacao[df_comparacao['Alteracao_CPF'] == True])
                resumo_ajustes.append({'Tipo_Ajuste': 'CPFs Formatados', 'Quantidade': cpfs_alterados})
            
            # Adicionar outros tipos de ajustes
            if metrics.get('documentos_padronizados', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'Documentos Processados', 'Quantidade': metrics['documentos_padronizados']})
            
            if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'CPFs com Zeros Adicionados', 'Quantidade': metrics['cpfs_com_zeros_adicional']})
            
            if metrics.get('registros_validos_com_letras', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'RGs com Letras Preservadas', 'Quantidade': metrics['registros_validos_com_letras']})
            
            df_resumo = pd.DataFrame(resumo_ajustes)
            df_resumo.to_excel(writer, sheet_name='Resumo_Ajustes', index=False)
            
            # Aba 3: Problemas Identificados
            if not metrics.get('resumo_ausencias', pd.DataFrame()).empty:
                metrics['resumo_ausencias'].to_excel(writer, sheet_name='Problemas_Identificados', index=False)
            
            # Aba 4: CPFs Problemáticos
            problemas_cpf = identificar_cpfs_problematicos(dados_processados['pagamentos'] if 'pagamentos' in dados_processados else pd.DataFrame())
            if not problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'].to_excel(writer, sheet_name='CPFs_Problematicos', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Erro ao gerar planilha de ajustes: {str(e)}")
        return None

# ATUALIZAR a função processar_dados para incluir análise de CPFs
def processar_dados(dados, nomes_arquivos=None):
    """Processa os dados para gerar métricas e análises"""
    metrics = {
        'beneficiarios_unicos': 0,
        'total_pagamentos': 0,
        'contas_unicas': 0,
        'projetos_ativos': 0,
        'valor_total': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'total_cpfs_duplicados': 0,
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'duplicidades_detalhadas': {},
        'pagamentos_pendentes': {},
        'total_registros_invalidos': 0,
        'problemas_cpf': {}  # NOVO: Análise de problemas com CPF
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # Processar planilha de PAGAMENTOS - apenas válidos
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        
        # Filtrar apenas pagamentos válidos (com número de conta)
        df = filtrar_pagamentos_validos(df_original)
        
        # NOVO: Analisar problemas com CPF
        metrics['problemas_cpf'] = identificar_cpfs_problematicos(df)
        
        # Resto do processamento permanece igual...
        # [mantenha o código existente aqui]

    return metrics

# ATUALIZAR a interface para mostrar problemas de CPF
# No with tab2: (Análise Detalhada) - Adicionar esta seção
with tab2:
    st.header("Análise Detalhada")
    
    # NOVA SEÇÃO: Problemas com CPF
    problemas_cpf = metrics.get('problemas_cpf', {})
    if problemas_cpf.get('total_problemas_cpf', 0) > 0:
        st.subheader("🔍 Problemas com CPF Identificados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("CPFs Vazios", problemas_cpf.get('cpfs_vazios', []))
        
        with col2:
            st.metric("CPFs com Caracteres Inválidos", len(problemas_cpf.get('cpfs_com_caracteres_invalidos', [])))
        
        with col3:
            st.metric("CPFs com Tamanho Incorreto", len(problemas_cpf.get('cpfs_com_tamanho_incorreto', [])))
        
        if not problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame()).empty:
            st.subheader("📋 Detalhes dos CPFs Problemáticos")
            st.dataframe(problemas_cpf['detalhes_cpfs_problematicos'], use_container_width=True)
    
    # [mantenha o resto do código existente da tab2]

# ATUALIZAR a tab6 (Relatórios) para incluir a planilha de ajustes
with tab6:
    st.header("Relatórios e Exportações")
    
    col1, col2, col3 = st.columns(3)  # NOVO: Adicionar terceira coluna
    
    with col1:
        st.subheader("Relatório Executivo (PDF)")
        if st.button("📄 Gerar Relatório PDF", type="primary"):
            with st.spinner("Gerando relatório PDF..."):
                pdf_bytes = gerar_pdf_executivo(dados, metrics, nomes_arquivos)
                if pdf_bytes:
                    st.success("✅ Relatório PDF gerado com sucesso!")
                    b64 = base64.b64encode(pdf_bytes).decode()
                    href = f'<a href="data:application/pdf;base64,{b64}" download="relatorio_pot_{data_hora_arquivo_brasilia()}.pdf">📥 Baixar Relatório PDF</a>'
                    st.markdown(href, unsafe_allow_html=True)
    
    with col2:
        st.subheader("Dados Completos (Excel)")
        if st.button("📊 Gerar Excel Completo"):
            with st.spinner("Gerando arquivo Excel..."):
                excel_bytes = gerar_excel_completo(dados, metrics)
                if excel_bytes:
                    st.success("✅ Arquivo Excel gerado com sucesso!")
                    b64 = base64.b64encode(excel_bytes).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="dados_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Excel Completo</a>'
                    st.markdown(href, unsafe_allow_html=True)
    
    # NOVA COLUNA: Planilha de Ajustes
    with col3:
        st.subheader("🛠️ Planilha de Ajustes")
        st.info("Gera planilha com todos os ajustes realizados nos dados")
        if st.button("📋 Gerar Planilha de Ajustes"):
            with st.spinner("Gerando planilha de ajustes..."):
                # Carregar dados originais novamente para comparação
                dados_originais = {}
                if 'pagamentos' in dados:
                    # Recarregar os dados originais sem processamento
                    upload_pagamentos = st.session_state.get("pagamentos")
                    if upload_pagamentos:
                        if upload_pagamentos.name.endswith('.xlsx'):
                            df_original = pd.read_excel(upload_pagamentos)
                        else:
                            df_original = pd.read_csv(upload_pagamentos, encoding='utf-8', sep=';')
                        dados_originais['pagamentos'] = df_original
                
                ajustes_bytes = gerar_planilha_ajustes(dados_originais, dados, metrics)
                if ajustes_bytes:
                    st.success("✅ Planilha de ajustes gerada com sucesso!")
                    b64 = base64.b64encode(ajustes_bytes).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="ajustes_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Planilha de Ajustes</a>'
                    st.markdown(href, unsafe_allow_html=True)
