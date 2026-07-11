"""Admin panel — server-rendered HTML + a fetch-based onboarding chat (no framework,
no build step, no external assets). Observe the whole organization, review/approve
tools (with source view), edit query permissions, trace the audit stream, and
onboard new sources through a conversational wizard. Mounted under /admin by api.py.
"""

import html
import json
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import onboarding, vault
from .config import settings
from .db import get_conn
from .github_webhook import _AUTO_END, _AUTO_START
from .models import local_available
from .toolgen import approve_tool

router = APIRouter(prefix="/admin")

# ---------------------------------------------------------------- design system

_FAVICON = ("data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 "
            "viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🐼</text></svg>")

_CSS = """
:root{
  --bg:#0a0e14; --panel:#10161f; --panel2:#151d29; --border:#1e2836; --border2:#2b3a4e;
  --text:#e6edf3; --muted:#8b98a9; --faint:#5c6875;
  --bamboo:#3fb950; --bamboo-deep:#238636; --blue:#58a6ff; --amber:#d29922; --red:#f85149;
  --violet:#bc8cff; --cyan:#39c5cf;
}
*{box-sizing:border-box}
body{font:14px/1.55 -apple-system,system-ui,"Segoe UI",sans-serif;margin:0;background:var(--bg);
  color:var(--text);-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none} a:hover{text-decoration:underline}
code{background:var(--panel2);border:1px solid var(--border);border-radius:5px;padding:1px 5px;
  font:12px ui-monospace,SFMono-Regular,Menlo,monospace}

/* ------- layout: fixed sidebar + main ------- */
.side{position:fixed;inset:0 auto 0 0;width:216px;background:var(--panel);
  border-right:1px solid var(--border);display:flex;flex-direction:column;padding:18px 12px;z-index:10}
.brand{display:flex;align-items:center;gap:10px;padding:4px 10px 16px;border-bottom:1px solid var(--border)}
.brand .logo{font-size:26px;filter:drop-shadow(0 0 10px rgba(63,185,80,.45))}
.brand b{font-size:16px;letter-spacing:.2px}
.brand small{display:block;color:var(--bamboo);font-size:9.5px;letter-spacing:1.6px;font-weight:600}
nav{margin-top:14px;display:flex;flex-direction:column;gap:2px}
nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;color:var(--muted);
  font-weight:500;border:1px solid transparent;transition:all .15s ease}
nav a:hover{color:var(--text);background:var(--panel2);text-decoration:none}
nav a.active{color:var(--text);background:linear-gradient(90deg,rgba(63,185,80,.16),rgba(63,185,80,.04));
  border-color:rgba(63,185,80,.35)}
nav a.active .ic{filter:none}
nav .ic{width:20px;text-align:center}
.side .foot{margin-top:auto;padding:10px;color:var(--faint);font-size:11px;border-top:1px solid var(--border)}
main{margin-left:216px;padding:26px 30px 60px;max-width:1160px}
.pagehead{display:flex;align-items:baseline;gap:12px;margin:0 0 4px}
.pagehead h1{font-size:21px;margin:0}
.pagehead .sub{color:var(--muted);font-size:13px}

/* ------- cards, grids, stats ------- */
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0;
  animation:rise .35s ease both;transition:border-color .15s ease}
.card:hover{border-color:var(--border2)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:14px 0}
.grid .card{margin:0}
.grid .card:nth-child(2){animation-delay:.04s}.grid .card:nth-child(3){animation-delay:.08s}
.grid .card:nth-child(4){animation-delay:.12s}.grid .card:nth-child(5){animation-delay:.16s}
.grid .card:nth-child(6){animation-delay:.2s}
.stat-row{display:flex;align-items:center;gap:12px}
.stat-ic{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;font-size:18px;flex:none}
.t-green{background:rgba(63,185,80,.14);border:1px solid rgba(63,185,80,.3)}
.t-blue{background:rgba(88,166,255,.12);border:1px solid rgba(88,166,255,.3)}
.t-amber{background:rgba(210,153,34,.13);border:1px solid rgba(210,153,34,.32)}
.t-violet{background:rgba(188,140,255,.12);border:1px solid rgba(188,140,255,.3)}
.t-cyan{background:rgba(57,197,207,.12);border:1px solid rgba(57,197,207,.3)}
.t-red{background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.3)}
.stat{font-size:24px;font-weight:700;line-height:1.1}
.lbl{color:var(--muted);font-size:11.5px;letter-spacing:.3px}
h2{font-size:15px;margin:26px 0 4px;display:flex;align-items:center;gap:8px}
h2 .hint{color:var(--faint);font-weight:400;font-size:12px}

/* ------- pills, chips, dots ------- */
.pill{padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;display:inline-block}
.ok{background:rgba(63,185,80,.15);color:#56d364;border:1px solid rgba(63,185,80,.4)}
.warn{background:rgba(210,153,34,.15);color:#e3b341;border:1px solid rgba(210,153,34,.4)}
.bad{background:rgba(248,81,73,.15);color:#ff7b72;border:1px solid rgba(248,81,73,.4)}
.mut{background:var(--panel2);color:var(--muted);border:1px solid var(--border2)}
.info{background:rgba(88,166,255,.13);color:#79c0ff;border:1px solid rgba(88,166,255,.4)}
.pill.pulse{animation:pulse 2.2s infinite}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--panel2);border:1px solid var(--border2);
  border-radius:8px;padding:3px 9px;font-size:12px;margin:2px 3px 2px 0}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}
.dot.g{background:var(--bamboo);box-shadow:0 0 6px rgba(63,185,80,.7)}
.dot.r{background:var(--red);box-shadow:0 0 6px rgba(248,81,73,.6)}
.dot.a{background:var(--amber)}

/* ------- tables ------- */
.tablewrap{overflow-x:auto;border:1px solid var(--border);border-radius:12px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:8px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--border)}
th{background:var(--panel);color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.7px;
  position:sticky;top:0}
tbody tr{transition:background .12s}
tbody tr:hover{background:rgba(88,166,255,.05)}
tbody tr:last-child td{border-bottom:0}

/* ------- forms & buttons ------- */
button,.btn{background:linear-gradient(180deg,#2ea043,#238636);color:#fff;border:1px solid rgba(255,255,255,.12);
  padding:7px 16px;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;
  transition:transform .12s ease,filter .12s ease,box-shadow .12s ease;display:inline-block}
button:hover,.btn:hover{filter:brightness(1.12);transform:translateY(-1px);
  box-shadow:0 4px 14px rgba(46,160,67,.35);text-decoration:none}
button:active{transform:scale(.98)}
button.sec,.btn.sec{background:var(--panel2);border-color:var(--border2);color:var(--text)}
button.sec:hover,.btn.sec:hover{box-shadow:0 4px 14px rgba(0,0,0,.4)}
button:disabled{opacity:.45;pointer-events:none}
input,textarea,select{background:var(--bg);color:var(--text);border:1px solid var(--border2);
  border-radius:8px;padding:8px 10px;width:100%;font:inherit;transition:border-color .15s,box-shadow .15s}
input:focus,textarea:focus,select:focus{outline:0;border-color:var(--bamboo);
  box-shadow:0 0 0 3px rgba(63,185,80,.18)}
label{display:block;margin:10px 0 4px;font-size:12px;color:var(--muted)}
pre{background:var(--bg);border:1px solid var(--border);padding:12px;border-radius:10px;overflow:auto;
  max-height:340px;font-size:12px;line-height:1.5}
details summary{cursor:pointer;color:var(--blue);font-size:12.5px;margin-top:8px}
details[open] summary{margin-bottom:6px}

/* ------- onboarding chat ------- */
.steps{display:flex;gap:0;margin:16px 0 4px;font-size:12px}
.step{flex:1;text-align:center;color:var(--faint);padding:9px 4px;border-bottom:2px solid var(--border);
  transition:all .3s ease;font-weight:600}
.step.active{color:var(--bamboo);border-color:var(--bamboo)}
.step.done{color:var(--muted);border-color:var(--bamboo-deep)}
.step.done::before{content:"✓ ";color:var(--bamboo)}
.chat{display:flex;flex-direction:column;gap:12px;margin:18px 0;min-height:60px}
.msg{max-width:660px;padding:11px 15px;border-radius:14px;font-size:13.5px;animation:rise .3s ease both}
.msg.you{align-self:flex-end;background:linear-gradient(135deg,#1f6feb,#1158c7);color:#fff;
  border-bottom-right-radius:4px}
.msg.panda{align-self:flex-start;background:var(--panel);border:1px solid var(--border);
  border-bottom-left-radius:4px;position:relative;padding-left:44px}
.msg.panda::before{content:"🐼";position:absolute;left:12px;top:9px;font-size:17px}
.msg.panda.err{border-color:rgba(248,81,73,.5);background:rgba(248,81,73,.07)}
.msg ul{margin:6px 0 2px 16px;padding:0}
.msg li{margin:2px 0}
.msg.form-slot{align-self:stretch;max-width:660px;background:var(--panel);border:1px dashed var(--border2);
  border-radius:14px}
.typing{display:flex;gap:5px;align-items:center;padding:14px 16px 14px 44px}
.typing span{width:7px;height:7px;border-radius:50%;background:var(--muted);
  animation:blink 1.2s infinite ease-in-out}
.typing span:nth-child(2){animation-delay:.18s}
.typing span:nth-child(3){animation-delay:.36s}

/* ------- agents.md timeline ------- */
.timeline{position:relative;margin:18px 0;padding-left:26px}
.timeline::before{content:"";position:absolute;left:8px;top:6px;bottom:6px;width:2px;
  background:linear-gradient(var(--bamboo),var(--border))}
.tl-entry{position:relative;margin:0 0 16px}
.tl-entry::before{content:"";position:absolute;left:-26px;top:5px;width:11px;height:11px;
  border-radius:50%;background:var(--bamboo);border:2px solid var(--bg);
  box-shadow:0 0 0 2px var(--bamboo)}
.tl-entry:first-child::before{box-shadow:0 0 0 2px var(--bamboo),0 0 8px 2px rgba(63,185,80,.6)}
.tl-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;font-size:12.5px;color:var(--muted)}
.tl-head b{color:var(--text);font-size:13.5px}
.tl-card ul{margin:2px 0 0 18px;padding:0}
.tl-card li{margin:3px 0}

/* ------- animations ------- */
@keyframes rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
@keyframes blink{0%,70%,100%{opacity:.25;transform:translateY(0)}35%{opacity:1;transform:translateY(-3px)}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(210,153,34,.4)}55%{box-shadow:0 0 0 7px rgba(210,153,34,0)}}
.empty{display:flex;flex-direction:column;align-items:center;gap:6px;color:var(--faint);
  padding:34px 10px;text-align:center}
.empty .big{font-size:30px;opacity:.6}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:6px}
::-webkit-scrollbar-track{background:transparent}
"""

