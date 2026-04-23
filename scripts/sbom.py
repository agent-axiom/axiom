from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from .release_manifest import sha256_for
except ImportError:  # pragma: no cover - exercised by direct script smoke tests
    from release_manifest import sha256_for


def build_sbom(*, package_name: str, version: str, files: list[Path]) -> dict[str, object]:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    package_spdx_id = "SPDXRef-Package-AXIOM"
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{package_name}-release-artifacts",
        "documentNamespace": f"urn:uuid:{uuid4()}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: axiom sbom.py"],
        },
        "packages": [
            {
                "name": package_name,
                "SPDXID": package_spdx_id,
                "downloadLocation": "NOASSERTION",
                "versionInfo": version,
                "filesAnalyzed": True,
            }
        ],
        "files": [],
        "relationships": [],
    }

    for index, path in enumerate(sorted(files, key=lambda candidate: candidate.name), start=1):
        file_spdx_id = f"SPDXRef-File-{index}"
        document["files"].append(
            {
                "fileName": path.name,
                "SPDXID": file_spdx_id,
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": sha256_for(path),
                    }
                ],
            }
        )
        document["relationships"].append(
            {
                "spdxElementId": package_spdx_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_spdx_id,
            }
        )

    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SPDX SBOM for release artifacts")
    parser.add_argument("--package-name", default="axiom-workflow")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("paths", nargs="+", help="Files to include")
    args = parser.parse_args(argv)
    payload = build_sbom(
        package_name=args.package_name,
        version=args.version,
        files=[Path(value) for value in args.paths],
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
