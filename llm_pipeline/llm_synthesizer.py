# llm_pipeline/llm_synthesizer.py
import json, os
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

# Load .env from the repo root regardless of current working dir
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# ✅ create global OpenAI client instance
_client = OpenAI()

SYSTEM = """You synthesize SMALL Java statement blocks for Correctness-by-Construction.
Input: a list of variables (name, modifiable?, type), a PRE condition and a POST condition written in KeY/Java-style logic.
Task: emit ONLY a valid Java statement block that mutates ONLY modifiable variables so that executing the block in a state
satisfying PRE leads to a state satisfying POST. No imports or class/method headers. No helpers; use plain Java expressions.
Return JSON: {"java": "<code>"}."""

def synthesize_java_update(variables, pre_condition_text, post_condition_text, is_loop_update=False):
    print(">>> Calling LLM for synthesis...")
    var_list = [{"name": n, "modifiable": m, "type": t} for (n,m,t) in variables]
    user_payload = {
        "variables": var_list,
        "pre_text":  pre_condition_text,
        "post_text": post_condition_text,
        "style": "emit Java statement block only",
        "is_loop_update": bool(is_loop_update),
    }
    resp = _client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(user_payload)}
        ],
        response_format={"type": "json_object"}
    )
    print(">>> LLM finished, response received.")
    data = json.loads(resp.choices[0].message.content)
    java = (data.get("java") or "").strip()
    if not java:
        raise RuntimeError("Model did not return a 'java' field.")
    return java
