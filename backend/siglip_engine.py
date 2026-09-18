"""
siglip_engine.py
Extracted ML logic from main.py — no logic changes, just restructured for use by FastAPI.
"""

import cv2
import torch
import open_clip
from PIL import Image
import numpy as np
import os
import pickle
import time
from pathlib import Path

# ----------------------------
# Configuration
# ----------------------------

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

STATIC_PIXEL_DIFF_THRESHOLD = 2.0   # mean abs pixel diff (0-255 scale) below this = static, skip
SEMANTIC_SIM_THRESHOLD = 0.93       # cosine sim above this = "same as last kept frame", skip

# Module-level state (loaded once on startup)
_model = None
_preprocess = None
_tokenizer = None

# In-memory index state
_index_state = {
    "status": "idle",           # idle | indexing | ready | error
    "video_path": None,
    "index_file": None,
    "frame_embeddings": None,
    "frame_images": [],
    "timestamps": [],
    "stats": {},
    "error": None,
}


# ----------------------------
# format_timestamp (unchanged)
# ----------------------------

def format_timestamp(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ----------------------------
# Load SigLIP (called once on startup)
# ----------------------------

def load_model():
    """Load SigLIP model and tokenizer into module globals."""
    global _model, _preprocess, _tokenizer

    # Resolve paths relative to the project root (one level up from backend/)
    project_root = Path(__file__).parent.parent
    weights_path = str(project_root / "open_clip_model.safetensors")
    tokenizer_path = str(project_root / "siglip_tokenizer")

    print(f"Loading SigLIP model on {DEVICE}...")
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        "ViT-B-16-SigLIP",
        pretrained=weights_path,
    )
    _tokenizer = open_clip.tokenizer.HFTokenizer(
        tokenizer_path,
        context_length=64,
    )
    _model = _model.to(DEVICE).eval()
    print("Model loaded.")


# ----------------------------
# Encode Image (unchanged logic)
# ----------------------------

