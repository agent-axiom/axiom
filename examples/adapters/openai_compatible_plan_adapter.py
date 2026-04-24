#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


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


def main() -> int:
    request = json.load(sys.stdin)
    base_url = _env("AXIOM_OPENAI_COMPAT_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    model = _env("AXIOM_OPENAI_COMPAT_MODEL", "local-model")
    api_key = _env("AXIOM_OPENAI_COMPAT_API_KEY")
    timeout = float(_env("AXIOM_OPENAI_COMPAT_TIMEOUT", "120"))

    prompt = {
        "task": request["task"],
        "sections": request["sections"],
        "workspace": request["workspace"],
        "instruction": (
            "Return only JSON matching AXIOM schemas/plan.schema.json. "
            "Use concrete write_scope entries from the task repo anchors when possible."
        ),
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an AXIOM planning adapter. Return valid JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, sort_keys=True)},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    http_request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"OpenAI-compatible adapter failed: {exc}", file=sys.stderr)
        return 1

    try:
        content = response_payload["choices"][0]["message"]["content"]
        plan = _extract_json_object(str(content))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"OpenAI-compatible adapter returned invalid plan JSON: {exc}", file=sys.stderr)
        return 1

    json.dump(plan, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
