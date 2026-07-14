import streamlit as st
from supabase import create_client, Client
from openai import OpenAI
import base64
import PyPDF2
import gpxpy
from datetime import date
import json
import xml.etree.ElementTree as ET
import gc  # Gerenciador de memória RAM para evitar crash de OOM

# Configura a página para modo amplo
st.set_page_config(page_title="Coach IA", layout="wide", initial_sidebar_state="collapsed")

# --- Conexões de Banco e IA ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

cliente_openai = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
nome_modelo = "gpt-4o-mini"

def processar_imagem_openai(arquivo_imagem):
    return base64.b64encode(arquivo_imagem.getvalue()).decode('utf-8')

# --- Controle de Sessão de Autenticação ---
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "plano_periodizacao" not in st.session_state:
    st.session_state.plano_periodizacao = None

# --- TELA DE LOGIN / CADASTRO ---
if st.session_state.auth_user is None:
    st.title("🏋️‍♂️ AI Coach - Login")
    st.subheader("Acesse sua conta para visualizar seus treinos isolados")
    
    tab_login, tab_cadastro = st.tabs(["🔑 Entrar", "📝 Criar Conta"])
    
    with tab_login:
        with st.form("form_login"):
            email_login = st.text_input("E-mail")
            senha_login = st.text_input("Senha", type="password")
            botao_logar = st.form_submit_button("Entrar no Painel")
            
            if botao_logar:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                    if res.user:
                        st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
                        st.success("Acesso autorizado!")
                        st.rerun()
                except Exception as erro:
                    st.error(f"Falha ao entrar: {erro}")
                    
    with tab_cadastro:
        with st.form("form_cadastro"):
            email_cad = st.text_input("E-mail para Cadastro")
            senha_cad = st.text_input("Defina sua Senha (min. 6 caracteres)", type="password")
            botao_cadastrar = st.form_submit_button("Registrar Novo Atleta")
            
            if botao_cadastrar:
                try:
                    res = supabase.auth.sign_up({"email": email_cad, "password": senha_cad})
                    if res.user:
                        st.success("Conta criada com sucesso! Faça o login na aba ao lado.")
                except Exception as erro:
                    st.error(f"Falha ao registrar: {erro}")
    st.stop()

# --- SEÇÃO DO USUÁRIO LOGADO ---
user_id = st.session_state.auth_user["id"]
user_email = st.session_state.auth_user["email"]

# Menu de Logout lateral
with st.sidebar:
    st.write(f"👤 Logado como:\n**{user_email}**")
    if st.button("🚪 Sair da Conta", use_container_width=True):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.auth_user = None
        st.session_state.mensagens = []
        st.session_state.treino_rascunho = None
        st.session_state.plano_periodizacao = None
        st.rerun()

# --- Estado de Sessão para Controle de Aprovação de Treinos ---
if "treino_rascunho" not in st.session_state:
    st.session_state.treino_rascunho = None

# --- Sincronização do Histórico Persistente com o Supabase (Isolado) ---
if "mensagens" not in st.session_state or not st.session_state.mensagens:
    try:
        historico_banco = supabase.table("historico_conversas").select("role", "content").eq("user_id", user_id).order("id", desc=False).limit(30).execute()
        st.session_state.mensagens = historico_banco.data if historico_banco.data else []
    except Exception:
        st.session_state.mensagens = []

# --- Carregamento de Artigos Científicos (Global/Compartilhado) ---
if "contexto_artigos" not in st.session_state:
    try:
        artigos_banco = supabase.table("artigos_metodologia").select("conteudo_texto").order("id", desc=True).limit(3).execute()
        if artigos_banco.data:
            texto_unificado = "\n\n".join([art["conteudo_texto"] for art in artigos_banco.data if art.get("conteudo_texto")])
            st.session_state.contexto_artigos = texto_unificado[:80000]
        else:
            st.session_state.contexto_artigos = ""
    except Exception:
        st.session_state.contexto_artigos = ""

# --- Memória Central do Coach (Isolado) ---
try:
    resposta_memoria = supabase.table("memoria_coach").select("diretriz").eq("user_id", user_id).order("id", desc=True).limit(1).execute()
    memoria_central = resposta_memoria.data[0]["diretriz"] if resposta_memoria.data else ""
except Exception:
    memoria_central = ""

