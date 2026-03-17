# 🦊 GitBot — GitLab Handbook & Direction Chatbot

> An AI-powered chatbot that lets employees and aspiring GitLab employees query the GitLab Handbook and product Direction pages in plain English — built with Gemini 2.5 Flash, FAISS, LangChain, and Streamlit.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://appchatbot-ui90.streamlit.app/)

---

## ✨ Features

| Feature | Details |
|---|---|
| 🔍 **RAG Pipeline** | Retrieval-Augmented Generation using FAISS + MMR search |
| 💬 **Streaming answers** | Live token-by-token output for snappy UX |
| 📚 **Source citations** | Every answer links back to the original Handbook/Direction page |
| 🛡️ **Guardrails** | Sensitive topic detection (HR, legal, compensation) with safety banners |
| 🔎 **Transparency panel** | Expandable debug view showing raw retrieved context chunks |
| 💡 **Suggested questions** | Onboarding prompts for new users |
| 🔄 **One-click re-index** | Sidebar button to re-scrape and rebuild the knowledge base |
| 🌐 **Public deployment** | Works on Streamlit Community Cloud (free) |

---

## 🏗️ Architecture

```
User Query
    │
    ▼
Streamlit UI (app.py)
    │
    ▼
GitLabChatbot.stream_chat()              ← src/chatbot.py
    │
    ├──► FAISS Retriever (MMR k=6)       ← src/vector_store.py
    │        │
    │        └── Custom GeminiEmbeddings (REST API, no SDK wrapper)
    │
    └──► Gemini 2.5 Flash (LangChain LCEL)
              │
              └── Streamed Answer + Sources + Guardrail Check
```

**Data flow (first run ~18-20 min, subsequent runs ~5 sec):**
```
scrape_all()          → data/scraped_pages.json   (~80 pages, UTF-8)
    │
    └── build_index() → data/faiss_index/          (~561 vectors)
```

---

## 🛠️ Tech Stack & Why

| Component | Choice | Why |
|---|---|---|
| **LLM** | Gemini 2.5 Flash | Works on free tier; newer and better than 1.5 Flash |
| **Embeddings** | `gemini-embedding-2-preview` | Custom REST class — bypasses broken LangChain wrapper |
| **Vector Store** | FAISS (local) | Zero cost; no external service; perfect for <10K docs |
| **RAG Framework** | LangChain 0.3.25 LCEL | Industry standard; composable; native streaming |
| **Frontend** | Streamlit 1.40 | Pure Python; built-in session state; one-click cloud deploy |
| **Scraping** | requests + BeautifulSoup | Simple, readable, UTF-8 forced for Windows compatibility |

> **Note on embeddings:** `langchain-google-genai 2.x` has a model name format bug that causes `400` errors. This project uses a custom `GeminiEmbeddings` class that calls Google's REST API directly, bypassing the wrapper entirely. It includes exponential backoff retry logic for free tier rate limits.

---

## 🚀 Quick Start (Local)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/gitlab-chatbot.git
cd gitlab-chatbot
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Mac/Linux:
source venv/bin/activate

# Windows PowerShell:
venv\Scripts\Activate.ps1
```

> If you get a PowerShell permissions error run this once:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up your API key

Create a `.env` file in the project root (same folder as `app.py`):

```
GOOGLE_API_KEY=your_actual_key_here
```

> Get a free key at: https://aistudio.google.com
> **No quotes** around the key in `.env`. Do not use `.env.example` — create a new `.env` file.

Also create `.streamlit/secrets.toml` (open Notepad, save as UTF-8, **not** UTF-8 BOM):

```toml
GOOGLE_API_KEY = "your_actual_key_here"
```

> **Quotes are required** in `.toml` format. Save with encoding set to `UTF-8` in Notepad — do not use PowerShell `echo` which saves as UTF-16.

### 5. Run the app

```bash
streamlit run app.py
```

> Always run from the project root directory where `app.py` lives.
> Never run with `python app.py` — Streamlit needs its own server.

The app opens at `http://localhost:8501`.

