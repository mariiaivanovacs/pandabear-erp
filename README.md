# PandaBear

A sovereign AI operations layer for your business systems. Your team asks questions
and requests actions in plain language, from chat; PandaBear answers from your real
data and executes real actions — gated by the same role-based permissions your
organization already trusts, fully audited, with credentials no model ever sees.

## Why PandaBear

- **Your data stays yours.** The model that talks to your team runs locally by
  default. It never holds a database credential, an API key, or a service-account
  file — those are injected directly into an isolated tool process at execution
  time and nowhere else.
- **Permissions are enforced by code, not prompts.** Every request is checked
  against a deterministic, fail-closed policy engine before anything runs. A model
  cannot talk its way around a rule the way it can talk its way around a system
  prompt — because it never gets the chance to try.
- **New integrations don't require an engineer.** Describe a data source in plain
  language; PandaBear works out what credentials it needs, connects, discovers the
  structure, and writes and tests the integration itself — all before a human
  reviews and approves anything that goes live.
- **Nothing runs unreviewed.** AI-generated tools pass a static security check
  before they're even sandboxed, and stay inert until a human clicks approve.
- **Institutional knowledge updates itself.** Every code change your team ships is
  distilled into plain-language notes automatically, so your AI coding tools and
  your team both stay current without anyone writing a changelog by hand.

## How it works

```
Your team's message (chat)
        |
        v
  understand      <- model-driven intent recognition and action selection
        |
        v
  authorize        <- deterministic policy engine: allow / deny / needs approval
        |
        v
  execute           <- isolated process, credential injected directly, never
        |              visible to any model or logged anywhere in the clear
        v
  respond            <- answer formatted from real results; only escalates to a
                         larger model when genuinely needed, with values masked
                         first and restored after
```

Every step is recorded in an audit trail, including an explicit record of whether a
credential was ever exposed to a model — enforced, not just claimed.

## What's included

- **Roles and permissions** that live as editable data, not code — granting or
  revoking access to a capability is a configuration change, not a deployment.
- **A credential vault** that is the only path any tool ever gets a real secret
  through, scoped per tool and encrypted at rest.
- **AI-assisted integration building**: point PandaBear at a new system, describe
  what your team needs to do with it, and it plans, builds, and verifies the
  integration — with a static safety gate on every line of generated code and a
  sandboxed live test before anything is ever activated.
- **Guided onboarding for new data sources**, run in an isolated planning session
  that only ever sees field names and types from your systems, never real values.
- **An admin console** for reviewing generated integrations, editing permissions,
  and watching a full activity trail in real time.
- **Chat-native access**, with support for per-conversation role switching.
- **Automatic engineering memory**: every push to your codebase is summarized and
  folded into a living `AGENTS.md`, the plain-markdown convention already read by
  Claude Code, Cursor, Copilot, Codex, and other AI coding tools — no extra
  integration required.

## Getting started

```bash
uv sync
cp .env.example .env   # fill in your model, database, and chat credentials
uv run python scripts/seed_credentials.py   # moves them into the encrypted vault
uv run uvicorn pandabear.api:app --port 8080
uv run python -m pandabear.telegram_bot     # optional chat interface
```

Admin console: `http://localhost:8080/admin`

## Tests

```bash
uv run pytest tests/ -q
```

## Keeping AGENTS.md current

Register a GitHub webhook (`push` event) on your repository pointing at
`/webhooks/github/push`, with a secret matching `vault://github/webhook_secret`.
Every push is summarized locally — no code or diff ever leaves the machine, no
GitHub API token required — and folded into `AGENTS.md` automatically.
