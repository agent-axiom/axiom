from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .config import layout_for
from .git import plan_workspace
from .models import TaskDocument, TaskMetadata
from .templates import FRONTMATTER_ORDER, REQUIRED_SECTIONS, render_new_task

TASK_ID_PATTERN = re.compile(r"AX-(?P<date>\d{8})-(?P<seq>\d{3})")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "task"


def _parse_scalar(value: str) -> object:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines()
    closing_index = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            closing_index = index
            break
    if closing_index is None:
        return {}, text

    payload: dict[str, object] = {}
    for line in lines[1:closing_index]:
        if not line.strip():
            continue
        key, _, raw_value = line.partition(":")
        payload[key.strip()] = _parse_scalar(raw_value.strip())

    body = "\n".join(lines[closing_index + 1 :]).lstrip("\n")
    return payload, body


def parse_sections(body: str) -> tuple[str, dict[str, str]]:
    title = ""
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in body.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections[current_section].append(line)

    normalized = {key: "\n".join(value).strip() for key, value in sections.items()}
    for required in REQUIRED_SECTIONS:
        normalized.setdefault(required, "")
    return title, normalized


def render_frontmatter(metadata: TaskMetadata) -> str:
    payload = metadata.to_dict()
    lines = ["---"]
    for key in FRONTMATTER_ORDER:
        value = payload.get(key, "")
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def render_task(task: TaskDocument) -> str:
    parts = [render_frontmatter(task.metadata), "", f"# {task.title}", ""]
    seen: set[str] = set()
    for section in REQUIRED_SECTIONS:
        seen.add(section)
        parts.append(f"## {section}")
        content = task.sections.get(section, "").rstrip()
        if content:
            parts.append(content)
        parts.append("")
    for section, content in task.sections.items():
        if section in seen:
            continue
        parts.append(f"## {section}")
        if content.rstrip():
            parts.append(content.rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def write_task(task: TaskDocument, path: Path | None = None) -> Path:
    target = path or task.path
    if target is None:
        raise ValueError("task path is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_task(task), encoding="utf-8")
    task.path = target
    return target


def load_task(path: Path) -> TaskDocument:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    title, sections = parse_sections(body)
    metadata = TaskMetadata.from_dict(frontmatter)
    return TaskDocument(
        metadata=metadata,
        title=title or metadata.title,
        sections=sections,
        path=path,
    )


def _next_task_sequence(repo_root: Path, day_stamp: str) -> int:
    tasks_root = layout_for(repo_root).tasks_root
    if not tasks_root.exists():
        return 1
    highest = 0
    for path in tasks_root.rglob("*.md"):
        match = TASK_ID_PATTERN.search(path.name)
        if not match:
            continue
        if match.group("date") != day_stamp:
            continue
        highest = max(highest, int(match.group("seq")))
    return highest + 1


def create_task(
    *,
    repo_root: Path,
    title: str,
    kind: str,
    now: datetime | None = None,
) -> Path:
    current_time = now or datetime.now(timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    layout = layout_for(repo_root)
    layout.ensure()
    day_stamp = current_time.strftime("%Y%m%d")
    sequence = _next_task_sequence(repo_root, day_stamp)
    task_id = f"AX-{day_stamp}-{sequence:03d}"
    slug = slugify(title)
    workspace = plan_workspace(repo_root, task_id, slug)
    task_dir = layout.tasks_root / current_time.strftime("%Y") / current_time.strftime("%m")
    task_path = task_dir / f"{task_id}-{slug}.md"
    document = render_new_task(
        task_id=task_id,
        title=title,
        kind=kind,
        now_iso=current_time.isoformat(),
        repo_root=repo_root.resolve(),
        base_branch=workspace.base_branch,
        branch=workspace.branch,
        worktree=workspace.worktree,
    )
    if workspace.bootstrap_reason:
        document.sections["Assumptions"] = workspace.bootstrap_reason
    return write_task(document, task_path)


def resolve_task_path(repo_root: Path, identifier: str) -> Path:
    candidate = Path(identifier)
    if candidate.exists():
        return candidate.resolve()

    repo_candidate = repo_root / identifier
    if repo_candidate.exists():
        return repo_candidate.resolve()

    tasks_root = layout_for(repo_root).tasks_root
    if not tasks_root.exists():
        raise FileNotFoundError(f"task not found: {identifier}")

    matches: list[Path] = []
    for path in sorted(tasks_root.rglob("*.md")):
        if path.name == identifier or path.stem == identifier or path.name.startswith(identifier):
            matches.append(path)
            continue
        task = load_task(path)
        if task.metadata.id == identifier:
            matches.append(path)

    if not matches:
        raise FileNotFoundError(f"task not found: {identifier}")
    return matches[0].resolve()


def list_task_paths(repo_root: Path) -> list[Path]:
    tasks_root = layout_for(repo_root).tasks_root
    if not tasks_root.exists():
        return []
    return sorted(tasks_root.rglob("*.md"))


def update_task(
    task_path: Path,
    *,
    status: str | None = None,
    section_updates: dict[str, str] | None = None,
    metadata_updates: dict[str, object] | None = None,
) -> TaskDocument:
    task = load_task(task_path)
    if status is not None:
        task.metadata.status = status
    if metadata_updates:
        for key, value in metadata_updates.items():
            setattr(task.metadata, key, value)
    if section_updates:
        task.sections.update(section_updates)
    task.metadata.updated_at = now_iso()
    write_task(task, task_path)
    return task


def repo_root_for(task_path: Path) -> Path:
    return Path(load_task(task_path).metadata.repo_root).resolve()
