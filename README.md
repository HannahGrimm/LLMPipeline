# llm_pipeline

Small-step synthesis pipeline that uses an LLM to synthesize small Java statement blocks for Correctness-by-Construction (CbC) / KeY workflows and then verifies them with KeY.

Key ideas
- Extract PRE/POST from a KeY `.key` file, read Java variables from a `.cbcmodel`, call an LLM to synthesize a short Java update (only mutating modifiable variables), splice the snippet back into the `.key` and run KeY headless to verify.
- Main orchestration: [`orchestrator.execute_llm_pipeline`](llm_pipeline/orchestrator.py) — see [llm_pipeline/orchestrator.py](llm_pipeline/orchestrator.py).
- CLI entrypoint: [`cli.main`](llm_pipeline/cli.py) — see [llm_pipeline/cli.py](llm_pipeline/cli.py).

Quickstart

1. Install dependencies
   - Use the project configuration in [pyproject.toml](pyproject.toml). Example:
     ```sh
     pip install -e .
     ```
     or
     ```sh
     poetry install
     ```

2. Provide credentials
   - The pipeline loads environment variables from  via . Add your LLM API key and any required settings there.

3. Run the pipeline (example)
   ```sh
   python -m llm_pipeline.cli \
     --src_dir . \
     --project MyProject \
     --statement_file StatementX \
     --statement_path evalData_noPredicates/diagrams/ExampleName/temp_StatementX_1/StatementX.key \
     --cbcmodel_path evalData_noPredicates/diagrams/ExampleName/ExampleName.cbcmodel \
     --cbc_id <cbc-node-id> \
     --temp_number 0