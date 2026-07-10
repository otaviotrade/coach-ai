import streamlit as st
from supabase import create_client, Client
from openai import OpenAI
import base64
import PyPDF2
import gpxpy
from datetime import date
import json
import xml.etree.ElementTree as ET

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

# --- 🧠 Sincronização do Histórico Persistente com o Supabase ---
if "mensagens" not in st.session_state:
    try:
        historico_banco = supabase.table("historico_conversas").select("role", "content").order("id", desc=False).limit(50).execute()
        st.session_state.mensagens = historico_banco.data if historico_banco.data else []
    except Exception:
        st.session_state.mensagens = []

# --- 📚 Carregamento Permanente de Artigos do Supabase ---
if "contexto_artigos" not in st.session_state:
    try:
        # Lógica: O Python consulta a tabela de artigos e unifica os textos para o contexto da IA
        artigos_banco = supabase.table("artigos_metodologia").select("conteudo_texto").execute()
        st.session_state.contexto_artigos = "\n\n".join([art["conteudo_texto"] for art in artigos_banco.data]) if artigos_banco.data else ""
    except Exception:
        st.session_state.contexto_artigos = ""

try:
    resposta_memoria = supabase.table("memoria_coach").select("diretriz").order("id", desc=True).limit(1).execute()
    memoria_central = resposta_memoria.data[0]["diretriz"] if resposta_memoria.data else ""
except Exception:
    memoria_central = ""

st.title("🏋️‍♂️ AI Coach de Treinos")

aba_chat, aba_pr, aba_docs, aba_cerebro = st.tabs([
    "💬 Coach Chat", 
    "🏆 Meus PRs", 
    "📚 Base de Conhecimento",
    "🧠 Cérebro do Coach"
])

# --- Aba 1: Coach Chat ---
with aba_chat:
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

    prompt = st.chat_input("Fale com seu Coach...")
    
    if prompt:
        st.session_state.mensagens.append({"role": "user", "content": prompt})
        try:
            supabase.table("historico_conversas").insert({"role": "user", "content": prompt}).execute()
        except Exception:
            pass

        with container_chat:
            with st.chat_message("user"):
                st.markdown(prompt)
            
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
                        for foto in fotos_treino:
                            imagem_base64 = processar_imagem_openai(foto)
                            conteudo_mensagem.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{imagem_base64}"}
                            })

                    mensagens_api = []
                    contexto_sistema = f"{memoria_central}\nData atual do sistema: {str(date.today())}.\nIMPORTANTE: Revise o histórico anterior com atenção para identificar lesões, dores musculares antigas, feedbacks e evolução do aluno."
                    mensagens_api.append({"role": "system", "content": contexto_sistema})
                    
                    for msg_historico in st.session_state.mensagens[:-1]:
                        mensagens_api.append({"role": msg_historico["role"], "content": msg_historico["content"]})
                    
                    # Correção: Injeção do prompt atual contendo os artigos unificados do Supabase
                    mensagens_api.append({"role": "user", "content": conteudo_mensagem})

                    tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": "salvar_treino_automatico",
                                "description": "Chame esta função para cada treino individual que identificar na análise de textos, fotos ou blocos de dados GPX.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "tipo_treino": {"type": "string", "enum": ["corrida", "crossfit"]},
                                        "data": {"type": "string", "description": "Data no formato YYYY-MM-DD."},
                                        "distancia": {"type": "number"},
                                        "elevacao_acumulada": {"type": "number"},
                                        "pace": {"type": "string"},
                                        "zonas_fc": {"type": "string"},
                                        "cadencia_media": {"type": "integer"},
                                        "descricao_wod": {"type": "string"},
                                        "tempo_score": {"type": "string"},
                                        "tipo_lpo": {"type": "string"},
                                        "percepcao_esforco": {"type": "integer"},
                                        "alerta_desconforto": {"type": "string"}
                                    },
                                    "required": ["tipo_treino", "data"]
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
                        mensagens_api.append(resposta_mensagem)
                        
                        for tool_call in resposta_mensagem.tool_calls:
                            if tool_call.function.name == "salvar_treino_automatico":
                                argumentos = json.loads(tool_call.function.arguments)
                                tipo = argumentos.get("tipo_treino")
                                data_registro = argumentos.get("data", str(date.today()))
                                
                                if tipo == "corrida":
                                    dados_inserir = {
                                        "data": data_registro,
                                        "distancia": argumentos.get("distancia"),
                                        "elevacao_acumulada": argumentos.get("elevacao_acumulada"),
                                        "pace": argumentos.get("pace"),
                                        "zonas_fc": argumentos.get("zonas_fc"),
                                        "cadencia_media": argumentos.get("cadencia_media")
                                    }
                                    dados_inserir = {k: v for k, v in dados_inserir.items() if v is not None}
                                    supabase.table("treinos_corrida").insert(dados_inserir).execute()
                                    st.info(f"💾 Registro de Corrida ({data_registro}) salvo automaticamente!")
                                    
                                elif tipo == "crossfit":
                                    dados_inserir = {
                                        "data": data_registro,
                                        "descricao_wod": argumentos.get("descricao_wod"),
                                        "tempo_score": argumentos.get("tempo_score"),
                                        "tipo_lpo": argumentos.get("tipo_lpo"),
                                        "percepcao_esforco": argumentos.get("percepcao_esforco"),
                                        "alerta_desconforto": argumentos.get("alerta_desconforto")
                                    }
                                    dados_inserir = {k: v for k, v in dados_inserir.items() if v is not None}
                                    supabase.table("treinos_crossfit").insert(dados_inserir).execute()
                                    st.info(f"💾 Registro de CrossFit ({data_registro}) salvo automaticamente!")

                                mensagens_api.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": "salvar_treino_automatico",
                                    "content": json.dumps({"status": "success"})
                                })
                        
                        segunda_resposta = cliente_openai.chat.completions.create(
                            model=nome_modelo,
                            messages=mensagens_api
                        )
                        resposta_ia = segunda_resposta.choices[0].message.content
                    else:
                        resposta_ia = resposta_mensagem.content
                    
                    st.markdown(resposta_ia)
                    st.session_state.mensagens.append({"role": "assistant", "content": resposta_ia})
                    try:
                        supabase.table("historico_conversas").insert({"role": "assistant", "content": resposta_ia}).execute()
                    except Exception:
                        pass
                    
                except Exception as e:
                    st.error(f"Erro ao processar: {e}")

