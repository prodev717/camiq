"""
app.py — FastAPI backend for Camiq CCTV semantic search
"""

import threading
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import siglip_engine as engine

# ----------------------------
# App Setup
# ----------------------------

app = FastAPI(title="Camiq API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

# ----------------------------
# Progress tracking (thread-safe)
# ----------------------------

_progress = {"pct": 0, "msg": ""}
_progress_lock = threading.Lock()


def _update_progress(pct: float, msg: str):
    with _progress_lock:
        _progress["pct"] = pct
        _progress["msg"] = msg


# ----------------------------
# Startup: load model once
# ----------------------------

@app.on_event("startup")
async def startup_event():
    engine.load_model()


# ----------------------------
# Schemas
# ----------------------------

class IndexRequest(BaseModel):
    video_path: str

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


# ----------------------------
# Endpoints
# ----------------------------

@app.post("/index")
async def index_video(req: IndexRequest, background_tasks: BackgroundTasks):
    """
    Start indexing a video in the background.
    Returns immediately; poll GET /index/status to track progress.
    """
    status = engine.get_status()
    if status["status"] == "indexing":
        raise HTTPException(status_code=409, detail="Indexing already in progress.")

    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    with _progress_lock:
        _progress["pct"] = 0
        _progress["msg"] = "Starting..."

    def run_indexing():
        try:
            engine.build_index(req.video_path, progress_callback=_update_progress)
        except Exception as e:
            pass  # error stored in engine state

    background_tasks.add_task(run_indexing)

    return {"message": "Indexing started", "video_path": req.video_path}


@app.get("/index/status")
async def index_status():
    """Return current indexing status and progress."""
    status = engine.get_status()
    with _progress_lock:
        pct = _progress["pct"]
        msg = _progress["msg"]

    return {
        **status,
        "progress_pct": pct,
        "progress_msg": msg,
    }


@app.post("/search")
async def search(req: SearchRequest):
    """
    Search the indexed video with a natural-language query.
    Returns top-K results with timestamps, scores, and frame indices.
    """
    try:
        results = engine.search(req.query, top_k=req.top_k)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "query": req.query,
        "results": results,
    }


@app.get("/frame/{frame_index}")
async def get_frame(frame_index: int):
    """Serve a specific indexed frame as a JPEG image."""
    try:
        jpeg_bytes = engine.get_frame(frame_index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(content=jpeg_bytes, media_type="image/jpeg")


@app.get("/video/stream")
async def stream_video(request: Request):
    """
    Serve the indexed video with HTTP Range request support.
    Range requests are required for the browser <video> element to seek.
    """
    video_path = engine.get_video_path()
    if not video_path or not os.path.isfile(video_path):
        raise HTTPException(status_code=404, detail="No video indexed yet or file not found.")

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("Range")

    CHUNK = 1024 * 1024  # 1 MB chunks

    if range_header:
        # Parse "bytes=START-END"
        try:
            byte_range = range_header.replace("bytes=", "").strip()
            start_str, end_str = byte_range.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else min(start + CHUNK - 1, file_size - 1)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Range header")

        if start >= file_size or end >= file_size:
            raise HTTPException(
                status_code=416,
                detail="Range Not Satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        content_length = end - start + 1

        def iter_range():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    # No Range header — stream the whole file
    def iter_full():
        with open(video_path, "rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    return StreamingResponse(
        iter_full(),
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
