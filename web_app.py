import streamlit as st
import os
from project import RAGApplication
from streamlit_mic_recorder import speech_to_text # Voice Library

# -------------------------
# 1. Page Configuration
# -------------------------
st.set_page_config(page_title="Smart AI Document Q&A", page_icon="🤖", layout="wide")

# -------------------------
# 2. Language Dictionary
# -------------------------
LANG_UI = {
    "English": {
        "title": "🤖 Smart Document Q&A",
        "subtitle": "Powered by Gemini Flash-Lite & Astra DB",
        "sidebar_lang": "🌐 Language / भाषा",
        "sidebar_settings": "⚙️ AI Settings",
        "temp_label": "Temperature (0.0 = Strict, 1.0 = Creative)",
        "download_btn": "📥 Download Chat Log",
        "chat_tab": "💬 Q&A Chat",
        "manage_tab": "📂 Manage Knowledge Base",
        "welcome": "👋 Welcome! Upload a document to start. I can read images, and if I don't know the answer, I will search the web!",
        "input_placeholder": "Ask a question about your documents...",
        "source_label": "Sources",
        "upload_header": "⬆️ Upload New Document",
        "upload_btn": "Process & Index Document",
        "upload_warning": "Note: PDFs with images take longer to process as the AI safely analyzes them.",
        "db_header": "🗄️ Database Manager",
        "no_docs_msg": "No documents are currently indexed.",
        "total_docs": "Total Documents:",
        "delete_btn": "Delete",
        "stt_lang": "en", 
        "voice_prompt": "🎤 Click to Speak"
    },
    "Hindi (हिन्दी)": {
        "title": "🤖 स्मार्ट दस्तावेज़ प्रश्नोत्तर",
        "subtitle": "जेमिनी फ्लैश-लाइट और एस्ट्रा डीबी द्वारा संचालित",
        "sidebar_lang": "🌐 भाषा / Language",
        "sidebar_settings": "⚙️ एआई सेटिंग्स",
        "temp_label": "रचनात्मकता स्तर (0.0 = सटीक, 1.0 = रचनात्मक)",
        "download_btn": "📥 चैट डाउनलोड करें",
        "chat_tab": "💬 चैट",
        "manage_tab": "📂 दस्तावेज़ प्रबंधन",
        "welcome": "👋 स्वागत है! शुरू करने के लिए एक दस्तावेज़ अपलोड करें।",
        "input_placeholder": "अपना प्रश्न पूछें...",
        "source_label": "स्रोत",
        "upload_header": "⬆️ नया दस्तावेज़ अपलोड करें",
        "upload_btn": "दस्तावेज़ को प्रोसेस करें",
        "upload_warning": "नोट: चित्रों वाले PDF को प्रोसेस होने में थोड़ा अधिक समय लगता है।",
        "db_header": "🗄️ डेटाबेस प्रबंधक",
        "no_docs_msg": "वर्तमान में कोई दस्तावेज़ उपलब्ध नहीं है।",
        "total_docs": "कुल दस्तावेज़:",
        "delete_btn": "हटाएं",
        "stt_lang": "hi", 
        "voice_prompt": "🎤 बोलने के लिए क्लिक करें"
    },
    "Marathi (मराठी)": {
        "title": "🤖 स्मार्ट दस्तऐवज प्रश्नोत्तरे",
        "subtitle": "जेमिनी फ्लॅश-लाइट आणि एस्ट्रा डीबी द्वारे समर्थित",
        "sidebar_lang": "🌐 भाषा / Language",
        "sidebar_settings": "⚙️ एआय सेटिंग्ज",
        "temp_label": "सर्जनशीलता पातळी (0.0 = अचूक, 1.0 = सर्जनशील)",
        "download_btn": "📥 चॅट डाउनलोड करा",
        "chat_tab": "💬 चॅट",
        "manage_tab": "📂 दस्तऐवज व्यवस्थापन",
        "welcome": "👋 स्वागत आहे! सुरू करण्यासाठी दस्तऐवज अपलोड करा.",
        "input_placeholder": "तुमचा प्रश्न विचारा...",
        "source_label": "संदर्भ",
        "upload_header": "⬆️ नवीन दस्तऐवज अपलोड करा",
        "upload_btn": "दस्तऐवज प्रोसेस करा",
        "upload_warning": "टीप: चित्रे असलेल्या PDF ला प्रोसेस होण्यासाठी थोडा जास्त वेळ लागतो.",
        "db_header": "🗄️ डेटाबेस व्यवस्थापक",
        "no_docs_msg": "सध्या कोणतेही दस्तऐवज उपलब्ध नाहीत.",
        "total_docs": "एकूण दस्तऐवज:",
        "delete_btn": "काढून टाका",
        "stt_lang": "mr", 
        "voice_prompt": "🎤 बोलण्यासाठी क्लिक करा"
    }
}

