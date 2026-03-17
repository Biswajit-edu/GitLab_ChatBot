import os
import sys
import logging
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))


load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)


try:
    from chatbot import _is_sensitive  # noqa: E402
except ImportError:
    def _is_sensitive(q: str) -> bool:  # fallback if src not yet on path
        return False


st.set_page_config(
    page_title="GitBot — GitLab Handbook Assistant",
    page_icon="🦊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
      /* GitLab brand colors */
      :root {
        --gl-orange: #FC6D26;
        --gl-purple: #6B4FBB;
        --gl-dark: #1F1F2E;
        --gl-light: #FAFAFA;
      }

      /* Header bar */
      .gl-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 0.5rem 0 1.2rem 0;
        border-bottom: 2px solid var(--gl-orange);
        margin-bottom: 1.5rem;
      }
      .gl-header h1 {
        margin: 0;
        font-size: 1.8rem;
        color: var(--gl-orange);
        font-weight: 700;
      }
      .gl-header p {
        margin: 0;
        font-size: 0.9rem;
        color: #888;
      }

      /* Source chips */
      .source-chip {
        display: inline-block;
        background: #f0f0f5;
        border-radius: 20px;
        padding: 3px 12px;
        margin: 3px;
        font-size: 0.78rem;
        color: var(--gl-purple);
        border: 1px solid #ddd;
      }
      .source-chip a { color: var(--gl-purple); text-decoration: none; }
      .source-chip a:hover { text-decoration: underline; }

      /* Guardrail banner */
      .guardrail-banner {
        background: #fff8e1;
        border-left: 4px solid #f9a825;
        padding: 10px 14px;
        border-radius: 4px;
        font-size: 0.85rem;
        margin-top: 8px;
      }

      /* Suggested questions */
      .suggested-q {
        background: #f5f3ff;
        border: 1px solid var(--gl-purple);
        border-radius: 8px;
        padding: 8px 14px;
        cursor: pointer;
        font-size: 0.85rem;
        color: var(--gl-purple);
        margin: 4px 0;
        width: 100%;
        text-align: left;
      }

      /* Stat card */
      .stat-card {
        background: var(--gl-orange);
        color: white;
        border-radius: 8px;
        padding: 10px 14px;
        text-align: center;
        font-weight: 700;
        font-size: 1.1rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="🔄 Loading GitLab knowledge base...")
def load_chatbot():
    from ingestion import scrape_all  # noqa: E402
    from vector_store import build_index  # noqa: E402
    from chatbot import GitLabChatbot  # noqa: E402

    
    try:
        if hasattr(st, "secrets"):
            secret_key = st.secrets.get("GOOGLE_API_KEY", None)
            if secret_key:
                os.environ["GOOGLE_API_KEY"] = secret_key
    except Exception:
        pass

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_google_api_key_here":
        st.error(
            "🔑 **GOOGLE_API_KEY not set.**  \n"
            "**Local**: Copy `.env.example` → `.env` and add your key.  \n"
            "**Streamlit Cloud**: Add it under Settings → Secrets.  \n"
            "Get a free key at https://aistudio.google.com"
        )
        st.stop()

    try:
        pages = scrape_all(max_pages=80)
        vectorstore = build_index(pages)
        bot = GitLabChatbot(vectorstore)
        bot._page_count = len(pages)
        bot._chunk_count = sum(len(p.get("chunks", [])) for p in pages)
        return bot
    except Exception as exc:
        st.error(f"❌ Failed to initialise knowledge base: {exc}")
        st.stop()



if "messages" not in st.session_state:
    st.session_state.messages = []          
if "show_sources" not in st.session_state:
    st.session_state.show_sources = True
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None


