from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PolicyConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PolicyConfig:
    path: Path
    verify_strict_allow: tuple[str, ...]


def _strip_scalar_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_policy_config(repo_root: Path) -> PolicyConfig:
    """Load AXIOM's deliberately small .axiom/policy.yaml subset.

    Supported shape:

    verify:
      strict_allow:
        - command string
    """
    path = repo_root / ".axiom" / "policy.yaml"
    if not path.exists():
        return PolicyConfig(path=path, verify_strict_allow=())

    strict_allow: list[str] = []
    section: tuple[str, ...] = ()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[: len(raw_line) - len(raw_line.lstrip(" "))].count("\t"):
            raise PolicyConfigError(f"{path}:{line_number}: tabs are not supported")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if stripped.endswith(":"):
            key = stripped[:-1].strip()
            if indent == 0 and key == "verify":
                section = ("verify",)
                continue
            if indent == 2 and section == ("verify",) and key == "strict_allow":
                section = ("verify", "strict_allow")
                continue
            raise PolicyConfigError(f"{path}:{line_number}: unsupported policy key {key!r}")

        if stripped.startswith("- "):
            if section != ("verify", "strict_allow"):
                raise PolicyConfigError(f"{path}:{line_number}: list item must be under verify.strict_allow")
            if indent != 4:
                raise PolicyConfigError(f"{path}:{line_number}: verify.strict_allow items must use four-space indentation")
            value = _strip_scalar_quotes(stripped[2:].strip())
            if not value:
                raise PolicyConfigError(f"{path}:{line_number}: empty verify.strict_allow command")
            strict_allow.append(value)
            continue

        raise PolicyConfigError(f"{path}:{line_number}: unsupported policy syntax")

    return PolicyConfig(path=path, verify_strict_allow=tuple(strict_allow))
