import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import (
    InvalidVideoError,
    RagServiceError,
    TranscriptUnavailableError,
    VideoNotProcessedError,
    ask_question,
    process_video,
)

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube RAG API",
    description="Process Hindi YouTube transcripts and ask grounded questions.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        dict.fromkeys(
            origin.strip()
            for origin in (
                f"http://localhost:5173,{os.getenv('FRONTEND_URL', '')}"
            ).split(",")
            if origin.strip()
        )
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessVideoRequest(BaseModel):
    url: str = Field(min_length=1)


class ProcessVideoResponse(BaseModel):
    video_id: str
    chunks: int
    message: str


class ChatRequest(BaseModel):
    video_id: str = Field(min_length=1)
    question: str = Field(min_length=1)


class Source(BaseModel):
    chunk_id: int
    content: str
    source: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/video/process",
    response_model=ProcessVideoResponse,
    summary="Process a YouTube video",
)
def process_video_endpoint(request: ProcessVideoRequest) -> dict[str, Any]:
    try:
        return process_video(request.url)
    except InvalidVideoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        logger.exception("Unexpected error while processing video")
        raise HTTPException(status_code=500, detail="Video processing failed.") from None


@app.post("/api/chat", response_model=ChatResponse, summary="Ask about a processed video")
def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        return ask_question(request.video_id, request.question)
    except (InvalidVideoError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoNotProcessedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RagServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        logger.exception("Unexpected error while answering question")
        raise HTTPException(status_code=500, detail="Question answering failed.") from None
