import os, time, shutil
from .splitProblemDefinition import split_problem_definition
from .readVariablesFromCorcModel import read_vars_from_corc_model
from .keyRunner import run_key
from .smtTreeParser import (
    cut_smt_assertion_from_file, parse_smt_to_tree, cleanup_tree_from_smt, print_tree_to_sygus
)
from .llm_synthesizer import synthesize_java_update
from .postprocess import write_timefile

TIME_POINTS = ["start","setup","split","key_pre","key_post","smt_pre","smt_post","read_vars","prep_prompt","start_synth","end_synth","java"]

def _setup_temp(project_folder, temp_folder, info):
    os.makedirs(temp_folder, exist_ok=True)
    shutil.copyfile(project_folder + info["statement_file"] + ".key", temp_folder + info["statement_file"] + ".key")
    helper_src = project_folder + "helper.key"
    if os.path.exists(helper_src):
        shutil.copyfile(helper_src, temp_folder + "helper.key")

def execute_llm_pipeline(info: dict) -> bool:
    info["timestamps"] = [time.time()]

    # mirror your old folder layout
    project_folder = info["src_dir"] + "prove" + info["project"] + "\\"
    temp_folder = project_folder + f"temp_{info['statement_file']}_{info['temp_number']}\\"

    _setup_temp(project_folder, temp_folder, info);                      info["timestamps"].append(time.time())

    # 1) split into pre/post .key like before
    split_out_pre  = temp_folder + info["statement_file"] + "_pre_gen.key"
    split_out_post = temp_folder + info["statement_file"] + "_post_gen.key"
    split_problem_definition(info, split_out_pre, split_out_post);        info["timestamps"].append(time.time())

    # 2) KeY -> SMT (unchanged)
    key_file = ".\\pythonScripts\\key-2.13.0-exe.jar"
    run_key(key_file, split_out_pre,  temp_folder);                       info["timestamps"].append(time.time())
    run_key(key_file, split_out_post, temp_folder);                       info["timestamps"].append(time.time())

    # 3) parse SMT to SyGuS-like strings (unchanged)
    key_out_suffix = "_goal_0.smt2"
    smt_pre  = cut_smt_assertion_from_file(split_out_pre  + key_out_suffix)
    tree_pre = cleanup_tree_from_smt(parse_smt_to_tree(smt_pre))
    pre_str  = print_tree_to_sygus(tree_pre).replace("u_", "");           info["timestamps"].append(time.time())

    smt_post  = cut_smt_assertion_from_file(split_out_post + key_out_suffix)
    tree_post = cleanup_tree_from_smt(parse_smt_to_tree(smt_post))
    post_str  = print_tree_to_sygus(tree_post).replace("u_", "");         info["timestamps"].append(time.time())

    # 4) read CORC variables from .cbcmodel (unchanged)
    variables = read_vars_from_corc_model(info["cbcmodel_path"], info["cbc_id"])
    # variables is [(name, is_modifiable, datatype), ...]
    info["timestamps"].append(time.time())

    # 5) Prepare & call LLM
    info["timestamps"].append(time.time())
    java_codeblock = synthesize_java_update(
        variables=variables,
        pre_condition_sygus_like=pre_str,
        post_condition_sygus_like=post_str,
        is_loop_update=info.get("isLoopUpdate", False)
    )
    info["timestamps"].append(time.time())

    # 6) persist results, timing
    with open(temp_folder + "javaCode.txt", "w", encoding="utf-8") as f:
        f.write(java_codeblock)

    write_timefile(temp_folder + "times.txt", TIME_POINTS, info["timestamps"])
    return True
