import re

# Matches \pre{...} and \post{...}
_PRE_RE  = re.compile(r'(?mis)\\pre\s*\{(.*?)\}')
_POST_RE = re.compile(r'(?mis)\\post\s*\{(.*?)\}')

# Matches: \problem {  PRE   ->  { … }   \<{ … }\>   POST  }
#   - any whitespace and line breaks allowed
#   - the { … } after '->' is the state update part (we ignore it)
#   - the \<{ … }\> is the program fragment (we ignore it; we splice the LLM code there)
_PROBLEM_RE = re.compile(
    r'(?mis)'                      # multi-line, dot matches newline, case-insensitive
    r'\\problem\s*\{'             # \problem {
    r'\s*(?P<pre>.*?)\s*'         # PRE (greedy minimal)
    r'->\s*\{.*?\}\s*'            # -> { ... }   (ignore)
    r'\\<\s*\{.*?\}\s*\\>\s*'     # \<{ ... }\>  (ignore)
    r'(?P<post>.*?)\s*'           # POST
    r'\}'                         # }
)

def extract_pre_post_from_key(key_path: str) -> tuple[str, str]:
    """Return (pre_text, post_text) from a .key file.
       Supports both:
         - \\pre{...} / \\post{...}
         - \\problem { PRE -> {…} \\<{ … }\\> POST }
    """
    with open(key_path, "r", encoding="utf-8") as f:
        txt = f.read()

    # 1) Try explicit \pre/\post blocks
    mpre  = _PRE_RE.search(txt)
    mpost = _POST_RE.search(txt)
    if mpre and mpost:
        return mpre.group(1).strip(), mpost.group(1).strip()

    # 2) Try \problem { PRE -> {...} \<{...}\> POST }
    mprob = _PROBLEM_RE.search(txt)
    if mprob:
        return mprob.group("pre").strip(), mprob.group("post").strip()

    raise ValueError(f"Could not find PRE/POST in: {key_path}")

