# AXIOM Release Transparency Design

## Goal

Add a source-first release transparency layer for AXIOM based on GitHub Releases and GitHub Actions, so users can inspect version/build metadata locally and verify release assets in closed environments without trusting opaque binaries.

## Scope

In scope:
- `axiom version` and `axiom version --verbose`
- embedded build metadata available outside a git checkout
- release manifest generation with `SHA256SUMS`
- SBOM generation for release artifacts
- GitHub Actions workflows for test and tagged release publication
- GitHub artifact attestations in the release workflow
- README and release verification documentation

Out of scope:
- native compiled binaries
- macOS notarization or Apple code signing
- full reproducible-build guarantees
- external signing infrastructure beyond GitHub Actions/GitHub Releases

## Decisions

### Delivery model

Keep AXIOM source-first. The canonical release outputs for this slice are:
- source distribution
- Python wheel
- release metadata files

This avoids introducing native packaging complexity before the trust and provenance story is clear.

### Local transparency

AXIOM should always be able to report its identity locally, even outside a git checkout. To support that, the package will ship a build metadata module with:
- package version
- git commit
- git tag
- build timestamp
- source repository URL

Local development builds will use safe fallback values such as `unknown` and `development`.

### Release artifacts

Each release should publish:
- `SHA256SUMS`
- `SBOM.spdx.json`
- wheel
- sdist

This is the minimum practical set that gives users integrity checks plus a machine-readable bill of materials without adding third-party signing dependencies to the repo.

### GitHub Actions as trust root

GitHub Actions and GitHub Releases are the release control plane for this slice. The release workflow should:
- trigger on version tags
- build artifacts in CI
- generate checksums and SBOM
- upload assets to the GitHub Release
- emit GitHub artifact attestations

### Verification docs

The repo should document:
- how to inspect local version/build metadata
- how to compare hashes
- how to use GitHub release verification commands
- what AXIOM does and does not prove today

## File Structure

- `src/axiom/version.py`: build metadata model and rendering helpers
- `src/axiom/_build.py`: generated-or-default embedded build metadata
- `scripts/release_manifest.py`: checksum manifest generator
- `scripts/sbom.py`: SBOM generator for release artifacts
- `.github/workflows/test.yml`: test workflow
- `.github/workflows/release.yml`: tagged release workflow
- `tests/unit/test_version.py`: version command tests
- `tests/unit/test_release_scripts.py`: manifest and SBOM tests
- `RELEASE.md`: release verification and publication documentation
- `README.md`: user-facing transparency and verification guidance

## Verification Strategy

Verification for this slice should cover:
- unit tests for verbose version output and metadata fallback behavior
- unit tests for release manifest generation
- unit tests for SBOM generation
- full test suite via `make test`
- local smoke test for `bin/axiom version --verbose`

## Risks

- build metadata drift between local source and CI release artifacts: mitigate by embedding metadata during release builds and documenting local fallback values
- weak SBOM quality from a stdlib-only implementation: mitigate by clearly scoping the SBOM to release artifacts and package metadata
- workflow complexity creep: mitigate by keeping releases limited to sdist, wheel, checksums, SBOM, and attestations

## Success Criteria

This slice is successful when:
1. `axiom version --verbose` prints stable build metadata locally.
2. A tagged GitHub Actions release produces wheel, sdist, `SHA256SUMS`, and `SBOM.spdx.json`.
3. The repo documents how a user in closed infrastructure verifies a release.
4. The implementation is covered by tests and does not require native binary packaging.