# --- Aba 2: Recordes Pessoais ---
with aba_pr:
    st.header("Recordes Pessoais")
    with st.form("form_pr", clear_on_submit=True):
        st.write("Registre seu novo PR:")
        data_recorde = st.date_input("Data do Recorde")
        movimento = st.selectbox("Movimento", ["Snatch", "Clean & Jerk", "Deadlift", "Back Squat", "Front Squat"])
        carga = st.number_input("Carga (kg)", min_value=0.0, step=0.5)
        peso_corporal = st.number_input("Seu Peso Corporal no dia (kg)", min_value=0.0, step=0.1)
        botao_salvar = st.form_submit_button("Salvar PR no Banco")
        
        if botao_salvar:
            dados_pr = {
                "data_recorde": str(data_recorde),
                "movimento": movimento,
                "carga": carga,
                "peso_corporal": peso_corporal
            }
            try:
                resposta = supabase.table("prs").insert(dados_pr).execute()
                if hasattr(resposta, 'data') and resposta.data:
                    st.success(f"🔥 PR de {movimento} ({carga}kg) salvo com sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar no banco: {e}")

# --- Aba 3: Base de Conhecimento (Gravação Permanente no Supabase) ---
with aba_docs:
    st.header("Diretório de Artigos")
    st.write("Suba PDFs com metodologias de treino.")
    arquivo_pdf = st.file_uploader("📚 Enviar Artigo (PDF)", type=["pdf"])
    if arquivo_pdf is not None:
        try:
            leitor = PyPDF2.PdfReader(arquivo_pdf)
            texto_extraido = ""
            for pagina in leitor.pages:
                texto_extraido += pagina.extract_text()
            
            # Mudança Lógica: O Python agora executa a inserção física permanente do texto extraído no Supabase
            dados_artigo = {
                "nome_arquivo": arquivo_pdf.name,
                "conteudo_texto": texto_extraido
            }
            supabase.table("artigos_metodologia").insert(dados_artigo).execute()
            
            # Atualiza o contexto da sessão imediatamente sem precisar recarregar a página
            st.session_state.contexto_artigos += f"\n\n{texto_extraido}"
            st.success(f"📚 Artigo '{arquivo_pdf.name}' lido e persistido permanentemente no Supabase!")
        except Exception as e:
            st.error(f"Erro ao ler e persistir o PDF: {e}")

# --- Aba 4: Cérebro do Coach ---
with aba_cerebro:
    st.header("Memória Central")
    with st.form("form_cerebro"):
        nova_diretriz = st.text_area("Diretrizes de Comportamento e Conhecimento", value=memoria_central, height=400)
        botao_salvar_memoria = st.form_submit_button("Atualizar Cérebro")
        if botao_salvar_memoria:
            try:
                supabase.table("memoria_coach").insert({"diretriz": nova_diretriz}).execute()
                st.success("Cérebro atualizado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")