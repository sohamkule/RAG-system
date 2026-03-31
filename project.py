import os
import uuid
import pandas as pd
import docx
import fitz  # PyMuPDF
import io
import time # 🆕 NEW: For the API Speed Bump
from PIL import Image
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import threading
import wikipedia # 🌐 NEW: Wikipedia Agentic Fallback

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from dotenv import load_dotenv

import google.generativeai as genai
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# -------------------------
# 🔹 Cassandra Connector (Astra DB Native Vector Search)
# -------------------------
class VectorDBConnector:
    def __init__(self, secure_connect_bundle_path: str, application_token: str, keyspace: str):
        self.cloud_config = {'secure_connect_bundle': secure_connect_bundle_path}
        self.auth_provider = PlainTextAuthProvider('token', application_token)
        self.cluster = Cluster(cloud=self.cloud_config, auth_provider=self.auth_provider)
        self.session = self.cluster.connect(keyspace)
        self.keyspace = keyspace
        self._create_tables()

    def _create_tables(self):
        self.session.execute("""
            CREATE TABLE IF NOT EXISTS document_store (
                chunk_id uuid PRIMARY KEY,
                doc_name text,
                doc_content text,
                doc_type text,
                embedding_vector vector<float, 3072>,
                created_at timestamp,
                metadata map<text, text>
            )
        """)
        
        self.session.execute("""
            CREATE CUSTOM INDEX IF NOT EXISTS ann_index 
            ON document_store(embedding_vector) 
            USING 'StorageAttachedIndex'
        """)

    def store_document_with_embedding(self, chunk_id: uuid.UUID, doc_name: str, content: str,
                                      doc_type: str, embedding_vector: List[float], metadata: Dict[str, str] = None):
        if metadata is None:
            metadata = {}
        
        query = """
            INSERT INTO document_store 
            (chunk_id, doc_name, doc_content, doc_type, embedding_vector, created_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.session.execute(query, (chunk_id, doc_name, content, doc_type, embedding_vector, datetime.now(), metadata))

    def search_similar_documents(self, query_vector: List[float], top_k: int = 5) -> List[Dict]:
        query = """
            SELECT doc_content, doc_name FROM document_store 
            ORDER BY embedding_vector ANN OF %s LIMIT %s
        """
        rows = self.session.execute(query, (query_vector, top_k))
        return [{"content": row.doc_content, "source": row.doc_name} for row in rows]

    def get_all_documents(self) -> List[str]:
        rows = self.session.execute("SELECT doc_name FROM document_store")
        return list(set([row.doc_name for row in rows if row.doc_name]))

    def delete_document(self, doc_name: str) -> int:
        query = "SELECT chunk_id FROM document_store WHERE doc_name = %s ALLOW FILTERING"
        rows = self.session.execute(query, (doc_name,))
        deleted_count = 0
        for row in rows:
            self.session.execute("DELETE FROM document_store WHERE chunk_id = %s", (row.chunk_id,))
            deleted_count += 1
        return deleted_count

# -------------------------
# 🔹 Document Loader (Multi-Modal & Quota Safe)
# -------------------------
class DocumentLoader:
    @staticmethod
    def describe_image(image_bytes: bytes) -> str:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            model = genai.GenerativeModel("gemini-2.5-flash-lite")
            prompt = """
            Analyze this image, chart, or diagram in detail. 
            Extract any text, data points, trends, or key visual information. 
            Write a comprehensive summary so that a text-search algorithm can understand what this image contains.
            """
            response = model.generate_content([prompt, image])
            return f"\n\n[🖼️ SYSTEM GENERATED IMAGE DESCRIPTION: {response.text}]\n\n"
        except Exception as e:
            return f"\n\n[⚠️ Image Extraction Failed: {str(e)}]\n\n"

    @staticmethod
    def load_pdf(file_path: str) -> str:
        doc = fitz.open(file_path)
        full_text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text:
                full_text += page_text + "\n"
            
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                description = DocumentLoader.describe_image(image_bytes)
                full_text += description
                
                time.sleep(4)
                
        return full_text

    @staticmethod
    def load_word(file_path: str) -> str:
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    @staticmethod
    def load_excel(file_path: str) -> str:
        xlsx = pd.ExcelFile(file_path)
        text = ""
        for sheet_name in xlsx.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            text += f"\nSheet: {sheet_name}\n"
            text += df.to_string(index=False) + "\n"
        return text

    @staticmethod
    def load_text(file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

# -------------------------
# 🔹 RAG Application (Agentic Workflow Enabled)
# -------------------------
class RAGApplication:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        secure_connect_bundle_path = os.getenv("ASTRA_DB_SECURE_BUNDLE_PATH")
        application_token = os.getenv("ASTRA_DB_TOKEN")
        keyspace = os.getenv("KEYSPACE")

        if not all([gemini_api_key, secure_connect_bundle_path, application_token, keyspace]):
            raise ValueError("Missing environment variables. Check your .env file.")

        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(model_name="gemini-2.5-flash-lite")
        self.chat_session = self.model.start_chat(history=[]) 

        self.embedding_model = GoogleGenerativeAIEmbeddings(
            google_api_key=gemini_api_key,
            model="models/gemini-embedding-001"
        )

        self.vector_db = VectorDBConnector(secure_connect_bundle_path, application_token, keyspace)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_document(self, file_path: str) -> str:
        file_path = Path(file_path)
        if file_path.suffix.lower() == '.pdf': return DocumentLoader.load_pdf(str(file_path))
        elif file_path.suffix.lower() == '.docx': return DocumentLoader.load_word(str(file_path))
        elif file_path.suffix.lower() in ['.xlsx', '.xls']: return DocumentLoader.load_excel(str(file_path))
        elif file_path.suffix.lower() == '.txt': return DocumentLoader.load_text(str(file_path))
        else: raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def _chunk_text(self, text: str) -> List[str]:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap, separators=["\n\n", "\n", ".", " ", ""])
        return text_splitter.split_text(text)

    def generate_embeddings(self, text: str) -> List[float]:
        return self.embedding_model.embed_query(text)

    def add_document(self, file_path: str, metadata: Dict[str, str] = None):
        content = self.parse_document(file_path)
        if not content: return None
        chunks = self._chunk_text(content)
        threads = []
        added_chunk_ids = []

        def process_chunk(chunk_text):
            chunk_id = uuid.uuid4()
            embedding_vector = self.generate_embeddings(chunk_text)
            self.vector_db.store_document_with_embedding(
                chunk_id=chunk_id, doc_name=Path(file_path).name, content=chunk_text,
                doc_type=Path(file_path).suffix[1:], embedding_vector=embedding_vector, metadata=metadata
            )
            added_chunk_ids.append(chunk_id)

        for chunk in chunks:
            t = threading.Thread(target=process_chunk, args=(chunk,))
            t.start()
            threads.append(t)

        for t in threads: t.join()
        return added_chunk_ids

    # -------------------------
    # 🧠 Agentic Routing Logic
    # -------------------------
    def ask_question(self, question: str, top_k: int = 5, temperature: float = 0.3) -> dict:
        query_embedding = self.generate_embeddings(question)
        
        # Phase 1: Local Knowledge Search (Astra DB)
        docs = self.vector_db.search_similar_documents(query_embedding, top_k)
        requires_web_search = False
        raw_answer = ""

        if not docs:
            requires_web_search = True
        else:
            context_blocks = [f"[Source File: {doc['source']}]\n{doc['content']}" for doc in docs]
            context = "\n\n".join(context_blocks)

            prompt = f"""
            You are an intelligent multilingual document assistant. 
            
            TASK:
            1. Analyze the user's question and determine the language.
            2. Use the provided context to answer the question.
            3. Respond COMPLETELY in the same language as the user's question.
            
            Each piece of context has a [Source File: filename] tag. 
            If the answer is absolutely not in the context, exactly say: "I don't have enough information". Do not guess.
            
            CRITICAL RULE: At the very end of your answer, you MUST include a line that exactly says "USED_SOURCES:" followed by a comma-separated list of the source files you used.
            
            Context:
            {context}
            
            Current User Question:
            {question}
            """
            
            response = self.chat_session.send_message(prompt, generation_config=genai.GenerationConfig(temperature=temperature))
            raw_answer = response.text
            
            if "I don't have enough information" in raw_answer:
                requires_web_search = True

        # Phase 2: Live Web Search (Agentic Fallback using Wikipedia)
        if requires_web_search:
            try:
                print("🌐 Local DB missing answer. Triggering Wikipedia Search...")
                
                # 🛠️ THE FIX: Rewind the AI's memory so it forgets it just failed!
                # This prevents the AI from stubbornly repeating "I don't have enough information."
                if len(self.chat_session.history) >= 2:
                    self.chat_session.history = self.chat_session.history[:-2]
                
                # Search Wikipedia for the top 3 matching articles
                search_results = wikipedia.search(question, results=3)
                
                if not search_results:
                    return {"answer": "I don't have enough information locally, and I couldn't find an answer on Wikipedia.", "sources": []}
                
                web_context_blocks = []
                for title in search_results:
                    try:
                        page = wikipedia.page(title, auto_suggest=False)
                        # Extract more text (2000 chars) to ensure we get the answer
                        web_context_blocks.append(f"[Source File: {page.url}]\nTitle: {page.title}\nSnippet: {page.summary[:2000]}")
                    except Exception:
                        pass 
                
                if not web_context_blocks:
                    return {"answer": "I found Wikipedia pages, but couldn't extract the text.", "sources": []}

                web_context = "\n\n".join(web_context_blocks)
                
                # 🛠️ DEBUGGING: Print the Wikipedia text to your VS Code terminal 
                # so you can see exactly what the AI is reading!
                print(f"\n📚 WIKIPEDIA CONTEXT PULLED:\n{web_context[:500]}...\n")
                
                web_prompt = f"""
                You are an intelligent multilingual agent. The user's question could not be answered using the local database, so Wikipedia was searched.
                
                TASK:
                1. Use the following Wikipedia snippets to answer the user's question.
                2. Respond COMPLETELY in the same language as the user's question.
                3. Do NOT say you lack information if the answer can be reasonably deduced from the text below.
                
                CRITICAL RULE: At the very end of your answer, you MUST include a line that exactly says "USED_SOURCES:" followed by a comma-separated list of the URLs you used from the results.
                
                Wikipedia Results:
                {web_context}
                
                Current User Question:
                {question}
                """
                
                response = self.chat_session.send_message(web_prompt, generation_config=genai.GenerationConfig(temperature=temperature))
                raw_answer = "🌐 *I couldn't find this in your uploaded documents, so I searched Wikipedia for you:*\n\n" + response.text

            except Exception as e:
                return {"answer": f"I don't have enough information locally, and the Wikipedia search failed: {str(e)}", "sources": []}

        # -------------------------
        # 🧠 Final Parsing
        # -------------------------
        answer_text = raw_answer
        actual_sources = []
        
        if "USED_SOURCES:" in raw_answer:
            parts = raw_answer.split("USED_SOURCES:")
            answer_text = parts[0].strip() 
            sources_string = parts[1].strip() 
            actual_sources = [s.strip() for s in sources_string.split(",") if s.strip()]
            actual_sources = list(set(actual_sources))

        return {
            "answer": answer_text,
            "sources": actual_sources
        }

    def get_indexed_documents(self) -> List[str]:
        return self.vector_db.get_all_documents()

    def delete_document(self, doc_name: str) -> int:
        return self.vector_db.delete_document(doc_name)