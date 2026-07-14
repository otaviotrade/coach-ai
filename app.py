# --- Aba 4: Base de Conhecimento ---
with aba_docs:
    st.header("Diretório de Artigos")
    st.write("Suba vários PDFs com metodologias de treino de uma vez.")
    
    # 1. Permite múltiplos uploads de uma só vez
    arquivos_pdf = st.file_uploader("📚 Enviar Artigos (PDFs)", type=["pdf"], accept_multiple_files=True)
    
    # 2. Botão de Upload Manual
    if st.button("🚀 Processar e Salvar Documentos no Supabase"):
        if arquivos_pdf:
            with st.spinner("Lendo e gravando documentos no Supabase..."):
                for arquivo in arquivos_pdf:
                    try:
                        leitor = PyPDF2.PdfReader(arquivo)
                        texto_extraido = ""
                        for pagina in leitor.pages:
                            texto_extraido += pagina.extract_text()
                        
                        dados_artigo = {
                            "nome_arquivo": arquivo.name,
                            "conteudo_texto": texto_extraido
                        }
                        
                        # Inserção no Supabase
                        supabase.table("artigos_metodologia").insert(dados_artigo).execute()
                        
                        # Atualiza contexto local
                        st.session_state.contexto_artigos = f"{texto_extraido}\n\n{st.session_state.contexto_artigos}"[:80000]
                        
                        # 3. Confirmação individual de sucesso
                        st.success(f"✅ Documento '{arquivo.name}' processado e gravado com sucesso!")
                        
                    except Exception as e:
                        st.error(f"Erro ao processar '{arquivo.name}': {e}")
        else:
            st.warning("Por favor, selecione pelo menos um arquivo PDF antes de clicar em enviar.")
