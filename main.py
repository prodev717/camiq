"""
Video understanding pipeline:

    Video
      |
    Sample every N seconds
      |
    SSIM vs previous KEPT frame (very fast)
      |
    SSIM > threshold?  --Yes--> Skip frame entirely
      |No
    Run YOLO
      |
    Compare detections with previous YOLO result
      |
    Major semantic change?  --No--> Skip VLM caption
      |Yes
    Qwen2.5-VL caption (via Ollama)

Requires: opencv-python, numpy, scikit-image, ultralytics, ollama
    pip install opencv-python numpy scikit-image ultralytics ollama
"""

import time
import cv2
import numpy as np
import ollama
from skimage.metrics import structural_similarity as ssim
from ultralytics import YOLO

model = YOLO("yolo26n.pt")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
SSIM_THRESHOLD = 0.95        # above this -> frames considered "the same", skip
SSIM_RESIZE = (320, 180)     # downscale before SSIM for speed
YOLO_CONF_THRESHOLD = 0.35   # ignore low-confidence detections when comparing
COUNT_CHANGE_THRESHOLD = 1   # per-class count delta that counts as "major"
NEW_CLASS_IS_MAJOR = True    # any newly appeared / vanished class = major change


# ---------------------------------------------------------------------------
# YOLO
# ---------------------------------------------------------------------------
def predict_from_bytes(image_bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        print("Failed to decode image.")
        return []
    results = model(image, verbose=False)
    predictions = []
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            predictions.append({
                "name": result.names[cls_id],
                "confidence": round(float(box.conf[0]), 3),
                "box": [round(x, 2) for x in box.xyxy[0].tolist()],
            })
    return predictions


# ---------------------------------------------------------------------------
# VLM captioning
# ---------------------------------------------------------------------------
def describe_image_with_ollama(image_bytes):
    response = ollama.chat(
        model="qwen2.5vl:3b",
        messages=[
            {
                "role": "user",
                "content": "Describe this image in 2 lines.",
                "images": [image_bytes],
            }
        ],
    )
    return response["message"]["content"]


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------
def extract_frames_in_memory(video_path, interval_seconds=2.0, jpeg_quality=90):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Cannot open video: {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        print("Unable to determine FPS.")
        cap.release()
        return []
    frame_step = max(1, int(fps * interval_seconds))
    frames = []
    frame_count = 0
    print(f"Processing {video_path}")
    print(f"FPS: {fps:.2f}")
    print(f"Sampling every {interval_seconds} seconds...\n")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_step == 0:
            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            success, encoded = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )
            if not success:
                frame_count += 1
                continue
            frames.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "timestamp_sec": timestamp_ms / 1000.0,
                    "width": frame.shape[1],
                    "height": frame.shape[0],
                    "channels": frame.shape[2],
                    "bytes": encoded.tobytes(),
                    "raw": frame,  # keep the raw ndarray around for SSIM
                }
            )
        frame_count += 1
    cap.release()
    print(f"\nExtracted {len(frames)} frames.\n")
    return frames