# -------------------------
# 3. Helper Functions
# -------------------------
@st.cache_resource
def load_backend():
    try:
        return RAGApplication()
    except Exception as e:
        st.error(f"Environment Setup Error: {str(e)}")
        st.stop()

def get_chat_history_text(ui):
    chat_text = f"--- {ui['title']} ---\n\n"
    for msg in st.session_state.messages:
        role = "User" if msg["role"] == "user" else "AI Assistant"
        chat_text += f"[{role}]: {msg['content']}\n"
        if msg.get("sources"):
            chat_text += f"{ui['source_label']}: {', '.join(msg['sources'])}\n"
        chat_text += "-" * 40 + "\n"
    return chat_text

# -------------------------
# 4. Initialize State
# -------------------------
rag_app = load_backend()

with st.sidebar:
    st.header("🌐 Language / भाषा")
    selected_lang = st.selectbox("Choose Interface Language", options=list(LANG_UI.keys()))
    ui = LANG_UI[selected_lang]

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": ui["welcome"]}]

st.title(ui["title"])
st.markdown(f"**{ui['subtitle']}**")

# -------------------------
# 5. Sidebar Options
# -------------------------
with st.sidebar:
    st.divider()
    st.header(ui["sidebar_settings"])
    ai_temperature = st.slider(ui["temp_label"], 0.0, 1.0, 0.3, 0.1)
    
    st.divider()
    st.download_button(
        label=ui["download_btn"],
        data=get_chat_history_text(ui),
        file_name="rag_chat_history.txt",
        mime="text/plain"
    )
    st.caption("Astra DB Vector Search Active 🟢")

# -------------------------
# 6. Main Tabs
# -------------------------
tab1, tab2 = st.tabs([ui["chat_tab"], ui["manage_tab"]])

with tab1:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                st.caption(f"📚 **{ui['source_label']}:** {', '.join(message['sources'])}")

    col1, col2 = st.columns([8, 2])
    with col2:
        st.write("") 
        spoken_prompt = speech_to_text(
            language=ui["stt_lang"], 
            start_prompt=ui["voice_prompt"], 
            stop_prompt="🛑 Stop Recording", 
            use_container_width=True, 
            just_once=True, 
            key='STT'
        )

    typed_prompt = st.chat_input(ui["input_placeholder"])
    actual_prompt = typed_prompt or spoken_prompt

    if actual_prompt:
        st.session_state.messages.append({"role": "user", "content": actual_prompt})
        with st.chat_message("user"):
            st.markdown(actual_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching DB and Web..."):
                try:
                    result = rag_app.ask_question(actual_prompt, temperature=ai_temperature)
                    answer_text = result["answer"]
                    sources = result["sources"]

                    st.markdown(answer_text)
                    if sources:
                        st.caption(f"📚 **{ui['source_label']}:** {', '.join(sources)}")
                    
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": answer_text,
                        "sources": sources
                    })
                except Exception as e:
                    st.error(f"Error: {str(e)}")

with tab2:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.header(ui["upload_header"])
        uploaded_file = st.file_uploader("Upload a file", label_visibility="collapsed", type=["pdf", "docx", "txt", "xlsx"])
        st.caption(ui["upload_warning"])
        
        if uploaded_file is not None:
            os.makedirs("temp_uploads", exist_ok=True)
            temp_file_path = os.path.join("temp_uploads", uploaded_file.name)
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            if st.button(ui["upload_btn"], type="primary"):
                with st.spinner(f"Indexing {uploaded_file.name}..."):
                    try:
                        added_chunks = rag_app.add_document(temp_file_path)
                        st.success(f"✅ Successfully indexed {len(added_chunks)} chunks!")
                        os.remove(temp_file_path)
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Error processing document: {str(e)}")

    with col2:
        st.header(ui["db_header"])
        with st.spinner("Loading documents..."):
            indexed_docs = rag_app.get_indexed_documents()
            
        if not indexed_docs:
            st.info(ui["no_docs_msg"])
        else:
            st.write(f"**{ui['total_docs']}** {len(indexed_docs)}")
            for doc in indexed_docs:
                doc_col, btn_col = st.columns([4, 1])
                with doc_col:
                    st.write(f"📄 `{doc}`")
                with btn_col:
                    if st.button(ui["delete_btn"], key=f"del_{doc}"):
                        with st.spinner("Deleting..."):
                            rag_app.delete_document(doc)
                            st.rerun()