@torch.no_grad()
def encode_image(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    image = _preprocess(image).unsqueeze(0).to(DEVICE)
    embedding = _model.encode_image(image)
    embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze(0).cpu()


# ----------------------------
# Encode Text (unchanged logic)
# ----------------------------

@torch.no_grad()
def encode_text(text: str):
    tokens = _tokenizer([text]).to(DEVICE)
    embedding = _model.encode_text(tokens)
    embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze(0).cpu()


# ----------------------------
# Frame difference helper (unchanged)
# ----------------------------

def is_static_frame(prev_gray, curr_gray):
    if prev_gray is None:
        return False
    diff = cv2.absdiff(prev_gray, curr_gray)
    return diff.mean() < STATIC_PIXEL_DIFF_THRESHOLD


# ----------------------------
# Build Frame Index (unchanged logic, adapted for background task)
# ----------------------------

def build_index(video_path: str, progress_callback=None):
    """
    Index a video file. Loads existing .pkl if available, otherwise builds from scratch.
    Updates the module-level _index_state dict throughout.
    progress_callback(pct: float, msg: str) is called periodically if provided.
    """
    global _index_state

    video_path = str(Path(video_path).resolve())
    index_file = os.path.splitext(video_path)[0] + "_siglip_index.pkl"

    _index_state.update({
        "status": "indexing",
        "video_path": video_path,
        "index_file": index_file,
        "frame_embeddings": None,
        "frame_images": [],
        "timestamps": [],
        "stats": {},
        "error": None,
    })

    try:
        if os.path.exists(index_file):
            # --- Load existing index ---
            if progress_callback:
                progress_callback(10, f"Loading existing index: {index_file}")

            with open(index_file, "rb") as f:
                index = pickle.load(f)

            frame_embeddings = index["embeddings"]
            timestamps = index["timestamps"]
            frame_images = []

            total = len(index["frames"])
            for i, buf in enumerate(index["frames"]):
                frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                frame_images.append(frame)
                if progress_callback and total > 0:
                    pct = 10 + int((i + 1) / total * 85)
                    progress_callback(pct, f"Loading frame {i+1}/{total}")

            _index_state.update({
                "status": "ready",
                "frame_embeddings": frame_embeddings,
                "frame_images": frame_images,
                "timestamps": timestamps,
                "stats": {
                    "total_frames": len(timestamps),
                    "source": "cached",
                    "index_file": index_file,
                },
            })

        else:
            # --- Build new index ---
            if progress_callback:
                progress_callback(0, "Opening video...")

            start_time = time.perf_counter()
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_interval = max(int(fps), 1)

            frame_embeddings = []
            frame_images = []
            timestamps = []

            last_kept_embedding = None
            prev_gray_for_diff = None
            frame_id = 0
            skipped_static = 0
            skipped_semantic = 0

            if progress_callback:
                progress_callback(2, "Indexing frames...")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_id % frame_interval == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                    # Stage 1: cheap static-frame skip
                    if is_static_frame(prev_gray_for_diff, gray):
                        skipped_static += 1
                        prev_gray_for_diff = gray
                        frame_id += 1
                        continue

                    prev_gray_for_diff = gray

                    # Stage 2: semantic dedup against last KEPT frame
                    emb = encode_image(frame)

                    if last_kept_embedding is not None:
                        sim = (emb @ last_kept_embedding).item()
                        if sim > SEMANTIC_SIM_THRESHOLD:
                            skipped_semantic += 1
                            frame_id += 1
                            continue

                    # Keep this frame
                    frame_embeddings.append(emb)
                    frame_images.append(frame.copy())
                    timestamps.append(frame_id / fps)
                    last_kept_embedding = emb

                    if progress_callback and total_frames > 0:
                        pct = 2 + int(frame_id / total_frames * 88)
                        progress_callback(pct, f"Indexed {format_timestamp(timestamps[-1])}")

                frame_id += 1

            cap.release()

            frame_embeddings_tensor = torch.stack(frame_embeddings)
            compressed_frames = []

            for frm in frame_images:
                _, buf = cv2.imencode(
                    ".jpg",
                    frm,
                    [cv2.IMWRITE_JPEG_QUALITY, 90],
                )
                compressed_frames.append(buf)

            index_data = {
                "video": video_path,
                "embeddings": frame_embeddings_tensor,
                "frames": compressed_frames,
                "timestamps": timestamps,
                "fps": fps,
                "thresholds": {
                    "static": STATIC_PIXEL_DIFF_THRESHOLD,
                    "semantic": SEMANTIC_SIM_THRESHOLD,
                },
            }

            with open(index_file, "wb") as f:
                pickle.dump(index_data, f)

            end_time = time.perf_counter()

            _index_state.update({
                "status": "ready",
                "frame_embeddings": frame_embeddings_tensor,
                "frame_images": frame_images,
                "timestamps": timestamps,
                "stats": {
                    "total_frames": len(timestamps),
                    "skipped_static": skipped_static,
                    "skipped_semantic": skipped_semantic,
                    "elapsed_seconds": round(end_time - start_time, 2),
                    "source": "new",
                    "index_file": index_file,
                },
            })

        if progress_callback:
            progress_callback(100, "Done")

    except Exception as e:
        _index_state["status"] = "error"
        _index_state["error"] = str(e)
        raise


# ----------------------------
# Search (unchanged logic)
# ----------------------------

def search(query: str, top_k: int = 5):
    """
    Search the current index for the given text query.
    Returns a list of dicts: {rank, timestamp, timestamp_str, score, frame_index}
    """
    if _index_state["status"] != "ready":
        raise RuntimeError("Index is not ready. Please index a video first.")

    frame_embeddings = _index_state["frame_embeddings"]
    timestamps = _index_state["timestamps"]

    text_embedding = encode_text(query)
    scores = frame_embeddings @ text_embedding

    k = min(top_k, len(scores))
    values, indices = torch.topk(scores, k=k)

    results = []
    for rank, (score, idx) in enumerate(zip(values, indices), start=1):
        idx_item = idx.item()
        results.append({
            "rank": rank,
            "frame_index": idx_item,
            "timestamp": timestamps[idx_item],
            "timestamp_str": format_timestamp(timestamps[idx_item]),
            "score": round(score.item(), 4),
        })

    return results


# ----------------------------
# Accessors
# ----------------------------

def get_status():
    return {
        "status": _index_state["status"],
        "video_path": _index_state["video_path"],
        "stats": _index_state["stats"],
        "error": _index_state["error"],
    }


def get_frame(frame_index: int):
    """Return a JPEG-encoded numpy buffer for the given frame index."""
    images = _index_state["frame_images"]
    if frame_index < 0 or frame_index >= len(images):
        raise IndexError(f"Frame index {frame_index} out of range (0-{len(images)-1})")
    frame = images[frame_index]
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


def get_video_path():
    return _index_state["video_path"]
