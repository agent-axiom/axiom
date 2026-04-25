from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release_manifest import build_manifest
from scripts.sbom import build_sbom
from scripts.installed_wheel_smoke import adapter_command, assert_artifact_outcome, python_inline_command, resolve_tool_path
from scripts.sync_schemas import check_schemas
from scripts.write_build_metadata import render_build_module


class ReleaseScriptTest(unittest.TestCase):
    def test_build_manifest_outputs_sha256_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "alpha.txt"
            second = root / "beta.txt"
            first.write_text("alpha", encoding="utf-8")
            second.write_text("beta", encoding="utf-8")

            manifest = build_manifest([second, first])

        lines = manifest.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("  alpha.txt"))
        self.assertTrue(lines[1].endswith("  beta.txt"))
        self.assertEqual(len(lines[0].split("  ", 1)[0]), 64)

    def test_build_sbom_emits_spdx_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "axiom-0.1.0.tar.gz"
            artifact.write_text("artifact", encoding="utf-8")

            sbom = build_sbom(
                package_name="axiom-workflow",
                version="0.1.0",
                files=[artifact],
            )

        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["name"], "axiom-workflow-release-artifacts")
        self.assertEqual(sbom["packages"][0]["versionInfo"], "0.1.0")
        self.assertEqual(sbom["files"][0]["fileName"], "axiom-0.1.0.tar.gz")
        checksum = sbom["files"][0]["checksums"][0]["checksumValue"]
        self.assertEqual(len(checksum), 64)
        json.dumps(sbom)

    def test_render_build_module_embeds_release_values(self) -> None:
        rendered = render_build_module(
            version="0.2.0",
            git_commit="abc1234",
            git_tag="v0.2.0",
            build_timestamp="2026-04-23T12:00:00Z",
            source_repo="https://github.com/agent-axiom/axiom",
        )

        self.assertIn('VERSION = "0.2.0"', rendered)
        self.assertIn('GIT_COMMIT = "abc1234"', rendered)
        self.assertIn('GIT_TAG = "v0.2.0"', rendered)

    def test_sbom_script_runs_as_top_level_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "axiom-0.1.0.tar.gz"
            artifact.write_text("artifact", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/sbom.py",
                    "--package-name",
                    "axiom-workflow",
                    "--version",
                    "0.1.0",
                    str(artifact),
                ],
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["packages"][0]["name"], "axiom-workflow")

    def test_installed_smoke_resolves_relative_tool_paths_from_invocation_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                resolve_tool_path(".venv/bin/python", cwd=root),
                str((root / ".venv/bin/python").resolve()),
            )

        self.assertEqual(resolve_tool_path("axiom", cwd=Path("/tmp")), "axiom")

    def test_installed_smoke_quotes_adapter_command_paths(self) -> None:
        command = adapter_command("/tmp/python bin/python", Path("/tmp/adapter dir/plan.py"))

        self.assertEqual(command, "'/tmp/python bin/python' '/tmp/adapter dir/plan.py'")

    def test_installed_smoke_quotes_verify_python_command(self) -> None:
        command = python_inline_command("/tmp/python bin/python", "print('ok')")

        self.assertEqual(command, "'/tmp/python bin/python' -c 'print('\"'\"'ok'\"'\"')'")

    def test_installed_smoke_asserts_artifact_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "verify.json"
            artifact.write_text(json.dumps({"outcome": "failed"}), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "expected outcome=passed"):
                assert_artifact_outcome(str(artifact), field="outcome", expected="passed")

    def test_check_schemas_reports_runtime_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "schemas"
            packaged = root / "src" / "axiom" / "schemas"
            source.mkdir(parents=True)
            packaged.mkdir(parents=True)
            (source / "plan.schema.json").write_text('{"type":"object"}\n', encoding="utf-8")
            (packaged / "plan.schema.json").write_text('{"type":"array"}\n', encoding="utf-8")

            issues = check_schemas(source, packaged)

        self.assertEqual(issues, ["schema drift: plan.schema.json"])
