"""OpenAI-compatible chat/vision client (OpenRouter) with rate-limit-aware retries."""
from __future__ import annotations

import base64
import json
import logging
import re
import time

import certifi
import httpx

from .config import Config

log = logging.getLogger("llm")

_SHARED_CLIENT: httpx.Client | None = None


def shared_client(timeout: float) -> httpx.Client:
    """One process-wide HTTP client; certifi bundle avoids slow Windows cert-store scans."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = httpx.Client(verify=certifi.where(), timeout=timeout)
    return _SHARED_CLIENT


class LLMAuthError(RuntimeError):
    pass


class LLMPermanentError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        key = cfg.openrouter_key
        if not key or key.startswith("PASTE-"):
            raise LLMAuthError(
                "OpenRouter API key missing. Edit D:\\IslamicResourceHub\\.env and set OPENROUTER_API_KEY."
            )
        self.base_url = cfg["llm"]["base_url"].rstrip("/")
        self.model = cfg.model
        # fallback pools (config-driven, with sensible defaults)
        raw_models = cfg["llm"].get("models")
        raw_vision = cfg["llm"].get("vision_models")
        self.models: list[str] = raw_models if isinstance(raw_models, list) and raw_models else [self.model]
        self.vision_models: list[str] = raw_vision if isinstance(raw_vision, list) and raw_vision else self.models
        self.timeout = cfg["llm"]["timeout_seconds"]
        self.backoff_base = cfg["llm"]["backoff_base_seconds"]
        self.backoff_max = cfg["llm"]["backoff_max_seconds"]
        self._client = shared_client(self.timeout)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.cfg["site"]["base_url"],
            "X-Title": "Islamic Resources Hub",
        }

    def _sleep_backoff(self, attempt: int, retry_after: float | None):
        if retry_after:
            delay = min(float(retry_after), self.backoff_max)
        else:
            delay = min(self.backoff_base * (2 ** attempt), self.backoff_max)
        log.warning("API busy (attempt %d) - waiting %.0fs", attempt, delay)
        time.sleep(delay)

    def _is_vision_payload(self, payload: dict) -> bool:
        for m in payload.get("messages", []):
            c = m.get("content")
            if isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    def _post(self, payload: dict, max_attempts: int = 12) -> dict:
        url = f"{self.base_url}/chat/completions"
        is_vision = self._is_vision_payload(payload)
        pool = self.vision_models if is_vision else self.models
        # ensure primary model is first for vision if not already
        if is_vision and self.model not in pool:
            pool = [self.model] + pool

        attempt = 0
        while True:
            attempt += 1
            tried_rate_limited: list[str] = []
            for model in pool:
                p = dict(payload)
                p["model"] = model
                # vision models typically don't need huge reasoning; keep as configured
                # but some free models reject reasoning/max_tokens - handle via retry without them
                for tweak in (0, 1):  # 0=as-is, 1=strip reasoning & cap max_tokens
                    if tweak == 1:
                        p.pop("reasoning", None)
                        if p.get("max_tokens", 0) > 8192:
                            p["max_tokens"] = 8192
                    try:
                        r = self._client.post(url, headers=self._headers(), json=p)
                    except httpx.TimeoutException:
                        log.warning("Timeout on %s, trying next model", model)
                        break  # try next model, outer backoff will handle if all timeout
                    except httpx.HTTPError as e:
                        log.warning("HTTP error on %s: %s", model, e)
                        break

                    if r.status_code == 429:
                        tried_rate_limited.append(model)
                        log.warning("Rate-limited on %s (%d/%d in pool), trying next", model, len(tried_rate_limited), len(pool))
                        # try next model immediately without sleeping
                        break
                    if r.status_code in (401, 403):
                        raise LLMAuthError(f"API rejected credentials ({r.status_code}): {r.text[:300]}")
                    if r.status_code >= 500 or r.status_code == 408:
                        log.warning("Server error %s on %s, trying next model", r.status_code, model)
                        break
                    if r.status_code == 400:
                        detail = r.text[:600].lower()
                        # unsupported param -> tweak and retry same model
                        if tweak == 0 and any(s in detail for s in ("reasoning", "max_tokens", "unknown parameter")):
                            log.warning("Model %s rejected param (%s), retrying without reasoning", model, detail[:120])
                            continue
                        if any(s in detail for s in ("context length", "too large", "invalid image", "image_url", "vision", "does not support image")):
                            # permanent for this model, try next
                            log.warning("Model %s cannot handle request (%s), skipping", model, detail[:120])
                            break
                        # other 400 - treat as permanent skip
                        log.warning("Model %s 400: %s, skipping", model, detail[:120])
                        break
                    try:
                        r.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        log.warning("HTTPStatusError on %s: %s", model, e)
                        break
                    # success
                    if model != self.model:
                        log.info("Fallback succeeded: %s (primary was %s)", model, self.model)
                    return r.json()

            # if we reach here, all models either rate-limited or errored
            if len(tried_rate_limited) == len(pool) and tried_rate_limited:
                # all rate-limited -> respect Retry-After if any, else exponential backoff
                ra = None
                # we already logged each 429; use backoff
                self._sleep_backoff(attempt, ra)
                continue
            if tried_rate_limited:
                # some rate-limited but others errored -> still backoff before full retry
                self._sleep_backoff(attempt, None)
                continue
            # all errored for other reasons -> backoff and retry whole pool
            self._sleep_backoff(attempt, None)

    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 131072) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning": {"max_tokens": 262144, "exclude": True},
        }
        data = self._post(payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMPermanentError(f"Unexpected API response shape: {json.dumps(data)[:400]}") from e

    def vision(self, prompt: str, image_bytes: bytes, mime: str, temperature: float = 0.1) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ]
        return self.chat(messages, temperature=temperature)

    def json_chat(self, system: str, user: str, temperature: float = 0.1) -> list | dict:
        raw = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=131072,
        )
        return parse_json(raw)


def parse_json(raw: str) -> list | dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    attempts = [text]
    # repair common truncation: close dangling objects / array
    last_brace = text.rfind("}")
    if last_brace != -1:
        trimmed = text[: last_brace + 1]
        attempts.append(trimmed)
        attempts.append(trimmed.rstrip().rstrip(",") + "]")
        attempts.append(trimmed.rstrip().rstrip(",") + "\n]")
    for candidate in attempts:
        for opener, closer in (("[", "]"), ("{", "}")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError(f"Model did not return valid JSON:\n{raw[:500]}")
