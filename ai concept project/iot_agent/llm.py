"""Thin LLM abstraction over an OpenAI-compatible chat API (DeepSeek by default).

Every agent, baseline, simulated user and judge calls `chat()`, so switching
provider/model only requires changing config.py or environment variables.
Features: retry with backoff, on-disk response cache, token usage accounting.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field

from openai import OpenAI

import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY is not set (see .env.example)")
        _client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
    return _client


@dataclass
class Usage:
    """Accumulates token usage and latency; one instance per experiment run."""
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    by_role: dict = field(default_factory=dict)

    def add(self, role: str, prompt: int, completion: int, secs: float):
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.seconds += secs
        r = self.by_role.setdefault(role, {"calls": 0, "prompt": 0, "completion": 0})
        r["calls"] += 1
        r["prompt"] += prompt
        r["completion"] += completion


USAGE = Usage()


def _cache_path(payload: dict):
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return config.CACHE_DIR / key[:2] / f"{key}.json"


def chat(messages, model=None, tools=None, json_mode=False, role="agent",
         temperature=None, use_cache=None) -> dict:
    """Send one chat completion request.

    Returns a dict: {"content": str|None, "tool_calls": [{"id","name","arguments"}], "usage": {...}}
    `role` is only a label for usage accounting (agent / user_sim / judge / baseline).
    """
    payload = {
        "model": model or config.AGENT_MODEL,
        "messages": messages,
        "temperature": config.TEMPERATURE if temperature is None else temperature,
    }
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    use_cache = config.USE_CACHE if use_cache is None else use_cache
    path = _cache_path(payload)
    if use_cache and path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
        # cached calls still count tokens so cost reports reflect a full run
        USAGE.add(role, result["usage"]["prompt"], result["usage"]["completion"], 0.0)
        return result

    client = _get_client()
    for attempt in range(config.MAX_RETRIES):
        try:
            t0 = time.time()
            resp = client.chat.completions.create(**payload)
            secs = time.time() - t0
            break
        except Exception as e:  # network / rate limit / 5xx
            if attempt == config.MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            print(f"[llm] {type(e).__name__}: {e}; retrying in {wait}s")
            time.sleep(wait)

    msg = resp.choices[0].message
    tool_calls = [
        {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
        for tc in (msg.tool_calls or [])
    ]
    u = resp.usage
    result = {
        "content": msg.content,
        "tool_calls": tool_calls,
        "usage": {"prompt": u.prompt_tokens, "completion": u.completion_tokens},
        "seconds": secs,
    }
    USAGE.add(role, u.prompt_tokens, u.completion_tokens, secs)

    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def chat_json(messages, **kw) -> dict:
    """Chat call that must return a JSON object; retries once if parsing fails."""
    for _ in range(2):
        out = chat(messages, json_mode=True, **kw)
        try:
            return json.loads(out["content"])
        except (TypeError, json.JSONDecodeError):
            kw["use_cache"] = False
    raise ValueError(f"Model did not return valid JSON: {out['content']!r}")
