"""The PandaBear request graph.

Model-driven where understanding is needed, deterministic where authority is
exercised:

    agent (LLM tool-calling) → policy_check (pure fn) → tool_executor (pure fn)
                                                       → respond (LLM formatting)

The model chooses WHICH capability fits the request via real function-calling
over the registry — there is no keyword/regex routing anywhere. But the model
cannot execute anything: its chosen call is handed to the deterministic policy
gate, and only an 'allow' reaches the executor.
"""

import json
import logging
import time
import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import audit, escalation, models, policy, registry
from .config import settings
from .executor import ToolExecutionError, execute

log = logging.getLogger("graph")

SYSTEM_PROMPT = """You are PandaBear, a company operations assistant.

You can only act through the provided functions — each one is an approved company
capability. Rules:
1. If the user's request matches a capability, call that function with arguments
   taken from their message. Never invent argument values that are not stated or
   clearly implied.
2. If required information is missing, ask a short clarifying question instead of
   calling a function.
3. If no capability matches, say so plainly and list what you CAN help with.
4. Never promise actions outside the provided functions."""


class GraphState(TypedDict, total=False):
    request_id: str
    user_id: str
    user_role: str
    user_message: str
    messages: list
    capability_id: str
    tool_args: dict
    policy_decision: str
    policy_reason: str
    tool_output: dict
    response: str
    model_used: str
    remote_model_used: bool
    done: bool          # agent answered directly (clarification / no-match)
    error_public: str


def agent_node(state: GraphState) -> GraphState:
    start = time.monotonic()
    tools = registry.as_openai_tools()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["user_message"]},
    ]

    capability_id, tool_args, direct_answer = None, None, None
    model_used, remote_used = "", False

    for attempt in range(2):  # one retry on malformed tool-call args
        try:
            msg, model_used, remote_used = models.chat(messages, tools=tools)
        except Exception as e:
            log.error("agent model call failed: %s", e)
            audit.log(state["request_id"], "agent", user_id=state.get("user_id"),
                      status="error", detail={"error": str(e)[:500]},
                      latency_ms=int((time.monotonic() - start) * 1000))
            return {"error_public": "I couldn't process that right now — the model backend is unavailable.", "done": True}

        if not msg.tool_calls:
            direct_answer = msg.content or "Could you rephrase that?"
            break

        tc = msg.tool_calls[0]
        try:
            tool_args = json.loads(tc.function.arguments or "{}")
            capability_id = tc.function.name
            break
        except json.JSONDecodeError:
            if attempt == 0:
                messages.append({"role": "assistant", "content": None,
                                 "tool_calls": [tc.model_dump()]})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": "ERROR: arguments were not valid JSON. Call the function again with valid JSON arguments."})
            else:
                direct_answer = "I couldn't map that to a valid action — could you rephrase?"

    latency = int((time.monotonic() - start) * 1000)

    if direct_answer is not None:
        audit.log(state["request_id"], "agent", user_id=state.get("user_id"),
                  model_used=model_used, remote_model_used=remote_used,
                  detail={"direct_answer": direct_answer[:500]}, latency_ms=latency)
        return {"response": direct_answer, "done": True,
                "model_used": model_used, "remote_model_used": remote_used}

    # the model picked a capability that must actually exist in the registry —
    # hallucinated function names are treated as no-match, not executed
    if not registry.get_capability(capability_id):
        audit.log(state["request_id"], "agent", user_id=state.get("user_id"),
                  model_used=model_used, remote_model_used=remote_used, status="error",
                  detail={"hallucinated_capability": capability_id}, latency_ms=latency)
        return {"response": "That isn't something I'm set up to do yet.", "done": True,
                "model_used": model_used, "remote_model_used": remote_used}

    audit.log(state["request_id"], "agent", user_id=state.get("user_id"),
              capability_id=capability_id, model_used=model_used,
              remote_model_used=remote_used,
              detail={"tool_args": tool_args}, latency_ms=latency)
    return {"capability_id": capability_id, "tool_args": tool_args,
            "model_used": model_used, "remote_model_used": remote_used}


def policy_node(state: GraphState) -> GraphState:
    cap = registry.get_capability(state["capability_id"])
    result = policy.evaluate(cap.get("policy_id"), state.get("user_role", ""), state["tool_args"])

    decision = result.decision
    if cap.get("requires_approval") and decision == "allow":
        decision = "approval_required"

    if decision == "approval_required":
        policy.record_pending_approval(
            state["request_id"], state["capability_id"], state["tool_args"],
            state.get("user_id", ""),
        )

    audit.log(state["request_id"], "policy_check", user_id=state.get("user_id"),
              user_role=state.get("user_role"), capability_id=state["capability_id"],
              policy_decision=decision,
              detail={"reason_code": result.reason_code},
              status="ok" if decision == "allow" else
                     ("denied" if decision == "deny" else "pending_approval"))
    return {"policy_decision": decision, "policy_reason": result.reason_code}


