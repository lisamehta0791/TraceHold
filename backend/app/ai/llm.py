"""Groq chat client with fixed settings, rate-limit handling and a full call log in Exasol."""
from __future__ import annotations

import itertools
import json
import os
import threading
import time

import httpx

from app import db

API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.0
SEED = 2026

_ids = itertools.count()
_log_lock = threading.Lock()


class AIUnavailable(RuntimeError):
    """AI is switched off or not configured; callers fall back to the non-AI path."""


def status() -> dict:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    switched_off = os.environ.get("TRACEHOLD_AI", "").lower() in ("off", "0", "false", "no")
    enabled = bool(key) and not switched_off
    reason = None if enabled else ("switched off (TRACEHOLD_AI=off)" if switched_off else "no GROQ_API_KEY in .env")
    return {"enabled": enabled, "provider": "Groq", "model": model(), "reason": reason,
            "temperature": TEMPERATURE, "seed": SEED}


def model() -> str:
    return os.environ.get("TRACEHOLD_AI_MODEL", DEFAULT_MODEL)


def new_id() -> int:
    return int(time.time() * 1000) * 1000 + next(_ids) % 1000


def _log(feature, mdl, prompt_version, input_ref, input_text, output_text, ms, state):
    try:
        with _log_lock:
            c = db.connect()
            try:
                c.execute(f"""INSERT INTO {db.AUDIT_SCHEMA}.AI_LOG VALUES ({{i}}, {{f}}, {{m}}, {{p}}, {{r}}, {{it}}, {{ot}},
                              {{t}}, {{ms}}, {{s}}, CURRENT_TIMESTAMP)""",
                          {"i": new_id(), "f": feature, "m": mdl, "p": prompt_version, "r": (input_ref or "")[:200],
                           "it": input_text[:200000], "ot": (output_text or "")[:200000], "t": TEMPERATURE,
                           "ms": round(ms, 1), "s": state})
                c.commit()
            finally:
                c.close()
    except Exception:  # logging must never break the feature; the response still carries everything
        pass


def chat_json(feature: str, prompt_version: str, messages: list[dict], input_ref: str = "",
              max_tokens: int = 2000, model_name: str | None = None) -> dict:
    """One chat completion that must return a JSON object. Retries on rate limits."""
    st = status()
    if not st["enabled"]:
        raise AIUnavailable(f"AI is off: {st['reason']}")
    mdl = model_name or model()
    body = {"model": mdl, "temperature": TEMPERATURE, "seed": SEED, "max_tokens": max(max_tokens, 1500),
            "response_format": {"type": "json_object"}, "messages": messages}
    if mdl.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # keep the token budget for the answer itself
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"}
    input_text = json.dumps(messages, ensure_ascii=False)
    t0 = time.perf_counter()
    last_err = ""
    for attempt in range(6):
        try:
            r = httpx.post(API_URL, json=body, headers=headers, timeout=90)
        except httpx.HTTPError as e:
            last_err = f"network: {e}"
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", "0") or 0) or 4 + attempt * 4
            last_err = "rate limited"
            time.sleep(min(wait, 30))
            continue
        if r.status_code == 400 and "json_validate_failed" in r.text and attempt < 2:
            # the model ran out of room or produced broken JSON: try again with more room
            body["max_tokens"] = min(body["max_tokens"] * 2, 8000)
            last_err = "model did not return valid JSON"
            continue
        if r.status_code >= 400:
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            break
        content = r.json()["choices"][0]["message"]["content"] or "{}"
        ms = (time.perf_counter() - t0) * 1000
        _log(feature, mdl, prompt_version, input_ref, input_text, content, ms, "OK")
        try:
            return {"data": json.loads(content), "model": mdl, "ms": round(ms), "raw": content}
        except json.JSONDecodeError:
            last_err = "model did not return valid JSON"
            break
    ms = (time.perf_counter() - t0) * 1000
    _log(feature, mdl, prompt_version, input_ref, input_text, last_err, ms,
         "RATE_LIMITED" if last_err == "rate limited" else "ERROR")
    raise RuntimeError(f"The AI service failed: {last_err}")
