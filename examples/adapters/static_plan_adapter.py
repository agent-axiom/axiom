from __future__ import annotations

import json
import sys


def main() -> int:
    request = json.load(sys.stdin)
    anchors = []
    for line in request.get("sections", {}).get("Repo Anchors", "").splitlines():
        anchor = line.strip().lstrip("-*").strip().strip("`")
        if anchor:
            anchors.append(anchor)
    if not anchors:
        anchors = ["app.py"]

    json.dump(
        {
            "summary": "Reference adapter plan.",
            "steps": [
                {
                    "id": "step-1",
                    "title": f"Apply the requested change in {anchors[0]}.",
                    "write_scope": anchors,
                    "checks": [],
                }
            ],
            "manual_smoke": [
                {
                    "id": "smoke-1",
                    "instruction": "Run the changed path manually and record observed output.",
                }
            ],
            "stop_conditions": [f"Stop if files outside {', '.join(anchors)} must change."],
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
