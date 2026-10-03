import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CHROMA_DIR = str(BASE_DIR / "my_chroma_db")
COLLECTION_NAME = "yt_vectors"


class RagError(Exception):
    """Base error for expected RAG failures."""


class InvalidVideoError(RagError):
    pass


class TranscriptUnavailableError(RagError):
    pass


class VideoNotProcessedError(RagError):
    pass


class RagServiceError(RagError):
    pass


def get_video_id(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise InvalidVideoError("A YouTube URL is required.")

    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/")[2]
    elif host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise InvalidVideoError("The URL must be a valid YouTube video URL.")
    return video_id


def _get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        _vector_store = Chroma(
            embedding_function=GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001"
            ),
            persist_directory=CHROMA_DIR,
            collection_name=COLLECTION_NAME,
        )
    return _vector_store


def _get_model() -> ChatGoogleGenerativeAI:
    global _model
    if _model is None:
        _model = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)
    return _model


def format_docs(retrieved_docs: list[Any]) -> str:
    return "\n\n".join(document.page_content for document in retrieved_docs)


_vector_store: Chroma | None = None
_model: ChatGoogleGenerativeAI | None = None

_prompt = PromptTemplate(
    template="""You are a helpful assistant that answers questions based only on the provided context.

Context:
{context}

Question:
{question}

Instructions:
- Answer the question using only the information present in the context.
- Do not make up or assume information that is not present in the context.
- If the answer cannot be found in the context, clearly say:
  "I couldn't find the answer in the provided transcript."
- Give a clear and concise answer.
- Answer in the same language as the user's question.
- If the context contains relevant details, explain them briefly rather than giving only a one-line answer.

Answer:
""",
    input_variables=["context", "question"],
)


def _existing_chunk_count(video_id: str) -> int:
    result = _get_vector_store()._collection.get(
        where={"video_id": video_id}, include=[]
    )
    return len(result.get("ids", []))


def _transcript_text(transcript: Any) -> str:
    parts = []
    for item in transcript:
        if isinstance(item, dict):
            value = item.get("text", "")
        else:
            value = getattr(item, "text", "")
        parts.append(str(value).strip())
    return " ".join(parts).strip()


def process_video(url: str) -> dict[str, Any]:
    video_id = get_video_id(url)
    try:
        existing_count = _existing_chunk_count(video_id)
        if existing_count:
            return {
                "video_id": video_id,
                "chunks": existing_count,
                "message": "Video was already processed",
            }

        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["hi"])
        text = _transcript_text(transcript)
        if not text:
            raise TranscriptUnavailableError("The Hindi transcript is empty.")

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.create_documents([text])
        for index, chunk in enumerate(chunks):
            chunk.metadata = {
                "video_id": video_id,
                "source": url,
                "chunk_id": index,
            }

        ids = [f"{video_id}:{index}" for index in range(len(chunks))]
        _get_vector_store().add_documents(chunks, ids=ids)
        return {
            "video_id": video_id,
            "chunks": len(chunks),
            "message": "Video processed successfully",
        }
    except (InvalidVideoError, TranscriptUnavailableError):
        raise
    except Exception as exc:
        raise TranscriptUnavailableError(
            "The Hindi transcript could not be retrieved or stored."
        ) from exc


def ask_question(video_id: str, question: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        raise InvalidVideoError("The video ID is invalid.")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty.")

    try:
        store = _get_vector_store()
        if _existing_chunk_count(video_id) == 0:
            raise VideoNotProcessedError("This video has not been processed.")

        retriever = store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 4, "filter": {"video_id": video_id}},
        )
        parallel_chain = RunnableParallel(
            {
                "context": retriever | RunnableLambda(format_docs),
                "question": RunnablePassthrough(),
            }
        )
        main_chain = (
            parallel_chain
            | _prompt
            | _get_model()
            | StrOutputParser()
        )
        answer = main_chain.invoke(question.strip())
        documents = retriever.invoke(question.strip())
        sources = [
            {
                "chunk_id": document.metadata.get("chunk_id"),
                "content": document.page_content,
                "source": document.metadata.get("source"),
            }
            for document in documents
        ]
        return {"answer": answer, "sources": sources}
    except (InvalidVideoError, ValueError, VideoNotProcessedError):
        raise
    except Exception as exc:
        raise RagServiceError("The question could not be answered.") from exc
