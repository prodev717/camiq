import cv2
import torch
import open_clip
from PIL import Image
import numpy as np
import os
import pickle
import time

def format_timestamp(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

# ----------------------------
# Configuration
# ----------------------------

VIDEO_PATH = "cctv.mp4"  # Change to your video
INDEX_FILE = os.path.splitext(VIDEO_PATH)[0] + "_siglip_index.pkl"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

STATIC_PIXEL_DIFF_THRESHOLD = 2.0   # mean abs pixel diff (0-255 scale) below this = static, skip
SEMANTIC_SIM_THRESHOLD = 0.93       # cosine sim above this = "same as last kept frame", skip

# ----------------------------
# Load SigLIP
# ----------------------------

model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-16-SigLIP",
    pretrained="open_clip_model.safetensors",
)

tokenizer = open_clip.tokenizer.HFTokenizer(
    "siglip_tokenizer", 
    context_length=64
)

model = model.to(DEVICE).eval()

# ----------------------------
# Encode Image
# ----------------------------


@torch.no_grad()
def encode_image(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    image = preprocess(image).unsqueeze(0).to(DEVICE)
    embedding = model.encode_image(image)
    embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze(0).cpu()


# ----------------------------
# Encode Text
# ----------------------------


@torch.no_grad()
def encode_text(text):
    tokens = tokenizer([text]).to(DEVICE)
    embedding = model.encode_text(tokens)
    embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze(0).cpu()


# ----------------------------
# Frame difference helper (cheap pre-filter)
# ----------------------------


def is_static_frame(prev_gray, curr_gray):
    if prev_gray is None:
        return False
    diff = cv2.absdiff(prev_gray, curr_gray)
    return diff.mean() < STATIC_PIXEL_DIFF_THRESHOLD


# ----------------------------
# Build Frame Index (with dedup)
# ----------------------------

if os.path.exists(INDEX_FILE):

    print(f"Loading existing index: {INDEX_FILE}")

    with open(INDEX_FILE, "rb") as f:
        index = pickle.load(f)

    frame_embeddings = index["embeddings"]
    timestamps = index["timestamps"]

    frame_images = []

    for buf in index["frames"]:
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        frame_images.append(frame)

else:
    start_time = time.perf_counter()
    cap = cv2.VideoCapture(VIDEO_PATH)

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = max(int(fps), 1)  # candidate check ~1x/sec

    frame_embeddings = []
    frame_images = []
    timestamps = []

    last_kept_embedding = None
    prev_gray_for_diff = None
    frame_id = 0

    skipped_static = 0
    skipped_semantic = 0

    print("Indexing video...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_id % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Stage 1: cheap static-frame skip (no model call needed)
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

            print(f"Indexed {timestamps[-1]:.1f}s")

        frame_id += 1

    cap.release()

    frame_embeddings = torch.stack(frame_embeddings)
    compressed_frames = []

    for frame in frame_images:
        _, buf = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 90],
        )
        compressed_frames.append(buf)

    index_data = {
        "video": VIDEO_PATH,
        "embeddings": frame_embeddings,
        "frames": compressed_frames,
        "timestamps": timestamps,
        "fps": fps,
        "thresholds": {
            "static": STATIC_PIXEL_DIFF_THRESHOLD,
            "semantic": SEMANTIC_SIM_THRESHOLD,
        },
    }

    with open(INDEX_FILE, "wb") as f:
        pickle.dump(index_data, f)

    print(f"\nSaved index to {INDEX_FILE}")
    print(f"\nIndexed {len(frame_embeddings)} frames.")
    print(f"Skipped {skipped_static} static frames, {skipped_semantic} near-duplicate frames.\n")
    end_time = time.perf_counter()
    print(f"Total time: {end_time - start_time:.2f} seconds")

# ----------------------------
# Interactive Search
# ----------------------------

TOP_K = 5


def build_grid(frames_with_labels, cols=5, thumb_size=(320, 240)):
    """Stack frames into a single image grid, 1 row x TOP_K cols by default."""
    thumbs = []
    for frame, label in frames_with_labels:
        thumb = cv2.resize(frame, thumb_size)
        cv2.putText(
            thumb, label, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
        )
        thumbs.append(thumb)

    rows = []
    for i in range(0, len(thumbs), cols):
        row_thumbs = thumbs[i:i + cols]
        # pad last row if incomplete
        while len(row_thumbs) < cols:
            row_thumbs.append(np.zeros_like(thumbs[0]))
        rows.append(np.hstack(row_thumbs))

    return np.vstack(rows)


while True:
    query = input("\nSearch (or 'exit'): ")
    if query.lower() == "exit":
        break

    text_embedding = encode_text(query)
    scores = frame_embeddings @ text_embedding

    values, indices = torch.topk(scores, k=min(TOP_K, len(scores)))

    print("\nTop Matches")
    print("-" * 50)

    grid_inputs = []
    for rank, (score, idx) in enumerate(zip(values, indices), start=1):
        idx = idx.item()
        ts = format_timestamp(timestamps[idx])
        print( f"{rank}. Timestamp: {ts:>8}   Score: {score.item():.4f}" )
        label = f"#{rank} {format_timestamp(timestamps[idx])} {score.item():.3f}"
        grid_inputs.append((frame_images[idx], label))

    grid = build_grid(grid_inputs, cols=len(grid_inputs))
    cv2.imshow("Top Matches", grid)
    cv2.waitKey(0)
    cv2.destroyWindow("Top Matches")