_NAV = [
    ("", "📊", "Overview"),
    ("/tools", "🔧", "Tools"),
    ("/policies", "🛡️", "Permissions"),
    ("/audit", "📜", "Audit"),
    ("/agents", "🧠", "AGENTS.md"),
    ("/onboarding", "➕", "Add source"),
]


def _shell(title: str, active: str, body: str, page_sub: str = "") -> str:
    nav = "".join(
        f'<a href="/admin{path}" class="{"active" if path == active else ""}">'
        f'<span class=ic>{icon}</span>{label}</a>'
        for path, icon, label in _NAV
    )
    sub = f'<span class=sub>{page_sub}</span>' if page_sub else ""
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · PandaBear</title>
<link rel=icon href="{_FAVICON}">
<style>{_CSS}</style></head><body>
<aside class=side>
  <div class=brand><span class=logo>🐼</span>
    <div><b>PandaBear</b><small>SOVEREIGN AI OPS</small></div></div>
  <nav>{nav}</nav>
  <div class=foot>local-first · zero egress by default<br>credentials never reach a model</div>
</aside>
<main><div class=pagehead><h1>{html.escape(title)}</h1>{sub}</div>{body}</main>
</body></html>"""


def _pill(text: str, cls: str) -> str:
    return f'<span class="pill {cls}">{html.escape(str(text))}</span>'


_NODE_TINT = {"agent": "info", "policy_check": "mut", "tool_executor": "mut",
              "respond": "mut", "response": "mut", "error": "bad"}
_TOOL_ICON = {"read_connector": "🔎", "action": "⚡", "policy_check": "🛡️", "formatter": "📝"}


def _status_pill(status: str) -> str:
    cls = {"ok": "ok", "denied": "bad", "error": "bad", "pending_approval": "warn"}.get(status, "mut")
    return _pill(status, cls)


# ---------------------------------------------------------------------- overview

@router.get("", response_class=HTMLResponse)
def overview():
    with get_conn() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                  for t in ("capabilities", "tools", "policies", "audit_logs")}
        pending_tools = conn.execute(
            "SELECT id FROM tools WHERE human_approved=0").fetchall()
        approvals = conn.execute(
            "SELECT COUNT(*) c FROM pending_approvals WHERE state='pending'").fetchone()["c"]
        exposures = conn.execute(
            "SELECT COALESCE(SUM(credential_exposed_to_model),0) c FROM audit_logs").fetchone()["c"]
        remote_calls = conn.execute(
            "SELECT COALESCE(SUM(remote_model_used),0) c FROM audit_logs").fetchone()["c"]
        avg_lat = conn.execute(
            "SELECT AVG(latency_ms) v FROM audit_logs WHERE node='tool_executor' "
            "AND latency_ms IS NOT NULL").fetchone()["v"]
        denials = conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE status='denied'").fetchone()["c"]
        recent = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 12").fetchall()
        domains = conn.execute(
            """SELECT d.name, c.id cap_id, c.description, c.risk_level, c.status
               FROM capabilities c LEFT JOIN domains d ON d.id=c.domain_id
               ORDER BY d.name, c.id""").fetchall()

    local_ok = local_available()
    refs = vault.list_refs()

    stats = f"""<div class=grid>
