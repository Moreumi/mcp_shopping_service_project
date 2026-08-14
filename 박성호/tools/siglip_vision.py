"""Local SigLIP image scoring for retrieval candidates.

This module is deliberately independent from the active search workflow.  It
can be evaluated as a method-B reranker before we enable it in production or
precompute the full catalog (method A).
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from functools import lru_cache
import os
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests
from PIL import Image


MODEL_ID = os.getenv("SIGLIP_MODEL_ID", "google/siglip-base-patch16-224")
CACHE_DIR = Path(os.getenv("SIGLIP_CACHE_DIR", "data/amazon_fashion/siglip_cache"))
DOWNLOAD_TIMEOUT = (5, 15)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# Precision-first: the requested color must beat every competing palette color.
# Returning fewer products is preferable to displaying a visibly wrong item.
COLOR_MARGIN_MIN = float(os.getenv("SIGLIP_COLOR_MARGIN_MIN", "0.0"))

COLOR_LABELS = {
    "Black": "a product whose main visible color is black",
    "White": "a product whose main visible color is white",
    "Red": "a product whose main visible color is red",
    "Blue": "a product whose main visible color is blue",
    "Brown": "a product whose main visible color is brown",
    "Green": "a product whose main visible color is green",
    "Pink": "a product whose main visible color is pink",
    "Gray": "a product whose main visible color is gray",
    "Beige": "a product whose main visible color is beige",
    "Navy": "a product whose main visible color is navy blue",
    "Yellow": "a product whose main visible color is yellow",
    "Orange": "a product whose main visible color is orange",
    "Purple": "a product whose main visible color is purple",
    "Silver": "a product whose main visible color is silver",
    "Gold": "a product whose main visible color is gold",
    "Multicolor": "a product whose main visible appearance is multicolored",
}

KIND_LABELS = {
    "Sneakers": {
        "positive": ("a photo of a sneaker", "a photo of an athletic shoe"),
        "negative": (
            "a photo of a shoe care kit",
            "a photo of shoe accessories",
            "a photo of socks",
            "a photo of product packaging without shoes",
        ),
    },
    "FormalShoes": {
        "positive": ("a photo of a formal dress shoe", "a photo of a loafer"),
        "negative": (
            "a photo of a sneaker",
            "a photo of a shoe care kit",
            "a photo of shoe accessories",
            "a photo of product packaging without shoes",
        ),
    },
}

_runtime = None
_runtime_lock = threading.Lock()


def _load_runtime():
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            return _runtime
        import torch
        from transformers import AutoModel, AutoProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # The demo must keep working without Hugging Face network access after
        # the one-time model download.
        local_only = os.getenv("SIGLIP_LOCAL_FILES_ONLY", "true").lower() != "false"
        processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=local_only)
        model = AutoModel.from_pretrained(MODEL_ID, local_files_only=local_only).to(device).eval()
        _runtime = (torch, processor, model, device)
        return _runtime


def runtime_status() -> dict:
    try:
        torch, _, _, device = _load_runtime()
        return {
            "ready": True,
            "model": MODEL_ID,
            "device": device,
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
        }
    except Exception as error:
        return {"ready": False, "model": MODEL_ID, "error": f"{type(error).__name__}: {error}"}


def _cache_path(image_url: str) -> Path:
    return CACHE_DIR / "image_features" / f"{sha256(image_url.encode('utf-8')).hexdigest()}.npy"


def _download_image(image_url: str) -> Image.Image:
    response = requests.get(
        image_url,
        timeout=DOWNLOAD_TIMEOUT,
        headers={"User-Agent": "shopping-assistant-demo/1.0"},
        stream=True,
    )
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError("image exceeds 10 MB")
    return Image.open(BytesIO(content)).convert("RGB")


def image_feature(image_url: str) -> np.ndarray:
    path = _cache_path(image_url)
    if path.exists():
        return np.load(path).astype(np.float32)

    torch, processor, model, device = _load_runtime()
    image = _download_image(image_url)
    inputs = processor(images=[image], return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        feature = model.get_image_features(**inputs)
        feature = feature / feature.norm(dim=-1, keepdim=True)
    result = feature[0].float().cpu().numpy()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, result.astype(np.float16))
    return result


def image_features_batch(image_urls: list[str], workers: int = 8) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Encode a batch in one GPU pass and reuse durable float16 cache files."""
    features: dict[str, np.ndarray] = {}
    errors: dict[str, str] = {}
    missing: list[str] = []
    for url in dict.fromkeys(image_urls):
        path = _cache_path(url)
        if path.exists():
            try:
                features[url] = np.load(path).astype(np.float32)
            except Exception:
                missing.append(url)
        else:
            missing.append(url)

    images: dict[str, Image.Image] = {}
    if missing:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_download_image, url): url for url in missing}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    images[url] = future.result()
                except Exception as error:
                    errors[url] = f"{type(error).__name__}: {error}"

    if images:
        torch, processor, model, device = _load_runtime()
        urls = list(images)
        inputs = processor(images=[images[url] for url in urls], return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            batch = model.get_image_features(**inputs)
            batch = batch / batch.norm(dim=-1, keepdim=True)
        for url, vector in zip(urls, batch.float().cpu().numpy(), strict=True):
            path = _cache_path(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, vector.astype(np.float16))
            features[url] = vector
    return features, errors


@lru_cache(maxsize=32)
def _cached_text_features(labels: tuple[str, ...]) -> np.ndarray:
    torch, processor, model, device = _load_runtime()
    inputs = processor(text=list(labels), padding="max_length", return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        features = model.get_text_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.float().cpu().numpy()


def text_features(labels: list[str]) -> np.ndarray:
    return _cached_text_features(tuple(labels)).copy()


def embed_visual_query(text: str) -> list[float]:
    """Embed text into SigLIP's shared image/text space."""
    return text_features([text])[0].tolist()


def score_image(image_url: str, labels: list[str]) -> dict[str, float]:
    image = image_feature(image_url)
    texts = text_features(labels)
    similarities = texts @ image
    return {label: float(score) for label, score in zip(labels, similarities, strict=True)}


def evaluate_candidate(product: dict, requested_kind: str | None, required_color: str | None) -> dict:
    image_url = product.get("image_url")
    if not image_url:
        return {"accepted": False, "reason": "missing_image", "vision_score": -1.0}

    labels: list[str] = []
    kind_rule = KIND_LABELS.get(requested_kind or "")
    if kind_rule:
        labels.extend(kind_rule["positive"])
        labels.extend(kind_rule["negative"])
    color_prompt = COLOR_LABELS.get(required_color or "")
    if required_color and not color_prompt:
        color_prompt = f"a product whose main visible color is {required_color.lower()}"
    color_prompts = list(dict.fromkeys(COLOR_LABELS.values()))
    if color_prompt and color_prompt not in color_prompts:
        color_prompts.append(color_prompt)
    if color_prompt:
        labels.extend(color_prompts)
    labels = list(dict.fromkeys(labels))
    if not labels:
        return {"accepted": True, "reason": "no_visual_constraint", "vision_score": 0.0}

    scores = score_image(image_url, labels)
    kind_margin = 0.0
    color_margin = 0.0
    accepted = True
    reasons = []

    if kind_rule:
        positive = max(scores[label] for label in kind_rule["positive"])
        negative = max(scores[label] for label in kind_rule["negative"])
        kind_margin = positive - negative
        if kind_margin <= 0:
            accepted = False
            reasons.append("wrong_product_kind")

    if color_prompt:
        requested_score = scores[color_prompt]
        competing = max(score for label, score in scores.items() if label in set(color_prompts) and label != color_prompt)
        color_margin = requested_score - competing
        if color_margin < COLOR_MARGIN_MIN:
            accepted = False
            reasons.append("wrong_visible_color")

    return {
        "accepted": accepted,
        "reason": ",".join(reasons) if reasons else "matched",
        "kind_margin": round(kind_margin, 4),
        "color_margin": round(color_margin, 4),
        "vision_score": round(kind_margin + color_margin, 4),
        "scores": {label: round(score, 4) for label, score in scores.items()},
    }


def rerank_candidates(
    products: list[dict],
    *,
    requested_kind: str | None = None,
    required_color: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return accepted products and an audit trail; never invent products."""
    accepted = []
    audit = []
    for product in products:
        try:
            evaluation = evaluate_candidate(product, requested_kind, required_color)
        except Exception as error:
            evaluation = {
                "accepted": False,
                "reason": f"vision_error:{type(error).__name__}",
                "vision_score": -1.0,
            }
        audit.append({"product_id": product.get("product_id"), "title": product.get("title"), **evaluation})
        if evaluation["accepted"]:
            accepted.append({**product, "vision_score": evaluation["vision_score"]})
    accepted.sort(key=lambda product: product.get("vision_score", 0), reverse=True)
    return accepted, audit
