from __future__ import annotations

import os
import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str


_SHELL_CONTROL_TOKENS = {";", "&&", "||", "|", ">", ">>", "<", "`"}
_PACKAGE_MANAGERS = {"pip", "pip3", "npm", "pnpm", "yarn", "uv", "poetry", "cargo", "go"}
_POLICY_PROFILES = {"standard", "strict", "permissive"}


def _command_name(executable: str) -> str:
    return executable.rsplit("/", 1)[-1]


def _env_allowlist() -> list[str]:
    raw = os.environ.get("AXIOM_POLICY_ALLOWLIST", "")
    return [item for item in raw.split(os.pathsep) if item]


def _is_allowlisted(command: str, command_allowlist: list[str]) -> bool:
    return command in command_allowlist or command in _env_allowlist()


def _is_known_test_runner(argv: list[str]) -> bool:
    if not argv:
        return False
    name = _command_name(argv[0])
    if name == "make" and argv[1:] == ["test"]:
        return True
    if name in {"pytest", "tox"}:
        return True
    if name in {"python", "python3"} and len(argv) >= 3 and argv[1] == "-m":
        return argv[2] in {"unittest", "pytest"}
    if name == "npm" and argv[1:] == ["test"]:
        return True
    if name == "cargo" and argv[1:2] == ["test"]:
        return True
    if name == "go" and argv[1:2] == ["test"]:
        return True
    if name == "uv" and len(argv) >= 3 and argv[1] == "run":
        runner = _command_name(argv[2])
        return runner in {"pytest", "tox"} or (runner in {"python", "python3"} and len(argv) >= 5 and argv[3] == "-m" and argv[4] in {"unittest", "pytest"})
    return False


def evaluate_command(
    command: str,
    *,
    profile: str | None = None,
    command_allowlist: list[str] | None = None,
) -> PolicyDecision:
    profile = profile or os.environ.get("AXIOM_POLICY_PROFILE", "standard")
    if profile not in _POLICY_PROFILES:
        return PolicyDecision("deny", f"unknown policy profile: {profile}")
    command_allowlist = command_allowlist or []
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return PolicyDecision("deny", f"could not parse command: {exc}")

    if not argv:
        return PolicyDecision("deny", "empty command")

    if any(arg in _SHELL_CONTROL_TOKENS for arg in argv):
        return PolicyDecision("deny", "shell control operators are not allowed in verification commands")

    command_name = _command_name(argv[0])

    if command_name in {"sh", "bash", "zsh"} and "-c" in argv[1:]:
        return PolicyDecision("deny", "shell command strings are not allowed")

    if command_name == "sudo":
        return PolicyDecision("deny", "sudo is not allowed")

    if command_name == "rm":
        return PolicyDecision("deny", "deletion commands are not allowed")

    if command_name == "git" and len(argv) >= 2:
        subcommand = argv[1]
        if subcommand == "reset" and "--hard" in argv[2:]:
            return PolicyDecision("deny", "destructive git operation is not allowed")
        if subcommand == "clean":
            return PolicyDecision("deny", "destructive git operation is not allowed")
        if subcommand in {"push", "rebase"}:
            if profile == "permissive":
                return PolicyDecision("allow", f"git {subcommand} allowed by permissive policy")
            return PolicyDecision("escalate", f"git {subcommand} requires explicit human approval")

    if profile == "strict":
        if _is_allowlisted(command, command_allowlist):
            return PolicyDecision("allow", "command allowed by strict policy allowlist")
        if _is_known_test_runner(argv):
            return PolicyDecision("allow", "known test runner allowed by strict policy")
        return PolicyDecision("deny", "strict policy allows only known test runners or explicitly allowlisted commands")

    if command_name in _PACKAGE_MANAGERS:
        install_words = {"install", "add", "remove", "uninstall", "sync", "lock", "update", "upgrade"}
        if any(word in argv[1:] for word in install_words):
            if profile == "permissive":
                return PolicyDecision("allow", "dependency change allowed by permissive policy")
            return PolicyDecision("escalate", "dependency changes require explicit human approval")

    return PolicyDecision("allow", f"command allowed by {profile} verification policy")