st.title("🏋️‍♂️ AI Coach de Treinos")

# Definição das abas do painel principal
aba_chat, aba_performance, aba_periodizacao, aba_pr, aba_docs, aba_cerebro = st.tabs([
    "💬 Coach Chat", 
    "📈 Resumo de Performance",
    "📅 Plano de Periodização",
    "🏆 Meus PRs", 
    "📚 Base de Conhecimento",
    "🧠 Cérebro do Coach"
])

# --- Aba 1: Coach Chat ---
with aba_chat:
    if st.session_state.treino_rascunho:
        rascunho = st.session_state.treino_rascunho
        tipo_formatado = "🏃‍♂️ CORRIDA" if rascunho.get("tipo_treino") == "corrida" else "🏋️‍♂️ CROSSFIT"
        
        with st.container(border=True):
            st.warning(f"📋 **Diagnóstico de Treino Gerado ({tipo_formatado}) - Aguardando sua Aprovação para Salvar:**")
            
            c_meta1, c_meta2, c_meta3 = st.columns(3)
            with c_meta1:
                st.write(f"**📅 Data:** {rascunho.get('data')}")
                if rascunho.get("tipo_treino") == "corrida":
                    st.write(f"**📏 Distância:** {rascunho.get('distancia')} km")
                    st.write(f"**⏱️ Pace Médio:** {rascunho.get('pace')}")
                else:
                    st.write(f"**📝 WOD:** {rascunho.get('descricao_wod')}")
                    st.write(f"**⏱️ Score/Tempo:** {rascunho.get('tempo_score')}")
            with c_meta2:
                if rascunho.get("tipo_treino") == "corrida":
                    st.write(f"**❤️ Frequência:** {rascunho.get('zonas_fc')}")
                    st.write(f"**🔄 Cadência:** {rascunho.get('cadencia_media')} ppm")
                    st.write(f"**⛰️ Elevação:** {rascunho.get('elevacao_acumulada')} m")
                else:
                    st.write(f"**🏋️ LPO Executado:** {rascunho.get('tipo_lpo')}")
                    st.write(f"**🔥 Percepção de Esforço (RPE):** {rascunho.get('percepcao_esforco')}/10")
            with c_meta3:
                st.write(f"**⚠️ Relato de Desconforto:** {rascunho.get('alerta_desconforto', 'Nenhum')}")

            st.markdown(f"---")
            st.markdown(f"**💬 Seu Feedback (Análise do Usuário):**\n*{rascunho.get('analise_usuario', 'Não informado')}*")
            st.markdown(f"**🧠 Análise Crítica do Coach (IA):**\n{rascunho.get('analise_ia')}")
            st.markdown(f"**📈 Relatório de Performance Geral (Histórico + Atual):**\n{rascunho.get('performance_geral')}")
            
            c_btn1, c_btn2 = st.columns(2)
            with c_btn1:
                if st.button("✅ Aprovar e Gravar no Supabase", use_container_width=True, key="btn_confirmar_banco"):
                    try:
                        if rascunho.get("tipo_treino") == "corrida":
                            payload = {
                                "data": rascunho.get("data"),
                                "distancia": rascunho.get("distancia"),
                                "elevacao_acumulada": rascunho.get("elevacao_acumulada"),
                                "pace": rascunho.get("pace"),
                                "zonas_fc": rascunho.get("zonas_fc"),
                                "cadencia_media": rascunho.get("cadencia_media"),
                                "analise_usuario": rascunho.get("analise_usuario"),
                                "analise_ia": rascunho.get("analise_ia"),
                                "performance_geral": rascunho.get("performance_geral"),
                                "user_id": user_id
                            }
                            supabase.table("treinos_corrida").insert({k: v for k, v in payload.items() if v is not None}).execute()
                        else:
                            payload = {
                                "data": rascunho.get("data"),
                                "descricao_wod": rascunho.get("descricao_wod"),
                                "tempo_score": rascunho.get("tempo_score"),
                                "tipo_lpo": rascunho.get("tipo_lpo"),
                                "percepcao_esforco": rascunho.get("percepcao_esforco"),
                                "alerta_desconforto": rascunho.get("alerta_desconforto"),
                                "analise_usuario": rascunho.get("analise_usuario"),
                                "analise_ia": rascunho.get("analise_ia"),
                                "performance_geral": rascunho.get("performance_geral"),
                                "user_id": user_id
                            }
                            supabase.table("treinos_crossfit").insert({k: v for k, v in payload.items() if v is not None}).execute()
                        
                        st.success("🎉 Dados de telemetria e análises críticas salvos com sucesso no Supabase!")
                        st.session_state.treino_rascunho = None
                        st.rerun()
                    except Exception as erro_banco:
                        st.error(f"Falha ao persistir dados: {erro_banco}")
            with c_btn2:
                if st.button("❌ Descartar e Ajustar Informações", use_container_width=True, key="btn_limpar_rascunho"):
                    st.session_state.treino_rascunho = None
                    st.rerun()

    with st.expander("📎 Anexar Mídias ao Chat (Fotos ou Arquivos GPX)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            fotos_treino = st.file_uploader("📸 Fotos do Treino", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="chat_foto")
        with c2:
            arquivos_gpx = st.file_uploader("📍 Arquivos GPX (Corrida)", type=["gpx"], accept_multiple_files=True, key="chat_gpx")

    st.divider()

    container_chat = st.container()

    with container_chat:
        for msg in st.session_state.mensagens:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    with st.form("form_chat", clear_on_submit=True):
        prompt = st.text_area("Fale com seu Coach...", placeholder="Relate as sensações do treino, dores ou envie fotos/gpx usando a área de anexo acima...", height=120)
        botao_enviar = st.form_submit_button("📤 Enviar para Análise do Coach")
    
    if botao_enviar and prompt.strip():
        st.session_state.mensagens.append({"role": "user", "content": prompt})
        try:
            supabase.table("historico_conversas").insert({"role": "user", "content": prompt, "user_id": user_id}).execute()
        except Exception:
            pass

        with container_chat:
            st.chat_message("user").markdown(prompt)
            
            with st.chat_message("assistant"):
                try:
                    prompt_enriquecido = prompt
                    if st.session_state.contexto_artigos != "":
                        prompt_enriquecido = f"Base teórica de artigos científicos para periodização:\n{st.session_state.contexto_artigos}\n\nInstrução do aluno: {prompt_enriquecido}"

                    if arquivos_gpx:
                        dados_acumulados = "\n\n[DADOS BRUTOS EXTRAÍDOS DE TODOS OS ARQUIVOS GPX SUBIDOS]:\n"
                        for arquivo in arquivos_gpx:
                            try:
                                arquivo.seek(0)
                                conteudo_texto = arquivo.read().decode("utf-8")
                                gpx = gpxpy.parse(conteudo_texto)
                                
                                distancia_total_metros = 0.0
                                ganho_elevacao_total = 0.0
                                lista_bpm = []
                                lista_cadencia = []
                                tempo_total_segundos = 0.0
                                data_treino = str(date.today())
                                
                                if gpx.tracks:
                                    for track in gpx.tracks:
                                        for segment in track.segments:
                                            if segment.points and segment.points[0].time and segment.points[-1].time:
                                                data_treino = str(segment.points[0].time.date())
                                                duracao = segment.points[-1].time - segment.points[0].time
                                                tempo_total_segundos += duracao.total_seconds()
                                            
                                            for i in range(len(segment.points) - 1):
                                                ponto_atual = segment.points[i]
                                                proximo_ponto = segment.points[i+1]
                                                
                                                distancia_ponto = ponto_atual.distance_3d(proximo_ponto)
                                                if distancia_ponto:
                                                    distancia_total_metros += distancia_ponto
                                                    
                                                if ponto_atual.elevation is not None and proximo_ponto.elevation is not None:
                                                    variacao = proximo_ponto.elevation - ponto_atual.elevation
                                                    if variacao > 0:
                                                        ganho_elevacao_total += variacao
                                                
                                                if ponto_atual.extensions:
                                                    for ext in ponto_atual.extensions:
                                                        try:
                                                            xml_str = ET.tostring(ext, encoding='utf-8').decode('utf-8')
                                                            root_ext = ET.fromstring(xml_str)
                                                            for elem in root_ext.iter():
                                                                tag_limpa = elem.tag.split('}')[-1].lower()
                                                                if tag_limpa in ['hr', 'heartrate', 'value', 'bpm'] and elem.text:
                                                                    lista_bpm.append(int(float(elem.text)))
                                                                if tag_limpa in ['cad', 'cadence'] and elem.text:
                                                                    lista_cadencia.append(int(float(elem.text)))
                                                        except Exception:
                                                            pass

                                distancia_km = distancia_total_metros / 1000.0
                                if distancia_km == 0:
                                    continue

                                dist_arredondada = float(round(distancia_km, 2))
                                elev_arredondada = float(round(ganho_elevacao_total, 2))

                                if tempo_total_segundos > 0:
                                    tempo_por_km_segundos = tempo_total_segundos / distancia_km
                                    minutos_pace = int(tempo_por_km_segundos // 60)
                                    segundos_pace = int(tempo_por_km_segundos % 60)
                                    pace_formatado = f"{minutos_pace}:{segundos_pace:02d} min/km"
                                else:
                                    pace_formatado = "--:-- min/km"

                                bpm_medio_str = f"{int(sum(lista_bpm) / len(lista_bpm))} BPM" if lista_bpm else "Sem dados de FC"
                                cadencia_media = int(sum(lista_cadencia) / len(lista_cadencia)) if lista_cadencia else None

                                dados_acumulados += f"- Arquivo: {arquivo.name}\n"
                                dados_acumulados += f"  Data Real: {data_treino} | Distância: {dist_arredondada} km | Altimetria: {elev_arredondada} m\n"
                                dados_acumulados += f"  Pace Médio Calculado: {pace_formatado} | Frequência Cardíaca: {bpm_medio_str} | Cadência Média: {cadencia_media}\n\n"
                                    
                            except Exception as erro_gpx:
                                dados_acumulados += f"- Erro na decodificação de {arquivo.name}: {erro_gpx}\n"
                                
                        prompt_enriquecido += dados_acumulados

                    conteudo_mensagem = [{"type": "text", "text": prompt_enriquecido}]

                    if fotos_treino:
                        for photo in fotos_treino:
                            imagem_base64 = processar_imagem_openai(photo)
                            conteudo_mensagem.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{imagem_base64}"}
                            })

                    # --- CORREÇÃO DE CONTEXTO: Janela de dados de treinos ---
                    contexto_maquina = "\n\n[MEMÓRIA DE TREINAMENTO E PROGRESSÃO (ÚLTIMOS 30 TREINOS)]:\n"
                    try:
                        corrida_historico = supabase.table("treinos_corrida").select("data", "distancia", "pace", "zonas_fc").eq("user_id", user_id).order("data", desc=True).limit(30).execute()
                        cross_historico = supabase.table("treinos_crossfit").select("data", "descricao_wod", "tempo_score", "alerta_desconforto").eq("user_id", user_id).order("data", desc=True).limit(30).execute()
                        saude_historico = supabase.table("metricas_diarias").select("data", "vfc", "nivel_dor_muscular", "horas_sono").eq("user_id", user_id).order("data", desc=True).limit(10).execute()
                        prs_historico = supabase.table("prs").select("movimento", "carga").eq("user_id", user_id).execute()
                        
                        if corrida_historico.data: contexto_maquina += f"- Histórico Corridas: {corrida_historico.data}\n"
                        if cross_historico.data: contexto_maquina += f"- Histórico CrossFit: {cross_historico.data}\n"
                        if saude_historico.data: contexto_maquina += f"- Histórico Biométrico: {saude_historico.data}\n"
                        if prs_historico.data: contexto_maquina += f"- Recordes Atuais (PRs): {prs_historico.data}\n"
                    except Exception:
                        pass

                    # --- CORREÇÃO DE MEMÓRIA: Periodização ativa ---
                    plano_ativo = st.session_state.get("plano_periodizacao")
                    contexto_periodizacao = f"\n[PLANO DE PERIODIZAÇÃO EXECUTADO PELO ATLETA]:\n{plano_ativo}\n" if plano_ativo else "\n[PLANO DE PERIODIZAÇÃO]: Nenhum planejamento gerado nesta sessão ainda.\n"

                    mensagens_api = []
                    contexto_sistema = f"{memoria_central}\nData atual do sistema: {str(date.today())}.\n{contexto_maquina}\n{contexto_periodizacao}\n"
                    contexto_sistema += (
                        "INSTRUÇÃO DE COMPORTAMENTO CRÍTICO (SEVERO):\n"
                        "Você é um Coach de Elite extremamente técnico, rigoroso e cientificamente inflexível. "
                        "Não massageie o ego do atleta e evite adjetivos de incentivo vazios. "
                        "Sua prioridade total é identificar falhas metodológicas, erros de pacing (ritmo), assimetria mecânica, "
                        "queda abrupta de cadência, excesso de fadiga acumulada por má qualidade do sono/VFC, e sinais de sobrecarga articular.\n\n"
                        "💡 SOBRE O CICLO ATUAL:\n"
                        "O atleta forneceu um histórico estendido de treinos e o plano de periodização científica gerado. "
                        "Use estes dados, cruze as datas dos treinos com o início do planejamento e calcule com precisão em qual semana "
                        "do ciclo/mesociclo nós estamos hoje. Se o atleta perguntar sobre a fase do ciclo ou semana, você DEVE analisar o histórico de corridas/WODs "
                        "para responder com precisão matemática.\n\n"
                        "⚠️ REQUISITO DE SEGURANÇA CRÍTICO:\n"
                        "Se o usuário estiver apenas fazendo perguntas, tirando dúvidas, batendo papo ou perguntando sobre sua planilha de periodização/semanas, "
                        "responda diretamente em texto puro. NUNCA, SOB HIPÓTESE ALGUMA, chame a ferramenta 'estruturar_analise_treino' para conversas comuns!"
                    )
                    
                    mensagens_api.append({"role": "system", "content": contexto_sistema})
                    
                    for msg_historico in st.session_state.mensagens[:-1]:
                        mensagens_api.append({"role": msg_historico["role"], "content": msg_historico["content"]})
                    
                    mensagens_api.append({"role": "user", "content": conteudo_mensagem})

                    # Trava estrita na descrição da ferramenta para evitar chamadas falsas
                    tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": "estruturar_analise_treino",
                                "description": (
                                    "Chame esta função EXCLUSIVAMENTE quando o usuário enviar um relato de um NOVO treino realizado hoje "
                                    "(ou subir arquivos GPX/fotos de um treino novo) para salvar no banco. NÃO chame esta função para perguntas "
                                    "conversacionais, dúvidas sobre periodização, relatórios de semanas ou histórico."
                                ),
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "tipo_treino": {"type": "string", "enum": ["corrida", "crossfit"]},
                                        "data": {"type": "string", "description": "Data do treino (YYYY-MM-DD)."},
                                        "distancia": {"type": "number"},
                                        "elevacao_acumulada": {"type": "number"},
                                        "pace": {"type": "string"},
                                        "zonas_fc": {"type": "string"},
                                        "cadencia_media": {"type": "integer"},
                                        "descricao_wod": {"type": "string"},
                                        "tempo_score": {"type": "string"},
                                        "tipo_lpo": {"type": "string"},
                                        "percepcao_esforco": {"type": "integer"},
                                        "alerta_desconforto": {"type": "string"},
                                        "analise_usuario": {"type": "string", "description": "Relato detalhado fornecido pelo aluno sobre as sensações dele."},
                                        "analise_ia": {"type": "string", "description": "Diagnóstico biomecânico e fisiológico ultra crítico, focado puramente em apontar falhas de ritmo, volume, cadência ou intensidade de forma dura."},
                                        "performance_geral": {"type": "string", "description": "Cruzamento comparativo do treino de hoje com os PRs históricos e dados de sono/fadiga mapeados na memória."}
                                    },
                                    "required": ["tipo_treino", "data", "analise_ia", "performance_geral"]
                                }
                            }
                        }
                    ]

                    resposta_openai = cliente_openai.chat.completions.create(
                        model=nome_modelo,
                        messages=mensagens_api,
                        tools=tools,
                        tool_choice="auto"
                    )
                    
                    resposta_mensagem = resposta_openai.choices[0].message
                    
                    if resposta_mensagem.tool_calls:
                        tool_call = resposta_mensagem.tool_calls[0]
                        if tool_call.function.name == "estruturar_analise_treino":
                            argumentos = json.loads(tool_call.function.arguments)
                            
                            st.session_state.treino_rascunho = argumentos
                            resposta_ia = f"📖 **Análise Concluída com Sucesso!** Montei um diagnóstico cruzando sua telemetria com seu histórico de saúde do banco. Por favor, revise o painel de aprovação acima para confirmar a gravação no Supabase."
                    else:
                        resposta_ia = resposta_mensagem.content
                    
                    st.markdown(resposta_ia)
                    st.session_state.mensagens.append({"role": "assistant", "content": resposta_ia})
                    try:
                        supabase.table("historico_conversas").insert({"role": "assistant", "content": resposta_ia, "user_id": user_id}).execute()
                    except Exception:
                        pass
                    
                    if resposta_mensagem.tool_calls:
                        st.rerun()
                    
                except Exception as e:
                    st.error(f"Erro ao processar: {e}")

