"""PreToolUse hook logic: the git guard and the review gate.

`hooks/prevent-project-commit.sh` and `hooks/require-review-gate.sh` are thin
wrappers that run `python3 -m aitk.hooks.git_guard` and
`python3 -m aitk.hooks.review_gate` with the toolkit root on PYTHONPATH. Both
share one shell tokenizer (`shell_tokens`). Modules here import only the
standard library and `aitk.project_state`, so a hook never loads the doctor,
installer or routing code.
"""