<div class=card><div class=stat-row><div class="stat-ic t-green">🧩</div>
  <div><div class=stat>{counts['capabilities']}</div><div class=lbl>capabilities</div></div></div></div>
<div class=card><div class=stat-row><div class="stat-ic t-blue">🔧</div>
  <div><div class=stat>{counts['tools']}</div><div class=lbl>tools</div></div></div></div>
<div class=card><div class=stat-row><div class="stat-ic t-violet">🛡️</div>
  <div><div class=stat>{counts['policies']}</div><div class=lbl>policies</div></div></div></div>
<div class=card><div class=stat-row><div class="stat-ic t-cyan">📜</div>
  <div><div class=stat>{counts['audit_logs']}</div><div class=lbl>audit events</div></div></div></div>
<div class=card><div class=stat-row><div class="stat-ic t-amber">🔐</div>
  <div><div class=stat>{len(refs)}</div><div class=lbl>vault credentials</div></div></div></div>
<div class=card><div class=stat-row><div class="stat-ic t-red">⛔</div>
  <div><div class=stat>{denials}</div><div class=lbl>denied requests</div></div></div></div>
</div>"""

    alerts = ""
    if pending_tools:
        names = ", ".join(f"<code>{html.escape(r['id'])}</code>" for r in pending_tools[:4])
        alerts += (f'<div class=card style="border-color:rgba(210,153,34,.5)">'
                   f'{_pill(f"{len(pending_tools)} awaiting approval", "warn pulse")} '
                   f'&nbsp;{names} &nbsp;<a class="btn sec" href=/admin/tools>Review now →</a></div>')
    if approvals:
        alerts += (f'<div class=card style="border-color:rgba(210,153,34,.5)">'
                   f'{_pill(f"{approvals} query approval(s) pending", "warn")}</div>')

    lat_txt = f"{avg_lat:.0f} ms" if avg_lat else "—"
    posture = f"""<h2>🔒 Security posture <span class=hint>measured, not asserted</span></h2>