# ---------------------------------------------------------------------------
# SSIM gate
# ---------------------------------------------------------------------------
def _prep_for_ssim(frame_bgr):
    """Grayscale + downscale a frame for fast SSIM comparison."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, SSIM_RESIZE, interpolation=cv2.INTER_AREA)
    return small


def compute_ssim(prev_gray_small, curr_frame_bgr):
    """Returns SSIM score between the previous kept frame and the current one."""
    curr_gray_small = _prep_for_ssim(curr_frame_bgr)
    score = ssim(prev_gray_small, curr_gray_small)
    return score, curr_gray_small


# ---------------------------------------------------------------------------
# Semantic change gate (based on YOLO detections)
# ---------------------------------------------------------------------------
def _class_counts(detections, conf_threshold=YOLO_CONF_THRESHOLD):
    counts = {}
    for det in detections:
        if det["confidence"] < conf_threshold:
            continue
        counts[det["name"]] = counts.get(det["name"], 0) + 1
    return counts


def has_major_semantic_change(prev_detections, curr_detections):
    """
    Compares two YOLO detection sets and decides whether the scene changed
    enough to warrant a fresh VLM caption.

    Triggers on:
      - a class appearing that wasn't there before (or vice versa)
      - the count of an existing class changing by more than
        COUNT_CHANGE_THRESHOLD
    """
    if prev_detections is None:
        # No prior frame to compare against -> first frame, always caption it
        return True

    prev_counts = _class_counts(prev_detections)
    curr_counts = _class_counts(curr_detections)

    prev_classes = set(prev_counts.keys())
    curr_classes = set(curr_counts.keys())

    appeared = curr_classes - prev_classes
    vanished = prev_classes - curr_classes

    if NEW_CLASS_IS_MAJOR and (appeared or vanished):
        return True

    for cls in prev_classes & curr_classes:
        if abs(curr_counts[cls] - prev_counts[cls]) > COUNT_CHANGE_THRESHOLD:
            return True

    return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def process_video(video_path, interval=5.0):
    frames = extract_frames_in_memory(video_path, interval)

    prev_ssim_gray = None      # small grayscale of the last KEPT frame
    prev_detections = None     # YOLO result of the last frame that ran YOLO

    stats = {"total": len(frames), "ssim_skipped": 0, "yolo_run": 0, "vlm_run": 0}

    for i, frame in enumerate(frames):
        print("=" * 80)
        print(f"Frame {i+1}/{len(frames)}")
        print(f"Timestamp : {frame['timestamp_sec']:.2f}s")
        print(f"Resolution: {frame['width']} x {frame['height']}")

        # --- Stage 1: SSIM gate -------------------------------------------------
        if prev_ssim_gray is not None:
            score, curr_ssim_gray = compute_ssim(prev_ssim_gray, frame["raw"])
            print(f"SSIM vs previous kept frame: {score:.4f}")
            if score > SSIM_THRESHOLD:
                print("-> Near-duplicate frame, skipping (no YOLO, no VLM).")
                stats["ssim_skipped"] += 1
                # Do NOT update prev_ssim_gray: keep comparing against the
                # last frame we actually kept, so slow drift still gets caught.
                print()
                continue
        else:
            curr_ssim_gray = _prep_for_ssim(frame["raw"])

        prev_ssim_gray = curr_ssim_gray

        # --- Stage 2: YOLO -------------------------------------------------------
        print("Running YOLO...")
        detections = predict_from_bytes(frame["bytes"])
        stats["yolo_run"] += 1
        if detections:
            for obj in detections:
                print(obj)
        else:
            print("No objects detected.")

        # --- Stage 3: semantic-change gate ---------------------------------------
        major_change = has_major_semantic_change(prev_detections, detections)
        prev_detections = detections

        if not major_change:
            print("-> No major semantic change vs previous frame, skipping VLM.")
            print()
            continue

        # --- Stage 4: VLM captioning ----------------------------------------------
        print("Major semantic change detected. Generating caption...\n")
        description = describe_image_with_ollama(frame["bytes"])
        stats["vlm_run"] += 1
        print(description)
        print()

    print("=" * 80)
    print("Summary")
    print(f"  Total sampled frames : {stats['total']}")
    print(f"  Skipped by SSIM      : {stats['ssim_skipped']}")
    print(f"  YOLO runs            : {stats['yolo_run']}")
    print(f"  VLM caption runs     : {stats['vlm_run']}")
    return stats


if __name__ == "__main__":
    VIDEO_FILE = "sample.mp4"
    INTERVAL_SECONDS = 5.0
    start_time = time.perf_counter()
    process_video(VIDEO_FILE, INTERVAL_SECONDS)
    end_time = time.perf_counter()
    cv2.destroyAllWindows()
    total_time = end_time - start_time

    print(f"\nTotal execution time: {total_time:.2f} seconds")
    print(f"Total execution time: {total_time / 60:.2f} minutes")