# --- Aba 2: Resumo de Performance Consolidada ---
with aba_performance:
    st.header("📈 Auditoria de Performance & Fraquezas")
    st.write("Esta seção analisa todo o seu banco de dados histórico para expor desequilíbrios, falhas de pacing, inconsistências e erros metodológicos.")

    if st.button("🔍 Rodar Auditoria de Performance da IA", use_container_width=True):
        with st.spinner("Compilando dados do Supabase e processando relatório analítico..."):
            try:
                historico_corrida = supabase.table("treinos_corrida").select("*").eq("user_id", user_id).order("data", desc=True).limit(10).execute().data
                historico_cross = supabase.table("treinos_crossfit").select("*").eq("user_id", user_id).order("data", desc=True).limit(10).execute().data
                historico_saude = supabase.table("metricas_diarias").select("*").eq("user_id", user_id).order("data", desc=True).limit(10).execute().data
                historico_prs = supabase.table("prs").select("*").eq("user_id", user_id).execute().data
                
                compilado_banco = {
                    "corridas": historico_corrida,
                    "crossfit": historico_cross,
                    "saude_sono_vfc": historico_saude,
                    "prs": historico_prs
                }
                
                mensagens_auditoria = [
                    {
                        "role": "system",
                        "content": (
                            "Você é um auditor de performance esportiva implacável, focado em triatlo, corrida e CrossFit/LPO. "
                            "Seu objetivo é analisar as últimas entradas e expor as fraquezas latentes do atleta. "
                            "Exponha erros de pacing (ex: flutuações severas de ritmo), cadência inadequada, perda de força nos PRs, "
                            "correlação entre treinos ruins e sono deficiente/baixa VFC, ou excesso de dores relatadas. "
                            "Organize em tópicos objetivos: 1. Falhas Críticas Identificadas, 2. Gargalos de Recuperação Fisiológica, "
                            "3. Ajustes Metodológicos Imediatos. Seja assertivo, duro e ultra analítico."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Dados brutos consolidados do banco do atleta para auditoria:\n{json.dumps(compilado_banco, default=str)}"
                    }
                ]
                
                resposta_openai = cliente_openai.chat.completions.create(
                    model=nome_modelo,
                    messages=mensagens_auditoria
                )
                
                st.session_state.auditoria_performance = resposta_openai.choices[0].message.content
            except Exception as e_audit:
                st.error(f"Erro ao extrair dados para auditoria: {e_audit}")
                
    if "auditoria_performance" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state.auditoria_performance)
    else:
        st.info("💡 Clique no botão acima para compilar seu histórico e gerar a auditoria analítica severa da IA.")