<div class=grid>
<div class=card><div class=stat-row>
  <span class="dot {'g' if local_ok else 'r'}"></span>
  <div><b>Local model {'online' if local_ok else 'OFFLINE'}</b>
  <div class=lbl>{html.escape(settings.local_model) if hasattr(settings,'local_model') else 'Ollama'} · answers stay on this machine</div></div></div></div>
<div class=card><div class=stat-row>
  <span class="dot {'g' if exposures == 0 else 'r'}"></span>
  <div><b>{exposures} credential exposures</b>
  <div class=lbl>across all {counts['audit_logs']} audited events</div></div></div></div>
<div class=card><div class=stat-row>
  <span class="dot a"></span>
  <div><b>{remote_calls} cloud escalations</b>
  <div class=lbl>masked/generalized before leaving the box</div></div></div></div>
<div class=card><div class=stat-row>
  <span class="dot g"></span>
  <div><b>{lat_txt} avg tool run</b>
  <div class=lbl>deterministic executor latency</div></div></div></div>
</div>
<div class=card>🔐 Vault holds <b>{len(refs)}</b> encrypted credential(s), all <code>model_visible=0</code>:<br>
{''.join(f'<span class=chip>🔒 {html.escape(r)}</span>' for r in refs) or '<span class=lbl>none yet</span>'}</div>"""

    if domains:
        dom_rows = "".join(
            f"<tr><td>{html.escape(r['name'] or '—')}</td>"
            f"<td><code>{html.escape(r['cap_id'])}</code></td>"
            f"<td>{html.escape(r['description'])}</td>"
            f"<td>{_pill('risk ' + str(r['risk_level']), 'mut')}</td>"
            f"<td>{_pill(r['status'], 'ok' if r['status'] == 'active' else 'mut')}</td></tr>"
            for r in domains)
        caps_html = (f'<div class=tablewrap><table><tr><th>domain</th><th>capability</th>'
                     f'<th>what it does</th><th>risk</th><th>status</th></tr>'
                     f'<tbody>{dom_rows}</tbody></table></div>')
    else:
        caps_html = ('<div class=card><div class=empty><span class=big>🧩</span>'
                     'No capabilities yet — <a href=/admin/onboarding>add your first source</a></div></div>')

    if recent:
        rows = "".join(
            f"<tr><td class=lbl>{html.escape(str(r['ts'])[5:19])}</td>"
            f"<td>{_pill(r['node'], _NODE_TINT.get(r['node'], 'mut'))}</td>"
            f"<td><code>{html.escape(r['capability_id'] or '·')}</code></td>"
            f"<td>{_status_pill(r['status'])}</td>"
            f"<td class=lbl>{html.escape(r['model_used'] or '')}{' ☁️' if r['remote_model_used'] else ''}</td>"
            f"<td>{'🔓' if r['credential_exposed_to_model'] else '🔒'}</td></tr>"
            for r in recent)
        activity = (f'<div class=tablewrap><table><tr><th>time</th><th>node</th><th>capability</th>'
                    f'<th>status</th><th>model</th><th>cred</th></tr><tbody>{rows}</tbody></table></div>')
    else:
        activity = ('<div class=card><div class=empty><span class=big>📜</span>'
                    'No activity yet — send a message through /chat or the Telegram bot</div></div>')

    body = f"""{stats}{alerts}{posture}
