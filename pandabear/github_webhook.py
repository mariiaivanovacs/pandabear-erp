"""GitHub push webhook -> AGENTS.md + org memory, auto-updating on every push.

AGENTS.md is a plain-markdown convention several AI coding tools already read
(Claude Code, Cursor, Copilot, Codex, and others) — no per-tool integration is
needed, only ONE file has to stay current. This module keeps it current
automatically: on every push, the local model reads the actual diff — from a
local clone, via plain `git diff`, never GitHub's API — and distills it into a
short note, which lands in two places:

  1. A clearly-delimited auto-generated section of AGENTS.md. Any AI tool
     that reads this repo picks it up on its next read — no restart, no
     re-index, no vendor lock-in, because it's just a file.
  2. The same organizational memory the chat bot already searches, so a
     plain-language question ("what changed in onboarding recently?") is
     answered from it too.

Signature verification matches GitHub's own scheme (HMAC-SHA256 over the raw
body, secret from the vault, constant-time compare) — the same trust model as
every other credential here: not in code, not in a model's context, checked
once at the boundary.
"""

import hashlib
import hmac
import json
import logging
import re
import subprocess
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from . import audit, memory, models, vault
from .config import settings

log = logging.getLogger("github_webhook")
router = APIRouter(prefix="/webhooks/github")

_AUTO_START = "<!-- pandabear:auto-changelog:start -->"
_AUTO_END = "<!-- pandabear:auto-changelog:end -->"
_MAX_ENTRIES = 20
_MAX_DIFF_CHARS = 6000
_ZERO_SHA = "0" * 40

DISTILL_SYSTEM = """You maintain a software project's institutional memory. You'll be shown a
git commit range: messages and a unified diff. Write a SHORT knowledge note (3-6 markdown
bullet points) capturing what changed and why it matters to someone who wasn't there — new or
changed behavior, config/schema changes, security-relevant changes, anything a teammate or an
AI assistant reading this repo later would want to know. Do not restate the diff line by line.
No preamble, no closing remarks — bullet points only."""


def _webhook_secret() -> str | None:
    return vault._load_store().get("vault://github/webhook_secret")


def _verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/push")
async def github_push(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    raw = await request.body()
    secret = _webhook_secret()
    if secret and not _verify_signature(raw, x_hub_signature_256, secret):
        raise HTTPException(401, "invalid signature")

    if x_github_event == "ping":
        return {"pong": True}
    if x_github_event != "push":
        return {"ignored": x_github_event}

    payload = json.loads(raw)
    if payload.get("deleted"):
        return {"ignored": "branch deletion"}

    # Ack GitHub immediately; distillation (a local-model call) runs after the
    # response goes out so the delivery never risks a webhook timeout.
    background_tasks.add_task(_process_push, payload)
    return {"accepted": True}


def _process_push(payload: dict) -> None:
    request_id = f"gh_{uuid.uuid4().hex[:10]}"
    repo = payload.get("repository", {}).get("full_name", "unknown/unknown")
    branch = (payload.get("ref") or "").removeprefix("refs/heads/")
    before, after = payload.get("before"), payload.get("after")
    pusher = (payload.get("pusher") or {}).get("name", "unknown")
    commits = payload.get("commits", [])

    try:
        commit_summary, diff_text = _collect_diff(before, after, commits)
        if not diff_text.strip():
            audit.log(request_id, "github_webhook", status="ok",
                      detail={"repo": repo, "branch": branch, "note": "empty diff, skipped"})
            return

        note = _distill(commit_summary, diff_text)
        _append_to_agents_md(branch, after or "", pusher, note)
        memory.add_note(
            f"[{repo}@{branch} {(after or '')[:7]}] {note}",
            source=f"github:{repo}", author=pusher,
        )
        audit.log(request_id, "github_webhook", status="ok",
                  detail={"repo": repo, "branch": branch, "commit": (after or "")[:7],
                          "pusher": pusher, "note_preview": note[:300]})
        log.info("AGENTS.md updated for %s@%s (%s)", repo, branch, (after or "")[:7])
    except Exception as e:
        log.exception("github push processing failed")
        audit.log(request_id, "github_webhook", status="error",
                  detail={"repo": repo, "error": str(e)[:500]})


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(settings.repo_path), *args],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout


def _collect_diff(before: str | None, after: str | None, commits: list[dict]) -> tuple[str, str]:
    _run_git("fetch", "origin")  # bring the local clone up to date before diffing
    messages = "\n".join(
        f"- {(c.get('message') or '').splitlines()[0]}" for c in commits
    ) or "(no commit messages)"

    if not before or before == _ZERO_SHA:
        # first push on this branch — no prior base to diff against
        diff = _run_git("show", after, "--stat", "--no-color") if after else ""
        return messages, diff[:_MAX_DIFF_CHARS]

    diff = _run_git("diff", f"{before}..{after}", "--no-color")
    return messages, diff[:_MAX_DIFF_CHARS]


def _distill(commit_summary: str, diff_text: str) -> str:
    msg, _, _ = models.chat(
        [{"role": "system", "content": DISTILL_SYSTEM},
         {"role": "user", "content": f"Commits:\n{commit_summary}\n\nDiff:\n{diff_text}"}],
    )
    return (msg.content or "").strip() or "(no summary produced)"


def _seed_agents_md() -> str:
    return (
        "# AGENTS.md\n\n"
        "Instructions and institutional context for AI coding assistants working in this "
        "repo (Claude Code, Cursor, Copilot, Codex, and others that read this file).\n\n"
        "## Recent changes (auto-updated by PandaBear on every push)\n\n"
        f"{_AUTO_START}\n{_AUTO_END}\n"
    )


def _append_to_agents_md(branch: str, sha: str, pusher: str, note: str) -> None:
    path = settings.agents_md_path
    text = path.read_text() if path.exists() else _seed_agents_md()
    if _AUTO_START not in text or _AUTO_END not in text:
        text = (text.rstrip() +
                f"\n\n## Recent changes (auto-updated by PandaBear on every push)\n\n"
                f"{_AUTO_START}\n{_AUTO_END}\n")

    pre, rest = text.split(_AUTO_START, 1)
    inner, post = rest.split(_AUTO_END, 1)

    entry = f"### {time.strftime('%Y-%m-%d %H:%M UTC')} · {pusher} · `{sha[:7]}` on `{branch}`\n{note.strip()}"
    existing_blocks = [b.strip() for b in re.split(r"\n(?=### )", inner.strip()) if b.strip()]
    blocks = ([entry] + existing_blocks)[:_MAX_ENTRIES]

    new_inner = "\n\n" + "\n\n".join(blocks) + "\n\n"
    path.write_text(pre + _AUTO_START + new_inner + _AUTO_END + post)