# Sidebar 
with st.sidebar:
    st.image(
        "https://about.gitlab.com/images/press/logo/png/gitlab-logo-500.png",
        width=140,
    )
    st.title("GitBot Settings")
    st.divider()

    bot = load_chatbot()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"<div class='stat-card'>{bot._page_count}<br><small>Pages</small></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div class='stat-card'>{bot._chunk_count}<br><small>Chunks</small></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.session_state.show_sources = st.toggle(
        "📚 Show sources after answers", value=True
    )
    show_transparency = st.toggle("🔍 Show retrieved context (debug)", value=False)

    st.divider()
    if st.button("🗑️ Clear chat history"):
        st.session_state.messages = []
        st.session_state.last_sources = []
        st.session_state.last_docs = []
        st.rerun()

    if st.button("🔄 Rebuild knowledge base"):
        from ingestion import scrape_all  # noqa: E402
        from vector_store import build_index  # noqa: E402
        with st.spinner("Rebuilding... this takes a few minutes."):
            pages = scrape_all(force=True)
            build_index(pages, force=True)
        st.success("Knowledge base rebuilt!")
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    st.caption(
        "GitBot uses **Gemini 2.5 Flash** + **FAISS** RAG. "
        "Answers are grounded in GitLab's public Handbook and Direction pages."
    )


st.markdown(
    """
    <div class="gl-header">
      <div>
        <h1>🦊 GitBot</h1>
        <p>Your AI guide to the GitLab Handbook & Product Direction</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Suggested questions
SUGGESTED = [
    "What are GitLab's core values and how do they guide daily work?",
    "How does GitLab's remote-first culture work in practice?",
    "What is GitLab's product direction for AI/ML (ModelOps)?",
    "What is the hiring process at GitLab?",
    "How does GitLab handle asynchronous communication?",
    "What are GitLab's total rewards and compensation principles?",
]

if not st.session_state.messages:
    st.markdown("#### 💡 Try asking...")
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTED):
        with cols[i % 2]:
            if st.button(q, key=f"suggest_{i}", use_container_width=True):
                st.session_state.pending_prompt = q
                st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🦊" if msg["role"] == "assistant" else "👤"):
        st.markdown(msg["content"])

# Chat input 
if prompt := st.chat_input("Ask me anything about the GitLab Handbook or Direction..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🦊"):
        history = st.session_state.messages[:-1]

        full_response = ""
        response_placeholder = st.empty()

        for token in bot.stream_chat(prompt, history):
            full_response += token
            response_placeholder.markdown(full_response + "▌")

        response_placeholder.markdown(full_response)

        retrieved_docs = getattr(bot, "_last_docs", [])
        st.session_state.last_docs = retrieved_docs

        if _is_sensitive(prompt):
            st.markdown(
                "<div class='guardrail-banner'>⚠️ <b>Sensitive topic detected.</b> "
                "Please verify compensation, legal, or HR information with the relevant "
                "GitLab team or your People Business Partner.</div>",
                unsafe_allow_html=True,
            )

        if st.session_state.show_sources and retrieved_docs:
            seen = set()
            source_html = "<br><small><b>📚 Sources:</b> "
            for doc in retrieved_docs:
                url = doc.metadata.get("url", "")
                title = doc.metadata.get("title", "GitLab")
                section = doc.metadata.get("section", "")
                label = f"{title}" + (f" › {section[:30]}" if section else "")
                if url not in seen:
                    seen.add(url)
                    source_html += (
                        f"<span class='source-chip'>"
                        f"<a href='{url}' target='_blank'>🔗 {label}</a>"
                        f"</span>"
                    )
            source_html += "</small>"
            st.markdown(source_html, unsafe_allow_html=True)

        if show_transparency and retrieved_docs:
            with st.expander("🔍 Retrieved context chunks (transparency)", expanded=False):
                for i, doc in enumerate(retrieved_docs, 1):
                    st.markdown(f"**Chunk {i}** — `{doc.metadata.get('url', '')}`")
                    st.markdown(f"*Section: {doc.metadata.get('section', 'N/A')}*")
                    st.text(doc.page_content[:500] + ("..." if len(doc.page_content) > 500 else ""))
                    st.divider()

    
    st.session_state.messages.append({"role": "assistant", "content": full_response})