# --- Aba 3: Plano de Periodização ---
with aba_periodizacao:
    st.header("📅 Planejamento de Periodização Científica")
    st.write("Esta aba sintetiza um plano de periodização estruturado para seus próximos ciclos baseado estritamente na base de artigos anexados na memória do Coach.")

    if st.button("🔄 Gerar/Atualizar Plano de Periodização Baseado na Memória Científica", use_container_width=True):
        with st.spinner("Analisando base teórica e gerando sua periodização sob medida..."):
            try:
                historico_prs = supabase.table("prs").select("*").eq("user_id", user_id).execute().data
                artigos = st.session_state.contexto_artigos if st.session_state.contexto_artigos else "Nenhum artigo científico anexado ainda."
                
                mensagens_periodizacao = [
                    {
                        "role": "system",
                        "content": (
                            "Você é um Head Coach de elite especializado em planejar planilhas de periodização esportiva baseadas estritamente em evidências científicas. "
                            "Sua missão é gerar um plano de periodização analítico, detalhado e implacável para os próximos ciclos de treino (focado em corrida, LPO e CrossFit). "
                            "Você deve usar as teorias e metodologias descritas nos artigos científicos fornecidos pelo usuário no contexto. "
                            "Seja extremamente técnico e detalhado: defina a estrutura dos próximos mesociclos e microciclos, distribuição de intensidade (Zonas de FC, Pacing), "
                            "estratégias de progressão de carga (RPE e % de 1RM baseando-se nos PRs reais dele) e protocolos rigorosos de recuperação ativa/deload. "
                            "Adote o tom severo e focado em performance absoluta, sem rodeios ou palavras vazias de incentivo."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Artigos científicos de referência (Base Teórica de Artigos):\n{artigos}\n\nRecordes Pessoais Atuais do Atleta (PRs):\n{json.dumps(historico_prs, default=str)}\n\nPor favor, monte o planejamento sistemático dos próximos ciclos."
                    }
                ]
                
                resposta_openai = cliente_openai.chat.completions.create(
                    model=nome_modelo,
                    messages=mensagens_periodizacao
                )
                
                st.session_state.plano_periodizacao = resposta_openai.choices[0].message.content
            except Exception as e_period:
                st.error(f"Erro ao gerar plano de periodização: {e_period}")
                
    if "plano_periodizacao" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state.plano_periodizacao)
    else:
        st.info("💡 Clique no botão acima para acionar a inteligência e estruturar sua periodização baseada nos artigos anexados.")

