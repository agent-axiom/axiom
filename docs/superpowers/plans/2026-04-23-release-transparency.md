# AXIOM Release Transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHub Releases and GitHub Actions based release transparency for AXIOM, including local version metadata, release checksums, SBOM generation, and verification docs.

**Architecture:** Keep AXIOM source-first and add a small embedded build metadata module plus deterministic Python scripts for release metadata generation. GitHub Actions will build the wheel and sdist, generate release metadata files, upload them to a GitHub Release, and emit artifact attestations.

**Tech Stack:** Python 3 standard library, `argparse`, `json`, `hashlib`, `pathlib`, `unittest`, GitHub Actions

---

### Task 1: Version metadata and CLI surface

**Files:**
- Create: `src/axiom/_build.py`
- Create: `src/axiom/version.py`
- Modify: `src/axiom/cli.py`
- Modify: `src/axiom/__init__.py`
- Test: `tests/unit/test_version.py`

- [ ] **Step 1: Write the failing version tests**

```python
from axiom.cli import main
from axiom.version import build_metadata


def test_version_verbose_includes_commit_and_source():
    metadata = build_metadata()
    assert "git_commit" in metadata.to_dict()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.unit.test_version -v`
Expected: FAIL with missing module or missing `version` command

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class BuildMetadata:
    version: str
    git_commit: str
    git_tag: str
    build_timestamp: str
    source_repo: str
```

```python
version_parser = subparsers.add_parser("version")
version_parser.add_argument("--verbose", action="store_true")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.unit.test_version -v`
Expected: PASS

### Task 2: Release manifest and SBOM scripts

**Files:**
- Create: `scripts/release_manifest.py`
- Create: `scripts/sbom.py`
- Test: `tests/unit/test_release_scripts.py`

- [ ] **Step 1: Write the failing release-script tests**

```python
from scripts.release_manifest import build_manifest
from scripts.sbom import build_sbom
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.unit.test_release_scripts -v`
Expected: FAIL with missing modules or missing functions

- [ ] **Step 3: Write minimal implementation**

```python
def build_manifest(paths: list[Path]) -> str:
    ...
```

```python
def build_sbom(*, package_name: str, version: str, files: list[Path]) -> dict[str, object]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.unit.test_release_scripts -v`
Expected: PASS

### Task 3: Release workflow files

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/release.yml`
- Modify: `pyproject.toml`
- Modify: `Makefile`

- [ ] **Step 1: Add test workflow**

```yaml
on:
  push:
  pull_request:
```

- [ ] **Step 2: Add release workflow**

```yaml
on:
  push:
    tags:
      - "v*"
```

- [ ] **Step 3: Add build and metadata steps**

```yaml
- run: python -m build
- run: python scripts/release_manifest.py dist/*
- run: python scripts/sbom.py dist/*
```

- [ ] **Step 4: Verify workflow files parse and repo tests still pass**

Run: `python3 -m unittest discover -s tests/unit -v`
Expected: PASS

### Task 4: Documentation and verification guidance

**Files:**
- Create: `RELEASE.md`
- Modify: `README.md`

- [ ] **Step 1: Add release verification guidance**

```markdown
Use `axiom version --verbose` to inspect local build metadata.
Compare local release asset hashes against `SHA256SUMS`.
Use GitHub release verification commands when GitHub CLI is available.
```

- [ ] **Step 2: Add closed-infra verification flow**

```markdown
Mirror the release assets internally, then verify hashes and provenance before promotion.
```

- [ ] **Step 3: Re-read docs for ambiguity and unfinished markers**

Run a grep for unfinished markers in `README.md` and `RELEASE.md`.
Expected: no matches

### Task 5: Final verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-23-release-transparency-design.md`
- Modify: `docs/superpowers/plans/2026-04-23-release-transparency.md`

- [ ] **Step 1: Run the full unit suite**

Run: `make test`
Expected: PASS with 0 failures

- [ ] **Step 2: Run the local version smoke test**

Run: `bin/axiom version --verbose`
Expected: prints version, git commit, git tag, build timestamp, and source repo

- [ ] **Step 3: Run the release metadata scripts against sample files**

Run: `python3 scripts/release_manifest.py README.md pyproject.toml`
Expected: prints deterministic SHA-256 manifest entries

- [ ] **Step 4: Re-run the full unit suite**

Run: `make test`
Expected: PASS with 0 failures