**First run:** Scraping ~2 min + indexing ~18-20 min (561 chunks at 2s per request due to free tier rate limits).
**Subsequent runs:** Loads from disk cache in ~5 seconds.

### 6. Build the index separately (optional, or needed when we don't want the app to stop while recreating/updating the Knowledge Base.)

```bash
python build_index.py

# Force re-scrape from scratch:
python build_index.py --force
```

---

## ☁️ Deploy to Streamlit Community Cloud

1. Push your repo to GitHub — the `data/` folder is gitignored so the index rebuilds on first launch.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Select your repo, set `app.py` as the main file.
4. Under **Advanced settings → Secrets**, add:
   ```toml
   GOOGLE_API_KEY = "your_key_here"
   ```
5. Click **Deploy**. Done! 🎉

---

## 📁 Project Structure

```
gitlab-chatbot/
├── app.py                        # Streamlit UI (entry point)
├── build_index.py                # CLI script to scrape + index
├── requirements.txt
├── .env                          # Your API key (not committed)
├── .gitignore
├── .streamlit/
│   ├── config.toml               # GitLab orange/purple theme
│   ├── secrets.toml              # Your API key for Streamlit (not committed)
│   └── secrets.toml.example
├── pages/
│   └── 2_About.py                # Architecture + design decisions page
├── tests/
│   ├── test_ingestion.py         # Unit tests for scraper
│   └── test_chatbot.py           # Unit tests for chatbot helpers
└── src/
    ├── ingestion.py              # Web scraping (requests + BeautifulSoup)
    ├── vector_store.py           # Custom GeminiEmbeddings + FAISS index
    └── chatbot.py                # RAG chain (LangChain LCEL + Gemini)
```

---

## 🧠 Key Design Decisions

### Why RAG instead of fine-tuning?
RAG is far more practical here: the GitLab Handbook updates frequently, and RAG lets us refresh the knowledge base with a single re-scrape — no retraining required. Fine-tuning would bake in stale information and cost hundreds of dollars.

### Why FAISS over Pinecone/Weaviate?
For ~561 document chunks, local FAISS is faster (no network round-trip), free, and zero-config. A production system at scale would graduate to a managed vector DB.

### Why MMR (Maximal Marginal Relevance) retrieval?
Standard top-k similarity search often returns near-duplicate chunks. MMR balances relevance with diversity, giving the LLM a richer, non-redundant context window.

### Why a custom embeddings class instead of langchain-google-genai?
`langchain-google-genai 2.x` has a model name format bug causing `400 unexpected model name format` errors. The custom `GeminiEmbeddings` class in `vector_store.py` calls Google's REST API directly — no middleware, no version conflicts, full control over batching and retry logic.

### Why gemini-2.5-flash?
`gemini-1.5-flash` returns 404 on the v1beta endpoint. `gemini-2.0-flash` has `limit: 0` on the free tier in India. `gemini-2.5-flash` is the latest available model that works reliably — and is actually a better model than originally planned.

### Guardrails approach
Rather than blocking queries, we add contextual safety banners for sensitive topics (compensation, legal, HR). This answers the question while reminding the user to verify through official channels — more useful than a wall.

---

## ⚠️ Windows-Specific Notes

- Use `venv\Scripts\Activate.ps1` not `venv/bin/activate`
- All files must be saved as **UTF-8** (not UTF-8 BOM, not UTF-16)
- Create `.streamlit/secrets.toml` manually in Notepad with UTF-8 encoding — do not use PowerShell `echo` which saves as UTF-16
- Delete FAISS index with: `Remove-Item -Recurse -Force data\faiss_index`

---

## 📊 Sample Questions to Try

- *"What are GitLab's CREDIT values?"*
- *"How does GitLab handle asynchronous communication?"*
- *"What is GitLab's direction for AI-assisted development?"*
- *"What is the onboarding process for new engineers?"*
- *"How does GitLab approach diversity and inclusion?"*
- *"What are the engineering career levels at GitLab?"*

---

## 📄 License

MIT
