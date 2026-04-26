#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float_env(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _extract_json_object(text: str) -> dict[str, object]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("model response must be a JSON object")
    return payload


def _validate_review(payload: dict[str, object]) -> None:
    for key in ("outcome", "summary", "findings", "next_phase"):
        if key not in payload:
            raise ValueError(f"review missing required key: {key}")
    if payload["outcome"] not in {"pass", "changes_requested", "blocked"}:
        raise ValueError("review outcome must be pass, changes_requested, or blocked")


def _extract_review(text: str) -> dict[str, object]:
    payload = _extract_json_object(text)
    _validate_review(payload)
    return payload


def _openai_chat_completion(
    *,
    base_url: str,
    body: dict[str, object],
    headers: dict[str, str],
    timeout: float,
    retries: int,
    retry_delay: float,
) -> dict[str, object]:
    url = f"{base_url}/chat/completions"
    attempts = max(retries, 0) + 1
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        http_request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("response body must be a JSON object")
            return payload
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            errors.append(f"attempt {attempt}/{attempts}: HTTP {exc.code}: {response_body}")
            if 400 <= exc.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"attempt {attempt}/{attempts}: {exc}")
        if attempt < attempts and retry_delay > 0:
            time.sleep(retry_delay)
    raise RuntimeError("; ".join(errors) or "request failed")


def main() -> int:
    request = json.load(sys.stdin)
    base_url = _env("AXIOM_OPENAI_COMPAT_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    model = _env("AXIOM_OPENAI_COMPAT_MODEL", "local-model")
    api_key = _env("AXIOM_OPENAI_COMPAT_API_KEY")
    timeout = _float_env("AXIOM_OPENAI_COMPAT_TIMEOUT", 120.0)
    retries = _int_env("AXIOM_OPENAI_COMPAT_RETRIES", 0)
    retry_delay = _float_env("AXIOM_OPENAI_COMPAT_RETRY_DELAY", 0.25)
    schema_retries = _int_env("AXIOM_OPENAI_COMPAT_SCHEMA_RETRIES", 1)

    prompt = {
        "task": request["task"],
        "sections": request["sections"],
        "workspace": request["workspace"],
        "latest_artifacts": request.get("latest_artifacts", {}),
        "diff": request.get("diff", ""),
        "instruction": (
            "Return only JSON matching AXIOM schemas/review.schema.json. "
            "Use outcome=pass only when the diff satisfies the task, verification evidence is credible, "
            "and no semantic findings remain."
        ),
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an AXIOM semantic review adapter. Return valid JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, sort_keys=True)},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    errors: list[str] = []
    for schema_attempt in range(1, max(schema_retries, 0) + 2):
        try:
            response_payload = _openai_chat_completion(
                base_url=base_url,
                body=body,
                headers=headers,
                timeout=timeout,
                retries=retries,
                retry_delay=retry_delay,
            )
            content = response_payload["choices"][0]["message"]["content"]
            review = _extract_review(str(content))
            json.dump(review, sys.stdout)
            return 0
        except RuntimeError as exc:
            errors.append(f"attempt {schema_attempt}: request failed: {exc}")
            break
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"attempt {schema_attempt}: invalid review JSON: {exc}")
        if schema_attempt <= schema_retries and retry_delay > 0:
            time.sleep(retry_delay)

    print(f"OpenAI-compatible review adapter failed: {'; '.join(errors)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