def executor_node(state: GraphState) -> GraphState:
    cap = registry.get_capability(state["capability_id"])
    tool = registry.get_tool(cap["tool_id"]) if cap.get("tool_id") else None
    if not tool:
        audit.log(state["request_id"], "tool_executor", capability_id=state["capability_id"],
                  status="error", detail={"error": "capability has no tool bound"})
        return {"error_public": "This capability isn't wired to an action yet."}

    try:
        output = execute(tool, state["tool_args"])
    except ToolExecutionError as e:
        audit.log(state["request_id"], "tool_executor", user_id=state.get("user_id"),
                  capability_id=state["capability_id"], tool_id=tool["id"], status="error",
                  detail={"internal": e.internal_detail[:1000]})
        return {"error_public": e.public_message}

    audit.log(state["request_id"], "tool_executor", user_id=state.get("user_id"),
              capability_id=state["capability_id"], tool_id=tool["id"],
              credential_exposed_to_model=False,
              detail={"output_keys": sorted(output.keys())},
              latency_ms=output.get("_latency_ms"))
    return {"tool_output": output}


def respond_node(state: GraphState) -> GraphState:
    start = time.monotonic()

    if state.get("error_public"):
        text = state["error_public"]
        audit.log(state["request_id"], "response", status="error",
                  detail={"response": text})
        return {"response": text}

    if state.get("policy_decision") == "deny":
        text = f"That action isn't permitted for your role ({state.get('user_role', 'unknown')})."
        audit.log(state["request_id"], "response", policy_decision="deny",
                  detail={"response": text})
        return {"response": text}

    if state.get("policy_decision") == "approval_required":
        text = "This needs approval before it can run — I've logged the request for a manager."
        audit.log(state["request_id"], "response", policy_decision="approval_required",
                  detail={"response": text})
        return {"response": text}

    # allow + tool ran: LOCAL model answers, or self-assesses that the question
    # needs heavier analysis — in which case the remote model is consulted with a
    # GENERALIZED query (values replaced by placeholders, rehydrated locally).
    output = {k: v for k, v in state["tool_output"].items() if not k.startswith("_")}
    messages = [
        {"role": "system", "content":
            "Turn this tool result into a short, professional answer to the user's request. "
            "Use ONLY facts present in the tool result — add nothing.\n"
            "EXCEPTION: if the request asks for analysis, judgment, recommendation, or "
            "multi-step reasoning that goes beyond restating these facts, reply with the "
            "single word ESCALATE instead of answering."},
        {"role": "user", "content":
            f"User asked: {state['user_message']}\n\nTool result:\n{json.dumps(output, default=str)}"},
    ]
    try:
        msg, model_used, remote_used = models.chat(messages)
        text = msg.content or json.dumps(output, default=str)
    except Exception as e:
        log.error("respond model call failed: %s", e)
        text = json.dumps(output, default=str)  # degrade to raw facts, never drop the answer
        model_used, remote_used = "none", False

    if text.strip().upper().startswith("ESCALATE") and settings.model_mode != "local":
        esc_start = time.monotonic()
        try:
            text, generalized_prompt = escalation.escalate(state["user_message"], output)
            audit.log(state["request_id"], "remote_escalation",
                      capability_id=state["capability_id"],
                      model_used=settings.cloud_model, remote_model_used=True,
                      credential_exposed_to_model=False,
                      detail={"generalized_prompt": generalized_prompt},
                      latency_ms=int((time.monotonic() - esc_start) * 1000))
            model_used, remote_used = settings.cloud_model, True
        except Exception as e:
            log.error("escalation failed: %s", e)
            text = json.dumps(output, default=str)

    audit.log(state["request_id"], "response", capability_id=state["capability_id"],
              model_used=model_used, remote_model_used=remote_used,
              detail={"response": text[:500]},
              latency_ms=int((time.monotonic() - start) * 1000))
    return {"response": text, "model_used": model_used, "remote_model_used": remote_used}


def _route_after_agent(state: GraphState) -> str:
    return END if state.get("done") else "policy_check"


def _route_after_policy(state: GraphState) -> str:
    return "tool_executor" if state["policy_decision"] == "allow" else "respond"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("agent", agent_node)
    g.add_node("policy_check", policy_node)
    g.add_node("tool_executor", executor_node)
    g.add_node("respond", respond_node)

    g.set_entry_point("agent")
    g.add_conditional_edges("agent", _route_after_agent, {END: END, "policy_check": "policy_check"})
    g.add_conditional_edges("policy_check", _route_after_policy,
                            {"tool_executor": "tool_executor", "respond": "respond"})
    g.add_edge("tool_executor", "respond")
    g.add_edge("respond", END)
    return g.compile()


_app = None


def ask(user_message: str, user_id: str = "demo_user", user_role: str = "branch_manager") -> dict:
    """Entry point used by the API, the Telegram bot, and tests."""
    global _app
    if _app is None:
        _app = build_graph()
    request_id = uuid.uuid4().hex[:12]
    final = _app.invoke(
        {"request_id": request_id, "user_id": user_id, "user_role": user_role,
         "user_message": user_message},
        {"recursion_limit": settings.max_agent_turns * 4},
    )
    return {
        "request_id": request_id,
        "response": final.get("response", final.get("error_public", "")),
        "capability_id": final.get("capability_id"),
        "policy_decision": final.get("policy_decision"),
        "model_used": final.get("model_used"),
        "remote_model_used": final.get("remote_model_used", False),
    }
