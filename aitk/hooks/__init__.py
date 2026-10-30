"""PreToolUse hook logic: the review gate.

`hooks/require-review-gate.sh` runs `python3 -m aitk.hooks.review_gate` with
the toolkit root on PYTHONPATH. It shares the standalone shell tokenizer in
`hooks/lib/shell_tokens.py` with the git guard (`hooks/lib/git_guard.py`), and
imports only the standard library and `aitk.project_state`, so a hook never
loads the doctor, installer or routing code.
"""
