# PandaBear

A sovereign AI operations assistant: natural language in, deterministic company
actions out, gated by policy, fully audited, credentials never seen by any model.

## Architecture

```
User message (Telegram, chat endpoint)
        |
        v
  agent node      <- LangGraph, model-driven tool selection via real function-calling
        |            (Qwen3-8B local by default, OpenAI as measured/audited fallback)
        v
  policy_check     <- deterministic Python, fail-closed default-deny.
        |             NOT model-driven on purpose: a policy gate an LLM can talk
        |             its way through defeats the point of having one.
        v
  tool_executor    <- subprocess isolation; a Fernet-encrypted vault injects the
        |             credential into the tool's env only. The model never sees it.
        v
  respond           <- local model formats the answer; escalates to cloud only on
                        explicit self-assessment, with values masked/generalized
                        first and rehydrated locally after
```

Every node writes to an append-only audit log (`data/pandabear.db`), including
whether a credential was ever exposed to a model (it never should be — that's a
tested invariant, not a hope).

## What's in here

- **Capabilities + roles** — SQLite-backed registry (`pandabear/registry.py`,
  `pandabear/policy.py`). Adding a permission is a row edit, not a redeploy.
- **Credential vault** (`pandabear/vault.py`) — the only way any tool gets a
  real credential; scoped per tool, never touched by the agent/model path.
- **AI tool generation** (`pandabear/toolgen.py`) — new deterministic tools are
  drafted by a cloud model, then must pass an AST airgap gate
  (`pandabear/airgap.py`, rejects socket/subprocess/eval/exec/open/etc.),
  a sandbox run, and a human approval click before going live.
- **Source onboarding** (`pandabear/onboarding.py`) — a *separate* model session
  plans which credentials a new source needs, an admin binds the real values
  (the model never sees them), the model probes structure only (field names/
  types, never data), builds and verifies tools, then the whole session is
  wiped.
- **Admin panel** (`pandabear/admin.py`, mounted at `/admin`) — live org
  overview, tool approval with source view, a policy editor, the full audit
  stream, and a chat-driven onboarding wizard.
- **Telegram bot** (`pandabear/telegram_bot.py`) — the primary chat surface for
  demos. Supports `/role branch_manager|barista|ops_manager` so a single
  account can switch personas live (useful for showing permission differences
  without a second phone); the reply footer shows which role answered.
- **GitHub push -> AGENTS.md** (`pandabear/github_webhook.py`) — every push to
  a registered repo is distilled by the local model into a short knowledge
  note, appended to that repo's `AGENTS.md` (a plain-markdown file several AI
  coding tools already read — Claude Code, Cursor, Copilot, Codex — so no
  per-tool integration is needed) and stored in the same organizational memory
  the chat bot searches, so "what changed in onboarding recently?" is
  answerable in plain language.

## Running it

```bash
uv sync
cp .env.example .env   # fill in OPENAI_API_KEY, FIREBASE_*, TELEGRAM_BOT_TOKEN
uv run python scripts/seed_credentials.py   # moves .env secrets into the vault
uv run uvicorn pandabear.api:app --port 8080
uv run python -m pandabear.telegram_bot     # optional, second process
```

Admin panel: `http://localhost:8080/admin`

## Tests

```bash
uv run pytest tests/ -q
```

## Keeping AGENTS.md current

Register a GitHub webhook (`push` event) on this repo pointing at
`/webhooks/github/push`, with a secret matching `vault://github/webhook_secret`.
Every push is distilled locally (no diff or code ever leaves the machine, no
GitHub API token required — the receiver runs `git diff` against its own local
clone) and appended to `AGENTS.md`, so any AI coding tool reading this repo
picks up what changed without anyone maintaining a changelog by hand.
