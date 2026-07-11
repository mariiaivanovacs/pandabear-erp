"""Model selection: local Ollama first, OpenAI as measured fallback.

model_mode:
  local — Ollama only (the sovereignty demo path; hard-fails if Ollama is down)
  cloud — OpenAI only (needs openai_api_key)
  auto  — local first; if the local call errors or returns an unusable tool call,
          the SAME request is retried once on the cloud model and the audit log
          records remote_model_used=true for that hop. This is the honest version
          of "use OpenAI if the local model is not good enough": fallback is
          per-request and visible, not a silent global switch.

The local path calls Ollama's NATIVE /api/chat, not its OpenAI-compatibility
endpoint: Qwen3 is a thinking model, and only the native API honors
`think: false` to skip the reasoning preamble. Through the OpenAI-compat /v1
endpoint that flag is silently ignored (measured: ~15s/call with thinking vs
~1-3s without) — a 5-10x difference on every routing hop. The tradeoff is a
small response-shape adapter below, kept local to this file so every other
module still sees a plain OpenAI-style message object.
"""

import json
import logging
from dataclasses import dataclass, field

import httpx
from openai import OpenAI

from .config import settings

log = logging.getLogger("models")

_cloud: OpenAI | None = None
_ollama_native_url = settings.ollama_base_url.removesuffix("/v1")


def _cloud_client() -> OpenAI:
    global _cloud
    if _cloud is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not configured and cloud model requested")
        _cloud = OpenAI(api_key=settings.openai_api_key)
    return _cloud


@dataclass
class _Function:
    name: str
    arguments: str  # JSON string, matching the OpenAI SDK's shape


@dataclass
class _ToolCall:
    id: str
    function: _Function
    type: str = "function"

    def model_dump(self) -> dict:
        return {"id": self.id, "type": self.type,
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


@dataclass
class _Message:
    content: str | None
    tool_calls: list[_ToolCall] = field(default_factory=list)


def chat(messages: list[dict], tools: list[dict] | None = None, *, force_cloud: bool = False, tool_choice=None):
    """Returns (message, model_name, remote_used). Applies the mode/fallback policy."""
    mode = "cloud" if force_cloud else settings.model_mode

    if mode in ("local", "auto"):
        try:
            msg = _call_local(settings.local_model, messages, tools)
            return msg, settings.local_model, False
        except Exception as e:
            if mode == "local":
                raise
            log.warning("local model failed (%s) — falling back to cloud", e)

    msg = _call_cloud(settings.cloud_model, messages, tools, tool_choice)
    return msg, settings.cloud_model, True


def _call_local(model: str, messages: list[dict], tools: list[dict] | None) -> _Message:
    payload: dict = {"model": model, "messages": messages, "think": False, "stream": False,
                      "options": {"temperature": 0}}
    if tools:
        payload["tools"] = tools
    resp = httpx.post(f"{_ollama_native_url}/api/chat", json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()["message"]

    calls = [
        _ToolCall(id=tc.get("id") or f"call_{i}",
                  function=_Function(name=tc["function"]["name"],
                                     arguments=json.dumps(tc["function"]["arguments"])))
        for i, tc in enumerate(data.get("tool_calls") or [])
    ]
    return _Message(content=data.get("content"), tool_calls=calls)


def _call_cloud(model: str, messages: list[dict], tools, tool_choice):
    kwargs: dict = {"model": model, "messages": messages, "temperature": 0}
    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    resp = _cloud_client().chat.completions.create(**kwargs)
    return resp.choices[0].message


def local_available() -> bool:
    try:
        httpx.get(f"{_ollama_native_url}/api/tags", timeout=5).raise_for_status()
        return True
    except Exception:
        return False
