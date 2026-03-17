import logging
import os
from typing import Iterator

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnablePassthrough
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are GitBot, an expert assistant for GitLab employees and aspiring employees. \
You have deep knowledge of GitLab's Handbook and product Direction pages.

Your personality:
- Helpful, precise, and transparent
- You celebrate GitLab's "build in public" and "everyone can contribute" values
- You acknowledge when you're uncertain rather than guessing

Guidelines:
1. Answer ONLY using the provided context. If the answer is not in the context, say so clearly.
2. Always end your response with a "📚 Sources" section listing the URLs you used.
3. If a question is ambiguous, ask a clarifying question.
4. For sensitive HR/legal topics, remind the user to verify with the relevant team.
5. Keep answers concise but complete. Use bullet points and headers for complex answers.
6. If you don't know something, say: "I couldn't find that in the GitLab Handbook or Direction pages. \
   You may want to check handbook.gitlab.com directly or ask your manager."

Context from GitLab's Handbook and Direction pages:
{context}
"""

GUARDRAILS = {
    "sensitive_topics": [
        "salary", "compensation", "termination", "fired", "lawsuit",
        "legal", "harassment", "discrimination", "medical", "visa",
    ],
    "safety_note": (
        "\n\n⚠️ **Note**: This involves a sensitive topic. "
        "Please verify this information with your People Business Partner or the Legal team."
    ),
}


def _format_docs(docs) -> str:
    """Format retrieved documents into a numbered context block."""
    formatted = []
    for i, doc in enumerate(docs, 1):
        section = doc.metadata.get("section", "")
        title = doc.metadata.get("title", "")
        url = doc.metadata.get("url", "")
        header = f"[{i}] {title}" + (f" — {section}" if section else "")
        formatted.append(f"{header}\nSource: {url}\n{doc.page_content}")
    return "\n\n---\n\n".join(formatted)


def _is_sensitive(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in GUARDRAILS["sensitive_topics"])


def _build_history_messages(history: list[dict]):
    """Convert our simple chat history dicts → LangChain message objects."""
    messages = []
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        else:
            messages.append(AIMessage(content=turn["content"]))
    return messages


class GitLabChatbot:

    def __init__(self, vectorstore: FAISS):
        self.retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 6, "fetch_k": 20},
        )

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0.2,          
            convert_system_message_to_human=True,  
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ])

    def _make_chain(self, retrieved_docs, history_messages):
        return (
            {
                "context": lambda _: _format_docs(retrieved_docs),
                "question": RunnablePassthrough(),
                "chat_history": lambda _: history_messages,
            }
            | self.prompt
            | self.llm
        )

    def chat(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> dict:

        history = history or []
        history_messages = _build_history_messages(history)

        retrieved_docs = self.retriever.invoke(query)

        chain = self._make_chain(retrieved_docs, history_messages)
        response = chain.invoke(query)

        answer = response.content

        seen_urls = set()
        sources = []
        for doc in retrieved_docs:
            url = doc.metadata.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    "title": doc.metadata.get("title", "GitLab Handbook"),
                    "url": url,
                    "section": doc.metadata.get("section", ""),
                    "source_type": doc.metadata.get("source_type", "handbook"),
                })

        guardrail_note = GUARDRAILS["safety_note"] if _is_sensitive(query) else None

        return {
            "answer": answer,
            "sources": sources,
            "guardrail_note": guardrail_note,
            "retrieved_docs": retrieved_docs,
        }

    def stream_chat(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> Iterator[str]:
       
        history = history or []
        history_messages = _build_history_messages(history)
        retrieved_docs = self.retriever.invoke(query)

        stream_chain = self._make_chain(retrieved_docs, history_messages)

        for chunk in stream_chain.stream(query):
            if chunk.content:
                yield chunk.content

        
        self._last_docs = retrieved_docs
        self._last_query = query
