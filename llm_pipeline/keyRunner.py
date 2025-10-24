# keyRunner.py
import subprocess, os
import shutil

def _find_java_executable():
    # 1) explicit env var JAVA
    java_env = os.getenv("JAVA")
    if java_env and os.path.isfile(java_env):
        return java_env
    # 2) JAVA_HOME -> bin\java.exe
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        candidate = os.path.join(java_home, "bin", "java.exe")
        if os.path.isfile(candidate):
            return candidate
    # 3) on PATH
    which = shutil.which("java")
    if which and os.path.isfile(which):
        return which
    # 4) last-resort: keep original hardcoded path if present
    fallback = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.11.9-hotspot\bin\java.exe"
    if os.path.isfile(fallback):
        return fallback
    return None

# Resolve once
JAVA = _find_java_executable()

def run_key(key_file, input_file, output_folder):
    # Preflight checks (helpful error messages)
    if not os.path.isfile(JAVA):
        raise FileNotFoundError(f"java.exe not found:\n  {JAVA}")
    if not os.path.isfile(key_file):
        raise FileNotFoundError(f"KeY jar not found:\n  {key_file}")
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    java_command = [
        JAVA,
        "-jar",
        key_file,
        "--auto",
        "--openGoalsSmtPath",
        output_folder,
        input_file,
    ]

    print(" ".join(java_command))
    try:
        # IMPORTANT: shell=False with a LIST on Windows
        result = subprocess.run(java_command, check=True, text=True, capture_output=True)
        # If you want to see KeY output:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print("KeY failed:")
        if e.stdout: print(e.stdout)
        if e.stderr: print(e.stderr)
        return e.returncode

