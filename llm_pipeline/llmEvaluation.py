"""
LLM Pipeline Evaluation Module

Automates execution of the LLM pipeline across multiple projects and statements.
Similar to sygusEvaluation.py but for the LLM-based synthesis pipeline.
"""

import os
import re
import json
from pathlib import Path
from pprint import pprint
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm
from .orchestrator import execute_llm_pipeline


class LLMEvaluation:
    """
    Orchestrates batch evaluation of the LLM pipeline across multiple projects and statements.
    """

    def __init__(self, src_dir: str):
        """
        Initialize the LLM evaluation runner.

        Args:
            src_dir: Base directory containing evalData_noPredicates/diagrams
        """
        self.src_dir = src_dir
        self.diagrams_dir = os.path.join(src_dir, "evalData_noPredicates", "diagrams")
        if not os.path.isdir(self.diagrams_dir):
            raise ValueError(f"Diagrams directory not found: {self.diagrams_dir}")

    def collect_files_for_evaluation(
        self, projects_to_evaluate: Optional[List[str]] = None
    ) -> Dict[int, Dict]:
        """
        Scan the directory structure and collect all statement files for evaluation.

        Args:
            projects_to_evaluate: List of project names to include. If None, includes all.

        Returns:
            Dictionary mapping task IDs to task configuration dictionaries.
        """
        task_dict = {}
        task_id = 1

        # Get all available projects if not specified
        if projects_to_evaluate is None:
            projects_to_evaluate = self._get_available_projects()

        for project in projects_to_evaluate:
            prove_folder_path = os.path.join(self.diagrams_dir, f"prove{project}")
            cbcmodel_path = os.path.join(self.diagrams_dir, f"{project}.cbcmodel")

            if not os.path.isdir(prove_folder_path):
                print(f"Warning: Prove folder not found for project '{project}': {prove_folder_path}")
                continue

            if not os.path.isfile(cbcmodel_path):
                print(f"Warning: CBCModel file not found for project '{project}': {cbcmodel_path}")
                continue

            # Find all Statement*.key files in the prove folder
            for root, dirs, files in os.walk(prove_folder_path):
                for filename in files:
                    if self._is_statement_file(filename):
                        statement_full_path = os.path.join(root, filename)
                        statement_name = filename.replace(".key", "")

                        # Extract metadata from the key file
                        cbc_id = self._get_cbc_id(statement_full_path)
                        modifiable_list = self._get_modifiable_vars(statement_full_path)
                        is_loop_update = self._get_is_loop_update(statement_full_path)

                        if cbc_id is None:
                            print(f"Warning: No cbc_id found in {statement_full_path}")
                            continue

                        task_dict[task_id] = {
                            "src_dir": self.src_dir,
                            "project": project,
                            "statement_file": statement_name,
                            "statement_path": statement_full_path,
                            "cbcmodel_path": cbcmodel_path,
                            "cbc_id": cbc_id,
                            "modifiable": modifiable_list or [],
                            "isLoopUpdate": is_loop_update or False,
                            "result": None,
                            "timestamps": [],
                        }
                        task_id += 1

        print(f"Collected {len(task_dict)} tasks for evaluation")
        return task_dict

    def execute_evaluation(
        self,
        task_dict: Dict[int, Dict],
        num_runs: int = 1,
        skip_projects: Optional[Dict[str, List[int]]] = None,
        verbose: bool = True,
    ) -> Dict[int, Dict]:
        """
        Execute the LLM pipeline for all collected tasks.

        Args:
            task_dict: Dictionary of tasks from collect_files_for_evaluation
            num_runs: Number of times to run each task
            skip_projects: Dict mapping project names to list of statement IDs to skip
            verbose: Whether to print progress information

        Returns:
            Updated task_dict with results
        """
        if skip_projects is None:
            skip_projects = {}

        total_tasks = len(task_dict) * num_runs
        pbar = tqdm(total=total_tasks, desc="Executing pipeline") if verbose else None

        for task_id, task_info in task_dict.items():
            project = task_info["project"]
            statement_file = task_info["statement_file"]

            # Extract statement number for skip logic
            statement_num = self._extract_statement_number(statement_file)
            if (
                project in skip_projects
                and statement_num in skip_projects[project]
            ):
                if verbose:
                    print(f"Skipping {project} Statement {statement_num}")
                if pbar:
                    pbar.update(num_runs)
                continue

            for run_num in range(num_runs):
                task_info["temp_number"] = str(run_num)

                try:
                    result = execute_llm_pipeline(task_info)
                    task_info["result"] = result
                    if verbose and run_num == 0:
                        print(
                            f"✓ {project} {statement_file} (run {run_num + 1}/{num_runs})"
                        )
                except Exception as e:
                    print(f"✗ Error in {project} {statement_file}: {str(e)}")
                    task_info["result"] = False

                if pbar:
                    pbar.update(1)

        if pbar:
            pbar.close()

        return task_dict

    def save_results(self, task_dict: Dict[int, Dict], output_path: str) -> None:
        """
        Save evaluation results to a JSON file.

        Args:
            task_dict: Task dictionary with results
            output_path: Path to save the results JSON
        """
        # Convert non-serializable data for JSON
        results = {}
        for task_id, task_info in task_dict.items():
            entry = {
                "project": task_info.get("project"),
                "statement_file": task_info.get("statement_file"),
                "cbc_id": task_info.get("cbc_id"),
                "result": task_info.get("result"),
            }

            # Optional richer fields produced by the orchestrator
            if "llm_input" in task_info:
                entry["llm_input"] = task_info.get("llm_input")
            if "llm_output" in task_info:
                entry["llm_output"] = task_info.get("llm_output")
            if "synthesis_seconds" in task_info:
                entry["synthesis_seconds"] = task_info.get("synthesis_seconds")

            results[str(task_id)] = entry

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {output_path}")

    def print_summary(self, task_dict: Dict[int, Dict]) -> None:
        """
        Print a summary of evaluation results.

        Args:
            task_dict: Task dictionary with results
        """
        total = len(task_dict)
        successful = sum(1 for t in task_dict.values() if t.get("result") is True)
        failed = sum(1 for t in task_dict.values() if t.get("result") is False)
        pending = sum(1 for t in task_dict.values() if t.get("result") is None)

        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Total tasks:     {total}")
        print(f"Successful:      {successful} ({100 * successful // total if total > 0 else 0}%)")
        print(f"Failed:          {failed} ({100 * failed // total if total > 0 else 0}%)")
        print(f"Pending:         {pending}")
        print("=" * 60 + "\n")

    # Helper methods
    def _get_available_projects(self) -> List[str]:
        """Get all available projects from the diagrams directory."""
        projects = set()
        for item in os.listdir(self.diagrams_dir):
            item_path = os.path.join(self.diagrams_dir, item)
            if os.path.isdir(item_path) and item.startswith("prove"):
                projects.add(item[5:])  # Remove "prove" prefix
        return sorted(list(projects))

    @staticmethod
    def _is_statement_file(filename: str) -> bool:
        """Check if a file is a statement file (Statement*.key)."""
        pattern = r"^Statement\d+\.key$"
        return re.match(pattern, filename) is not None

    @staticmethod
    def _get_cbc_id(file_path: str) -> Optional[str]:
        """Extract CBC statement ID from a key file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                pattern = r"//statementid:\{([0-9a-fA-F-]+)\}"
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
        except Exception as e:
            print(f"Error reading CBC ID from {file_path}: {e}")
        return None

    @staticmethod
    def _get_modifiable_vars(file_path: str) -> Optional[List[str]]:
        """Extract modifiable variables from a key file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                pattern = r"\/\/mutable:\s*\{([^}]*)\}"
                match = re.search(pattern, content)
                if match:
                    return [x.strip() for x in match.group(1).split(",") if x.strip()]
        except Exception as e:
            print(f"Error reading modifiable vars from {file_path}: {e}")
        return None

    @staticmethod
    def _get_is_loop_update(file_path: str) -> Optional[bool]:
        """Extract isLoopUpdate flag from a key file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "//isLoopUpdate:{true}" in content:
                    return True
                elif "//isLoopUpdate:{false}" in content:
                    return False
        except Exception as e:
            print(f"Error reading isLoopUpdate from {file_path}: {e}")
        return None

    @staticmethod
    def _extract_statement_number(statement_file: str) -> int:
        """Extract the numeric part from Statement*.key filename."""
        match = re.search(r"Statement(\d+)", statement_file)
        if match:
            return int(match.group(1))
        return -1


def main():
    """
    Example usage of LLMEvaluation class.
    """
    # Configuration
    src_dir = r"C:\Users\hanna\OneDrive\Dokumente\LLMPipeline"
    projects_to_evaluate = None  # Specify projects or None for all
    num_runs = 10  # Number of times to run each statement

    # Projects/statements to skip (optional)
    skip_projects = {
        #"LinearSearch": [1,2],
        #"maxElement": [1,2,3,4,5],
        #"DutchFlag": [1,2,3,4],
        #"sort": [1,2,3,4,5],
        #"Exponentation": [1,2,3],
        #"FactorialGraphical": [1,2,3],
        #"Logarithm": [1,2],
        #"push": [1,2,3,4,5]  # Add statement numbers to skip, e.g., [1, 3]
        
        
    }

    # Create evaluator
    evaluator = LLMEvaluation(src_dir)

    # Collect all tasks
    print("Collecting tasks...")
    task_dict = evaluator.collect_files_for_evaluation(projects_to_evaluate)

    # Execute evaluation
    print(f"\nExecuting pipeline ({num_runs} runs per task)...")
    task_dict = evaluator.execute_evaluation(
        task_dict, num_runs=num_runs, skip_projects=skip_projects, verbose=True
    )

    # Print summary
    evaluator.print_summary(task_dict)

    # Save results
    results_path = os.path.join(src_dir, "evaluation_results.json")
    evaluator.save_results(task_dict, results_path)


if __name__ == "__main__":
    main()
