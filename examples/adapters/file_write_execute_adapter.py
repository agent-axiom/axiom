from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    workspace = Path(str(request["workspace"]))
    target = workspace / "app.py"
    target.write_text("print('adapter changed')\n", encoding="utf-8")
    json.dump({"summary": "Reference execute adapter updated app.py."}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
