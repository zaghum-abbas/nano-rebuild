#!/usr/bin/env python3
"""Automatic prompt/response capture for 8x assignment agent logs.

Fires via Cursor hooks:
  - beforeSubmitPrompt  -> PROMPT entry
  - afterAgentResponse  -> RESPONSE entry (final assistant text only)

Writes to .agent-logs/YYYY-MM-DD_HH-MM-SS_<session-id>.md
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

AUTHOR = os.environ.get("AGENT_LOG_AUTHOR", "zaghum-abbas")
TOOL = "cursor"
PROJECT = "naano-rebuild"
DEFAULT_MODEL = "composer"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_ts(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def project_root() -> Path:
    env = os.environ.get("CURSOR_PROJECT_DIR")
    if env:
        return Path(env)
    # Script lives at <root>/.cursor/hooks/capture-agent-log.py
    return Path(__file__).resolve().parents[2]


def short_id(conversation_id: str) -> str:
    return (conversation_id or "unknown")[:8]


def safe_session_token(conversation_id: str) -> str:
    token = conversation_id or "unknown"
    return re.sub(r"[^A-Za-z0-9_-]", "-", token)[:36]


def model_name(payload: dict) -> str:
    return payload.get("model_id") or payload.get("model") or DEFAULT_MODEL


def read_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def ensure_dirs(root: Path) -> tuple[Path, Path]:
    logs = root / ".agent-logs"
    state = root / ".cursor" / "hooks" / "state"
    logs.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    return logs, state


def state_path(state_dir: Path, conversation_id: str) -> Path:
    return state_dir / f"{safe_session_token(conversation_id)}.json"


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def yaml_frontmatter(meta: dict) -> str:
    return (
        "---\n"
        f"session_id: {meta['session_id']}\n"
        f"date: {meta['date']}\n"
        f"author: {meta['author']}\n"
        f"model: {meta['model']}\n"
        f"tool: {meta['tool']}\n"
        f"project: {meta['project']}\n"
        f"total_exchanges: {meta['total_exchanges']}\n"
        f"first_prompt_time: {meta['first_prompt_time']}\n"
        f"last_prompt_time: {meta['last_prompt_time']}\n"
        "---\n"
    )


def intro_block(meta: dict) -> str:
    return (
        f"\n# Session Log - {meta['date']}\n\n"
        f"Session: `{short_id(meta['session_id'])}` | "
        f"Project: `{meta['project']}` | "
        f"Author: `{meta['author']}`\n\n"
        "---\n\n"
    )


def header_block(meta: dict) -> str:
    return yaml_frontmatter(meta) + intro_block(meta)


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :]


def rewrite_with_meta(text: str, meta: dict) -> str:
    _, body = split_frontmatter(text)
    if not body.lstrip().startswith("# Session Log"):
        body = intro_block(meta) + body.lstrip("\n")
    return yaml_frontmatter(meta) + body


def append_entry(log_file: Path, meta: dict, entry: str) -> None:
    if log_file.exists():
        current = log_file.read_text(encoding="utf-8")
        updated = rewrite_with_meta(current, meta) + entry
    else:
        updated = header_block(meta) + entry
    log_file.write_text(updated, encoding="utf-8")


def replace_response_entry(log_file: Path, meta: dict, num: int, entry: str) -> None:
    """Keep only the latest RESPONSE for a turn (final assistant text only)."""
    if not log_file.exists():
        append_entry(log_file, meta, entry)
        return

    current = rewrite_with_meta(log_file.read_text(encoding="utf-8"), meta)
    sid = short_id(meta["session_id"])
    pattern = (
        rf"\[LOG_ENTRY type=RESPONSE num={num} session={re.escape(sid)}\]"
        rf".*?(?=\n\[LOG_ENTRY |\Z)"
    )
    new_text, count = re.subn(
        pattern, entry.rstrip("\n") + "\n\n", current, count=1, flags=re.S
    )
    if count:
        log_file.write_text(new_text, encoding="utf-8")
    else:
        log_file.write_text(current + entry, encoding="utf-8")


def format_entry(
    kind: str, num: int, session_id: str, ts: str, model: str, body: str
) -> str:
    sid = short_id(session_id)
    return (
        f"[LOG_ENTRY type={kind} num={num} session={sid}]\n"
        f"timestamp: {ts}\n"
        f"model: {model}\n\n"
        f"{body.rstrip()}\n\n\n"
    )


def meta_from_state(state: dict) -> dict:
    return {
        "session_id": state["session_id"],
        "date": state["date"],
        "author": state["author"],
        "model": state["model"],
        "tool": state["tool"],
        "project": state["project"],
        "total_exchanges": state["total_exchanges"],
        "first_prompt_time": state["first_prompt_time"],
        "last_prompt_time": state["last_prompt_time"],
    }


def new_session_state(
    conversation_id: str,
    model: str,
    ts: str,
    now: datetime,
    logs_dir: Path,
) -> dict:
    filename = (
        f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_"
        f"{safe_session_token(conversation_id)}.md"
    )
    return {
        "session_id": conversation_id,
        "date": now.strftime("%Y-%m-%d"),
        "author": AUTHOR,
        "model": model,
        "tool": TOOL,
        "project": PROJECT,
        "total_exchanges": 0,
        "first_prompt_time": ts,
        "last_prompt_time": ts,
        "log_file": str(logs_dir / filename),
        "current_num": 0,
        "current_generation_id": None,
    }


def handle_prompt(payload: dict, root: Path) -> dict:
    logs_dir, state_dir = ensure_dirs(root)
    conversation_id = payload.get("conversation_id") or "unknown"
    generation_id = payload.get("generation_id") or ""
    prompt = payload.get("prompt") or ""
    model = model_name(payload)
    now = utc_now()
    ts = iso_ts(now)

    sp = state_path(state_dir, conversation_id)
    state = load_state(sp)
    if not state:
        state = new_session_state(conversation_id, model, ts, now, logs_dir)

    state["total_exchanges"] = int(state.get("total_exchanges", 0)) + 1
    state["current_num"] = state["total_exchanges"]
    state["current_generation_id"] = generation_id
    state["last_prompt_time"] = ts
    state["model"] = model
    if not state.get("first_prompt_time"):
        state["first_prompt_time"] = ts

    entry = format_entry(
        "PROMPT",
        state["current_num"],
        state["session_id"],
        ts,
        model,
        prompt,
    )
    append_entry(Path(state["log_file"]), meta_from_state(state), entry)
    save_state(sp, state)
    return {"continue": True}


def handle_response(payload: dict, root: Path) -> dict:
    logs_dir, state_dir = ensure_dirs(root)
    conversation_id = payload.get("conversation_id") or "unknown"
    text = payload.get("text") or ""
    model = model_name(payload)
    ts = iso_ts()

    sp = state_path(state_dir, conversation_id)
    state = load_state(sp)
    if not state:
        now = utc_now()
        state = new_session_state(conversation_id, model, ts, now, logs_dir)
        state["total_exchanges"] = 1
        state["current_num"] = 1
        state["current_generation_id"] = payload.get("generation_id")

    num = int(state.get("current_num") or state.get("total_exchanges") or 1)
    state["model"] = model

    entry = format_entry(
        "RESPONSE",
        num,
        state["session_id"],
        ts,
        model,
        text,
    )
    replace_response_entry(Path(state["log_file"]), meta_from_state(state), num, entry)
    save_state(sp, state)
    return {}


def main() -> int:
    try:
        payload = read_stdin()
    except json.JSONDecodeError:
        print("{}")
        return 0

    event = payload.get("hook_event_name") or ""
    root = project_root()

    try:
        if event == "beforeSubmitPrompt":
            out = handle_prompt(payload, root)
        elif event == "afterAgentResponse":
            out = handle_response(payload, root)
        else:
            out = {}
    except Exception as exc:  # noqa: BLE001 — fail open
        sys.stderr.write(f"capture-agent-log error: {exc}\n")
        out = {"continue": True} if event == "beforeSubmitPrompt" else {}

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
