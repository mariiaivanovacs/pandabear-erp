"""FastAPI surface: chat endpoint, per-request audit trace, approval actions.
Run: uv run uvicorn pandabear.api:app --port 8080"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import audit
from .admin import router as admin_router
from .db import get_conn, init_db
from .github_webhook import router as github_router
from .graph import ask
from .models import local_available
from .toolgen import approve_tool

app = FastAPI(title="PandaBear")
init_db()
app.include_router(admin_router)
app.include_router(github_router)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo_user"
    user_role: str = "branch_manager"


@app.get("/health")
def health():
    return {"ok": True, "local_model_available": local_available()}


@app.post("/chat")
def chat(req: ChatRequest):
    return ask(req.message, user_id=req.user_id, user_role=req.user_role)


@app.get("/audit/{request_id}")
def audit_trace(request_id: str):
    rows = audit.trace(request_id)
    if not rows:
        raise HTTPException(404, "no audit trail for that request id")
    return rows


@app.get("/approvals")
def pending_approvals():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM pending_approvals WHERE state = 'pending' ORDER BY created_at"
        ).fetchall()


@app.post("/approvals/{approval_id}/{decision}")
def resolve_approval(approval_id: int, decision: str, resolved_by: str = "admin"):
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pending_approvals WHERE id = ? AND state = 'pending'",
            (approval_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "no pending approval with that id")
        conn.execute(
            "UPDATE pending_approvals SET state = ?, resolved_at = CURRENT_TIMESTAMP, resolved_by = ? WHERE id = ?",
            (decision, resolved_by, approval_id),
        )
    return {"id": approval_id, "state": decision}


@app.post("/tools/{tool_id}/approve")
def approve(tool_id: str, approved_by: str = "admin"):
    approve_tool(tool_id, approved_by)
    return {"tool_id": tool_id, "human_approved": True, "status": "active"}
