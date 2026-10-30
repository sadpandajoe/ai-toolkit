"""The git guard (hooks/lib/git_guard.py) behind hooks/prevent-project-commit.sh.

Every case runs the wrapper end to end with a synthetic PreToolUse payload in a
scratch repository under a fresh temporary directory, and checks the exit code:
0 allows, 2 blocks. The cases port the retired shell smoke suite and add the
P1 ones: commands behind `timeout`, `nohup`, `xargs` and `nice`,
newline-separated commands, `git add <state> && git commit`, and `gh pr ready`
and `gh pr merge` without the user's AITK_PR_READY=1.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import git_guard  # noqa: E402
import shell_tokens  # noqa: E402
sys.path.pop(0)
from aitk.hooks import review_gate  # noqa: E402

STATE_FILES = git_guard.STATE_FILES
WRAPPER = ROOT / "hooks" / "prevent-project-commit.sh"
OVERRIDES = ("AITK_PR_READY", "SKIP_PR_GATE", "SKIP_PRECHECK")


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def base_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in OVERRIDES}
    env.pop("PYTHONPATH", None)
    return env


# Blocked in a repository where PROJECT.md is staged.
STAGED_BLOCK = (
    "git commit -m state",
    "cd {repo} && git commit -m state",
    "cd / && git -C {repo_rel} commit -m state",
    "cd / && env -C {repo} git commit -m state",
    "cd / && env --chdir={repo} git commit -m state",
    "env -C / true; git commit -m state",
    "cd / && GIT_DIR={repo}/.git GIT_WORK_TREE={repo} git commit -m state",
    "git --work-tree={repo} --git-dir={repo}/.git commit -m state",
    "git -c alias.ci=commit ci -m state",
    "git ci -m state",
    'f(){{ git "$@"; }}; f commit -m state',
    "g=git; $g commit -m state",
)

# Blocked in a repository with nothing staged in its default index.
CLEAN_BLOCK = (
    "GIT_INDEX_FILE={index} git commit -m state",
    # --no-verify, -n and signing overrides, in every spelling and wrapper
    "git commit --no-verify -m bad",
    "git commit --no-verif -m bad",
    "git commit --no-veri -m bad",
    "/usr/bin/git commit --no-verify -m bad",
    "git --no-pager commit --no-verify -m bad",
    "command git commit --no-verify -m bad",
    "env FOO=bar git commit --no-verify -m bad",
    "( git commit --no-verify -m bad )",
    "if git commit --no-verify -m bad; then echo ok; fi",
    "for x in 1; do git commit --no-verify -m bad; done",
    "sudo git commit --no-verify -m bad",
    "bash -lc 'git commit --no-verify -m bad'",
    "bash -lc -- 'git commit --no-verify -m bad'",
    "sh -c 'git commit --no-verify -m bad'",
    "sh -c -- 'git commit --no-verify -m bad'",
    "sh -c 'git \"$1\" --no-verify -m bad' x commit",
    'sh -c "git \\"\\$1\\" --no-verify -m bad" x commit',
    "zsh -c 'git commit --no-verify -m bad'",
    "zsh -c -- 'git commit --no-verify -m bad'",
    "sh -c 'git \"$@\"' sh commit --no-verify -m bad",
    'sh -c "git \\"\\$@\\"" sh commit --no-verify -m bad',
    "bash -lc 'f(){{ git commit --no-verify -m bad; }}; f'",
    'f(){{ git "$@"; }}; f commit --no-verify -m bad',
    'function f {{ git "$@"; }}; f commit --no-verify -m bad',
    'function f() {{ git "$@"; }}; f commit --no-verify -m bad',
    "bash -lc 'f(){{ git \"$@\"; }}; f commit --no-verify -m bad'",
    "bash -lc 'function f {{ git \"$@\"; }}; f commit --no-verify -m bad'",
    "g=git; $g commit --no-verify -m bad",
    "eval 'git commit --no-verify -m bad'",
    "git${{IFS}}commit --no-verify -m bad",
    "git${{IFS}} commit --no-verify -m bad",
    "git -c user.name=Test commit -n -m bad",
    "git -c alias.nv='commit --no-verify' nv -m bad",
    "git -c alias.nvshell='!git commit --no-verify' nvshell -m bad",
    "git -c alias.a='!git nv' -c alias.nv='commit --no-verify' a --allow-empty -m bad",
    "git -c alias.outer='!git -c alias.inner=\"commit --no-verify\" inner' outer --allow-empty -m bad",
    "git nv -m bad",
    "git nvshell -m bad",
    "GIT_CONFIG_GLOBAL={global_config} git bad -m bypass",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify' git nv -m bad",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify'; git nv -m bad",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null; git commit -m bad",
    "A='commit --no-verify' git --config-env=alias.nv=A nv -m bad",
    "export A='commit --no-verify'; git --config-env=alias.nv=A nv -m bad",
    "git -c core.hooksPath=/dev/null commit -m bad",
    "git -c commit.gpgsign=false commit -m bad",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m bad",
    "HP=/dev/null git --config-env=core.hooksPath=HP commit -m bad",
    "GS=false git --config-env=commit.gpgsign=GS commit -m bad",
    "git -C {repo} commit --no-verify -m bad",
    "git commit -nm bad",
    "git commit --no-gpg-sign -m bad",
    "git commit --no-gpg-sig -m bad",
    "git commit --no-g -m bad",
    # force-push and delete of main, and --no-verify on push
    "git push -f",
    "( git push -f )",
    "( git push --force )",
    "( git push -f origin )",
    "git -C {repo} push -f",
    "git push -f origin",
    "git push --force-w origin main",
    "git push --force-wi origin main",
    "git push --force-with origin main",
    "git push --force-with-l origin main",
    "git push --force-with-le origin main",
    "git push --force-with-lea origin main",
    "git push --force-with-leas origin main",
    "git push -f origin main",
    "git push -uf origin main",
    "git push --force-with-lease=refs/heads/main origin main",
    "git push -f origin HEAD",
    "git push --force --all origin",
    "git push --mirror --force origin",
    # a global option whose value is the next word hides nothing: `HEAD` is no subcommand
    "git --attr-source HEAD push -f origin main",
    "git --super-prefix sub/ push -f origin main",
    "git --attr-source=HEAD push -f origin main",
    "git --attr-source HEAD commit --no-verify -m bad",
    # a dashed entry point is the command it names, wherever the executable lives
    "git-push -f origin main",
    "git-push --no-verify origin feature",
    "git-commit --no-verify -m bad",
    "/usr/lib/git-core/git-push -f origin main",
    "$(git --exec-path)/git-push -f origin main",
    "\"$(git --exec-path)\"/git-push -f origin main",
    # a variable that holds a dashed entry point is read like the entry point
    "G=git-push; $G -f origin main",
    "G=/usr/lib/git-core/git-push; $G --force origin main",
    "G=git-push\n$G -f origin main",
    "git push --no-verify origin feature",
    "git push --no-verif origin feature",
    "git push --no-veri origin feature",
    "git -c alias.fpm='push --force origin main' fpm",
    "git -c alias.fpshell='!f(){{ git push --force origin main; }}; f' fpshell",
    "git fpm",
    "git fpshell",
    "git -c core.hooksPath=/dev/null push origin feature",
    "git push origin :main",
    "git push --delete origin main",
    "git push --del origin main",
    "git push --force origin :",
    "git push origin +:",
    "git push origin +main",
    "git push origin +HEAD:main",
    # command and process substitution
    "echo `git commit --no-verify -m bad`",
    ': "$(git commit --no-verify -m bad)"',
    "cat <(git commit --no-verify -m bad)",
    ': "$(git${{IFS}}commit --no-verify -m bad)"',
    "echo `git${{IFS}}commit --no-verify -m bad`",
    "cat <(git${{IFS}}commit --no-verify -m bad)",
    ': "$(git -c core.hooksPath=/dev/null commit -m bad)"',
    ': "$(g=git; $g commit --no-verify -m bad)"',
    # P1: wrappers that run the rest of the line, and newline-separated commands
    "timeout 60 git commit --no-verify -m bad",
    "timeout -s KILL 60 git push -f origin main",
    "nohup git push -f origin main",
    "nohup git commit -n -m bad &",
    "printf 'x\\n' | xargs git commit --no-verify -m",
    "xargs -n 1 git push --force origin main < /dev/null",
    "nice git commit --no-verify -m bad",
    "nice -n 5 git push -f origin main",
    "echo first\ngit commit --no-verify -m bad",
    "git status\ngit push -f origin main",
    "true\n\ntimeout 30 git commit -n -m bad",
    # P1: state files and .ai-toolkit/ added earlier in the same command
    "git add PROJECT.md && git commit -m state",
    "git add PROJECT.md; git commit -m state",
    "git add -A && git commit -m everything",
    "git add . && git commit -m everything",
    "git add .ai-toolkit/config.json && git commit -m config",
    "git add -f .ai-toolkit/config.json && git commit -m config",
    "git add notes.txt PLAN.md && git commit -m state",
    "git add PROJECT.md\ngit commit -m state",
    "timeout 60 git add PROJECT.md && nice git commit -m state",
    "git commit -m first; git add PROJECT.md && git commit -m state",
    # fused operator runs (`;(`, `&&(`, `)&&`, `);`, `)|`) split into the operators they are
    "git fetch;(git push -f origin main)",
    "git status&&(git push --force origin main)",
    "(git status)&&git push -f origin main",
    "(git status);git push -f origin main",
    "(git status)|git push -f origin main",
    "git status||(git push -f origin main)",
    "f()(git push -f origin main); f",
    "echo $(git status);git push -f origin main",
    # the git and gh heads on a case-insensitive filesystem run git and gh
    "GIT push --force origin main",
    "Git push -f origin main",
    "/usr/bin/GIT push -f origin main",
    "GIT-PUSH -f origin main",
    "git status; GIT commit --no-verify -m bad",
    "G=GIT-PUSH; $G -f origin main",
    # git for-each-repo runs the words after its options as a git command in each repository
    "git -c x.r=. for-each-repo --config=x.r push -f origin main",
    "git for-each-repo --config x.r push -f origin main",
    "git for-each-repo --keep-going --config=x.r push -f origin main",
    "git-for-each-repo --config=x.r push -f origin main",
    # a command mentioning GIT (any case) that does not parse
    "GIT commit -m 'unbalanced",
    # A command that mentions git and does not parse
    "git commit -m 'unbalanced",
)

CLEAN_ALLOW = (
    "echo --no-verify",
    "echo git commit --no-verify",
    "git commit -m 'mention -n flag'",
    "git commit -mnope",
    "git push -uf origin feature",
    "git push --force-with-lease origin feature",
    "git add notes.txt && git commit -m notes",
    "timeout 60 git commit -m fine",
    "nohup git push origin feature",
    "nice -n 5 git status",
    "echo first\ngit commit -m fine",
    "echo 'unbalanced",
    "ls -la",
    # ordinary operators and redirections stay whole when the runs are split
    "ls 2>&1 | tee out.txt",
    "ls &>/dev/null",
    "ls &>>out.txt && git status",
    "ls 2>&1|tee out.txt; git status",
    "git status;(git log --oneline)",
    "(git status)&&git log",
    "cat <<'EOF'\n);(\nEOF",
    "GIT status",
    "git for-each-repo --config=x.r maintenance run",
    # `-c alias.x` counts only among git's global options, not as a subcommand's own option
    "git grep -c alias.x docs/push.md",
    "git log -c alias.x push",
)

PR_PUBLISH_BLOCK = (
    # an alias set in the same segment as the text it runs
    "git config alias.x '!gh pr ready 12' && git x",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='!gh pr ready 12'; git x",
    "gh pr merge 12 --squash",
    "gh pr ready 12",
    "gh pr merge",
    "gh -R owner/repo pr merge 12",
    "gh pr merge --auto --squash 12",
    "SKIP_PR_GATE=1 gh pr ready 12",
    "SKIP_PR_GATE=1 gh pr merge 12",
    "timeout 30 gh pr merge 12",
    "nohup gh pr ready 12",
    "echo ok\ngh pr ready 12",
    "git status && gh pr merge 12",
    "bash -c 'gh pr merge 12'",
    "env FOO=1 gh pr ready 12",
    "gh pr merge 'unbalanced",
    # a typed override is not the user's: only the session environment counts
    "AITK_PR_READY=1 gh pr merge 12 --squash",
    "AITK_PR_READY=1 gh pr ready 12",
    "env AITK_PR_READY=1 gh pr ready 12",
    # behind a wrapper the tokenizer does not know, and through eval/-c with `--`
    "setsid gh pr ready 12",
    "setsid -w gh pr merge 12",
    "uv run gh pr merge 12 --squash",
    "flock /tmp/x gh pr merge 12",
    "chronic gh pr ready 12",
    "watch -n1 gh pr ready 12",
    "find . -maxdepth 0 -exec gh pr ready 12 \\;",
    "find . -maxdepth 0 -exec gh pr merge 12 \\;",
    "builtin command gh pr ready 12",
    "builtin command gh pr merge 12",
    "eval -- 'gh pr ready 12'",
    "eval -- 'gh pr merge 12'",
    "bash -c -- 'gh pr merge 12'",
    "setsid bash -c 'gh pr ready 12'",
    "uv run env FOO=1 gh pr ready 12",
    "setsid sh -c 'cd . && gh pr merge 12'",
    "flock /tmp/x -c 'gh pr merge 12'",
    "su -c 'gh pr ready 12'",
    "script -qc 'gh pr merge 12' /dev/null",
    # a gh or git word that is only an argument of the wrapper comes first
    "flock /tmp/gh gh pr merge 12",
    "find . -name git -exec gh pr merge 12 \\;",
    "find ~/src/gh -maxdepth 0 -exec gh pr ready 12 \\;",
    "find . -maxdepth 0 -name gh -o -exec gh pr ready 12 \\;",
    "uv run --with git gh pr merge 12",
    # a function body runs when the function is called, whatever its name
    "echo() {{ gh pr ready 12; }}; echo",
    "gh() {{ command gh pr merge 12; }}; gh",
    "function gh {{ command gh pr merge 12; }}; gh",
    # git runs a shell for these
    "git rebase -x 'gh pr merge 12' HEAD~1",
    "git rebase -i -x 'gh pr ready 12' HEAD~2",
    "git rebase -ix 'gh pr ready 12' HEAD~2",
    "git rebase --exec 'gh pr ready 12' HEAD~1",
    "git rebase --exec='gh pr ready 12' main",
    "git -C . rebase -x'gh pr merge 12' main",
    "git bisect run gh pr ready 12",
    "git submodule foreach gh pr merge 12",
    "git submodule foreach --recursive 'gh pr merge 12'",
    "git -c alias.x='!gh pr ready 12' x",
    "uv run git rebase -x 'gh pr ready 12' main",
    "git --attr-source HEAD rebase -x 'gh pr merge 12' main",
    # a dashed entry point hands text on exactly as `git rebase` and the others do
    "git-rebase -x 'gh pr merge 12' HEAD~1",
    "git-rebase --exec='gh pr ready 12' main",
    "git-bisect run gh pr ready 12",
    "git-submodule foreach gh pr merge 12",
    "git submodule--helper foreach gh pr merge 12",
    "git-submodule--helper foreach gh pr merge 12",
    "/usr/lib/git-core/git-rebase -x 'gh pr ready 12' main",
    "$(git --exec-path)/git-rebase -x 'gh pr ready 12' main",
    "setsid git-rebase -x 'gh pr merge 12' main",
    # a git-* head that git does not install is an ordinary executable, rescanned like any
    "./git-run gh pr merge 12",
    "git-x sh -c \"gh pr merge 12\"",
    "/opt/x/git-wrap env gh pr ready 12",
    "git-wrap gh pr ready 12",
    # writing an alias that holds the text is a mention in a git segment too
    "git config alias.m '!gh pr merge'",
    "git config --global alias.m '!gh pr merge 12'",
    "git -C . config --add alias.m '!gh pr ready 12'",
    "git-config alias.m '!gh pr merge'",
    # a backslash-newline inside single quotes survives the tokenizer and splits `pr`
    "git -c 'alias.x=!gh p\\\nr merge 12' x",
    "git submodule foreach 'gh p\\\nr ready 12'",
    # git joins these words into one shell command, so their quoting survives
    "git bisect run sh -c 'gh pr merge 12'",
    "git submodule foreach sh -c 'gh pr merge 12'",
    "git submodule foreach bash -c 'gh pr ready 12'",
    "git submodule foreach --recursive sh -c 'gh pr merge 12'",
    # an inline alias runs with the words after its name appended
    "git -c alias.x='!gh' x pr merge 12",
    "git -c alias.x='!gh' x pr ready 12",
    "git -c alias.X='!gh' x pr merge 12",
    "git -c alias.x='!git' x -c alias.y='!gh pr merge 12' y",
    # an alias chain: an inline alias that names another, `!` text, or a git command line
    "git -c alias.x='!git' -c alias.y='!gh' x y pr merge 12",
    "git -c alias.x=y -c alias.y='!gh' x pr merge 12",
    "git -c alias.x=y -c alias.y=z -c alias.z='!gh' x pr ready 12",
    "git -c alias.r='rebase -x \"gh pr merge 12\"' r HEAD~1",
    "git -c alias.r=rebase r -x 'gh pr merge 12' HEAD~1",
    "git -c alias.r=rebase -c alias.q=r q --exec='gh pr ready 12' HEAD~1",
    "git -c alias.s=submodule s foreach gh pr merge 12",
    # the same through the environment git reads its config from, when it is visible
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='!gh pr ready 12' git x",
    "GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0=y GIT_CONFIG_KEY_1=alias.y GIT_CONFIG_VALUE_1='!gh' git x pr merge 12",
    "A='!gh pr ready 12' git --config-env=alias.x=A x",
    # an inline alias next to a gated mention blocks whatever the alias is: the
    # guard never decides whether git runs it (git ignores an alias that shadows a builtin)
    "git -c alias.rebase=status rebase -x \"gh pr merge 12\" HEAD~1",
    "git -c alias.rebase='!true' rebase -x \"gh pr merge 12\" HEAD~1",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=\"!gh pr merge 12\" setsid git p",
    "git -c alias.p=push -c alias.x='!flock /tmp/x git p' x",
    "git -c alias.p=push -c alias.x='!env GIT_CONFIG_COUNT=0 git p' x",
    "git -c alias.p=push p origin feature",  # accepted over-block: a push through an inline alias
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=ALIAS.p GIT_CONFIG_VALUE_0=push uv run git p",
    "A='!gh pr merge 12' git --config-env alias.p=A p",
    "git -calias.p=push p",
    # git runs the first word of foreach and bisect run as shell text when it has
    # whitespace, and appends the other words
    "git submodule foreach 'gh pr merge' 12",
    "git submodule foreach --recursive 'gh pr ready' 12",
    "git bisect run 'gh pr merge' 12",
    # git joins the words of a payload, so the quoting a shell removes is stripped before the match
    "git submodule foreach \"gh''\" pr merge 12",
    "git bisect run \"gh''\" pr ready 12",
    "git bisect run \"git''\" push",
    "git rebase -x 'gh\"\" pr ready 12' HEAD~1",
    # accepted over-block: the body of an inline alias is walked even when the
    # command never runs it
    "git -c alias.x='!gh pr ready 12' status",
    # accepted over-block: a quoted `()` followed by a quoted `{` reads as a function head
    "echo '()' '{{' gh pr ready 12",
    # a function head is `name()` followed by its `{` body
    "f(){{ gh pr ready 12; }}; f",
    "f() {{ gh pr merge 12; }}; f",
    # fused operator runs hide the command after them unless they are split
    "git status;(gh pr merge 12)",
    "git status&&(gh pr merge 12)",
    "(git status)&&gh pr merge 12",
    "(git status)|gh pr merge 12",
    "(git status);gh pr merge 12",
    "echo $(git status); gh pr merge 12",
    "x=$(git status); gh pr merge 12",
    "f()(gh pr merge 12); f",
    # the gh head on a case-insensitive filesystem runs gh
    "GH pr merge 12",
    "Gh pr ready 12",
    "/usr/local/bin/GH pr merge 12",
    "setsid GH pr merge 12",
    "git status; GIT submodule foreach 'gh pr merge' 12",
    # git for-each-repo hands the words after its options to git in each repository
    "git for-each-repo --config=x.r sh -c 'gh pr merge 12'",
    "git -c x.r=. for-each-repo --config=x.r push origin feature",
    # `-c alias.x` among git's global options is an inline alias
    "git -c alias.m='!gh pr merge' m 12",
)

# Known limits of the default traversal behind the wrappers it rescans through (the
# git_guard module docstring lists them): a real `gh pr ready` or `gh pr merge` the
# guard does not see, so it is allowed. The protection that holds is the session
# environment: no override there, no ready PR from the toolkit's own commands.
PR_PUBLISH_LIMITS = (
    "g=gh; $g pr merge 12",
    "watch 'gh pr ready 12'",
    "tmux new-session -d 'gh pr merge 12'",
    # other places git runs a shell it was given: filters
    "git filter-branch --index-filter 'gh pr ready 12' HEAD",
    # the whole class: a git config value or a tool option that git runs through a shell,
    # other than `-c alias.*` (the representatives; core.editor, sequence.editor,
    # diff.external, core.sshCommand, mergetool.<n>.cmd and `--config-env` are the same)
    "git -c core.pager='gh pr ready 12' log",
    "git -c credential.helper='!gh pr ready 12' fetch",
    "git difftool -x 'gh pr ready 12'",
    "git -c sequence.editor='gh pr ready 12' rebase -i HEAD~1",
    # the same alias through an environment an earlier command exported, the text and the
    # alias key never in one segment: not visible here
    "export A='!gh pr ready 12'; git --config-env=alias.x=A x",
    "V='!gh pr ready 12'; export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0=$V; git x",
    # the persistent two-step alias: writing `git config alias.m '!gh pr merge'` blocks, but
    # a value routed through a variable is not text in the segment, and the alias used by a
    # later command (`git m 12`, a file or an earlier call set it) is an ordinary git command
    "V='!gh pr merge'; git config alias.m \"$V\"; git m 12",
    "git m 12",
    # an alias value assigned in the environment of a shell, the key set inside its payload
    "env A='!gh pr merge 12' sh -c 'git --config-env=alias.x=A x'",
)

PR_PUBLISH_ALLOW = (
    "gh pr ready 12 --undo",
    "gh pr merge --help",
    "gh pr view 12",
    "GH pr view 12",
    "gh pr checks 12",
    "gh pr create --draft --title t --body b",
    "echo gh pr merge",
    "printf 'gh pr merge\\n'",
    "setsid gh pr view 12",
    "uv run gh pr ready 12 --undo",
    "uv run pytest tests/",
    "gcc -c main.c",
    "python3 -c 'print(1)'",
    "flock /tmp/x git status",
    "find . -name '*.py' -exec grep -l gh {{}} \\;",
    "flock /tmp/gh git status",
    "find . -exec grep x {{}} \\;",
    "find . -name git -exec grep x {{}} \\;",
    "echo gh pr ready",
    "echo hi",
    "echo() {{ echo hi; }}; echo",
    "uv run pytest",
    "git status",
    "git rebase -i HEAD~3",
    "git rebase -x 'make test' main",
    "git rebase --exec 'pytest -q' main",
    "git submodule update --init",
    "git submodule foreach 'git status'",
    "git bisect start",
    "git bisect run make test",
    "git -c alias.x='!git status' x",
    "git -c alias.st=status st",
    "git -C '~' status",
    # an inline alias without a gated mention is not unreadable, whatever it is
    "git -c alias.x=\"foo 'bar\" x",
    "git -c alias.x=y -c alias.y=x x",
    "git -c alias.x='--no-pager log' x",
    "git -c alias.st=status st && gh pr view 12",
    "git rebase -x 'make test' HEAD~1",
    "git rebase -ix 'pytest -q' HEAD~2",
    "git bisect run ./t.sh",
    "git submodule foreach 'echo $name'",
    "git -c alias.st=status -c alias.s=st s -sb",
    # a bare `alias.NAME` word is a name, not a configured alias
    "grep alias.x",
    "rg alias.cleanup",
    "gh pr view alias.cleanup",
    "git push origin alias.cleanup",
    "grep -rn alias.x docs/push.md",
    "grep -c alias.x docs/push.md",
    "rg -c alias.cleanup push.md",
    "git grep alias.cleanup -- push.sh",
    "git-push origin alias.cleanup",
    "git --attr-source HEAD status",
    "git --attr-source HEAD push origin feature",
    "git-push origin feature",
    "$(git --exec-path)/git-status",
    "git-rebase -x 'make test' main",
    "git submodule--helper foreach 'echo $name'",
    "git -c alias.l='log --oneline' l -5",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.st GIT_CONFIG_VALUE_0=status git st",
    "git -c core.pager=cat log",
    # a quoted `()` is an argument, not a function head
    "echo '()' gh pr ready 12",
    "echo '()'",
    # a quoted argument stays one word: no unresolved command
    "git bisect run ./t.sh \"it's\"",
    "git submodule foreach ./t.sh \"it's\"",
)

# Blocked whatever they run: the command sets, appends to or exports an override.
OVERRIDE_ASSIGNMENT_BLOCK = (
    # operator runs the lexer used to fuse into one token are split, so the subshell or
    # function body after them is read
    "(>/dev/null AITK_PR_READY=1 bin/aitk deliver)",
    "f()( AITK_PR_READY=1 bin/aitk deliver ); f",
    "f()(AITK_PR_READY=1 bin/aitk deliver); f",
    "true;(AITK_PR_READY=1 bin/aitk deliver)",
    "true;(AITK_PR_READY='0 1' bin/aitk deliver)",
    "true;(typeset -xF SKIP_PRECHECK=0)",
    "(true)&&AITK_PR_READY=1 bin/aitk deliver",
    "true&&(AITK_PR_READY=1 bin/aitk deliver)",
    "true|(AITK_PR_READY=1 bin/aitk deliver)",
    "AITK_PR_READY=1 gh pr ready 12",
    "env SKIP_PR_GATE=1 gh pr create --draft --fill",
    "SKIP_PRECHECK=1 git push",
    "export AITK_PR_READY=1; bin/aitk deliver --ready",
    "AITK_PR_READY=1 uv run aitk deliver --ready",
    "eval -- 'SKIP_PRECHECK=1 true'",
    "builtin eval -- 'SKIP_PR_GATE=1 true'",
    "bash -c -- 'SKIP_PRECHECK=1 true'",
    "uv run bash -c -- 'AITK_PR_READY=1 bin/aitk deliver'",
    "bash -c 'AITK_PR_READY=1 gh pr ready 12'",
    "AITK_PR_READY=yes gh pr view 12",
    "AITK_PR_READY=1; export AITK_PR_READY; uv run aitk deliver --ready",
    "set -a; AITK_PR_READY=1; uv run aitk deliver --ready",
    "SKIP_PRECHECK=1; git push",
    "AITK_PR_READY=1",
    "env AITK_PR_READY=1",
    "{{ AITK_PR_READY=1; }}; gh pr ready 12",
    "export AITK_PR_READY",
    "typeset -x SKIP_PR_GATE",
    "declare -x AITK_PR_READY=1; gh pr ready 12",
    "readonly SKIP_PRECHECK=1; git push",
    "export AITK_PR_READY=1 SKIP_PR_GATE=1",
    "bash -c 'AITK_PR_READY=1; export AITK_PR_READY; gh pr ready 12'",
    "x=$(SKIP_PR_GATE=1; gh pr create --fill)",
    "export AITK_PR_READY; uv run aitk deliver --ready 'unbalanced",
    "AITK_PR_READY+=1 uv run aitk deliver --ready",
    "AITK_PR_READY+=0",
    "AITK_PR_READY+=false",
    "AITK_PR_READY+=",
    "FOO+=x SKIP_PRECHECK=1 git push",
    "export AITK_PR_READY+=0",
    "builtin export AITK_PR_READY=1",
    "command export AITK_PR_READY=1",
    "command builtin export AITK_PR_READY+=1",
    "builtin command export AITK_PR_READY=1",
    "builtin declare -x SKIP_PR_GATE+=false",
    "bash -c 'AITK_PR_READY+=1; true'",
    "builtin eval 'SKIP_PRECHECK+=1; true'",
    "env -S 'AITK_PR_READY+=1 uv run aitk deliver --ready'",
    "AITK_PR_READY=1 bash -c ''",
    "AITK_PR_READY+=1 uv run aitk deliver --ready 'unbalanced",
    "builtin export AITK_PR_READY; uv run aitk deliver --ready 'unbalanced",
    # redirections stand anywhere in a simple command, ahead of a prefix too
    "2>&1 AITK_PR_READY=1 bin/aitk deliver --ready",
    "2>/dev/null AITK_PR_READY=1 bin/aitk deliver --ready",
    ">out.txt SKIP_PR_GATE=1 gh pr create --fill",
    "&>>log.txt SKIP_PRECHECK=1 git push",
    "env >out.txt AITK_PR_READY=1 bin/aitk deliver --ready",
    # a function body runs when the function is called
    "f() {{ AITK_PR_READY=1 bin/aitk deliver --ready; }}; f",
    "function f {{ AITK_PR_READY=1 bin/aitk deliver --ready; }}; f",
    "function f() {{ export SKIP_PR_GATE=1; }}; f",
    # env, a shell or eval behind a wrapper the tokenizer does not know
    "setsid env AITK_PR_READY=1 bin/aitk deliver --ready",
    "uv run env SKIP_PR_GATE=1 gh pr create --fill",
    "find . -exec env AITK_PR_READY=1 bin/aitk deliver --ready \\;",
    "setsid bash -c 'export AITK_PR_READY=1; bin/aitk deliver --ready'",
    "echo env AITK_PR_READY=1",
    # arithmetic and nameref declarations: the value is not the literal text
    "declare -ix AITK_PR_READY=false",
    "declare -i count='AITK_PR_READY=1'",
    "declare -n ref=AITK_PR_READY; ref=1",
    # value-changing attributes and quoted or split values the scan resolves
    "integer -x AITK_PR_READY=1; bin/aitk deliver --ready",
    "float -x AITK_PR_READY=0; bin/aitk deliver --ready",
    "false=1; typeset -xF AITK_PR_READY=false; bin/aitk deliver --ready",
    "typeset -xZ5 AITK_PR_READY=0; bin/aitk deliver --ready",
    "AITK_PR_READY='0 1' bin/aitk deliver --ready",
    "bash -c 'AITK_PR_READ''Y=1 bin/aitk deliver --ready'",
    "eval 'AITK_PR_READ''Y=\"0 1\" bin/aitk deliver --ready'",
    "AITK_PR_READY\\\n=1 bin/aitk deliver --ready",
)

# Known limits of the token scan (the git_guard module docstring lists the
# classes). Each is a real override the scan does not see, so the hook allows it:
# a tripwire, not a sandbox. The protection that holds is elsewhere: `bin/aitk
# deliver` cannot open a ready PR, and `gh pr ready`/`gh pr merge` read the
# override only from the session environment. The test below pins this list so a
# fix moves the case into OVERRIDE_ASSIGNMENT_BLOCK and the docstring stays true.
OVERRIDE_SCAN_LIMITS = (
    # a redirection operator erased together with a quoted or numeric option value
    "env -u '>' AITK_PR_READY=1 bin/aitk deliver",
    "env -u 1 >/dev/null AITK_PR_READY=1 bin/aitk deliver",
    # shell-specific grammar: zsh anonymous functions and precommand modifiers, a
    # function named after a wrapper, a `-c --` payload, a nameref set by a plain value
    "() {{ AITK_PR_READY=1 bin/aitk deliver; }}",
    "env() {{ AITK_PR_READY=1 bin/aitk deliver; }}; env",
    "nocorrect AITK_PR_READY=1 bin/aitk deliver",
    "repeat 1 AITK_PR_READY=1 bin/aitk deliver",
    "coproc AITK_PR_READY=1 bin/aitk deliver",
    "declare -n r; r=AITK_PR_READY; declare -x r=1; bin/aitk deliver",
    # brace expansion builds the name
    "env {{AITK_PR_READY,X}}=1 bin/aitk deliver",
    "export {{AITK_PR_READY,X}}=1; bin/aitk deliver",
    # arithmetic and parameter-expansion setters (these export under `set -a`)
    "set -a; (( AITK_PR_READY = 1 )); bin/aitk deliver",
    "set -a; let SKIP_PRECHECK++; git push",
    "export AITK_PR_READY=0; ((++AITK_PR_READY)); bin/aitk deliver",
    "let AITK_PR_READY=1; bin/aitk deliver",
    "AITK_PR_READY[0]=1; bin/aitk deliver",
    "set -a; : ${{AITK_PR_READY:=1}}; bin/aitk deliver",
    "set -a; : ${{AITK_PR_READY=1}}; bin/aitk deliver",
    # values the tokenizer reads as falsy or empty
    "AITK_PR_READY=(1) bin/aitk deliver",
    "AITK_PR_READY=0\r1 bin/aitk deliver",
    "AITK_PR_READY=<(true) bin/aitk deliver",
    # a name quoted with a locale string
    "export AITK_PR_$\"READY\"=1; bin/aitk deliver",
    # write targets that are not assignments, scripts run separately, names built at run time
    "set -a; read AITK_PR_READY <<< 1; bin/aitk deliver",
    "set -a; printf -v AITK_PR_READY 1; bin/aitk deliver",
    "set -a; mapfile -t AITK_PR_READY <<< 1; bin/aitk deliver",
    "source ./set-override.sh; bin/aitk deliver",
    ". ./set-override.sh; bin/aitk deliver",
    "v=AITK_PR_READY; export \"${{!v}}\"=1; bin/aitk deliver",
    "X=READY; eval \"AITK_PR_$X=1\"; bin/aitk deliver",
    "export $'\\x41ITK_PR_READY=1'; bin/aitk deliver",
    "env $(printf 'AITK_PR_READY=1') bin/aitk deliver",
    # an alias body is quoted text, and a profile write alters later shell startup
    "alias deliver='AITK_PR_READY=1 bin/aitk deliver'; deliver",
    "echo 'export AITK_PR_READY=1' >> ~/.zshrc",
    # heredoc bodies are skipped, so a body piped to a shell is not read
    "bash <<'EOF'\nAITK_PR_READY=1 bin/aitk deliver\nEOF",
    "cat <<'EOF'\nSKIP_PRECHECK=1\nEOF",
)

# Read-only mentions and clean false assignments stay allowed.
OVERRIDE_ASSIGNMENT_ALLOW = (
    "grep -rn AITK_PR_READY .",
    "git log --grep=AITK_PR_READY",
    "echo \"$AITK_PR_READY\"",
    "declare -p AITK_PR_READY",
    "env -u AITK_PR_READY git status",
    "echo AITK_PR_READY_X=1",
    "echo XAITK_PR_READY=1",
    # the plan's ALLOW cases: text that only mentions an assignment is not one
    "echo AITK_PR_READY=1",
    "echo AITK_PR_READY+=1",
    "git push # SKIP_PRECHECK=1",
    "git log --grep=SKIP_PRECHECK=1",
    # ordinary commands whose text happens to carry export wording and a name
    "git commit -m 'fix: export check' -m 'AITK_PR_READY=1 now counts only from the session'",
    "git grep 'integer.*AITK_PR_READY'",
    "git grep -n 'declare -n.*SKIP_PR_GATE'",
    "echo AITK_PR_READY=0",
    "echo AITK_PR_READY=false",
    "echo AITK_PR_READY=no",
    "echo AITK_PR_READY=off",
    "echo AITK_PR_READY=''",
    "echo AITK_PR_READY=\"0\"",
    "echo AITK_PR_READY='FALSE'",
    "echo AITK_PR_READY=\"off\"",
    "builtin export AITK_PR_READY=0",
    "command builtin export SKIP_PR_GATE=false",
    "builtin command export SKIP_PRECHECK=",
    "FOO+=x git status",
    "AITK_PR_READY=0 gh pr view 12",
    "AITK_PR_READY=0",
    "export AITK_PR_READY=0",
    "export SKIP_PR_GATE=",
    "unset AITK_PR_READY",
    "printenv AITK_PR_READY",
    "FOO=1 git status",
    "FOO=1",
    "git log --oneline 2>&1 | head",
    "echo env FOO=1",
    "declare -i count=1",
    "f() {{ git status; }}; f",
)


class GitGuardHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        base = Path(cls.temporary.name).resolve()
        cls.global_config = base / "global.gitconfig"
        cls.staged = cls.make_repo(base / "staged")
        cls.clean = cls.make_repo(base / "clean")
        cls.alt_index = base / "alt.index"

        # PROJECT.md staged in the default index of one repository, and every
        # state file staged in its own non-default index.
        (cls.staged / "PROJECT.md").write_text("state\n")
        git(cls.staged, "add", "PROJECT.md")
        for state_file in STATE_FILES:
            (cls.staged / state_file).write_text("state\n")
            index = {"GIT_INDEX_FILE": str(cls.staged / f"{state_file}.index")}
            git(cls.staged, "read-tree", "--empty", env=index)
            git(cls.staged, "add", state_file, env=index)

        # The other repository stages nothing by default; PROJECT.md sits in an
        # alternate index, and state files and .ai-toolkit/ wait unstaged.
        for name in ("PROJECT.md", "PLAN.md", "notes.txt"):
            (cls.clean / name).write_text("state\n")
        (cls.clean / ".ai-toolkit").mkdir()
        (cls.clean / ".ai-toolkit" / "config.json").write_text("{}\n")
        git(cls.clean, "add", "PROJECT.md", env={"GIT_INDEX_FILE": str(cls.alt_index)})

        git(
            cls.clean,
            "config",
            "--global",
            "alias.bad",
            "commit --no-verify",
            env={"GIT_CONFIG_GLOBAL": str(cls.global_config)},
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def make_repo(cls, path: Path) -> Path:
        path.mkdir()
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        git(path, "config", "alias.ci", "commit")
        git(path, "config", "alias.nv", "commit --no-verify")
        git(path, "config", "alias.nvshell", "!git commit --no-verify")
        git(path, "config", "alias.fpm", "push --force origin main")
        git(path, "config", "alias.fpshell", "!f(){ git push --force origin main; }; f")
        return path

    def expand(self, template: str, repo: Path) -> str:
        return template.format(
            repo=repo,
            repo_rel=str(repo).lstrip("/"),
            index=self.alt_index,
            global_config=self.global_config,
        )

    def run_hook(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str] | None = None,
        wrapper_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
        return subprocess.run(
            ["bash", str(WRAPPER)],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            env=wrapper_env if wrapper_env is not None else {**base_env(), **(env or {})},
            timeout=60,
        )

    def assert_cases(self, templates: tuple[str, ...], repo: Path, expected: int, **kwargs) -> None:
        for template in templates:
            command = self.expand(template, repo)
            with self.subTest(command=command, expected=expected):
                result = self.run_hook(command, repo, **kwargs)
                self.assertEqual(expected, result.returncode, result.stderr)
                if expected == 2:
                    self.assertIn("BLOCKED", result.stderr)

    def test_staged_state_files_block_a_commit(self) -> None:
        self.assert_cases(STAGED_BLOCK, self.staged, 2)

    def test_every_state_file_in_a_non_default_index_blocks(self) -> None:
        templates = tuple(
            f"GIT_INDEX_FILE={{repo}}/{state_file}.index git commit -m state" for state_file in STATE_FILES
        )
        self.assert_cases(templates, self.staged, 2)

    def test_bypasses_and_force_pushes_block(self) -> None:
        self.assert_cases(CLEAN_BLOCK, self.clean, 2)

    def test_ordinary_commands_are_allowed(self) -> None:
        self.assert_cases(CLEAN_ALLOW, self.clean, 0)
        self.assert_cases(("echo --no-verify", "echo git commit --no-verify"), self.staged, 0)

    def test_state_commit_names_the_files(self) -> None:
        result = self.run_hook("git add .ai-toolkit/config.json && git commit -m config", self.clean)
        self.assertEqual(2, result.returncode)
        self.assertIn(".ai-toolkit/config.json", result.stderr)
        self.assertIn("stay out of commits", result.stderr)

    def test_pr_ready_and_merge_need_the_users_override(self) -> None:
        self.assert_cases(PR_PUBLISH_BLOCK, self.clean, 2)
        self.assert_cases(PR_PUBLISH_BLOCK, self.clean, 2, env={"SKIP_PR_GATE": "1"})
        self.assert_cases(PR_PUBLISH_ALLOW, self.clean, 0)
        self.assert_cases(PR_PUBLISH_LIMITS, self.clean, 0)
        self.assert_cases(
            ("gh pr merge 12 --squash", "gh pr ready 12", "nohup gh pr ready 12"),
            self.clean,
            0,
            env={"AITK_PR_READY": "1"},
        )
        for falsy in ("0", "false", "no", "off", "OFF", " No ", ""):
            with self.subTest(falsy=falsy):
                self.assert_cases(("gh pr ready 12",), self.clean, 2, env={"AITK_PR_READY": falsy})
        merge = self.run_hook("gh pr merge 12", self.clean)
        self.assertIn("ask the user", merge.stderr)
        self.assertNotIn("AITK_PR_READY", merge.stderr)

    def test_a_long_run_of_rescan_words_stays_fast_and_blocks(self) -> None:
        # Every later rescan word used to be rescanned again from each of its own later
        # words, so the work grew with the fourth power of the word count.
        for text in (
            "true " + "sh " * 200 + "; gh pr merge 12",
            "true " + "sh " * 200 + "gh pr merge 12",
            "true " + "sh env " * 100 + "; gh pr ready 12",
            "true " + "sh " * 4000 + "gh pr merge 12",  # past the work budget: fail-safe
        ):
            with self.subTest(words=len(text.split())):
                started = time.monotonic()
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, str(self.clean), {})
                self.assertLess(time.monotonic() - started, 3.0)
        walked = list(shell_tokens.commands("true " + "sh " * 200 + "; gh pr merge 12", str(self.clean)))
        self.assertLess(len(walked), 1000)
        self.assertEqual(["gh", "pr", "merge", "12"], walked[-1].argv)

    def test_the_work_budget_counts_characters_not_words(self) -> None:
        # Few words, one very long one: every rescan tail carries the long word, so
        # the cost is in characters (the word count alone let these run for ~40s).
        gh_run = "true " + "gh " * 300 + "x" * 100_000 + "; gh pr merge 12"
        sh_run = "true " + "sh " * 400 + "'" + "x" * 100_000 + "'; gh pr create --fill"
        for name, text in (("gh300", gh_run), ("sh400", sh_run)):
            with self.subTest(case=name):
                started = time.monotonic()
                walked = list(shell_tokens.commands(text, str(self.clean)))
                self.assertLess(time.monotonic() - started, 3.0)
                self.assertTrue(any(found.unreadable for found in walked))
                started = time.monotonic()
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, str(self.clean), {})
                self.assertLess(time.monotonic() - started, 3.0)
                started = time.monotonic()
                result = self.run_hook(text, self.clean)
                self.assertLess(time.monotonic() - started, 5.0)
                self.assertEqual(2, result.returncode, result.stderr)
        # an ordinary long command is under the cap: still read in full
        body = "x" * 50_000
        walked = list(shell_tokens.commands(f"flock /tmp/x gh pr merge 12 --body {body}", str(self.clean)))
        self.assertFalse(any(found.unreadable for found in walked))
        self.assertIn("gh", [found.name for found in walked])

    def test_an_exhausted_budget_fails_closed_whatever_the_text_says(self) -> None:
        cwd = str(self.clean)
        spent = "true " + "sh " * 4000
        for text in (
            spent + "; git -c alias.x=\"!g'h' pr merge 12\" x",  # no contiguous gh in the segment
            spent + "; gh pr merge 12",
            spent + "gh pr merge 12",
            spent + "; echo hi",  # an exhausted segment is unreadable, not a text match
            "true " + "sh " * 4000,
        ):
            with self.subTest(words=len(text.split()), tail=text[len(spent) :]):
                with self.assertRaises(git_guard.Blocked) as caught:
                    git_guard.evaluate(text, cwd, {})
                self.assertIn("gh pr", str(caught.exception))
                result = self.run_hook(text, self.clean)
                self.assertEqual(2, result.returncode, result.stderr)
        exhausted = [found for found in shell_tokens.commands(spent, cwd) if found.unreadable]
        self.assertEqual([None], [found.workdir for found in exhausted])
        self.assertTrue(all(found.unresolved for found in exhausted))
        # the user's session override still lifts the block, as for any gh pr publish
        git_guard.evaluate(spent + "; gh pr merge 12", cwd, {"AITK_PR_READY": "1"})

    def test_a_101_entry_config_prefix_with_an_alias_on_the_last_entry_blocks(self) -> None:
        # No count is parsed: the alias key anywhere in the prefix, next to a gated mention, blocks.
        filler = " ".join(f"GIT_CONFIG_KEY_{n}=core.x{n} GIT_CONFIG_VALUE_{n}=v" for n in range(100))
        prefix = f"GIT_CONFIG_COUNT=101 {filler} GIT_CONFIG_KEY_100=alias.p"
        for wrapper in ("", "setsid ", "uv run ", "flock /tmp/x "):
            text = f"{prefix} GIT_CONFIG_VALUE_100='!gh pr merge 12' {wrapper}git p"
            with self.subTest(wrapper=wrapper):
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, str(self.clean), {})
        # the same prefix without a gated mention is an ordinary command
        git_guard.evaluate(f"{prefix} GIT_CONFIG_VALUE_100=status git p", str(self.clean), {})

    def test_a_git_run_payload_or_inline_alias_with_a_gated_mention_is_unreadable(self) -> None:
        cwd = str(self.clean)
        for text in (
            "git rebase -x 'gh pr merge 12' HEAD~1",
            "git bisect run \"git''\" push",
            "git submodule foreach \"gh''\" pr merge 12",
            "git -c alias.rebase=status rebase -x 'gh pr merge 12' HEAD~1",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0='!gh pr merge 12' setsid git p",
        ):
            with self.subTest(text=text):
                walked = list(shell_tokens.commands(text, cwd))
                self.assertTrue(any(found.unreadable and found.unresolved for found in walked))
        for text in (
            "git rebase -x 'make test' HEAD~1",
            "git bisect run ./t.sh",
            "git submodule foreach 'echo $name'",
            "git -c alias.st=status st",
            "git -c alias.st=status st; gh pr view 12",
        ):
            with self.subTest(text=text):
                self.assertFalse(any(found.unreadable for found in shell_tokens.commands(text, cwd)))

    def test_what_mentions_a_gated_operation(self) -> None:
        for text in (
            "gh pr merge 12", "gh -R o/r pr view 12", "g\\h pr ready", "\"gh''\" pr create", "git push",
            "git'' push", "`gh` pr list", "echo push", "pr merge 12", "pr ready", "pr create --fill",
            "$g pr new", "make push",
            "gh p\\\nr create", "!gh p\\\nr merge", "g\\\nh pr ready",  # a backslash-newline joins the words
        ):
            with self.subTest(text=text):
                self.assertTrue(shell_tokens.mentions_gated(text))
        for text in (
            "make test", "echo $name", "git status", "gh repo view", "gh issue list", "pushd /tmp",
            "git log --oneline", "pr", "",
        ):
            with self.subTest(text=text):
                self.assertFalse(shell_tokens.mentions_gated(text))

    def test_which_words_configure_an_inline_alias(self) -> None:
        # the prefixed forms need no context; a bare `alias.NAME` is a name unless it is the
        # value of -c/--config-env, an `alias.NAME=` word beside a git word, or a git config word
        for segment, configures, expected in (
            (["git", "-calias.x=y", "x"], False, True),
            (["git", "--config-env=alias.x=A", "x"], False, True),
            (["GIT_CONFIG_KEY_0=alias.x", "git", "x"], False, True),
            (["git", "-c", "alias.x=y", "x"], False, True),
            (["g", "-c", "alias.x", "x"], False, False),  # no git word: an accepted limit
            (["git", "-C", "d", "-c", "alias.x", "x"], False, True),
            (["git-push", "-c", "alias.x", "x"], False, True),
            (["./git-run", "-c", "alias.x=y", "x"], False, False),
            (["g", "--config-env", "alias.x=A", "x"], False, True),
            (["git", "alias.x=y"], False, True),
            (["/usr/bin/git", "alias.x=y"], False, True),
            (["git-config", "alias.x=y"], False, True),
            (["git", "config", "alias.x", "!gh"], True, True),
            (["grep", "alias.x"], False, False),
            (["grep", "-c", "alias.push", "docs"], False, False),
            (["rg", "-c", "alias.x", "push.md"], False, False),
            (["grep", "alias.x=1"], False, False),
            (["rg", "alias.cleanup"], False, False),
            (["gh", "pr", "view", "alias.cleanup"], False, False),
            (["git", "push", "origin", "alias.cleanup"], False, False),
            (["git", "log", "alias.x"], False, False),
        ):
            with self.subTest(segment=segment, configures=configures):
                self.assertEqual(expected, shell_tokens.sets_inline_alias(segment, configures))

    def test_a_dashed_git_entry_point_is_git_and_its_subcommand(self) -> None:
        for argv, expected in (
            (["git", "push", "x"], ["git", "push", "x"]),
            (["/usr/bin/git", "push"], ["/usr/bin/git", "push"]),
            (["git-push", "origin", "x"], ["git", "push", "origin", "x"]),
            (["/usr/lib/git-core/git-rebase", "-x", "t"], ["git", "rebase", "-x", "t"]),
            (["git-submodule--helper", "foreach"], ["git", "submodule--helper", "foreach"]),
            (["git-"], None),
            (["gitk"], None),
            # only a name git installs is an entry point; any other git-* word is an executable
            (["./git-run", "gh", "pr"], None),
            (["git-x"], None),
            (["/opt/x/git-wrap", "env"], None),
            (["git-lfs", "push"], None),
            (["gh", "pr"], None),
            ([], None),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(expected, shell_tokens.git_argv(argv))
        self.assertTrue(shell_tokens.is_git_word("git-push"))
        self.assertFalse(shell_tokens.is_git_word("digit-push"))
        for word in ("./git-run", "git-x", "/opt/x/git-wrap", "git-"):
            with self.subTest(word=word):
                self.assertFalse(shell_tokens.is_git_word(word))
        for word in ("git-push", "/usr/lib/git-core/git-rebase", "git-submodule--helper", "git-bisect", "git-commit"):
            with self.subTest(word=word):
                self.assertTrue(shell_tokens.is_git_word(word))
        self.assertEqual(["x"], shell_tokens.git_runs_text(["git-rebase", "-x", "x"], ["git-rebase", "-x", "x"]))
        self.assertEqual(
            ["gh", "pr"], shell_tokens.git_runs_text(["git", "submodule--helper", "foreach", "gh", "pr"], ["git", "submodule--helper", "foreach", "gh", "pr"])
        )

    def test_words_are_searched_in_order_after_each_other(self) -> None:
        gh_pr_verb = (shell_tokens.WORD_GH, shell_tokens.WORD_PR, git_guard.UNRESOLVED_PR_PUBLISH[2])
        for text, verb in (
            ("gh pr merge 12", "merge"),
            ("x gh -R o/r pr ready", "ready"),
            ("pr gh pr merge", "merge"),  # the first `pr` before `gh` does not count
            ("gh pr view; gh pr ready 12", "ready"),
            ("gh\npr\nmerge", "merge"),
        ):
            with self.subTest(text=text):
                self.assertEqual(verb, shell_tokens.words_in_order(text, *gh_pr_verb).group(1))
        for text in ("pr gh merge", "gh merge pr", "gh pr", "ghpr merge", "gh pr merged", "git pull", ""):
            with self.subTest(text=text):
                self.assertIsNone(shell_tokens.words_in_order(text, *gh_pr_verb))
        self.assertIsNotNone(shell_tokens.words_in_order("git-push", shell_tokens.WORD_GIT, shell_tokens.WORD_PUSH))
        self.assertIsNone(shell_tokens.words_in_order("push git", shell_tokens.WORD_GIT, shell_tokens.WORD_PUSH))

    def test_matching_unresolved_text_is_linear(self) -> None:
        # `\bgh\b.*\bpr\b.*\b(ready|merge)\b` and `\bexport\b[^;&|\n]*\bNAME\b` retried from every
        # `gh pr` / `export` word across the rest of the text: quadratic on ~170 KB with no match.
        cwd = str(self.clean)
        unmatched_pr = "gh pr " * 30000
        unmatched_export = "export " * 25000
        self.assertGreater(len(unmatched_pr), 170_000)
        started = time.monotonic()
        self.assertIsNone(shell_tokens.words_in_order(unmatched_pr, *git_guard.UNRESOLVED_PR_PUBLISH))
        self.assertFalse(git_guard.unresolved_sets_override(unmatched_export))
        self.assertLess(time.monotonic() - started, 3.0)
        # the same text as an unresolved command (the payload does not tokenize), end to end
        for text, check in (
            (f'bash -c "{unmatched_pr}\'"', lambda: git_guard.check_pr_publish(text, cwd, {})),
            (f'bash -c "{unmatched_export}\'"', lambda: git_guard.check_override_assignment(text, cwd)),
        ):
            with self.subTest(length=len(text)):
                started = time.monotonic()
                check()
                self.assertLess(time.monotonic() - started, 3.0)
        # what matched before still matches, with the verb the message names
        for text, verb in (
            ('bash -c "gh pr merge 12 \'"', "merge"),
            ('bash -c "echo; gh -R o/r pr ready 12 \'"', "ready"),
            ('bash -c "' + unmatched_pr + 'gh pr merge \'"', "merge"),
        ):
            with self.subTest(text=text[:40]):
                with self.assertRaises(git_guard.Blocked) as caught:
                    git_guard.check_pr_publish(text, cwd, {})
                self.assertIn(f"gh pr {verb}", str(caught.exception))
        for text in (
            'bash -c "export AITK_PR_READY \'"',
            'bash -c "echo hi; declare -x SKIP_PR_GATE \'"',
            'bash -c "builtin export SKIP_PRECHECK=1 \'"',
            'bash -c "' + unmatched_export + 'SKIP_PRECHECK \'"',
        ):
            with self.subTest(text=text[:40]):
                with self.assertRaises(git_guard.Blocked):
                    git_guard.check_override_assignment(text, cwd)
        for text in (
            'bash -c "export X; echo AITK_PR_READY \'"',  # a separator ends the export
            'bash -c "echo AITK_PR_READY; export X \'"',  # the mention comes before the builtin
            'bash -c "echo AITK_PR_READY 0 \'"',
        ):
            with self.subTest(text=text[:40]):
                git_guard.check_override_assignment(text, cwd)

    def test_git_dash_C_is_followed_lexically_and_capped(self) -> None:
        # `-C` moves the directory with os.path.normpath: no realpath, no `~` expansion; more
        # than 16 hops (and --git-dir/--work-tree/GIT_DIR/GIT_WORK_TREE) leave it unknown (None)
        for args, expected in (
            (["-C", "a", "-C", "../b", "status"], ("/base/b", 4)),
            (["-C", "/abs", "-C", "x", "push"], ("/abs/x", 4)),
            # a value the shell expands, or with a newline, is unknown before any path arithmetic
            (["-C", "~", "status"], (None, 2)),
            (["-C", "~/..", "push"], (None, 2)),
            (["-C", "$OTHER/..", "push"], (None, 2)),
            (["-C", "${OTHER}", "push"], (None, 2)),
            (["-C", "`pwd`/..", "push"], (None, 2)),
            (["-C", "a\nb", "push"], (None, 2)),
            (["-C", "", "push"], ("/base", 2)),
            (["-C", "sub", "push"], ("/base/sub", 2)),
            (["-C", "sub", "-C", "$X", "push"], (None, 4)),
            (["-C", "link/..", "push"], ("/base", 2)),
            (["--git-dir=/x/.git", "push"], (None, 1)),
            (["--work-tree", "/x", "push"], (None, 2)),
            # every global option with a separate value word; `--exec-path` alone has none
            (["--attr-source", "HEAD", "push"], ("/base", 2)),
            (["--super-prefix", "sub/", "-C", "a", "push"], ("/base/a", 4)),
            (["--namespace", "ns", "--config-env", "alias.x=A", "push"], ("/base", 4)),
            (["--attr-source=HEAD", "--exec-path", "push"], ("/base", 2)),
            (["--exec-path=/x", "push"], ("/base", 1)),
            (["-C", "a"] * 16 + ["push"], ("/base/" + "/".join(["a"] * 16), 32)),
            (["-C", "a"] * 17 + ["push"], (None, 34)),
            (["-C", "a"] * 5000 + ["push"], (None, 10000)),
        ):
            with self.subTest(args=args[:6]):
                self.assertEqual(expected, shell_tokens.git_globals(args, "/base"))
        self.assertEqual((None, 0), shell_tokens.git_globals(["push"], "/base", {"GIT_DIR": "/x"}))
        self.assertEqual((None, 0), shell_tokens.git_globals(["push"], "/base", {"GIT_WORK_TREE": "/x"}))

    def test_cd_to_a_target_the_shell_expands_leaves_the_directory_unknown(self) -> None:
        folder = self.clean / "sub"
        folder.mkdir(exist_ok=True)
        literal = self.clean / "$DIR"
        literal.mkdir(exist_ok=True)
        self.addCleanup(literal.rmdir)
        base = str(self.clean)
        for args, expected in (
            (["sub"], f"{base}/sub"),
            ([""], base),
            (["-"], base),
            (["$OTHER/.."], None),  # not the directory above a folder named `$OTHER`
            (["$DIR"], None),  # a folder with that literal name exists, but the shell expands it
            (["`pwd`"], None),
            (["a\nb"], None),
        ):
            with self.subTest(args=args):
                self.assertEqual(expected, shell_tokens.advance_dir(base, args))
        self.assertIsNone(shell_tokens.advance_dir(None, ["sub"]))
        self.assertEqual(os.path.expanduser("~"), shell_tokens.advance_dir(base, ["~"]))
        # through the walk: the directory stays unknown for the command after the cd
        walked = list(shell_tokens.commands('cd "$OTHER/.." && gh pr view 1', base))
        self.assertIsNone(walked[-1].workdir)
        walked = list(shell_tokens.commands("cd sub && gh pr view 1", base))
        self.assertEqual(f"{base}/sub", walked[-1].workdir)

    def test_mentions_push_joins_a_backslash_newline_like_mentions_gated(self) -> None:
        for text in ("git pu\\\nsh origin feature", "git -c 'alias.x=!git pu\\\nsh origin feature' x", "pu\\\nsh"):
            with self.subTest(text=text):
                self.assertTrue(shell_tokens.mentions_push(text))
        self.assertTrue(shell_tokens.mentions_gated("gh p\\\nr create"))
        self.assertEqual(shell_tokens.unquoted("pu\\\nsh 'a'\"b\""), "push ab")
        for text in ("git pull", "echo pushed", "pu\nsh", "git pu\\sh"):
            with self.subTest(text=text):
                self.assertEqual(text == "git pu\\sh", shell_tokens.mentions_push(text))

    def test_a_substitution_with_a_long_run_of_git_words_is_scanned_in_linear_time(self) -> None:
        # `\bgit(?:\s+|-|\$\{...\})[^)]*(commit|push)\b` retried from every `git` and `git-` word
        # across the rest of the body: 15s at 40000 words, 31s for evaluate() at 240 KB.
        cwd = str(self.clean)
        for unit in ("git ", "git- ", "A=git $B ", "git${x} ", "a" * 40 + " "):
            body = unit * (170_000 // len(unit))
            with self.subTest(unit=unit[:12]):
                for text in (f"echo $({body})", f"echo `{body}`", f"cat <({body})"):
                    started = time.monotonic()
                    self.assertFalse(git_guard.has_unsafe_git_substitution(text))
                    self.assertLess(time.monotonic() - started, 3.0)
                    # a commit or push at the very end is still found
                    started = time.monotonic()
                    self.assertTrue(git_guard.has_unsafe_git_substitution(text[:-1] + " git push origin)" if text.endswith(")") else text[:-1] + " git push origin`"))
                    self.assertLess(time.monotonic() - started, 3.0)
                text = f"echo $({body})\ngh pr merge 12"
                started = time.monotonic()
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, cwd, {})
                self.assertLess(time.monotonic() - started, 3.0)
        # an opener with no closer, and one very long word, cost nothing extra either
        for text in ("echo " + "$(" * 80_000, "echo $(" + "a" * 200_000 + ")", "echo " + "`x " * 60_000):
            started = time.monotonic()
            git_guard.has_unsafe_git_substitution(text)
            self.assertLess(time.monotonic() - started, 3.0)

    def test_the_linear_substitution_scan_matches_the_patterns_it_replaced(self) -> None:
        import random
        import re

        def reference(command_text: str) -> bool:
            substitution_pattern = r"`[^`]*`|\$\([^)]*\)|<\([^)]*\)"
            git_pattern = r"\bgit(?:\s+|-|\$\{[^}]+\})[^)]*(commit|push)\b"
            variable_git_pattern = r"[A-Za-z_][A-Za-z0-9_]*=git[^)]*\$[A-Za-z_][A-Za-z0-9_]*\s+(commit|push)\b"
            for match in re.finditer(substitution_pattern, command_text):
                body = match.group(0)
                if re.search(git_pattern, body) or re.search(variable_git_pattern, body):
                    return True
            return False

        words = [
            "git", "git ", "git-", "git${x}", "git${", " ", "-", "$(", "$(", ")", "`", "<(", "push",
            " push", "commit", "pushed", "x", "A=git", "=git", " $A push", "${a}", "{", "}", "1", "_", "\n",
        ]
        rng = random.Random(7)
        found = 0
        for _ in range(40_000):
            text = "".join(rng.choice(words) for _ in range(rng.randint(1, 14)))
            expected = reference(text)
            found += expected
            self.assertEqual(expected, git_guard.has_unsafe_git_substitution(text), repr(text))
        self.assertGreater(found, 200)  # the sample has both outcomes

    def test_substitution_text_is_charged_against_the_work_budget(self) -> None:
        # Every `$(` rescanned to the end of the text and every body walked again: this input
        # ran for ~70s before the scan was charged (and then the hook timeout let it through).
        cwd = str(self.clean)
        text = 'echo "' + "$(" * 5000 + '" ; gh pr merge 1'
        started = time.monotonic()
        with self.assertRaises(git_guard.Blocked):
            git_guard.evaluate(text, cwd, {})
        self.assertLess(time.monotonic() - started, 5.0)
        started = time.monotonic()
        walked = list(shell_tokens.commands(text, cwd))
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertTrue(any(found.unreadable for found in walked))
        self.assertEqual(["gh", "pr", "merge", "1"], walked[-1].argv)
        # a substitution that fits the budget is still read in full
        walked = list(shell_tokens.commands('echo "$(gh pr merge 1)"', cwd))
        self.assertFalse(any(found.unreadable for found in walked))
        self.assertIn(["gh", "pr", "merge", "1"], [found.argv for found in walked])

    def test_a_long_chain_of_C_options_stays_fast_and_still_blocks(self) -> None:
        cwd = str(self.clean)
        text = "git " + "-C x " * 20000 + "status; gh pr merge 12"
        started = time.monotonic()
        walked = list(shell_tokens.commands(text, cwd))
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(["gh", "pr", "merge", "12"], walked[-1].argv)
        with self.assertRaises(git_guard.Blocked):
            git_guard.evaluate(text, cwd, {})

    def test_operator_runs_are_split_into_shell_operators(self) -> None:
        # shlex returns a run of operator characters as one token; the command after it
        # then reads as arguments of the one before
        for text, expected in (
            ("a;(b)", ["a", ";", "(", "b", ")"]),
            ("a&&(b)||c", ["a", "&&", "(", "b", ")", "||", "c"]),
            ("(a)|b", ["(", "a", ")", "|", "b"]),
            ("echo $(a); b", ["echo", "$", "(", "a", ")", ";", "b"]),
            ("f()(a)", ["f", "()", "(", "a", ")"]),
            ("f() { a; }", ["f", "()", "{", "a", ";", "}"]),
            # redirection operators stay whole
            ("a 2>&1 | b", ["a", "2", ">&", "1", "|", "b"]),
            ("a &>/dev/null", ["a", "&>", "/dev/null"]),
            ("a &>>x && b", ["a", "&>>", "x", "&&", "b"]),
            ("a >>x; b", ["a", ">>", "x", ";", "b"]),
            ("a <<<x|b", ["a", "<<<", "x", "|", "b"]),
            ("a >|x;b", ["a", ">|", "x", ";", "b"]),
            ("a |& b", ["a", "|&", "b"]),
            ("a <>x;(b)", ["a", "<>", "x", ";", "(", "b", ")"]),
        ):
            with self.subTest(text=text):
                self.assertEqual(expected, shell_tokens.tokenize(text))
        for text in ("git fetch;(git push -f origin main)", "git status&&(git push --force origin main)"):
            with self.subTest(text=text):
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, str(self.clean), {})
        walked = [c.argv for c in shell_tokens.commands("git status;(gh pr merge 12)", str(self.clean))]
        self.assertIn(["gh", "pr", "merge", "12"], walked)

    def test_for_each_repo_hands_git_a_command(self) -> None:
        for argv, expected in (
            (["git", "for-each-repo", "--config=x.r", "push", "-f", "origin", "main"], ["push", "-f", "origin", "main"]),
            (["git", "for-each-repo", "--config", "x.r", "push", "origin"], ["push", "origin"]),
            (["git", "for-each-repo", "--conf", "x.r", "--keep-going", "push"], ["push"]),
            (["git", "for-each-repo", "--config=x.r", "--", "push", "origin"], ["push", "origin"]),
            (["git", "-c", "x.r=.", "for-each-repo", "--config=x.r", "gh", "pr", "merge"], ["gh", "pr", "merge"]),
            (["git-for-each-repo", "--config=x.r", "push"], ["push"]),
            (["git", "for-each-repo", "--config=x.r", "maintenance", "run"], ["maintenance", "run"]),
            (["git", "for-each-repo"], []),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(expected, shell_tokens.git_runs_text(argv, argv))
        # only a gated mention in what git runs makes the command unreadable
        flagged = list(shell_tokens.commands("git for-each-repo --config=x.r push -f origin main", str(self.clean)))
        self.assertTrue(flagged[0].unreadable)
        calm = list(shell_tokens.commands("git for-each-repo --config=x.r maintenance run", str(self.clean)))
        self.assertFalse(any(c.unreadable for c in calm))

    def test_inline_alias_dash_c_counts_only_among_git_global_options(self) -> None:
        for segment, expected in (
            (["git", "grep", "-c", "alias.x", "docs/push.md"], False),
            (["git", "log", "-c", "alias.x", "push"], False),
            (["git", "-c", "alias.x=!gh x", "x"], True),
            (["git", "-c", "alias.m=!gh pr merge", "m", "12"], True),
            (["git", "-C", "d", "-c", "alias.x", "x"], True),
            (["git", "-c", "core.pager=cat", "-c", "alias.x=y", "x"], True),
            (["git", "log", "-calias.x=y"], True),  # the prefixed spelling needs no context
            (["git", "log", "--config-env", "alias.x=A"], True),
        ):
            with self.subTest(segment=segment):
                self.assertEqual(expected, shell_tokens.sets_inline_alias(segment, False))

    def test_tab_and_glob_characters_leave_a_path_unknown(self) -> None:
        for value in ("/p/[w]ork", "/p/w*", "/p/wor?", "/p/work\t", "/p/\twork"):
            with self.subTest(value=value):
                self.assertIsNone(shell_tokens.git_globals(["-C", value, "push"], "/start")[0])
                self.assertIsNone(shell_tokens.advance_dir("/start", [value]))
        self.assertEqual("/p/work", shell_tokens.git_globals(["-C", "/p/work", "push"], "/start")[0])
        with tempfile.TemporaryDirectory() as temporary:
            plain = os.path.realpath(temporary)
            self.assertEqual(plain, shell_tokens.advance_dir("/start", [plain]))

    def test_cd_to_the_git_toplevel_follows_the_repository(self) -> None:
        top = str(self.clean)
        sub = self.clean / "sub"
        sub.mkdir(exist_ok=True)
        for spelling in (
            'cd "$(git rev-parse --show-toplevel)"',
            "cd $(git rev-parse --show-toplevel)",
            "cd `git rev-parse --show-toplevel`",
            'cd "`git rev-parse --show-toplevel`"',
        ):
            with self.subTest(spelling=spelling):
                walked = list(shell_tokens.commands(f"{spelling} && gh pr create --fill", str(sub)))
                (creation,) = [c for c in walked if c.argv[:3] == ["gh", "pr", "create"]]
                self.assertEqual(top, creation.workdir)
        # outside a repository, and for any other substitution, the directory is unknown
        with tempfile.TemporaryDirectory() as bare:
            walked = list(shell_tokens.commands('cd "$(git rev-parse --show-toplevel)" && gh pr create', bare))
            self.assertIsNone(walked[-1].workdir)
        for other in ('cd "$(git rev-parse --show-cdup)"', 'cd "$(git rev-parse --show-toplevel)/x"', 'cd "$HOME"'):
            with self.subTest(other=other):
                walked = list(shell_tokens.commands(f"{other} && gh pr create", top))
                self.assertIsNone(walked[-1].workdir)

    def test_a_long_run_of_dashed_pushes_stays_fast_and_blocks(self) -> None:
        # each action used to keep the whole remaining text, and the token list was
        # copied for every dashed entry point
        text = "G=git-push; " + "$G --no-verify origin feature; " * 30000
        started = time.monotonic()
        tokens = shell_tokens.tokenize(text)
        actions = git_guard.parse_git_actions(tokens, str(self.clean))
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(30000, len(actions))
        self.assertTrue(all(len(action["args"]) == 3 for action in actions))
        with self.assertRaises(git_guard.Blocked):
            git_guard.evaluate(text, str(self.clean), {})

    def test_the_guard_stops_itself_before_its_hook_timeout_and_blocks(self) -> None:
        def slow(*_args: object) -> None:
            time.sleep(10)

        def run(command: str) -> tuple[int, str]:
            payload = json.dumps({"tool_input": {"command": command}, "cwd": str(self.clean)})
            with mock.patch.object(git_guard, "DEADLINE_SECONDS", 0.05), mock.patch.object(
                git_guard, "evaluate", slow
            ), mock.patch("sys.stdin", io.StringIO(payload)), mock.patch("sys.stderr", io.StringIO()) as stderr:
                started = time.monotonic()
                status = git_guard.main()
                self.assertLess(time.monotonic() - started, 5.0)
                return status, stderr.getvalue()

        # whatever the text mentions: quoting hides git from a mention match
        for command in ("git status", "GH pr view 1", "export AITK_PR_READY=1", "ls -la", "g'i't push"):
            with self.subTest(command=command):
                status, message = run(command)
                self.assertEqual(2, status)
                self.assertIn("too large or complex", message)
        # and with the real evaluator on inputs it cannot finish in time
        for command in (
            "git status; " * 40000,
            "g'i't status; " * 40000 + "g'i't push --no-verify origin feature",
        ):
            payload = json.dumps({"tool_input": {"command": command}, "cwd": str(self.clean)})
            with self.subTest(command=command[-40:]), mock.patch.object(
                git_guard, "DEADLINE_SECONDS", 0.01
            ), mock.patch("sys.stdin", io.StringIO(payload)), mock.patch("sys.stderr", io.StringIO()) as stderr:
                self.assertEqual(2, git_guard.main())
                self.assertIn("too large or complex", stderr.getvalue())
        # the timer is disarmed afterwards
        self.assertEqual((0.0, 0.0), signal.getitimer(signal.ITIMER_REAL))

    def test_the_review_gate_stops_itself_before_its_hook_timeout_and_blocks(self) -> None:
        def slow(*_args: object) -> None:
            time.sleep(10)

        payload = json.dumps({"tool_input": {"command": "gh pr create --fill"}, "cwd": str(self.clean)})
        with mock.patch.object(review_gate, "DEADLINE_SECONDS", 0.05), mock.patch.object(
            review_gate, "evaluate", slow
        ), mock.patch("sys.stdin", io.StringIO(payload)), mock.patch("sys.stderr", io.StringIO()) as stderr:
            started = time.monotonic()
            self.assertEqual(2, review_gate.main())
            self.assertLess(time.monotonic() - started, 5.0)
            self.assertIn("too large or complex", stderr.getvalue())

    def test_the_in_process_deadlines_sit_below_the_hook_timeouts(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"]
        timeouts = {Path(h["command"].split("/hooks/")[1].rstrip('"')).name: h["timeout"] for h in hooks}
        # a margin for interpreter start-up and the wrapper around the deadline
        self.assertLessEqual(git_guard.DEADLINE_SECONDS + 5, timeouts["prevent-project-commit.sh"])
        self.assertLessEqual(review_gate.DEADLINE_SECONDS + 3, timeouts["require-review-gate.sh"])

    def test_heads_are_compared_without_case(self) -> None:
        self.assertEqual(["GIT", "status"], shell_tokens.git_argv(["GIT", "status"]))
        self.assertEqual(["git", "push", "x"], shell_tokens.git_argv(["GIT-PUSH", "x"]))
        self.assertEqual(["git", "push", "x"], shell_tokens.git_argv(["/usr/lib/Git-Push", "x"]))
        self.assertIsNone(shell_tokens.git_argv(["GIT-RUN", "x"]))
        self.assertTrue(shell_tokens.is_git_word("GIT"))
        self.assertTrue(shell_tokens.is_git_word("/x/Git-Rebase"))
        self.assertFalse(shell_tokens.is_git_word("./GIT-RUN"))
        (found,) = shell_tokens.commands("GH pr merge 12", str(self.clean))
        self.assertTrue(found.is_gh)

    def test_override_assignments_in_a_command_are_blocked(self) -> None:
        for env in (None, {"AITK_PR_READY": "1"}):
            for template in OVERRIDE_ASSIGNMENT_BLOCK:
                command = self.expand(template, self.clean)
                with self.subTest(command=command, env=env):
                    result = self.run_hook(command, self.clean, env=env)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertIn("environment the session started with", result.stderr)
                    for name in OVERRIDES:
                        self.assertNotIn(name, result.stderr)

    def test_read_only_override_mentions_are_allowed(self) -> None:
        self.assert_cases(OVERRIDE_ASSIGNMENT_ALLOW, self.clean, 0)

    def test_one_truthy_rule_for_overrides(self) -> None:
        for value in (None, "", "0", "false", "False", "no", "NO", "off", "Off", "  off  ", " 0 "):
            with self.subTest(value=value):
                self.assertFalse(shell_tokens.truthy(value))
        for value in ("1", "yes", "true", "on", "0 1", "2"):
            with self.subTest(value=value):
                self.assertTrue(shell_tokens.truthy(value))

    def test_the_documented_scan_limits_are_the_real_ones(self) -> None:
        # The module docstring lists these as what the token scan cannot see. A
        # case that starts blocking belongs in OVERRIDE_ASSIGNMENT_BLOCK and out
        # of the docstring's list; one that was never allowed should not be listed.
        self.assert_cases(OVERRIDE_SCAN_LIMITS, self.clean, 0)

    def test_commands_yield_assignment_only_segments_only_when_asked(self) -> None:
        cwd = str(self.clean)
        text = "AITK_PR_READY=1; export AITK_PR_READY; uv run aitk deliver --ready"
        self.assertEqual(
            [["export", "AITK_PR_READY"], ["uv", "run", "aitk", "deliver", "--ready"]],
            [c.argv for c in shell_tokens.commands(text, cwd)],
        )
        found = list(shell_tokens.commands(text, cwd, include_assignments=True))
        self.assertEqual([], found[0].argv)
        self.assertEqual({"AITK_PR_READY": "1"}, found[0].assignments)
        self.assertEqual(["export", "AITK_PR_READY"], found[1].argv)

        # the nested path: the assignment comes out before `true`
        nested = list(shell_tokens.commands("bash -c 'SKIP_PR_GATE=1; true'", cwd, include_assignments=True))
        self.assertEqual([[], ["true"]], [c.argv for c in nested])
        self.assertEqual({"SKIP_PR_GATE": "1"}, nested[0].assignments)
        self.assertEqual([["true"]], [c.argv for c in shell_tokens.commands("bash -c 'SKIP_PR_GATE=1; true'", cwd)])

        # appends: default recognition is unchanged, the opt-in one keeps the raw key
        self.assertFalse(shell_tokens.is_assignment("FOO+=x"))
        self.assertTrue(shell_tokens.is_assignment("FOO+=x", include_append=True))
        # (the default traversal reads `FOO+=x` as the command name and rescans from `git`)
        self.assertEqual(
            [["git", "status"], ["FOO+=x", "git", "status"]],
            [c.argv for c in shell_tokens.commands("FOO+=x git status", cwd)],
        )
        (opt_in,) = shell_tokens.commands("FOO+=x git status", cwd, include_assignments=True)
        self.assertEqual(["git", "status"], opt_in.argv)
        self.assertEqual({"FOO+": "x"}, opt_in.assignments)

        # `builtin` is unwrapped only by the opt-in scan; `command` composes with it
        for spelling in ("builtin export AITK_PR_READY=1", "command builtin export AITK_PR_READY=1"):
            self.assertEqual(
                [["builtin", "export", "AITK_PR_READY=1"]],
                [c.argv for c in shell_tokens.commands(spelling, cwd)],
                spelling,
            )
        self.assertEqual(
            [["export", "AITK_PR_READY=1"]],
            [c.argv for c in shell_tokens.commands("builtin export AITK_PR_READY=1", cwd, include_assignments=True)],
        )
        self.assertEqual(
            [["export", "AITK_PR_READY=1"]],
            [c.argv for c in shell_tokens.commands("builtin command export AITK_PR_READY=1", cwd, include_assignments=True)],
        )

        # redirections and function heads are skipped only by the opt-in scan
        self.assertEqual(
            [["git", "status"], ["2", ">&", "1", "AITK_PR_READY=1", "git", "status"]],
            [c.argv for c in shell_tokens.commands("2>&1 AITK_PR_READY=1 git status", cwd)],
        )
        (redirected,) = shell_tokens.commands("2>&1 AITK_PR_READY=1 git status", cwd, include_assignments=True)
        self.assertEqual((["git", "status"], {"AITK_PR_READY": "1"}), (redirected.argv, redirected.assignments))
        self.assertEqual(
            [["git", "status"], ["f"]],
            [c.argv for c in shell_tokens.commands("f() { git status; }; f", cwd, include_assignments=True)],
        )

        # a later env, shell, eval, gh or git word is walked again behind a head the
        # tokenizer does not know, by the default traversal too; an inert head
        # (`echo`, `printf`, `grep`) only prints, so the default traversal leaves its
        # words alone while the opt-in scan still reads them
        self.assertEqual(
            [["echo", "setsid", "gh", "pr", "merge"]],
            [c.argv for c in shell_tokens.commands("echo setsid gh pr merge", cwd)],
        )
        self.assertEqual(
            [["gh", "pr", "merge", "12"], ["flock", "/tmp/x", "gh", "pr", "merge", "12"]],
            [c.argv for c in shell_tokens.commands("flock /tmp/x gh pr merge 12", cwd)],
        )
        self.assertEqual(
            [["gh", "pr", "merge"]], [c.argv for c in shell_tokens.commands("eval -- 'gh pr merge'", cwd)]
        )
        self.assertEqual(
            [["true"], ["setsid", "env", "AITK_PR_READY=1", "true"]],
            [c.argv for c in shell_tokens.commands("setsid env AITK_PR_READY=1 true", cwd)],
        )
        later = list(shell_tokens.commands("setsid env AITK_PR_READY=1 true", cwd, include_assignments=True))
        self.assertIn((["true"], {"AITK_PR_READY": "1"}), [(c.argv, c.assignments) for c in later])

        # an empty nested payload cannot erase the outer assignment
        self.assertEqual([], list(shell_tokens.commands("AITK_PR_READY=1 bash -c ''", cwd)))
        (outer,) = shell_tokens.commands("AITK_PR_READY=1 bash -c ''", cwd, include_assignments=True)
        self.assertEqual({"AITK_PR_READY": "1"}, outer.assignments)

    def test_missing_python_fails_closed_on_guarded_commands(self) -> None:
        with tempfile.TemporaryDirectory() as bin_dir:
            for tool in ("bash", "cat", "dirname"):
                found = shutil.which(tool)
                self.assertIsNotNone(found, tool)
                os.symlink(found, Path(bin_dir) / tool)
            env = {"PATH": bin_dir, "HOME": str(self.clean)}
            blocked = self.run_hook("git commit -m fine", self.clean, wrapper_env=env)
            self.assertEqual(2, blocked.returncode, blocked.stderr)
            self.assertIn("python3 is not on PATH", blocked.stderr)
            pr = self.run_hook("gh pr merge 12", self.clean, wrapper_env=env)
            self.assertEqual(2, pr.returncode, pr.stderr)
            override = self.run_hook("export AITK_PR_READY=1", self.clean, wrapper_env=env)
            self.assertEqual(2, override.returncode, override.stderr)
            self.assertNotIn("AITK_PR_READY", override.stderr)
            newline = self.run_hook("\nAITK_PR_READY=1 bin/aitk deliver --ready", self.clean, wrapper_env=env)
            self.assertEqual(2, newline.returncode, newline.stderr)
            allowed = self.run_hook("ls -la", self.clean, wrapper_env=env)
            self.assertEqual(0, allowed.returncode, allowed.stderr)

    def test_an_internal_error_fails_closed_on_git_gh_and_overrides(self) -> None:
        def broken(*_args: object) -> None:
            raise RuntimeError("boom")

        cases = (
            ("git status", 2),
            ("gh pr view 12", 2),
            ("export AITK_PR_READY=1", 2),
            ("SKIP_PRECHECK=1 make lint", 2),
            ("ls -la", 0),
        )
        # No external boundary can raise an internal error deterministically, so patch the evaluator.
        for command, expected in cases:
            payload = json.dumps({"tool_input": {"command": command}, "cwd": str(self.clean)})
            with self.subTest(command=command), mock.patch.object(git_guard, "evaluate", broken), mock.patch(
                "sys.stdin", io.StringIO(payload)
            ), mock.patch("sys.stderr", io.StringIO()) as stderr:
                self.assertEqual(expected, git_guard.main())
                if expected == 2:
                    self.assertIn("hook failed", stderr.getvalue())

    def test_a_module_in_the_project_directory_cannot_shadow_the_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            git(project, "init", "-q", "-b", "main")
            (project / "aitk").mkdir()
            (project / "aitk" / "__init__.py").write_text("raise SystemExit(0)\n")
            (project / "json.py").write_text("raise SystemExit(0)\n")
            result = subprocess.run(
                ["bash", str(WRAPPER)],
                input=json.dumps({"tool_input": {"command": "git commit --no-verify -m x"}, "cwd": str(project)}),
                text=True,
                capture_output=True,
                check=False,
                cwd=project,
                env=base_env(),
                timeout=60,
            )
            self.assertEqual(2, result.returncode, result.stderr)

    def test_guard_runs_without_the_aitk_package(self) -> None:
        probe = (
            "import json, sys\n"
            f"sys.path.insert(0, {str(ROOT / 'hooks' / 'lib')!r})\n"
            "import git_guard\n"
            "print(json.dumps(sorted(name for name in sys.modules if name.startswith('aitk'))))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-E", "-s", "-c", probe],
                text=True,
                capture_output=True,
                check=True,
                cwd=tmp,
                env=base_env(),
            )
        self.assertEqual([], json.loads(result.stdout))

    def test_state_files_match_project_state(self) -> None:
        # Until project_state goes, the guard's own copy must not drift from it.
        from aitk.project_state import STATE_FILES as RECORDED

        self.assertEqual(RECORDED, STATE_FILES)


if __name__ == "__main__":
    unittest.main()