<h2>🧩 Capabilities by domain</h2>{caps_html}
<h2>⚡ Recent activity <span class=hint>latest 12 events · <a href=/admin/audit>full log</a></span></h2>
{activity}"""
    return _shell("Overview", "", body, "everything your organization's AI can do, see, and touch")


# ------------------------------------------------------------------------- tools

@router.get("/tools", response_class=HTMLResponse)
def tools_page():
    with get_conn() as conn:
        tools = conn.execute(
            "SELECT * FROM tools ORDER BY human_approved, created_at DESC").fetchall()
    if not tools:
        body = ('<div class=card><div class=empty><span class=big>🔧</span>No tools yet — '
                '<a href=/admin/onboarding>onboard a source</a> to generate some</div></div>')
        return _shell("Tools", "/tools", body)

    out = []
    for t in tools:
        icon = _TOOL_ICON.get(t["type"], "🔧")
        src = ""
        path = settings.tools_dir.parent / t["file_path"]
        if path.is_file():
            src = html.escape(path.read_text()[:6000])
        approve_btn = ""
        badge = _pill("approved", "ok")
        if not t["human_approved"]:
            badge = _pill("UNAPPROVED", "warn pulse")
            approve_btn = (f'<form method=post action="/admin/tools/{html.escape(t["id"])}/approve" '
                           f'style="display:inline;margin-left:8px"><button>✓ Approve &amp; activate</button></form>')
        gen = html.escape(t["generated_by"] or "?")
        gen_badge = _pill("🤖 " + gen, "info") if gen != "human" else _pill("👤 human", "mut")
        out.append(f"""<div class=card>
<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
  <span style=font-size:18px>{icon}</span><b>{html.escape(t['id'])}</b>
  {_pill(t['type'], 'mut')} {badge} {gen_badge}
  <span class=chip>🔐 {html.escape(t['credential_scope'] or 'no credential')}</span>
  <span class=lbl>⏱ {t['timeout_seconds']}s timeout</span>{approve_btn}
</div>
<details><summary>view source ({len(src.splitlines())} lines, airgap-validated)</summary>
<pre>{src}</pre></details></div>""")
    total = len(tools)
    pending = sum(1 for t in tools if not t["human_approved"])
    sub = f"{total} tools · {pending} awaiting review" if pending else f"{total} tools · all approved"
    return _shell("Tools", "/tools", "".join(out), sub)


@router.post("/tools/{tool_id}/approve")
def do_approve(tool_id: str):
    approve_tool(tool_id, approved_by="admin-ui")
    return RedirectResponse("/admin/tools", status_code=303)


# -------------------------------------------------------------------- permissions

@router.get("/policies", response_class=HTMLResponse)
def policies_page():
    with get_conn() as conn:
        pols = conn.execute("SELECT * FROM policies ORDER BY id").fetchall()
        caps = conn.execute("SELECT id, policy_id FROM capabilities").fetchall()
    cap_by_pol: dict = {}
    for c in caps:
        cap_by_pol.setdefault(c["policy_id"], []).append(c["id"])

    out = []
    for p in pols:
        rules = json.loads(p["rules"])
        chips = "".join(
            f'<span class=chip>👤 {html.escape(r.get("role", "?"))} → '
            f'{_pill(r.get("decision", "?"), {"allow": "ok", "deny": "bad"}.get(r.get("decision"), "warn"))}'
            f'{"&nbsp;≤ " + str(r["limit"]) if r.get("limit") is not None else ""}</span>'
            for r in rules) or '<span class=lbl>no explicit rules — default applies to everyone</span>'
        used = "".join(f"<code>{html.escape(c)}</code> " for c in cap_by_pol.get(p["id"], [])) or "—"
        dd = p["default_decision"]
        out.append(f"""<div class=card>
<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
  <b>🛡️ {html.escape(p['id'])}</b>
  <span class=lbl>default: {_pill(dd, {'allow':'ok','deny':'bad'}.get(dd,'warn'))}</span>
  <span class=lbl>guards: {used}</span></div>
