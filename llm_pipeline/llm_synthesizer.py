# llm_pipeline/llm_synthesizer.py
import os, json, re, time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import httpx


# ──────────────────────────────────────────────────────────────────────────────
# Environment / client
# ──────────────────────────────────────────────────────────────────────────────

# Always load .env from project root (…/SynthAI/.env or your repo root)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Put it in your project .env")

# Configurable via env (or leave defaults)
MODEL_PRIMARY   = os.getenv("LLM_MODEL", "gpt-5-2025-08-07")    # you verified this works
MODEL_FALLBACK  = os.getenv("LLM_MODEL_FALLBACK", "gpt-4-0613")
CLIENT_TIMEOUT  = float(os.getenv("LLM_TIMEOUT",  "3600"))  # seconds
CLIENT_RETRIES  = int(os.getenv("LLM_RETRIES",    "1"))

# Single client reused across calls
_client = OpenAI(api_key=API_KEY, timeout=CLIENT_TIMEOUT, max_retries=CLIENT_RETRIES)


# ──────────────────────────────────────────────────────────────────────────────
# Prompt + utilities
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM = """
You are a small-step synthesis assistant for Java updates in CbC/KeY workflows. 
Your task is to generate the minimal but logically sufficient Java statement block 
that transforms any state satisfying the PRE-condition into one satisfying the POST-condition.

Input format (JSON): { "variables": [{"name": str, "modifiable": bool, "type": str}, ...], "pre_text": str, "post_text": str, "style": str, "is_loop_update": bool }

Rules:
- Modify only variables flagged "modifiable".
- Never modify or write to non-modifiable variables.
- Prefer straight-line (loop-free) code unless "is_loop_update" is true.
- Use only declared variables and their types. No new variables.
- Use plain Java expressions only (no methods, helpers, or class/method headers).
- You may read from non-modifiable arrays or objects to use their values in assignments.
- If a swap or movement between array partitions is required by the pre/post difference 
  (e.g., element classification boundaries shift or an element crosses between partitions), 
  you must perform the appropriate value swap using a temporary modifiable variable if available.
- Ensure array accesses remain within bounds implied by PRE.
- Always ensure that the variant variable strictly decreases when present.
- Produce all statements necessary to make POST true — not just the minimal syntactic change, 
  but the minimal *semantic* change that preserves all invariants and updates all affected variables.
- If "style" contains "emit Java statement block only", output code only, with no prose.
- Always output EXACTLY this JSON format: {"java": "<Java statements separated by semicolons>"}
"""


# remove low-value boilerplate from PRE/POST to shrink tokens/latency
NOISE_PATTERNS = [
    r'\bwellFormed\s*\(\s*heap\s*\)',
    r'\b[A-Za-z0-9_]+\.<created>\s*=\s*TRUE',
    r'\bheapAtPre\s*:=\s*heap',
    r'\s{2,}',  # collapse long spaces
]

def shrink_spec(text: str, limit: int = 6000) -> str:
    s = text
    for pat in NOISE_PATTERNS:
        s = re.sub(pat, ' ', s)
    # normalize whitespace and trim
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:limit]

def _parse_java_from_response(content: str) -> str:
    """
    We ask for JSON like: {"java": "<code>"}.
    If the model returns code fences or plain text, do a best-effort extract.
    """
    # Try JSON first
    try:
        data = json.loads(content)
        java = (data.get("java") or "").strip()
        if java:
            return java
    except Exception:
        pass

    # Try fenced blocks ```java ... ``` or ``` ... ```
    m = re.search(r"```(?:java)?\s*(.*?)```", content, flags=re.S)
    if m:
        return m.group(1).strip()

    # Fallback: return content as-is (caller may validate)
    return content.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main entry
# ──────────────────────────────────────────────────────────────────────────────

def synthesize_java_update(variables, pre_condition_text, post_condition_text, is_loop_update=False) -> str:
    """
    variables: list[(name, modifiable: bool, type)]
    pre_condition_text / post_condition_text: KeY/Java-style logic strings
    is_loop_update: bool (we pass it through so the model may choose a loop-friendly update)
    """
    # Prepare payload
    var_list = [{"name": n, "modifiable": m, "type": t} for (n, m, t) in variables]
    payload = {
        "variables": var_list,
        "pre_text":  shrink_spec(pre_condition_text),
        "post_text": shrink_spec(post_condition_text),
        "style": "emit Java statement block only",
        "is_loop_update": bool(is_loop_update),
    }
    payload_text = json.dumps(payload, ensure_ascii=False)

    def _call(model: str) -> str:
        print(f">>> Calling LLM model={model} (payload chars={len(payload_text)})")
        t0 = time.time()
        # NOTE: We intentionally do NOT use response_format here for maximum compatibility
        resp = _client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",    "content": payload_text},
            ],
            # You can set temperature etc. here if you like:
            # temperature=0.2,
            timeout=CLIENT_TIMEOUT,  # per-call timeout safeguard
            store=True
        )
        print(resp)
        took = time.time() - t0
        content = resp.choices[0].message.content or ""
        java = _parse_java_from_response(content)
        print(f">>> LLM finished in {took:.1f}s, code chars={len(java)}")
        if not java:
            raise RuntimeError("Model returned empty 'java' code.")
        return java

    try:
        return _call(MODEL_PRIMARY)
    except (httpx.TimeoutException, httpx.ReadError, httpx.ConnectError) as e:
        print(f"!!! LLM timeout/network error on {MODEL_PRIMARY}: {e}. Retrying with fallback {MODEL_FALLBACK}...")
        return _call(MODEL_FALLBACK)
    except Exception as e:
        # Last resort: try fallback once for other errors (e.g., model not available)
        print(f"!!! LLM error on {MODEL_PRIMARY}: {e}. Trying fallback {MODEL_FALLBACK}...")
        return _call(MODEL_FALLBACK)