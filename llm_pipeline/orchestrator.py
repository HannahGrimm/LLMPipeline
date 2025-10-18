import os, time, shutil, re
from os.path import join, exists, normpath, dirname
from .prepost_extractor import extract_pre_post_from_key
from .readVariablesFromCorcModel import read_vars_from_corc_model
from .keyRunner import run_key
from .llm_synthesizer import synthesize_java_update
from .postprocess import write_timefile

TIME_POINTS = ["start","setup","extract","read_vars","prep_prompt","start_synth","end_synth","splice","verify","done"]

_SANITIZE_REPLACEMENTS = [
    (r'(?mi)^\s*\\javaSource\b.*\n', ''),
    (r'(?mi)^\s*\\classpath\b.*\n', ''),
    (r'(?mi)^\s*\\bootclasspath\b.*\n', ''),
]

def _sanitize_key_file(path: str, replacement_java_src: str | None = None) -> None:
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    for pat, rep in _SANITIZE_REPLACEMENTS:
        txt = re.sub(pat, rep, txt)
    # optionally enforce a local javaSource:
    # if replacement_java_src:
    #     if r"\javaSource" not in txt:
    #         txt = f'\\javaSource "{replacement_java_src}"\n' + txt
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

def _setup_temp(statement_path: str, temp_folder: str, statement_file: str) -> str:
    os.makedirs(temp_folder, exist_ok=True)
    dst_key = join(temp_folder, statement_file + ".key")
    shutil.copyfile(statement_path, dst_key)
    # try copying helper.key from source dir
    helper_src = join(dirname(statement_path), "helper.key")
    if exists(helper_src):
        shutil.copyfile(helper_src, join(temp_folder, "helper.key"))
    _sanitize_key_file(dst_key, replacement_java_src=dirname(statement_path))
    return dst_key

def _splice_llm_code(original_key_path: str, output_key_path: str, llm_code: str) -> None:
    with open(original_key_path, "r", encoding="utf-8") as f:
        src = f.read()

    # Preferred: explicit marker
    if "//@SYNTHESIS_HOLE" in src:
        patched = src.replace("//@SYNTHESIS_HOLE", llm_code)
    else:
        # Fallback: insert before the last '}' inside \program { ... }
        import re
        prog_re = re.compile(r'(?s)\\program\s*\{\s*(\{.*?\})\s*\}\s*\\endprogram')
        m = prog_re.search(src)
        if not m:
            raise RuntimeError("Could not locate \\program { ... } block in .key")

        java_block = m.group(1)
        # insert before the final '}' of that Java block
        idx = java_block.rfind('}')
        if idx == -1:
            raise RuntimeError("Malformed program block: missing closing '}'")

        java_block_patched = java_block[:idx].rstrip() + "\n" + llm_code + "\n" + java_block[idx:]
        patched = src[:m.start(1)] + java_block_patched + src[m.end(1):]

    with open(output_key_path, "w", encoding="utf-8") as f:
        f.write(patched)

def execute_llm_pipeline(info: dict) -> bool:
    info["timestamps"] = [time.time()]

    # derive working folder near the original .key
    statement_path = normpath(info["statement_path"])
    statement_dir  = dirname(statement_path)
    temp_folder    = normpath(join(statement_dir, f"temp_{info['statement_file']}_{info['temp_number']}"))

    # copy & sanitize
    temp_key = _setup_temp(statement_path, temp_folder, info["statement_file"])
    info["timestamps"].append(time.time())

    # extract PRE/POST from the original .key (or from the sanitized copy)
    pre_text, post_text = extract_pre_post_from_key(temp_key)
    info["timestamps"].append(time.time())

    # read variables from the given cbcmodel
    if not exists(info["cbcmodel_path"]):
        raise FileNotFoundError(f"cbcmodel not found:\n  {info['cbcmodel_path']}")
    variables = read_vars_from_corc_model(info["cbcmodel_path"], info["cbc_id"])
    info["timestamps"].append(time.time())

    # LLM synthesis
    info["timestamps"].append(time.time())
    java_codeblock = synthesize_java_update(
        variables=variables,
        pre_condition_text=pre_text,
        post_condition_text=post_text,
        is_loop_update=info.get("isLoopUpdate", False)
    )
    info["timestamps"].append(time.time())

    # persist snippet
    with open(join(temp_folder, "javaCode.txt"), "w", encoding="utf-8") as f:
        f.write(java_codeblock)

    # splice code into a verification .key and run KeY once
    verify_key = join(temp_folder, info["statement_file"] + "_withLLM.key")
    _splice_llm_code(temp_key, verify_key, java_codeblock)
    info["timestamps"].append(time.time())

    # run KeY (headless) for verification; we reuse your run_key wrapper
    # Using --openGoalsSmtPath is fine; KeY exits 0 on success.
    key_file = normpath(join(dirname(__file__), "..", "pythonScripts", "key-2.13.0-exe.jar"))
    run_key(key_file, verify_key, temp_folder)
    info["timestamps"].append(time.time())

    # timing
    with open(join(temp_folder, "times.txt"), "w", encoding="utf-8") as f:
        from .postprocess import write_timefile
        write_timefile(f.name, TIME_POINTS, info["timestamps"])
    return True