<div style=margin:8px 0>{chips}</div>
<details><summary>edit rules</summary>
<form method=post action="/admin/policies/{html.escape(p['id'])}">
<label>rule JSON — <code>[{{"role": "...", "decision": "allow|deny|approval_required", "limit": n?}}]</code></label>
<textarea name=rules rows=4>{html.escape(json.dumps(rules, indent=2))}</textarea>
<label>default decision (anyone not matched above)</label>
<select name=default_decision>
{"".join(f'<option {"selected" if dd == d else ""}>{d}</option>' for d in ("deny", "allow", "approval_required"))}
</select><br><br><button>💾 Save policy</button></form></details></div>""")
    return _shell("Permissions", "/policies", "".join(out),
                  "who may run which capability — deterministic, fail-closed, model can't override")


@router.post("/policies/{policy_id}")
def save_policy(policy_id: str, rules: str = Form(...), default_decision: str = Form(...)):
    try:
        parsed = json.loads(rules)
    except json.JSONDecodeError:
        return RedirectResponse("/admin/policies", status_code=303)
    with get_conn() as conn:
        conn.execute("UPDATE policies SET rules=?, default_decision=? WHERE id=?",
                     (json.dumps(parsed), default_decision, policy_id))
    return RedirectResponse("/admin/policies", status_code=303)


# ------------------------------------------------------------------------- audit

_AUDIT_JS = """
function filterAudit(){
  var n=document.getElementById('f-node').value,
      s=document.getElementById('f-status').value,
      q=document.getElementById('f-q').value.toLowerCase(),
      shown=0;
  document.querySelectorAll('#audit tbody tr').forEach(function(tr){
    var ok=(!n||tr.dataset.node===n)&&(!s||tr.dataset.status===s)
           &&(!q||tr.textContent.toLowerCase().indexOf(q)>=0);
    tr.style.display=ok?'':'none'; if(ok)shown++;
  });
  document.getElementById('f-count').textContent=shown+' shown';
}
"""


@router.get("/audit", response_class=HTMLResponse)
def audit_page():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200").fetchall()
        nodes = sorted({r["node"] for r in rows})
        statuses = sorted({r["status"] for r in rows})

    trs = "".join(
        f'<tr data-node="{html.escape(r["node"])}" data-status="{html.escape(r["status"])}">'
        f"<td class=lbl>{html.escape(str(r['ts'])[5:19])}</td>"
        f"<td><code title={html.escape(r['request_id'])}>{html.escape(r['request_id'][:8])}</code></td>"
        f"<td>{_pill(r['node'], _NODE_TINT.get(r['node'], 'mut'))}</td>"
        f"<td><code>{html.escape(r['capability_id'] or '·')}</code></td>"
        f"<td>{html.escape(r['policy_decision'] or '')}</td>"
        f"<td class=lbl>{html.escape(r['model_used'] or '')}{' ☁️' if r['remote_model_used'] else ''}</td>"
        f"<td>{'🔓 <b>EXPOSED</b>' if r['credential_exposed_to_model'] else '🔒'}</td>"
        f"<td class=lbl>{str(r['latency_ms']) + ' ms' if r['latency_ms'] else ''}</td>"
        f"<td>{_status_pill(r['status'])}</td></tr>"
        for r in rows)

    filters = f"""<div class=card style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
<span>🔍</span>
<input id=f-q placeholder="search anything…" style=max-width:220px oninput=filterAudit()>
<select id=f-node style=max-width:170px onchange=filterAudit()><option value="">all nodes</option>
{"".join(f'<option>{html.escape(n)}</option>' for n in nodes)}</select>
<select id=f-status style=max-width:150px onchange=filterAudit()><option value="">all statuses</option>
{"".join(f'<option>{html.escape(s)}</option>' for s in statuses)}</select>
<span class=lbl id=f-count>{len(rows)} shown</span></div>"""

    body = f"""{filters}
<div class=tablewrap><table id=audit>
<tr><th>time</th><th>request</th><th>node</th><th>capability</th><th>decision</th>
<th>model</th><th>cred</th><th>latency</th><th>status</th></tr>
<tbody>{trs}</tbody></table></div>
<script>{_AUDIT_JS}</script>"""
    return _shell("Audit", "/audit", body,
                  "every node of every request · 🔒 = credential never reached a model")


# ------------------------------------------------------------------------ agents.md

_ENTRY_RE = re.compile(
    r"^###\s+(?P<date>\S+ \S+ UTC)\s*·\s*(?P<pusher>.+?)\s*·\s*`(?P<sha>[a-f0-9]+)`\s*on\s*`(?P<branch>[^`]+)`\s*\n(?P<body>.*)",
    re.DOTALL,
)


def _parse_agents_md(text: str) -> tuple[str, list[dict], str]:
    """Returns (preamble, entries, raw_auto_section) — entries newest-first,
    matching how github_webhook.py writes them."""
    if _AUTO_START not in text or _AUTO_END not in text:
        return text.strip(), [], ""
    pre, rest = text.split(_AUTO_START, 1)
    inner, _post = rest.split(_AUTO_END, 1)
    blocks = [b.strip() for b in re.split(r"\n(?=### )", inner.strip()) if b.strip()]

    entries = []
    for b in blocks:
        m = _ENTRY_RE.match(b)
        if not m:
            entries.append({"date": "", "pusher": "", "sha": "", "branch": "", "bullets": [b]})
            continue
        bullets = [ln.strip(" -") for ln in m.group("body").splitlines() if ln.strip().startswith("-")]
        entries.append({"date": m.group("date"), "pusher": m.group("pusher"),
                        "sha": m.group("sha"), "branch": m.group("branch"),
                        "bullets": bullets or [m.group("body").strip()]})
    return pre.strip(), entries, inner.strip()


@router.get("/agents", response_class=HTMLResponse)
def agents_md_page():
    path = settings.agents_md_path
    if not path.exists():
        body = ('<div class=card><div class=empty><span class=big>🧠</span>'
                'No AGENTS.md yet — it\'s created automatically on the first push to a '
                'registered GitHub repo.<br><span class=lbl>Register a webhook (push event) '
                'pointing at <code>/webhooks/github/push</code> to get started.</span></div></div>')
        return _shell("AGENTS.md", "/agents", body)

    raw = path.read_text()
    preamble, entries, _ = _parse_agents_md(raw)

    if entries:
        tl = "".join(f"""<div class=tl-entry><div class=card><div class=tl-head>
