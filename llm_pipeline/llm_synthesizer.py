# llm_pipeline/llm_synthesizer.py
import json, os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_client = OpenAI()  # uses OPENAI_API_KEY from env

SYSTEM = """You are a synthesis engine for small Java code updates in Correctness-by-Construction workflows.
Given variables (name, modifiable?, type), a PRE condition and a POST condition (SyGuS-ish syntax), emit ONLY a valid Java code block that mutates ONLY modifiable variables to satisfy POST while preserving PRE where necessary. Avoid changing unmodifiable vars. No imports unless essential. No class/headers—just a method body snippet."""
# You can tighten this over time.

def synthesize_java_update(variables, pre_condition_sygus_like, post_condition_sygus_like, is_loop_update=False):
    var_list = [{"name": n, "modifiable": m, "type": t} for (n,m,t) in variables]
    user = {
        "variables": var_list,
        "pre":  pre_condition_sygus_like,
        "post": post_condition_sygus_like,
        "style": "emit Java statement block only"
    }
    if is_loop_update:
        user["hint"] = "This is a loop update; ensure variant decreases or invariant preserved."

    # Ask for strict JSON wrapper so it's easy to parse.
    response = _client.chat.completions.create(
        model="gpt-5",  # or your preferred model
        messages=[
            {"role":"system","content": SYSTEM},
            {"role":"user","content": json.dumps(user)}
        ],
        response_format={"type": "json_object"}  # structured output
    )
    text = response.choices[0].message.content
    data = json.loads(text)
    java = data.get("java", "").strip()
    if not java:
        raise RuntimeError("Model did not return 'java' field.")
    return java
