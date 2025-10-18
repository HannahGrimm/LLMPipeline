# llm_pipeline/cli.py
import argparse, json
from .orchestrator import execute_llm_pipeline

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_dir", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--statement_file", required=True)
    ap.add_argument("--statement_path", required=True)
    ap.add_argument("--cbcmodel_path", required=True)
    ap.add_argument("--cbc_id", required=True)
    ap.add_argument("--temp_number", default="0")
    ap.add_argument("--isLoopUpdate", action="store_true")
    args = ap.parse_args()

    info = vars(args)
    ok = execute_llm_pipeline(info)
    print("SUCCESS" if ok else "NO-OP")


if __name__ == "__main__":
    main()