🔀 <b>{html.escape(e['sha'] or '·')}</b> on {_pill(e['branch'] or '?', 'mut')}
&nbsp;by <b>{html.escape(e['pusher'] or 'unknown')}</b>
&nbsp;<span class=lbl>{html.escape(e['date'])}</span></div>
<div class=tl-card><ul>{''.join(f'<li>{html.escape(bl)}</li>' for bl in e['bullets'])}</ul></div>
</div></div>""" for e in entries)
        timeline = f'<div class=timeline>{tl}</div>'
    else:
        timeline = ('<div class=card><div class=empty><span class=big>📭</span>'
                    'File exists but no pushes recorded yet.</div></div>')

    body = f"""<div class=card>{html.escape(preamble).replace(chr(10)+chr(10), '<br><br>').replace(chr(10), ' ')}</div>
<h2>🕒 Auto-updated changelog <span class=hint>newest first · distilled locally on every push, never sent to a cloud model</span></h2>
{timeline}
<details><summary>view raw AGENTS.md</summary><pre>{html.escape(raw)}</pre></details>"""
    return _shell("AGENTS.md", "/agents", body,
                  f"{len(entries)} recorded push(es) · read automatically by Claude Code, Cursor, Copilot, Codex and others")


# -------------------------------------------------------- onboarding (async chat)

def _assemble_secret(fields_form: dict[str, str]) -> dict | str:
    """If one field is clearly a full credential document (e.g. a GCP/Firebase
    service-account JSON), store it directly — that's the shape platform probe
    tools like fb_probe.py expect as PANDABEAR_CREDENTIAL. Any other planned
    fields (e.g. project_id) are typically already embedded in that document.
    Otherwise keep every field as a named dict for generated tools to parse."""
    for value in fields_form.values():
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and {"private_key", "client_email"} <= parsed.keys():
            return value
    return fields_form


_ONBOARD_JS = r"""
var chat=document.getElementById('chat'), session=null, planFields=[];
function esc(s){var t=document.createElement('span');t.textContent=s==null?'':s;return t.innerHTML;}
function scrollLast(el){el.scrollIntoView({behavior:'smooth',block:'end'});}
function bubble(cls,inner){var d=document.createElement('div');d.className='msg '+cls;
  d.innerHTML=inner;chat.appendChild(d);scrollLast(d);return d;}
function typing(){var d=document.createElement('div');d.className='msg panda typing';
  d.innerHTML='<span></span><span></span><span></span>';chat.appendChild(d);scrollLast(d);return d;}
function slot(inner){var d=document.createElement('div');d.className='msg form-slot';
  d.innerHTML=inner;chat.appendChild(d);scrollLast(d);return d;}
function setStep(n){document.querySelectorAll('.step').forEach(function(el,i){
  el.classList.toggle('active',i===n);el.classList.toggle('done',i<n);});}
