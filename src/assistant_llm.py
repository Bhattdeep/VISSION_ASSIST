"""
assistant_llm.py - Free-tier-friendly assistant integration.

Currently uses the Gemini Developer API over plain HTTP so the project
does not depend on extra SDKs and can work with a Google AI Studio key.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterable, Optional


DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def build_scene_context(detections, distance_cm: Optional[float], depth_ready: bool) -> str:
    parts = []

    if distance_cm is not None:
        parts.append(
            f"Nearest measured obstacle distance: about {distance_cm:.0f} centimeters."
        )
    else:
        parts.append("No hardware distance sensor reading is currently available.")

    if detections:
        desc = []
        for det in list(detections)[:5]:
            name = getattr(det, "class_name", getattr(det, "name", "object"))
            conf = getattr(det, "confidence", getattr(det, "conf", 0.0))
            pos = getattr(det, "h_position", getattr(det, "pos", "unknown"))
            est_cm = getattr(det, "estimated_distance_cm", getattr(det, "distance_cm", None))
            if est_cm is not None:
                desc.append(f"{name} ({conf:.0%}, {pos}, about {est_cm:.0f} cm)")
            else:
                desc.append(f"{name} ({conf:.0%}, {pos})")
        parts.append("Visible objects: " + ", ".join(desc) + ".")
    else:
        parts.append("Visible objects: none confidently detected.")

    parts.append(f"Depth overlay status: {'available' if depth_ready else 'not available'}.")
    return " ".join(parts)


def _history_to_text(history: Optional[Iterable[dict]]) -> str:
    if not history:
        return ""

    lines = []
    for item in list(history)[-10:]:
        role = item.get("role", "user").upper()
        content = item.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("No response candidates returned by Gemini.")

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "").strip() for p in parts if p.get("text")]
    answer = " ".join(texts).strip()
    if not answer:
        raise RuntimeError("Gemini returned an empty response.")
    return answer


def ask_free_llm(
    question: str,
    api_key: Optional[str] = None,
    detections=None,
    distance_cm: Optional[float] = None,
    depth_ready: bool = False,
    history: Optional[Iterable[dict]] = None,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> str:
    provider = (provider or DEFAULT_PROVIDER).strip().lower()
    if provider != "gemini":
        raise ValueError(f"Unsupported provider '{provider}'. Only Gemini is configured.")

    api_key = (api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "Missing Gemini API key. Paste a Google AI Studio key or set GEMINI_API_KEY."
        )

    scene = build_scene_context(detections, distance_cm, depth_ready)
    history_text = _history_to_text(history)

    prompt = (
        "You are a concise safety assistant for a wearable vision aid used by a visually "
        "impaired person. Answer in 1 to 3 plain-text sentences. Prioritize safety and "
        "use the current scene context when relevant.\n\n"
        f"CURRENT SCENE:\n{scene}\n\n"
    )

    if history_text:
        prompt += f"RECENT CONVERSATION:\n{history_text}\n\n"

    prompt += f"USER QUESTION:\n{question}"

    url = GEMINI_URL.format(model=model)
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 220,
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error ({exc.code}): {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini API connection failed: {exc.reason}") from exc

    return _extract_gemini_text(payload)