# --- Aba 4: Recordes Pessoais ---
with aba_pr:
    st.header("Recordes Pessoais")
    with st.form("form_pr", clear_on_submit=True):
        st.write("Registre seu novo PR:")
        data_recorde = st.date_input("Data do Recorde")
        movimento = st.text_input("Movimento", placeholder="Ex: Snatch, Clean & Jerk, Back Squat, Deadlift...")
        carga = st.number_input("Carga (kg)", min_value=0.0, step=0.5)
        peso_corporal = st.number_input("Seu Peso Corporal no dia (kg)", min_value=0.0, step=0.1)
        botao_salvar = st.form_submit_button("Salvar PR no Banco")
        
        if botao_salvar:
            if not movimento.strip():
                st.error("Por favor, digite o nome do movimento antes de salvar.")
            else:
                dados_pr = {
                    "data_recorde": str(data_recorde),
                    "movimento": movimento.strip(),
                    "carga": carga,
                    "peso_corporal": peso_corporal,
                    "user_id": user_id
                }
                try:
                    resposta = supabase.table("prs").insert(dados_pr).execute()
                    if hasattr(resposta, 'data') and resposta.data:
                        st.success(f"🔥 PR de {movimento.strip()} ({carga}kg) salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar no banco: {e}")

# --- Aba 5: Base de Conhecimento (Global/Replicado para todos) ---
with aba_docs:
    st.header("Diretório de Artigos")
    st.warning("⚠️ Base de conhecimento compartilhada globalmente entre todos os atletas do sistema.")
    
    arquivos_pdf = st.file_uploader("📚 Enviar Artigos (PDFs)", type=["pdf"], accept_multiple_files=True, key="doc_upload_pdf")
    
    if st.button("🚀 Processar e Salvar Documentos no Supabase", use_container_width=True):
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
                        
                        # Salva sem user_id para manter a tabela global
                        supabase.table("artigos_metodologia").insert(dados_artigo).execute()
                        
                        st.session_state.contexto_artigos = f"{texto_extraido}\n\n{st.session_state.contexto_artigos}"[:80000]
                        st.success(f"✅ Documento '{arquivo.name}' processado e gravado com sucesso!")
                        
                        del leitor
                        del texto_extraido
                        del dados_artigo
                        gc.collect()
                        
                    except Exception as e:
                        st.error(f"Erro ao processar '{arquivo.name}': {e}")
        else:
            st.warning("Por favor, selecione pelo menos um arquivo PDF antes de clicar em enviar.")

# --- Aba 6: Cérebro do Coach (Isolado) ---
with aba_cerebro:
    st.header("Memória Central")
    with st.form("form_cerebro"):
        nova_diretriz = st.text_area("Diretrizes de Comportamento e Conhecimento", value=memoria_central, height=400)
        botao_salvar_memoria = st.form_submit_button("Atualizar Cérebro")
        if botao_salvar_memoria:
            try:
                supabase.table("memoria_coach").insert({"diretriz": nova_diretriz, "user_id": user_id}).execute()
                st.success("Cérebro updated com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