async function api(path,payload){
  var r=await fetch('/admin/onboarding/api/'+path,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  var j=await r.json();
  if(!r.ok||j.error)throw new Error(j.error||('HTTP '+r.status));
  return j;
}

function descForm(prefill){
  var s=slot('<label>Describe the data source and what staff should be able to ask</label>'+
    '<textarea id=desc rows=3 placeholder="e.g. Our Firestore has an \'orders\' collection. Staff should check order status by order id.">'+esc(prefill||'')+'</textarea>'+
    '<br><br><button id=go>Start →</button>');
  s.querySelector('#go').onclick=async function(){
    var text=s.querySelector('#desc').value.trim(); if(!text)return;
    this.disabled=true; s.remove(); bubble('you',esc(text));
    var t=typing();
    try{
      var plan=await api('plan',{description:text});
      t.remove(); session=plan.session_id; planFields=plan.credential_fields||[];
      var list=planFields.map(function(f){return '<li><code>'+esc(f.name)+'</code> — '+
        esc(f.description)+(f.secret?' 🔒':'')+'</li>';}).join('');
      bubble('panda','Looks like a <b>'+esc(plan.source_kind)+'</b> source (via <code>'+
        esc(plan.sdk)+'</code>). '+esc(plan.notes||'')+
        '<br>I need:<ul>'+list+'</ul>Values go straight into the encrypted vault — I never see them.');
      credForm(); setStep(1);
    }catch(e){t.remove();bubble('panda err','⚠️ '+esc(e.message));descForm(text);}
  };
}

function credForm(){
  var inputs=planFields.map(function(f,i){
    return '<label>'+esc(f.name)+' — '+esc(f.description)+'</label>'+
      '<input data-cred="'+esc(f.name)+'" type="'+(f.secret?'password':'text')+'">';
  }).join('');
  var s=slot('<label>a short name for this source (letters/numbers/underscore)</label>'+
    '<input id=srcname pattern="[a-zA-Z0-9_]+" placeholder="e.g. orders_db">'+inputs+
    '<br><br><button id=go>🔐 Seal to vault &amp; connect</button>');
  s.querySelector('#go').onclick=async function(){
    var name=s.querySelector('#srcname').value.trim();
    if(!/^[a-zA-Z0-9_]+$/.test(name)){s.querySelector('#srcname').focus();return;}
    var creds={},missing=false;
    s.querySelectorAll('[data-cred]').forEach(function(inp){
      if(!inp.value.trim())missing=true; creds[inp.dataset.cred]=inp.value;});
    if(missing)return;
    this.disabled=true; s.remove();
    bubble('you','🔒 credentials for <code>'+esc(name)+'</code> — '+
      Object.keys(creds).map(function(k){return esc(k)+'=••••••';}).join(', '));
    var t=typing();
    try{
      var res=await api('bind',{session_id:session,source_name:name,credentials:creds});
      t.remove();
      if(!res.connected){
        bubble('panda err','⚠️ Sealed to the vault, but the connection failed: '+
          esc(res.error||'unknown error')+'. Check the values and try again.');
        credForm(); return;
      }
      var cols=res.collections||{};
      var list=Object.keys(cols).map(function(c){
        return '<li><code>'+esc(c)+'</code>: '+esc(Object.keys(cols[c]).join(', '))+'</li>';}).join('');
      bubble('panda','✅ Connected. Structure discovered (field names &amp; types only — I never read values):'+
        '<ul>'+list+'</ul>Now — what should your staff be able to ask this source?');
      goalsForm(); setStep(2);
    }catch(e){t.remove();bubble('panda err','⚠️ '+esc(e.message));credForm();}
  };
}

function goalsForm(){
  var s=slot('<label>Goals — one per line is fine</label>'+
    '<textarea id=goals rows=3 placeholder="e.g. Check order status by order id. Look up a customer\'s tier."></textarea>'+
    '<br><br><button id=go>🤖 Design &amp; build tools</button>');
  s.querySelector('#go').onclick=async function(){
    var goals=s.querySelector('#goals').value.trim(); if(!goals)return;
    this.disabled=true; s.remove(); bubble('you',esc(goals));
    var t=typing();
    bubble('panda','Designing capabilities, generating code, running the airgap AST gate and a live sandbox check — this takes a moment…');
    try{
      var res=await api('generate',{session_id:session,goals:goals});
      t.remove();
      var items=(res.generated||[]).map(function(g){
        return '<li>'+(g.ok?'✅':'❌')+' <code>'+esc(g.tool_id)+'</code>'+
          (g.sandbox_verify&&g.sandbox_verify.ok?' — sandbox verified':'')+'</li>';}).join('');
      bubble('panda','Built '+(res.generated||[]).length+' tool(s):<ul>'+items+
        '</ul>They stay <b>inert until you approve them</b>.');
      bubble('panda','🧹 Session wiped — my planning notes and your structure dump are destroyed. '+
        'Only the tools, policies, and the sealed vault entry remain.');
      slot('<a class=btn href=/admin/tools>✓ Review &amp; approve tools</a> '+
        '<a class="btn sec" href=/admin/onboarding>➕ Add another source</a>');
      setStep(3);
    }catch(e){t.remove();bubble('panda err','⚠️ '+esc(e.message));goalsForm();}
  };
}

bubble('panda','Hi! I onboard new data sources in a separate, disposable session. '+
  'Describe the source below — I\'ll work out what credentials I need (I never see their values), '+
  'test the connection myself, and build you deterministic, airgap-checked tools.');
descForm('');
setStep(0);
"""


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page():
    body = f"""<div class=steps>
<div class=step>1 · Describe</div><div class=step>2 · Credentials</div>
<div class=step>3 · Goals</div><div class=step>4 · Approve</div></div>
<div class=chat id=chat></div>
<script>{_ONBOARD_JS}</script>"""
    return _shell("Add source", "/onboarding", body,
                  "a separate model session plans, connects, builds, verifies — then forgets")


@router.post("/onboarding/api/plan")
async def api_plan(request: Request):
    data = await request.json()
    try:
        return onboarding.start(str(data.get("description", "")))
    except Exception as e:  # surfaced as a chat error bubble
        return {"error": str(e)}


@router.post("/onboarding/api/bind")
async def api_bind(request: Request):
    data = await request.json()
    sid = str(data.get("session_id", ""))
    name = str(data.get("source_name", ""))
    creds = {str(k): str(v) for k, v in (data.get("credentials") or {}).items()}
    try:
        onboarding.bind_credentials(sid, name, _assemble_secret(creds))
        return onboarding.probe(sid)
    except Exception as e:
        return {"error": str(e)}


@router.post("/onboarding/api/generate")
async def api_generate(request: Request):
    data = await request.json()
    sid = str(data.get("session_id", ""))
    try:
        result = onboarding.generate(sid, str(data.get("goals", "")))
        result["finalized"] = onboarding.finalize(sid)
        return result
    except Exception as e:
        return {"error": str(e)}
