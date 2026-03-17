import streamlit as st

st.set_page_config(page_title="About GitBot", page_icon="📖", layout="wide")

st.title("📖 How GitBot Works")
st.caption("Architecture, design decisions, and every real technical choice made during development.")

# ── Architecture diagram ───────────────────────────────────────────────────────
st.header("🏗️ System Architecture")

st.code("""
┌─────────────────────────────────────────────────────────────────┐
│                     BUILD TIME (runs once)                      │
│                                                                 │
│  GitLab Handbook ──┐                                            │
│  GitLab Direction ─┤──► requests + BeautifulSoup Scraper       │
│  (~80 pages)       │         │                                  │
│                    │         ▼                                  │
│                    │   scraped_pages.json  (UTF-8 cached)       │
│                    │         │                                  │
│                    │         ▼                                  │
│                    │   Section Chunker (500+ chars/chunk)       │
│                    │         │    ~561 chunks total             │
│                    │         ▼                                  │
│                    │   Custom GeminiEmbeddings class            │
│                    │   REST API → v1beta                        │
│                    │   model: gemini-embedding-2-preview        │
│                    │   2s delay between requests (rate limit)   │
│                    │         │                                  │
│                    └───► FAISS Index  ──► saved to disk        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    QUERY TIME (per message)                     │
│                                                                 │
│  User Query                                                     │
│      │                                                          │
│      ▼                                                          │
│  GeminiEmbeddings.embed_query()  (REST v1beta)                  │
│      │                                                          │
│      ▼                                                          │
│  FAISS MMR Search  →  Top 6 diverse chunks + metadata          │
│      │                                                          │
│      ▼                                                          │
│  ChatPromptTemplate                                             │
│  ┌─────────────────────────────────────────┐                   │
│  │ System: "Answer only from context..."   │                   │
│  │ History: [prev turns]                   │                   │
│  │ Context: [chunk 1] [chunk 2] ... [6]    │                   │
│  │ Human:  <user query>                    │                   │
│  └─────────────────────────────────────────┘                   │
│      │                                                          │
│      ▼                                                          │
│  ChatGoogleGenerativeAI  (gemini-2.5-flash, temp=0.2)          │
│      │                                                          │
│      ▼                                                          │
│  Streamed Answer + Source Citations + Guardrail Check           │
└─────────────────────────────────────────────────────────────────┘
""", language=None)

# ── Key decisions ──────────────────────────────────────────────────────────────
st.header("⚙️ Key Design Decisions")

col1, col2 = st.columns(2)

with col1:
    with st.expander("🤔 Why RAG instead of fine-tuning?", expanded=True):
        st.markdown("""
        **RAG wins here for 3 reasons:**

        1. **Freshness** — GitLab's Handbook updates constantly. RAG lets us 
           refresh by re-scraping. Fine-tuning bakes in stale data permanently.

        2. **Cost** — Fine-tuning costs hundreds of dollars. 
           RAG runs entirely on the free tier.

        3. **Transparency** — RAG cites its sources. Fine-tuned models 
           can't tell you *why* they believe something.
        """)

    with st.expander("🗄️ Why FAISS over Pinecone / Weaviate?"):
        st.markdown("""
        For **~561 document chunks**, local FAISS is the right tool:
        - **Free** — no external service, no extra API key
        - **Fast** — in-process, no network round-trip
        - **Simple** — serialises to two files on disk, loads in seconds

        At **>1M vectors** a managed DB (Pinecone, Weaviate, Qdrant) 
        makes sense. Picking the right tool for the scale is the point.
        """)

    with st.expander("🔍 Why MMR retrieval?"):
        st.markdown("""
        **Maximal Marginal Relevance** balances:
        - **Relevance** to the query (cosine similarity)
        - **Diversity** among returned chunks (avoids near-duplicates)

        Without MMR you often get 6 almost-identical chunks — the same 
        paragraph repeated across pages. MMR ensures the LLM sees 
        genuinely different context every time.
        """)

    with st.expander("✂️ Why 500+ char chunk minimum?"):
        st.markdown("""
        Originally set to 50 chars, then raised to 150, then 300, then 500.

        **Why:** The free tier embedding API has strict rate limits. 
        Smaller chunks = more chunks = more API calls = more 429 errors.
        500 chars keeps the total under ~561 chunks which completes 
        within free tier limits at 2 requests/second.

        **Trade-off:** Very short sections (nav labels, one-liners) are 
        dropped. This is acceptable — they carry no useful context anyway.
        """)

