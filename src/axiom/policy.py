from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str


_SHELL_CONTROL_TOKENS = {";", "&&", "||", "|", ">", ">>", "<", "`"}
_PACKAGE_MANAGERS = {"pip", "pip3", "npm", "pnpm", "yarn", "uv", "poetry", "cargo", "go"}


def evaluate_command(command: str) -> PolicyDecision:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return PolicyDecision("deny", f"could not parse command: {exc}")

    if not argv:
        return PolicyDecision("deny", "empty command")

    if any(arg in _SHELL_CONTROL_TOKENS for arg in argv):
        return PolicyDecision("deny", "shell control operators are not allowed in verification commands")

    executable = argv[0]
    command_name = executable.rsplit("/", 1)[-1]

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
            return PolicyDecision("escalate", f"git {subcommand} requires explicit human approval")

    if command_name in _PACKAGE_MANAGERS:
        install_words = {"install", "add", "remove", "uninstall", "sync", "lock", "update", "upgrade"}
        if any(word in argv[1:] for word in install_words):
            return PolicyDecision("escalate", "dependency changes require explicit human approval")

    return PolicyDecision("allow", "command allowed by verification policy")
