-- PandaBear metadata schema (description.md §2A, trimmed to what the demo exercises)

CREATE TABLE IF NOT EXISTS domains (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    aliases     TEXT DEFAULT '[]',          -- JSON array
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capabilities (
    id                   TEXT PRIMARY KEY,
    domain_id            TEXT REFERENCES domains(id),
    intent               TEXT NOT NULL,
    description          TEXT NOT NULL,      -- what the model sees when deciding
    example_utterances   TEXT DEFAULT '[]',  -- JSON array
    required_entities    TEXT DEFAULT '[]',  -- JSON array of arg names
    tool_id              TEXT,
    policy_id            TEXT,
    risk_level           INTEGER CHECK (risk_level BETWEEN 1 AND 5) DEFAULT 1,
    requires_approval    INTEGER DEFAULT 0,
    remote_model_allowed INTEGER DEFAULT 0,
    status               TEXT CHECK (status IN ('active','disabled')) DEFAULT 'active',
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tools (
    id                TEXT PRIMARY KEY,
    type              TEXT CHECK (type IN ('read_connector','action','policy_check','formatter')) NOT NULL,
    entrypoint        TEXT NOT NULL,          -- "tools.firebase.check_stock.run"
    file_path         TEXT NOT NULL,          -- "tools/firebase/check_stock.py"
    input_schema      TEXT NOT NULL,          -- JSON schema (what the model fills in)
    output_schema     TEXT DEFAULT '{}',
    credential_scope  TEXT,                   -- resolved via credential_bindings, never by the model
    timeout_seconds   INTEGER DEFAULT 30,
    generated_by      TEXT,                   -- model name, or 'human'
    human_approved    INTEGER DEFAULT 0,      -- generated tools stay inactive until approved
    status            TEXT CHECK (status IN ('active','disabled','testing')) DEFAULT 'testing',
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS policies (
    id               TEXT PRIMARY KEY,
    action           TEXT NOT NULL,
    rules            TEXT NOT NULL,           -- JSON: [{"role":..., "decision":..., "limit":...}]
    default_decision TEXT CHECK (default_decision IN ('allow','deny','approval_required')) DEFAULT 'deny',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS credential_bindings (
    id               TEXT PRIMARY KEY,
    credential_scope TEXT NOT NULL,
    vault_ref        TEXT NOT NULL,           -- "vault://firebase/admin"
    allowed_tools    TEXT DEFAULT '[]',       -- JSON array of tool ids
    model_visible    INTEGER DEFAULT 0,       -- always 0 in the real product; 1 only for demo pass 1
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_id                  TEXT NOT NULL,
    user_id                     TEXT,
    user_role                   TEXT,
    node                        TEXT NOT NULL,  -- agent | policy_check | tool_executor | response | error
    capability_id               TEXT,
    tool_id                     TEXT,
    policy_decision             TEXT,
    model_used                  TEXT,           -- which model made this hop's decision
    remote_model_used           INTEGER DEFAULT 0,
    credential_exposed_to_model INTEGER DEFAULT 0,
    detail                      TEXT DEFAULT '{}',  -- JSON, sanitized
    latency_ms                  INTEGER,
    status                      TEXT CHECK (status IN ('ok','denied','pending_approval','error')) DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    tool_args     TEXT NOT NULL,               -- JSON
    user_id       TEXT,
    state         TEXT CHECK (state IN ('pending','approved','rejected')) DEFAULT 'pending',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at   TIMESTAMP,
    resolved_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts);
CREATE INDEX IF NOT EXISTS idx_capabilities_status ON capabilities(status);