with col2:
    with st.expander("⚡ Why gemini-2.5-flash?", expanded=True):
        st.markdown("""
        | Model | Status on free tier |
        |---|---|
        | gemini-1.5-flash | Not available (v1beta 404) |
        | gemini-2.0-flash | limit: 0 in India region |
        | gemini-2.0-flash-lite | limit: 0 in India region |
        | **gemini-2.5-flash** | **Works** |

        Google restricts certain models by region on the free tier.
        `gemini-2.5-flash` is actually a **newer and better model** 
        than what was originally planned — an unintentional upgrade.
        """)

    with st.expander("🎨 Why Streamlit over React?"):
        st.markdown("""
        - **Pure Python** — no npm, no webpack, no TypeScript
        - **Built-in session state** — conversation memory for free
        - **Streaming support** — live token output with minimal code
        - **Streamlit Cloud** — push to GitHub, deployed in 2 minutes
        - **The brief said simplest and best** — this is it

        React makes sense when you need custom interactions or are 
        integrating into an existing web app. Not here.
        """)

    with st.expander("🛡️ How do guardrails work?"):
        st.markdown("""
        Rather than **blocking** sensitive queries (bad UX), GitBot:

        1. **Answers the question** using Handbook content
        2. **Adds a warning banner** reminding the user to verify 
           with HR / Legal / their People Business Partner

        Topics monitored: salary, compensation, termination, legal, 
        harassment, discrimination, medical, visa.

        This follows GitLab's own value of **transparency** — 
        give people information, not paternalistic walls.
        """)

    with st.expander("🔧 Why a custom embeddings class?"):
        st.markdown("""
        `langchain-google-genai 2.x` had a model name format bug — 
        it mangled `models/text-embedding-004` into an invalid format 
        causing `400 unexpected model name format` errors.

        **Fix:** Wrote a custom `GeminiEmbeddings` class that calls 
        Google's REST API directly with `requests`. This:
        - Bypasses the broken LangChain wrapper entirely
        - Gives full control over model name, task type, and batching
        - Adds retry logic with exponential backoff for 429 errors
        - Is only ~40 lines of clean, readable Python

        **Interview point:** Knowing *when* to bypass a library and 
        call the API directly is a key engineering skill.
        """)


# ── Data sources ───────────────────────────────────────────────────────────────
st.header("📄 Data Sources")

st.markdown("""
| Source | URL | Content |
|---|---|---|
| **GitLab Handbook** | handbook.gitlab.com | Values, processes, people policies, engineering |
| **GitLab Direction** | about.gitlab.com/direction | Product roadmap, stage direction, vision |

**~80 pages** scraped, **~561 chunks** indexed after filtering short sections.
Section-level chunking means citations link to the exact heading, not just the page.
""")

st.info(
    "💡 The knowledge base is cached on disk. "
    "Use the **Rebuild** button in the sidebar to refresh it."
)

# ── Tech stack ─────────────────────────────────────────────────────────────────
st.header("🛠️ Final Tech Stack")

cols = st.columns(4)
stack = [
    ("🤖 LLM", "gemini-2.5-flash", "Latest Gemini, works on free tier in India"),
    ("🔢 Embeddings", "gemini-embedding-2-preview", "Custom REST class, bypasses LangChain wrapper"),
    ("🗄️ Vector DB", "FAISS (local)", "Zero cost, in-process, saves to disk"),
    ("⛓️ Framework", "LangChain 0.3.25", "LCEL pipeline, langchain_core imports"),
    ("🖥️ Frontend", "Streamlit 1.40", "Pure Python, session state, streaming"),
    ("🕸️ Scraping", "requests + BS4", "UTF-8 forced, 0.5s polite delay"),
    ("🔑 API", "Google AI Studio", "Free tier, same key for embed + chat"),
    ("💾 Cache", "JSON + FAISS on disk", "Rebuild once, loads in 5s after"),
]
for i, (icon_name, tech, reason) in enumerate(stack):
    with cols[i % 4]:
        st.metric(label=icon_name, value=tech, help=reason)