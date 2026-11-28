"""The git guard (hooks/lib/git_guard.py) behind hooks/prevent-project-commit.sh.

Every case runs the wrapper end to end with a synthetic PreToolUse payload in a
scratch repository under a fresh temporary directory, and checks the exit code:
0 allows, 2 blocks. The cases port the retired shell smoke suite and add the
P1 ones: commands behind `timeout`, `nohup`, `xargs` and `nice`,
newline-separated commands, `git add <state> && git commit`, and a non-draft
`gh pr create`, `gh pr ready` and `gh pr merge` without the user's
AITK_PR_READY=1.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
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
import gh_args  # noqa: E402
import shell_tokens  # noqa: E402
sys.path.pop(0)

STATE_FILES = git_guard.STATE_FILES
WRAPPER = ROOT / "hooks" / "prevent-project-commit.sh"
OVERRIDES = ("AITK_PR_READY", "SKIP_PRECHECK")


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
    # a directory the guard cannot read is no clean index: the commit blocks
    'cd "$PWD" && git commit -m state',
    "cd -P {repo} && git commit -m state",
    "cd ~/{repo_home} && git commit -m state",
    # a cd that fails leaves the shell where it was
    "cd /nonexistent-aitk-dir; git commit -m state",
)

# Blocked in a repository with nothing staged in its default index.
CLEAN_BLOCK = (
    # a force push whose branch the guard cannot read blocks: it may be main
    "cd /nonexistent-aitk-dir; git push --force",
    "cd -P . && git push --force",
    'cd "$PWD" && git push --force',
    "cd ~/{repo_home} && git push --force",
    "git -C ~/{repo_home} push --force",
    # in a directory the guard cannot read, a word that is no git command may be an alias
    'cd "$PWD" && git fpm',
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
    # a retired override (SKIP_PR_GATE, v0.3) lifts nothing
    "SKIP_PR_GATE=1 gh pr ready 12",
    "SKIP_PR_GATE=1 gh pr merge 12",
    "timeout 30 gh pr merge 12",
    "nohup gh pr ready 12",
    "echo ok\ngh pr ready 12",
    "git status && gh pr merge 12",
    "bash -c 'gh pr merge 12'",
    "env FOO=1 gh pr ready 12",
    "gh pr merge 'unbalanced",
    # A PR opens as a draft.
    "gh pr create --title t --body b",
    # the verb as gh finds it: an unknown flag before it takes the next word as its value
    "gh pr -t view merge 12",
    "gh pr --body view merge 12",
    "gh pr -t list create --fill",
    # a verb or a gh the guard cannot read
    "V=merge; gh pr $V 12",
    'gh "$SUB" merge 12',
    "g=gh; $g pr merge 12",
    '"$GH" pr ready 12',
    "${{GH}} pr merge 12",
    # gh pr revert opens a pull request
    "gh pr revert 12",
    "gh pr revert 12 --title -d",
    # flags as pflag reads them: `-d` is the title, a value it cannot parse sets nothing
    "gh pr create -ft -d",
    "gh pr create -d=false --fill",
    "gh pr create -fd=false",
    "gh pr create --draft=tRuE --fill",
    "gh pr create --draft=yes --fill",
    # a flag the tables do not know grants no draft, help or undo
    "gh pr create --some-new-flag --draft --fill",
    # a flag's value is no request for help, on every verb
    "gh pr merge 12 --squash --body -h",
    "gh pr merge 12 -b --help",
    "gh pr merge 12 --subject -h",
    # `--repo` takes `--undo` as its value, and `--undo=false` is no undo
    "gh pr ready 12 --repo --undo",
    "gh pr ready 12 --undo=false",
    # `-h` is no cobra boolean at the root or `pr` level: it takes the next word
    "gh pr -sb -h 12 merge",
    "gh -sb -h 12 pr merge",
    "gh pr -sb --h 12 merge",
    "gh pr -db -h 12 revert --draft=false",
    "gh pr -rb -h create merge",
    # text the guard cannot parse: every gated match counts, a draft flag only in its own command
    "gh pr revert 9 --draft && gh pr ready 12 'x",
    "gh pr create -d --fill; gh pr merge 12 'x",
    "gh pr create --fill; ls -d . 'x",
    "gh pr revert 9; ls -d . 'x",
    # a command name behind an expansion, in every form
    '"${{GH:-/usr/local/bin/gh}}" pr merge 12',
    '"$(realpath /usr/local/bin/gh)" pr merge 12',
    "g=gx; ${{g/x/h}} pr merge 12",
    "$(command -v gh) pr merge 12",
    "`which gh` pr merge 12",
    "{{gh,}} pr merge 12",
    "gh {{pr,}} merge 12",
    "gh pr {{merge,}} 12",
    "gh pr merg[e] 12",
    # a positional that may become a flag grants no draft, help or undo
    "X=--draft=false; gh pr create --fill --draft $X",
    "X=--undo=false; gh pr ready 12 --undo $X",
    "X=--help=false; gh pr merge 12 --squash --help $X",
    "X=--help=false; gh pr create --fill --help $X",
    "gh pr create --fill --draft {{--draft=false,}}",
    "gh pr ready --undo \"$PR\"",
    # flags past an unquoted substitution are not read
    "gh pr create --draft --fill --title $(echo t) --draft=false",
    "gh pr ready 12 --undo $(true) --undo=false",
    "gh pr create --draft --fill --title >(cat) --draft=false",
    # the unknown verb
    "gh pr $V 12",
    "gh $SUB list",
    'gh "$@"',
    "for v in view checks; do gh pr $v 12; done",
    # a flag's value is no request for help: gh opens a non-draft PR titled `-h`
    "gh pr create --title -h --body x",
    "gh pr create -t t --body --help",
    "gh pr create --help=false --title t --body b",
    "gh pr create --attach -h.png --title t --body b",
    "gh pr create --fill",
    "gh pr create --draft=false --fill",
    "gh pr create -t d --fill",
    "gh pr new --fill",
    "git push -u origin HEAD && gh pr create --fill",
    "git push -u origin HEAD\ngh pr create --fill",
    "timeout 60 gh pr create --fill",
    "bash -lc 'gh pr create --fill'",
    "gh pr create --title $'it\\'s fixed' --body x",
    "AITK_PR_READY=1 gh pr create --fill",
    "env AITK_PR_READY=1 gh pr create --fill",
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
    "watch 'gh pr ready 12'",
    # a variable that holds more than the name, and one behind an unknown wrapper
    "c='gh pr'; $c merge 12",
    "c='gh pr merge'; $c 12",
    "c='gh pr merge 12'; $c",
    "g=gh; setsid $g pr merge 12",
    'setsid "$GH" pr merge 12',
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
    # `gh api`: the whole call in a variable, `curl`, and other API writes are not modelled;
    # GitHub's branch protection is the boundary there
    "gh api $ARGS",
    "curl -X PUT https://api.github.com/repos/o/r/pulls/12/merge",
    "gh api -X PUT repos/o/r/git/refs/heads/main -f sha=abc",
    "gh api -X POST repos/o/r/merges -f base=main -f head=x",
    "gh repo sync --force",
)

PR_PUBLISH_ALLOW = (
    "gh pr ready 12 --undo",
    "gh pr ready 12 --undo=true",
    "gh pr ready --undo -R o/r 12",
    "gh pr revert 12 --draft",
    "gh pr revert 12 -d -t t",
    "gh pr create -d=true --fill",
    "gh pr create --draft=T --fill",
    "gh pr create -fd=1",
    "gh pr create --fill -t x -d",
    "gh pr merge -h",
    "gh -R o/r pr merge --help",
    '"$GH" pr view 12',
    "gh pr view \"$N\"",
    "gh pr view $N --json body",
    "gh pr -R o/r view 12",
    "gh run view $ID --log-failed",
    'gh --jq "$Q" api /x',
    "gh pr --json $F view 12",
    'gh pr create --title "$T" -b "$B" --draft --fill',
    "gh pr -h view checks",
    "gh pr merge --help",
    "gh pr view 12",
    "GH pr view 12",
    "gh pr checks 12",
    "gh pr create --draft --title t --body b",
    "gh pr create -d --fill",
    "gh pr create -fd",
    "gh pr create --draft=true --fill",
    "gh --repo o/r pr create --fill --draft",
    "gh pr create --help",
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
    # a number apart from its operator is the option's value, not a descriptor
    "env -u 1 >/dev/null AITK_PR_READY=1 ./ship.sh",
    # an ANSI-C-quoted name is decoded before the lexer reads it
    "export $'\\x41ITK_PR_READY=1'; ./ship.sh",
    # operator runs the lexer used to fuse into one token are split, so the subshell or
    # function body after them is read
    "(>/dev/null AITK_PR_READY=1 ./ship.sh)",
    "f()( AITK_PR_READY=1 ./ship.sh ); f",
    "f()(AITK_PR_READY=1 ./ship.sh); f",
    "true;(AITK_PR_READY=1 ./ship.sh)",
    "true;(AITK_PR_READY='0 1' ./ship.sh)",
    "true;(typeset -xF SKIP_PRECHECK=0)",
    "(true)&&AITK_PR_READY=1 ./ship.sh",
    "true&&(AITK_PR_READY=1 ./ship.sh)",
    "true|(AITK_PR_READY=1 ./ship.sh)",
    "AITK_PR_READY=1 gh pr ready 12",
    "env SKIP_PRECHECK=1 gh pr create --draft --fill",
    "SKIP_PRECHECK=1 git push",
    "export AITK_PR_READY=1; ./ship.sh --ready",
    "AITK_PR_READY=1 uv run ship --ready",
    "eval -- 'SKIP_PRECHECK=1 true'",
    "builtin eval -- 'AITK_PR_READY=1 true'",
    "bash -c -- 'SKIP_PRECHECK=1 true'",
    "uv run bash -c -- 'AITK_PR_READY=1 ./ship.sh'",
    "bash -c 'AITK_PR_READY=1 gh pr ready 12'",
    "AITK_PR_READY=yes gh pr view 12",
    "AITK_PR_READY=1; export AITK_PR_READY; uv run ship --ready",
    "set -a; AITK_PR_READY=1; uv run ship --ready",
    "SKIP_PRECHECK=1; git push",
    "AITK_PR_READY=1",
    "env AITK_PR_READY=1",
    "{{ AITK_PR_READY=1; }}; gh pr ready 12",
    "export AITK_PR_READY",
    "typeset -x SKIP_PRECHECK",
    "declare -x AITK_PR_READY=1; gh pr ready 12",
    "readonly SKIP_PRECHECK=1; git push",
    "export FOO=1 SKIP_PRECHECK=1",
    "bash -c 'AITK_PR_READY=1; export AITK_PR_READY; gh pr ready 12'",
    "x=$(SKIP_PRECHECK=1; gh pr create --fill)",
    "export AITK_PR_READY; uv run ship --ready 'unbalanced",
    "AITK_PR_READY+=1 uv run ship --ready",
    "AITK_PR_READY+=0",
    "AITK_PR_READY+=false",
    "AITK_PR_READY+=",
    "FOO+=x SKIP_PRECHECK=1 git push",
    "export AITK_PR_READY+=0",
    "builtin export AITK_PR_READY=1",
    "command export AITK_PR_READY=1",
    "command builtin export AITK_PR_READY+=1",
    "builtin command export AITK_PR_READY=1",
    "builtin declare -x SKIP_PRECHECK+=false",
    "bash -c 'AITK_PR_READY+=1; true'",
    "builtin eval 'SKIP_PRECHECK+=1; true'",
    "env -S 'AITK_PR_READY+=1 uv run ship --ready'",
    "AITK_PR_READY=1 bash -c ''",
    "AITK_PR_READY+=1 uv run ship --ready 'unbalanced",
    "builtin export AITK_PR_READY; uv run ship --ready 'unbalanced",
    # redirections stand anywhere in a simple command, ahead of a prefix too
    "2>&1 AITK_PR_READY=1 ./ship.sh --ready",
    "2>/dev/null AITK_PR_READY=1 ./ship.sh --ready",
    ">out.txt SKIP_PRECHECK=1 gh pr create --fill",
    "&>>log.txt SKIP_PRECHECK=1 git push",
    "env >out.txt AITK_PR_READY=1 ./ship.sh --ready",
    # a function body runs when the function is called
    "f() {{ AITK_PR_READY=1 ./ship.sh --ready; }}; f",
    "function f {{ AITK_PR_READY=1 ./ship.sh --ready; }}; f",
    "function f() {{ export SKIP_PRECHECK=1; }}; f",
    # env, a shell or eval behind a wrapper the tokenizer does not know
    "setsid env AITK_PR_READY=1 ./ship.sh --ready",
    "uv run env SKIP_PRECHECK=1 gh pr create --fill",
    "find . -exec env AITK_PR_READY=1 ./ship.sh --ready \\;",
    "setsid bash -c 'export AITK_PR_READY=1; ./ship.sh --ready'",
    "echo env AITK_PR_READY=1",
    # arithmetic and nameref declarations: the value is not the literal text
    "declare -ix AITK_PR_READY=false",
    "declare -i count='AITK_PR_READY=1'",
    "declare -n ref=AITK_PR_READY; ref=1",
    # value-changing attributes and quoted or split values the scan resolves
    "integer -x AITK_PR_READY=1; ./ship.sh --ready",
    "float -x AITK_PR_READY=0; ./ship.sh --ready",
    "false=1; typeset -xF AITK_PR_READY=false; ./ship.sh --ready",
    "typeset -xZ5 AITK_PR_READY=0; ./ship.sh --ready",
    "AITK_PR_READY='0 1' ./ship.sh --ready",
    "bash -c 'AITK_PR_READ''Y=1 ./ship.sh --ready'",
    "eval 'AITK_PR_READ''Y=\"0 1\" ./ship.sh --ready'",
    "AITK_PR_READY\\\n=1 ./ship.sh --ready",
)

# Known limits of the token scan (the git_guard module docstring lists the
# classes). Each is a real override the scan does not see, so the hook allows it:
# a tripwire, not a sandbox. The protection that holds is elsewhere: a non-draft
# `gh pr create`, `gh pr ready` and `gh pr merge` read the override only from the
# session environment. The test below pins this list so a
# fix moves the case into OVERRIDE_ASSIGNMENT_BLOCK and the docstring stays true.
OVERRIDE_SCAN_LIMITS = (
    # a redirection operator erased together with a quoted option value
    "env -u '>' AITK_PR_READY=1 ./ship.sh",
    # shell-specific grammar: zsh anonymous functions and precommand modifiers, a
    # function named after a wrapper, a `-c --` payload, a nameref set by a plain value
    "() {{ AITK_PR_READY=1 ./ship.sh; }}",
    "env() {{ AITK_PR_READY=1 ./ship.sh; }}; env",
    "nocorrect AITK_PR_READY=1 ./ship.sh",
    "repeat 1 AITK_PR_READY=1 ./ship.sh",
    "coproc AITK_PR_READY=1 ./ship.sh",
    "declare -n r; r=AITK_PR_READY; declare -x r=1; ./ship.sh",
    # brace expansion builds the name
    "env {{AITK_PR_READY,X}}=1 ./ship.sh",
    "export {{AITK_PR_READY,X}}=1; ./ship.sh",
    # arithmetic and parameter-expansion setters (these export under `set -a`)
    "set -a; (( AITK_PR_READY = 1 )); ./ship.sh",
    "set -a; let SKIP_PRECHECK++; git push",
    "export AITK_PR_READY=0; ((++AITK_PR_READY)); ./ship.sh",
    "let AITK_PR_READY=1; ./ship.sh",
    "AITK_PR_READY[0]=1; ./ship.sh",
    "set -a; : ${{AITK_PR_READY:=1}}; ./ship.sh",
    "set -a; : ${{AITK_PR_READY=1}}; ./ship.sh",
    # values the tokenizer reads as falsy or empty
    "AITK_PR_READY=(1) ./ship.sh",
    "AITK_PR_READY=0\r1 ./ship.sh",
    "AITK_PR_READY=<(true) ./ship.sh",
    # a name quoted with a locale string
    "export AITK_PR_$\"READY\"=1; ./ship.sh",
    # write targets that are not assignments, scripts run separately, names built at run time
    "set -a; read AITK_PR_READY <<< 1; ./ship.sh",
    "set -a; printf -v AITK_PR_READY 1; ./ship.sh",
    "set -a; mapfile -t AITK_PR_READY <<< 1; ./ship.sh",
    "source ./set-override.sh; ./ship.sh",
    ". ./set-override.sh; ./ship.sh",
    "v=AITK_PR_READY; export \"${{!v}}\"=1; ./ship.sh",
    "X=READY; eval \"AITK_PR_$X=1\"; ./ship.sh",
    "env $(printf 'AITK_PR_READY=1') ./ship.sh",
    # an alias body is quoted text, and a profile write alters later shell startup
    "alias deliver='AITK_PR_READY=1 ./ship.sh'; deliver",
    "echo 'export AITK_PR_READY=1' >> ~/.zshrc",
    # heredoc bodies are skipped, so a body piped to a shell is not read
    "bash <<'EOF'\nAITK_PR_READY=1 ./ship.sh\nEOF",
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
    "git grep -n 'declare -n.*SKIP_PRECHECK'",
    "echo AITK_PR_READY=0",
    "echo AITK_PR_READY=false",
    "echo AITK_PR_READY=no",
    "echo AITK_PR_READY=off",
    "echo AITK_PR_READY=''",
    "echo AITK_PR_READY=\"0\"",
    "echo AITK_PR_READY='FALSE'",
    "echo AITK_PR_READY=\"off\"",
    "builtin export AITK_PR_READY=0",
    "command builtin export AITK_PR_READY=false",
    "builtin command export SKIP_PRECHECK=",
    "FOO+=x git status",
    "AITK_PR_READY=0 gh pr view 12",
    "AITK_PR_READY=0",
    "export AITK_PR_READY=0",
    "export SKIP_PRECHECK=",
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
        # A commit with a passing scripts/verify.py record, so `gh pr create` cases test
        # the draft rule alone (the verify gate has its own tests/test_verify_gate.py).
        cls.verified = cls.make_repo(base / "verified")
        (cls.verified / "app.py").write_text("x = 1\n")
        git(cls.verified, "add", "app.py")
        git(cls.verified, "commit", "-q", "-m", "base")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify.py"), "--", "true"],
            cwd=cls.verified,
            env=base_env(),
            capture_output=True,
            check=True,
        )
        cls.alt_index = base / "alt.index"
        # a checkout on a feature branch, and one on a detached HEAD
        cls.feature = cls.make_repo(base / "feature")
        git(cls.feature, "commit", "-q", "--allow-empty", "-m", "base")
        git(cls.feature, "switch", "-q", "-c", "feature")
        git(cls.clean, "remote", "add", "fork", str(base / "no-such-fork"))
        cls.detached = cls.make_repo(base / "detached")
        git(cls.detached, "commit", "-q", "--allow-empty", "-m", "base")
        git(cls.detached, "switch", "-q", "--detach")

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
            repo_home=os.path.relpath(repo, Path.home()),
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

    def test_a_force_push_is_checked_in_the_directory_it_runs_in(self) -> None:
        main, feature = self.clean, self.feature
        home = {"main_home": os.path.relpath(main, Path.home()), "feature_home": os.path.relpath(feature, Path.home())}
        for template, expected in (
            ("cd {main} && git push --force", 2),
            ("pushd {main} && git push --force", 2),
            ("cd ~/{main_home} && git push --force", 2),
            ("git push --force", 0),
            ("cd ~/{feature_home} && git push --force", 0),
            ("cd -P {feature} && git push --force", 0),
            # the cd fails, so the push runs here, on feature
            ("cd /nonexistent-aitk-dir; git push --force", 0),
        ):
            command = template.format(main=main, feature=feature, **home)
            with self.subTest(command=command):
                self.assertEqual(expected, self.run_hook(command, feature).returncode)
        # a detached HEAD is a branch the guard read: no branch, so not main
        for command in ("git push --force origin HEAD", "git push --force"):
            with self.subTest(command=command, repo="detached"):
                self.assertEqual(0, self.run_hook(command, self.detached).returncode)

    def test_the_directory_model_follows_subshells_and_conditional_cds(self) -> None:
        base = self.clean
        (base / "other").mkdir(exist_ok=True)
        here, other = str(base), str(base / "other")
        for command, expected in (
            # a subshell, a command substitution and a process substitution restore the directory
            ("(cd other); gh pr view 1", here),
            ("(cd other && npm test); gh pr view 1", here),
            ("echo $(cd other && pwd); gh pr view 1", here),
            ("cat <(cd other && ls); gh pr view 1", here),
            # words after a substitution are that command's arguments, not a cd of their own
            ("echo $(true) cd other; gh pr view 1", here),
            ("echo $(true) cd other && gh pr view 1", here),
            # a substitution where the command word stands may print nothing (`$(echo x >&2)`),
            # whatever its body looks like: the directory is unknown
            ("$(echo echo) cd other; gh pr view 1", None),
            ("$(echo x >/dev/null) cd other; gh pr view 1", None),
            ("diff <(true) cd other; gh pr view 1", here),
            ("echo $(true) $(true) cd other; gh pr view 1", here),
            ("echo $((1+2)) cd other; gh pr view 1", here),
            # after assignments only, the words start the command
            ("X=$(true) cd other && gh pr view 1", other),
            ("X=$(true) Y=$(true) cd other && gh pr view 1", other),
            ("(cd other && gh pr view 1)", other),
            # the rest of an && chain runs only if the cd did
            ("x && cd other && gh pr view 1", other),
            ("cd other && gh pr view 1", other),
            # an unconditional cd decides by whether the directory exists
            ("cd other || exit 1; gh pr view 1", other),
            # a cd that may not have run: unknown once its list ends
            ("false && cd other; gh pr view 1", None),
            ("true || cd other && gh pr view 1", None),
            ("if true; then cd other; fi; gh pr view 1", None),
            ("for i in 1; do cd other; done; gh pr view 1", None),
            ("cd other | cat; gh pr view 1", None),
            ("cd other & gh pr view 1", None),
            # a cd the walk cannot see run
            ("eval 'cd other'; gh pr view 1", None),
            ("f() { cd other; }; f; gh pr view 1", None),
            # a prefix that changes nothing about cd
            ("builtin cd other && gh pr view 1", other),
            ("command cd other && gh pr view 1", other),
            # a group runs in this shell
            ("{ cd other; }; gh pr view 1", other),
            # a quoted or escaped paren is a bare token: the paren stack is not trusted
            ("echo ')'; cd other && gh pr view 1", None),
            ("find . \\( -name x \\) ; cd other && gh pr view 1", None),
            ("echo ')'; gh pr view 1", here),
            # a `~` in an assigned value: bash keeps a quoted one, and the quotes are gone here
            ("S='~/other'; cd $S && gh pr view 1", None),
            # an absolute cd makes the directory known again
            (f"false && cd other; cd {here} && gh pr view 1", here),
            # case bodies are bodies, and their parens are pattern syntax
            ("case x in a) cd other;; esac; gh pr view 1", None),
            ("case x in a) true;; esac; (cd other); gh pr view 1", here),
            ("case x in (a) true;; esac; (cd other); gh pr view 1", here),
            ("while x; do cd other; done; gh pr view 1", None),
            ("until x; do cd other; done; gh pr view 1", None),
            # a group that ends in `&` or a pipe, or only runs conditionally
            ("{ cd other; } & gh pr view 1", None),
            ("{ cd other; } | cat; gh pr view 1", None),
            ("x && { cd other; }; gh pr view 1", None),
            ("x && cd other || gh pr view 1", None),
            # the exact words `cd`, `pushd`, `popd`, after builtin/command/time prefixes
            ("time -p cd other && gh pr view 1", other),
            ("time cd other && gh pr view 1", other),
            ("CD other && gh pr view 1", here),
            ("/usr/bin/cd other && gh pr view 1", here),
            ("command -v cd; gh pr view 1", here),
            ("command -V cd; gh pr view 1", here),
            # a function runs where it is called: once one is defined, a cd after it is unknown
            ("function f { cd other; }; f; gh pr view 1", None),
            ("f()\n{\n  cd other\n}\ngh pr view 1", None),
            ("function f\n{\n  cd other\n}\ngh pr view 1", None),
            ("f ( ) { cd other; }; gh pr view 1", None),
            ("f() { echo '}'; cd other; }; gh pr view 1", None),
            ("f() { gh pr view 1; }; cd other; f", None),
            (f"f() {{ cd other; }}; cd {here}; gh pr view 1", None),
            # fi, done and esac close a body only as the first word of a segment
            ("case x in a) true;; done) cd other;; esac; gh pr view 1", None),
            ("if false; then command fi; cd other; fi; gh pr view 1", None),
            ("if false; then X=1 fi; cd other; fi; gh pr view 1", None),
            # a quoted or escaped operator, or a paren in ${...}, is a bare token
            ("echo '('; cd other; echo ')'; gh pr view 1", None),
            ("echo \\(; cd other; echo \\); gh pr view 1", None),
            ("echo ${x:-(}; cd other; echo ${y:-)}; gh pr view 1", None),
            ("echo ';' cd other ';'; gh pr view 1", None),
            ("find . -exec true {} \\; ; cd other && gh pr view 1", None),
            # a variable an earlier segment set to a literal path
            ("S=other; cd $S && gh pr view 1", other),
            ("S=other; cd ${S} && gh pr view 1", other),
            ("S=other; cd \"$S/.\" && gh pr view 1", other),
            ("export S=other; cd $S && gh pr view 1", other),
            ("T=1 S=other; cd $S && gh pr view 1", other),
            ("S=other; ( S=sub ); cd $S && gh pr view 1", other),
            ("S=$X; cd $S && gh pr view 1", None),
            ("S=other; S=$X; cd $S && gh pr view 1", None),
            ("S=other; S+=x; cd $S && gh pr view 1", None),
            ("S=other; read S; cd $S && gh pr view 1", None),
            ("S=other; unset S; cd $S && gh pr view 1", None),
            ("S=other; eval 'true'; cd $S && gh pr view 1", None),
            ("false && S=other; cd $S && gh pr view 1", None),
            ("true || S=other; cd $S && gh pr view 1", None),
            ("S=other | cat; cd $S && gh pr view 1", None),
            ("S=other & cd $S && gh pr view 1", None),
            ("if x; then S=other; fi; cd $S && gh pr view 1", None),
            ("(S=other); cd $S && gh pr view 1", None),
            ("S=other cd $S && gh pr view 1", None),
            ("S=other; cd ${S:-x} && gh pr view 1", None),
            ("S=other; T=x; cd $S$T && gh pr view 1", None),
            ("cd $PWD && gh pr view 1", None),
            ("cd $UNSET && gh pr view 1", None),
            # an assignment after a keyword, in a group, with a redirection, cut or an element
            ("S=other; if x; then S=sub; fi; cd $S && gh pr view 1", None),
            ("S=other; if x; then :; else S=sub; fi; cd $S && gh pr view 1", None),
            ("S=other; for d in x; do S=sub; done; cd $S && gh pr view 1", None),
            ("S=other; { S=sub; }; cd $S && gh pr view 1", None),
            ("S=other; S=sub >/dev/null; cd $S && gh pr view 1", None),
            ("S=other; S=`echo sub`; cd $S && gh pr view 1", None),
            ("S=other; S[0]=sub; cd $S && gh pr view 1", None),
            ("S=other; S=sub cd $S && gh pr view 1", other),
            ("S='other x'; cd $S && gh pr view 1", None),
            # a `;` inside a body does not end the list that a backgrounded compound closes
            ("cd other && { :; :; } & gh pr view 1", None),
            ("cd other && for i in 1; do :; done & gh pr view 1", None),
            ("cd other && if x; then :; fi & gh pr view 1", None),
            ("cd other && while x; do :; done & gh pr view 1", None),
            # a nested `case` is a keyword, not a pattern
            ("case x in a) case y in b) :;; esac; cd other;; esac; gh pr view 1", None),
        ):
            with self.subTest(command=command):
                walked = [found for found in shell_tokens.commands(command, here) if found.is_gh]
                self.assertEqual(1, len(walked))
                self.assertEqual(expected, walked[0].workdir)

    def test_a_force_push_after_a_subshell_or_conditional_cd_is_checked_where_it_runs(self) -> None:
        main, feature = self.clean, self.feature
        for template, cwd, expected in (
            # from main: the push runs in main, or may
            ("(cd {feature}); git push --force", main, 2),
            ("echo $(cd {feature}); git push --force", main, 2),
            ("false && cd {feature}; git push --force", main, 2),
            ("true || cd {feature} && git push --force", main, 2),
            ("if true; then cd {feature}; fi; git push --force", main, 2),
            ("eval 'cd {feature}'; git push --force", main, 2),
            ("f() {{ cd {feature}; }}; f; git push --force", main, 2),
            ("cd {feature} | cat; git push --force", main, 2),
            # from main: the push runs in feature
            ("(cd {feature} && git push --force)", main, 0),
            ("cd {feature} || exit 1; git push --force", main, 0),
            ("x=1 && cd {feature} && git push --force", main, 0),
            ("builtin cd {feature} && git push --force", main, 0),
            ("{{ cd {feature}; }}; git push --force", main, 0),
            # from feature: the push runs in feature (blocked before: the subshell's cd leaked)
            ("(cd {main} && git status); git push --force", feature, 0),
            # an ungated command never blocks on an unknown directory
            ("false && cd {feature}; git status", main, 0),
            # fake parens never restore: the cd between them runs here
            ("echo '('; cd {main}; echo ')'; git push --force", feature, 2),
            ("echo \\(; cd {main}; echo \\); git push --force", feature, 2),
            ("echo ${{x:-(}}; cd {main}; echo ${{y:-)}}; git push --force", feature, 2),
            ("echo ';' cd {main} ';'; git push --force", feature, 2),
            # only the exact builtin words move the shell
            ("CD {feature}; git push --force", main, 2),
            ("/usr/bin/cd {feature}; git push --force", main, 2),
            ("time -p cd {feature} && git push --force", main, 0),
            ("command cd {feature} && git push --force", main, 0),
            # a function's cd runs at the call
            ("f() {{ cd {main}; }}; cd {feature}; f; git push --force", feature, 2),
            ("f()\n{{\n  cd {feature}\n}}\ngit push --force", main, 2),
            # a variable set to a literal path names that directory
            ("S={feature}; cd $S && git push --force", main, 0),
            ("S={feature}; git -C $S push --force", main, 0),
            ('S={feature}; cd "$S" && git push --force', main, 0),
            ("export S={feature}; cd ${{S}} && git push --force", main, 0),
            ("S={main}; cd $S && git push --force", feature, 2),
            ("S={main}; git -C $S push --force", feature, 2),
            ("false && S={feature}; cd $S && git push --force", main, 2),
            ("false && S={main}; git -C $S push --force", feature, 2),
            ("S={feature} cd $S && git push --force", main, 2),
            ("(S={feature}); cd $S && git push --force", main, 2),
            ("S={feature}; S=$OTHER; cd $S && git push --force", main, 2),
            ("S={feature}; S=$OTHER; git -C $S push --force", main, 2),
            # an assignment the table must not miss
            ("DIR={feature}; if [ -d {main} ]; then DIR={main}; fi; cd $DIR && git push --force", feature, 2),
            ("DIR={feature}; if [ -d {main} ]; then DIR={main}; fi; git -C $DIR push --force", feature, 2),
            ("DIR={feature}; if [ -d {main} ]; then DIR={main}; fi; env -C $DIR git push --force", feature, 2),
            ("D={feature}; for d in x; do D={main}; done; cd $D && git push --force", feature, 2),
            ("S={feature}; {{ S={main}; }}; cd $S && git push --force", feature, 2),
            ("S={feature}; S={main} >/dev/null; cd $S && git push --force", feature, 2),
            ("S={feature}; S=`echo {main}`; cd $S && git push --force", feature, 2),
            ("S={feature}; S[0]={main}; cd $S && git push --force", feature, 2),
            ("S='{feature} x'; cd $S && git push --force", main, 2),
            # a list closed by `&` after a compound keeps the cd it held
            ("cd {feature} && {{ :; :; }} & git push --force", main, 2),
            # an argument that spells cd, after a substitution, moves nothing
            ("echo $(true) cd {feature}; git push --force", main, 2),
            ("echo $(true) cd {feature} && git push --force", main, 2),
            ("X=$(true) cd {feature} && git push --force", main, 0),
            ("cd {feature} && for i in 1; do :; done & git push --force", main, 2),
            ("cd {feature} && if true; then :; fi & git push --force", main, 2),
            ("cd {feature} && while false; do :; done & git push --force", main, 2),
            # the shell expands the current branch where it stands, not in the push's directory
            ("git -C {feature} push --force origin $(git branch --show-current)", main, 2),
            ('git -C {feature} push --force origin "$(git branch --show-current)"', main, 2),
            ("git -C {feature} push --force origin `git branch --show-current`", main, 2),
            ("env -C {feature} git push --force origin $(git branch --show-current)", main, 2),
            ("git -C {main} push --force origin $(git branch --show-current)", feature, 2),
            # `@` is HEAD, a lone remote is a remote and `heads/main` is main
            ("git push --force origin @", main, 2),
            ("git push --force origin @", feature, 0),
            ("git push --force fork", main, 2),
            ("cd $NOWHERE && git push --force fork", feature, 2),
            ("git push --force origin HEAD:heads/main", feature, 2),
            ("git push --force origin heads/main", feature, 2),
        ):
            command = template.format(main=main, feature=feature)
            with self.subTest(command=command):
                self.assertEqual(expected, self.run_hook(command, cwd).returncode)

    def test_a_literal_variable_names_the_directory_of_a_commit(self) -> None:
        for command, expected in (
            ("S={staged}; cd $S && git commit -m state", 2),
            ("S={clean}; cd $S && git commit -m x", 0),
            ("S={staged}; git -C $S commit -m state", 2),
            ("S={clean}; git -C $S commit -m x", 0),
            ("S=$X; cd $S && git commit -m x", 2),
            ("S={clean}; if true; then S={staged}; fi; cd $S && git commit -m x", 2),
        ):
            command = command.format(staged=self.staged, clean=self.clean)
            with self.subTest(command=command):
                self.assertEqual(expected, self.run_hook(command, self.staged).returncode)

    def test_home_is_the_home_directory_in_a_cd_target(self) -> None:
        home = self.clean
        (home / "homesub").mkdir(exist_ok=True)
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            for command, expected in (
                ("cd $HOME/homesub && gh pr view 1", str(home / "homesub")),
                ("cd ${HOME}/homesub && gh pr view 1", str(home / "homesub")),
                ("cd $HOME && gh pr view 1", str(home)),
                ("HOME=$X; cd $HOME/homesub && gh pr view 1", None),
            ):
                with self.subTest(command=command):
                    walked = [c for c in shell_tokens.commands(command, "/") if c.is_gh]
                    self.assertEqual([expected], [c.workdir for c in walked])

    def test_a_quoted_redirection_operator_hides_no_flag(self) -> None:
        for command in (
            "gh pr create --draft --fill --title '>' --draft=false",
            "gh pr create --draft --fill --body '<' --draft=false",
            "gh pr create --draft --fill --title \\> --draft=false",
            "gh pr create --draft --fill --title '>>' --draft=false",
            "gh pr create --draft --fill --title=$(echo t) --draft=false",
            "gh api --jq '>' -X PUT repos/o/r/pulls/12/merge",
            "gh pr merge 12 --help --help=false",
        ):
            with self.subTest(command=command):
                self.assertEqual(2, self.run_hook(command, self.verified).returncode)
        # the verify gate loses no `--head`, and has no override
        for command in (
            "gh pr create --draft --fill --title '>' --head other",
            "gh pr create --draft --fill --body=$(cat b.md) --head other",
        ):
            with self.subTest(command=command):
                result = self.run_hook(command, self.verified, env={"AITK_PR_READY": "1"})
                self.assertEqual(2, result.returncode, result.stderr)
        # a draft create next to one is told to run on its own, override or not
        for env in ({}, {"AITK_PR_READY": "1"}):
            with self.subTest(env=env):
                result = self.run_hook("echo '>' && gh pr create --draft --fill", self.verified, env=env)
                self.assertEqual(2, result.returncode)
                self.assertIn("as a command of its own", result.stderr)
        # one quoted word with an operator in it changes nothing
        for command in ("gh pr create --draft --fill --title 'a > b'", "gh pr merge 12 --help"):
            with self.subTest(command=command):
                self.assertEqual(0, self.run_hook(command, self.verified).returncode)

    def test_a_quoted_separator_in_unparsed_nested_text_does_not_split_gh_pr(self) -> None:
        command = 'gh pr -t "a;b" merge 12'
        for _ in range(5):
            command = "sh -c " + shlex.quote(command)
        self.assertEqual(2, self.run_hook(command, self.verified).returncode)

    def test_graphql_variable_definitions_and_endpoint_spellings(self) -> None:
        for query in (
            "query($o: String! $n: String!){x}",
            "query($o: String!\n$n: String!){x}",
        ):
            with self.subTest(query=query):
                self.assertFalse(gh_args.read_api(["graphql", "-f", "query=" + query]).unreadable_query)
        self.assertTrue(gh_args.read_api(["graphql", "-f", "query={x(a: \"$5\")}"]).unreadable_query)
        for endpoint in ("repos/o/r/pulls/12/./merge", "repos/o//r/pulls/12/merge", "repos/o/r/pulls/12/%6Derge"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(gh_args.MERGE_API, gh_args.api_effect(["-X", "PUT", endpoint]))
        self.assertEqual(
            gh_args.MERGE_API,
            gh_args.api_effect(["-X", "POST", "-H", "X-HTTP-Method-Override: PUT", "repos/o/r/pulls/12/merge"]),
        )
        self.assertIsNone(gh_args.api_effect(["repos/o/r/pulls/12"]))
        self.assertTrue(gh_args.walk(["12", "--help"], "merge").asks_help)
        self.assertFalse(gh_args.walk(["12", "--help", "--help=false"], "merge").asks_help)

    def test_the_two_readers_walk_a_payload_under_the_same_doubt(self) -> None:
        here = str(self.clean)
        for command, expected in (
            ("echo ')'; bash -c 'cd /usr && git push'", None),
            ("false && cd /tmp; env -C /usr git push", None),
            ("bash -c 'cd /usr && git push'", "/usr"),
            ("env -C /usr git push", "/usr"),
        ):
            with self.subTest(command=command):
                walked = [c for c in shell_tokens.commands(command, here) if c.name == "git"]
                self.assertEqual([expected], [c.workdir for c in walked])
        # the alias recursions keep the flag
        self.assertTrue(
            git_guard.parse_git_actions(
                shell_tokens.tokenize("echo ')'; git -c alias.p=push p"), here
            )[0]["untrusted"]
        )

    def test_a_crash_in_the_guard_blocks_what_quoting_hides(self) -> None:
        deep = "f() { " * 400 + ":; " + "}; " * 400
        self.assertEqual(2, self.run_hook(deep + "g'i't commit --no-verify -m x", self.clean).returncode)
        # an internal error reads the unquoted text, not only the raw one
        with mock.patch.object(git_guard, "evaluate", side_effect=RuntimeError("boom")):
            for command, expected in (("g'i't push", 2), ("echo hello", 0)):
                with self.subTest(command=command):
                    stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": "/"}))
                    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stderr", io.StringIO()):
                        self.assertEqual(expected, git_guard.main())

    def test_ansi_c_quoting_does_not_hide_the_rest_of_the_command(self) -> None:
        self.assertEqual(2, self.run_hook("echo $'\\'' ; git commit --no-verify -m x #'", self.clean).returncode)
        self.assertEqual(0, self.run_hook("printf $'a\\nb'; git status", self.clean).returncode)
        self.assertEqual(["printf", "a\nb", ";", "git", "status"], shell_tokens.tokenize("printf $'a\\nb'; git status")[:5][:2] + [";", "git", "status"])
        self.assertEqual(["echo", "'", ";", "echo"], shell_tokens.tokenize("echo $'\\'' ; echo"))
        with self.assertRaises(ValueError):
            shell_tokens.tokenize("echo $'abc")

    def test_a_push_destination_behind_an_expansion_is_unknown(self) -> None:
        for command, repo, expected in (
            ("git push --force origin $BR", self.clean, 2),
            ("git push --force origin $BR", self.feature, 2),
            ("git push --delete origin `echo x`", self.feature, 2),
            ("git push origin $BR", self.clean, 0),
            ("git push --force origin \"$(git branch --show-current)\"", self.clean, 2),
            ("git push --force origin \"$(git branch --show-current)\"", self.feature, 0),
            ("git push --force origin $(git branch --show-current)", self.clean, 2),
            ("git push --force origin $(git branch --show-current)", self.feature, 0),
            ("git push --force origin `git branch --show-current`", self.feature, 0),
        ):
            with self.subTest(command=command, repo=repo.name):
                self.assertEqual(expected, self.run_hook(command, repo).returncode)

    def test_ordinary_commands_are_allowed(self) -> None:
        self.assert_cases(CLEAN_ALLOW, self.clean, 0)
        self.assert_cases(("echo --no-verify", "echo git commit --no-verify"), self.staged, 0)

    def test_nested_text_the_guard_cannot_parse_is_read_in_every_gated_match(self) -> None:
        for inner in (
            "gh pr revert 9 -d; gh pr merge 12",
            "gh pr revert 9 --draft && gh pr ready 12",
            "gh pr create -d --fill; gh pr merge 12",
            "gh pr create --fill; ls -d .",
            "gh pr revert 9; ls -d .",
        ):
            command = inner
            for _ in range(5):
                command = "sh -c " + shlex.quote(command)
            with self.subTest(inner=inner):
                result = self.run_hook(command, self.verified)
                self.assertEqual(2, result.returncode, result.stderr)

    def test_an_unreadable_verb_asks_for_the_literal_command(self) -> None:
        result = self.run_hook("gh pr $V 12", self.verified)
        self.assertEqual(2, result.returncode)
        self.assertIn("Write the command and the verb literally", result.stderr)

    def test_state_commit_names_the_files(self) -> None:
        result = self.run_hook("git add .ai-toolkit/config.json && git commit -m config", self.clean)
        self.assertEqual(2, result.returncode)
        self.assertIn(".ai-toolkit/config.json", result.stderr)
        self.assertIn("stay out of commits", result.stderr)

    def test_pr_ready_and_merge_need_the_users_override(self) -> None:
        # Every case runs where the commit has a passing verify record, so a block on a
        # creation comes from the draft rule, not from the verify gate.
        self.assert_cases(PR_PUBLISH_BLOCK, self.verified, 2)
        # the retired v0.3 override in the session environment lifts nothing either
        self.assert_cases(PR_PUBLISH_BLOCK, self.verified, 2, env={"SKIP_PR_GATE": "1"})
        self.assert_cases(PR_PUBLISH_BLOCK, self.verified, 2, env={"AITK_PR_READY": "0"})
        self.assert_cases(PR_PUBLISH_ALLOW, self.verified, 0)
        self.assert_cases(PR_PUBLISH_LIMITS, self.clean, 0)
        self.assert_cases(("gh pr create --fill",), self.verified, 0, env={"AITK_PR_READY": "1"})
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

    def test_gh_api_calls_that_publish_a_pr_follow_the_pr_rules(self) -> None:
        merge_or_ready = (
            "gh api -X PUT repos/o/r/pulls/12/merge",
            "gh api --method=put repos/{{owner}}/{{repo}}/pulls/12/merge",
            "gh api -iX PUT repos/o/r/pulls/12/merge",
            "gh api repos/o/r/pulls/$PR/merge -X PUT -f merge_method=squash",
            "gh api /repos/o/r/pulls/12/merge -X GET -X PUT",
            "gh api https://api.github.com/repos/o/r/pulls/12/merge --method PUT",
            "gh api graphql -f query='mutation{{mergePullRequest(input:{{}}){{clientMutationId}}}}'",
            "gh api /graphql -f query='mutation{{markPullRequestReadyForReview(input:{{}}){{clientMutationId}}}}'",
            "gh api graphql -f query='mutation{{enablePullRequestAutoMerge(input:{{}}){{clientMutationId}}}}'",
            "gh api graphql -f query='mutation{{enqueuePullRequest(input:{{}}){{clientMutationId}}}}'",
            "\"$GH\" api -X PUT repos/o/r/pulls/12/merge",
            # git handed text that runs one
            "git rebase -x 'gh api -X PUT repos/o/r/pulls/12/merge' HEAD~1",
        )
        # opening a PR this way skips the verify gate, which has no override
        create = (
            "gh api repos/o/r/pulls -f title=t -f head=x -f base=main",
            "gh api 'repos/o/r/pulls?x=1' -f title=t",
            "gh api -X POST repos/o/r/pulls --input body.json",
            "gh api graphql -f query='mutation{{createPullRequest(input:{{}}){{clientMutationId}}}}'",
            "gh api graphql -f query='mutation{{revertPullRequest(input:{{}}){{clientMutationId}}}}'",
        )
        # a query the guard cannot read could be any of them
        unreadable = (
            "gh api graphql --input query.json",
            "gh api graphql -F query=@query.graphql",
            "gh api graphql -f query=\"$Q\"",
            "gh api graphql -f query=\"$(cat q.graphql)\"",
        )
        allowed = (
            "gh api repos/o/r/pulls",
            "gh api repos/o/r/pulls/12",
            "gh api repos/o/r/pulls/12/merge",
            "gh api repos/o/r/pulls/12/merge --method GET",
            "gh api repos/o/r/pulls -X GET -f state=open",
            "gh api repos/o/r/pulls/12/comments -f body=ok",
            "gh api repos/o/r/issues/12/comments -f body=ok",
            "gh api graphql -f query='query{{viewer{{login}}}}'",
            "gh api graphql -f query='query($n:Int!){{viewer{{repositories(first:$n){{totalCount}}}}}}' -F n=1",
            "gh api graphql -f query='mutation{{addComment(input:{{}}){{clientMutationId}}}}'",
        )
        self.assert_cases(merge_or_ready + create + unreadable, self.verified, 2)
        self.assert_cases(allowed, self.verified, 0)
        # the user's override lifts merging and readying, never an unchecked PR or an unread query
        self.assert_cases(merge_or_ready[:-1], self.verified, 0, env={"AITK_PR_READY": "1"})
        self.assert_cases(create + unreadable, self.verified, 2, env={"AITK_PR_READY": "1"})

    def test_gh_api_reads_the_shell_around_it(self) -> None:
        merge = (
            "gh api >/dev/null -X PUT repos/o/r/pulls/12/merge",
            "gh >/dev/null api -X PUT repos/o/r/pulls/12/merge",
            "gh api repos/o/r/pulls/$(echo 12)/merge -X PUT",
            "gh api graphql -F id=$(echo x) -f query='mutation{{mergePullRequest(input:{{}}){{clientMutationId}}}}'",
            "gh api -X PUT 'repos/o/r/pulls/12/merge#x'",
            "gh api -X PUT repositories/1/pulls/12/merge",
            "gh api -X PUT \"repos/o/r/pulls/12/${{X:?}}erge\"",
            "gh api https://ghe.example.com/api/graphql -f query='mutation{{mergePullRequest(input:{{}}){{clientMutationId}}}}'",
            "gh >/dev/null pr merge 12",
            "gh pr >/dev/null merge 12",
            "gh 2>&1 pr ready 12",
        )
        create = (
            "gh api repos/$(echo o/r)/pulls -f title=t",
            "gh api repositories/1/pulls -f title=t",
            "gh api 'repos/o/r/pulls#x' -f title=t",
            "echo repos/o/r/pulls/12/merge | xargs gh api -X PUT",
            "gh api graphql -f query=\"mutation{{$M(input:{{}}){{clientMutationId}}}}\"",
        )
        allowed = (
            "gh api repos/o/r/pulls > \"$OUT\"",
            "gh api graphql -f query='query{{viewer{{login}}}}' >> $LOG",
            "gh api repos/o/r/pulls 2>\"$ERR\"",
            "gh api repos/o/r/pulls/$PR -X PATCH -f body=x",
            "gh api -X PATCH repos/{{owner}}/{{repo}}/issues/$N -f state=closed",
            "gh api -X DELETE repos/{{owner}}/{{repo}}/issues/comments/$ID",
            "gh api repos/$GITHUB_REPOSITORY/statuses/$SHA -f state=success",
            "gh api -X HEAD repos/o/r/pulls",
            "gh api -X PUT \"repos/{{owner}}/{{repo}}/contents/docs/$NAME.md\" -f message=m",
            "gh api graphql -f query='query($ids:[ID!]!){{nodes(ids:$ids){{id}}}}' -f 'ids[]=A'",
            "gh api -h",
            "VERSION=$(cat VERSION) npm run api graphql --input f",
            "git rebase -x 'gh api repos/o/r/pulls/1/comments' HEAD~1",
        )
        self.assert_cases(merge, self.verified, 2)
        self.assert_cases(create, self.verified, 2)
        self.assert_cases(allowed, self.verified, 0)
        self.assert_cases(("$(command -v gh) pr merge 12",), self.verified, 2)
        # a literal backtick in a query is unreadable: an accepted over-block, no override
        backtick = "gh api graphql -f query='mutation{{addComment(input:{{body:\"`x`\"}}){{clientMutationId}}}}'"
        self.assert_cases((backtick,), self.verified, 2, env={"AITK_PR_READY": "1"})
        # with the override a merge goes through, a create or an unread query does not
        self.assert_cases(merge[:2] + merge[4:8], self.verified, 0, env={"AITK_PR_READY": "1"})

    def test_a_text_fallback_for_gh_api_names_gh_api(self) -> None:
        for command in (
            "git rebase -x 'gh api repos/o/r/pulls' HEAD~1",
            "git rebase -x 'gh api graphql --input q.json' HEAD~1",
            "git rebase -x 'gh api -X PUT repos/o/r/pulls/12/merge' HEAD~1",
        ):
            result = self.run_hook(command, self.verified)
            self.assertEqual(2, result.returncode, command)
            self.assertIn("gh api", result.stderr, command)

    def test_a_non_draft_pr_is_sent_back_for_a_draft(self) -> None:
        result = self.run_hook("gh pr create --fill", self.verified)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("--draft", result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        # The override is the user's to set; the message never spells it out.
        self.assertNotIn("AITK_PR_READY", result.stderr)

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
        # AITK_PR_READY lifts the publish check's block, but an unreadable command could
        # hide a `gh pr create`, and the verify gate has no override, so it still blocks
        with self.assertRaises(git_guard.Blocked) as caught:
            git_guard.evaluate(spent + "; gh pr merge 12", cwd, {"AITK_PR_READY": "1"})
        self.assertIn("could not be read in full", str(caught.exception))

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
            'bash -c "echo hi; declare -x AITK_PR_READY \'"',
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
            (["-"], None),  # the previous directory is not tracked
            (["$OTHER/.."], None),  # not the directory above a folder named `$OTHER`
            (["$DIR"], None),  # a folder with that literal name exists, but the shell expands it
            (["`pwd`"], None),
            (["a\nb"], None),
        ):
            with self.subTest(args=args):
                self.assertEqual(expected, shell_tokens.advance_dir(base, args))
        self.assertIsNone(shell_tokens.advance_dir(None, ["sub"]))
        self.assertEqual(os.path.expanduser("~"), shell_tokens.advance_dir(base, ["~"]))
        self.assertEqual(os.path.expanduser("~"), shell_tokens.advance_dir(base, []))  # a bare `cd`
        self.assertEqual(f"{base}/sub", shell_tokens.advance_dir(base, ["-P", "sub"]))
        walked = list(shell_tokens.commands("pushd sub && popd && gh pr view 1", base))
        self.assertIsNone(walked[-1].workdir)  # the directory stack is not tracked
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

    def test_many_git_commands_in_one_command_stay_fast(self) -> None:
        # each push asked git the same questions again: about 25 ms each, past the deadline at 3,000
        for text in ("git push origin feature; " * 3000, "x git push origin feature; " * 3000):
            with self.subTest(text=text[:20]):
                started = time.monotonic()
                git_guard.evaluate(text, str(self.feature), {})
                self.assertLess(time.monotonic() - started, 10.0)

    def test_long_runs_of_words_that_may_expand_to_nothing_stay_fast_and_block(self) -> None:
        # one reading per empty word nested past Python's recursion limit, and every `$(` read
        # the command's words again from its first
        cwd = str(self.feature)
        for text in (
            "$X " * 3000 + f"cd {self.clean}; git push --force",
            "$X command " * 1500 + f"cd {self.clean}; git push --force",
            "`true` " * 3000 + f"cd {self.clean}; git push --force",
            "$(true) " * 2000 + f"cd {self.clean}; git push --force",
            "$X " * 5000 + "git push --force origin main",
        ):
            with self.subTest(text=text[:20]):
                started = time.monotonic()
                with self.assertRaises(git_guard.Blocked):
                    git_guard.evaluate(text, cwd, {})
                self.assertLess(time.monotonic() - started, 5.0)

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
        for other in ('cd "$(git rev-parse --show-cdup)"', 'cd "$(git rev-parse --show-toplevel)/x"', 'cd "$HOME$X"'):
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

    def test_the_in_process_deadlines_sit_below_the_hook_timeouts(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"]
        timeouts = {Path(h["command"].split("/hooks/")[1].rstrip('"')).name: h["timeout"] for h in hooks}
        # a margin for interpreter start-up and the wrapper around the deadline
        self.assertLessEqual(git_guard.DEADLINE_SECONDS + 5, timeouts["prevent-project-commit.sh"])

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
        text = "AITK_PR_READY=1; export AITK_PR_READY; uv run ship --ready"
        self.assertEqual(
            [["export", "AITK_PR_READY"], ["uv", "run", "ship", "--ready"]],
            [c.argv for c in shell_tokens.commands(text, cwd)],
        )
        found = list(shell_tokens.commands(text, cwd, include_assignments=True))
        self.assertEqual([], found[0].argv)
        self.assertEqual({"AITK_PR_READY": "1"}, found[0].assignments)
        self.assertEqual(["export", "AITK_PR_READY"], found[1].argv)

        # the nested path: the assignment comes out before `true`
        nested = list(shell_tokens.commands("bash -c 'SKIP_PRECHECK=1; true'", cwd, include_assignments=True))
        self.assertEqual([[], ["true"]], [c.argv for c in nested])
        self.assertEqual({"SKIP_PRECHECK": "1"}, nested[0].assignments)
        self.assertEqual([["true"]], [c.argv for c in shell_tokens.commands("bash -c 'SKIP_PRECHECK=1; true'", cwd)])

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
            newline = self.run_hook("\nAITK_PR_READY=1 ./ship.sh --ready", self.clean, wrapper_env=env)
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

    # ---- round 2: the classes the second Fable review found ----

    def hook_codes(self, cases: tuple, **kwargs) -> None:
        for template, repo, expected in cases:
            command = template.format(main=self.clean, feature=self.feature)
            with self.subTest(command=command, repo=repo.name):
                result = self.run_hook(command, repo, **kwargs)
                self.assertEqual(expected, result.returncode, result.stderr)

    def test_unparsed_nested_text_blocks_wherever_origin_main_does(self) -> None:
        main_verbs = shell_tokens.words_in_order
        frozen_pattern = (shell_tokens.WORD_GH, shell_tokens.WORD_PR, re.compile(r"\b(ready|merge|create|new)\b"))

        def main_blocks(text: str) -> bool:
            # origin/main's rule for text that did not parse, frozen
            match = main_verbs(text, *frozen_pattern)
            return bool(match and not (match.group(1) in {"create", "new"} and git_guard.DRAFT_FLAG.search(text)))

        holders = ("$((1|2))", "${X-a;b}", '"$(echo "a;b")"', "$'a\\';b'", "'a;b'", '"a|b"', "# it's\n")
        verbs = ("merge 12", "ready 12", "create --fill", "create --draft --fill", "new --fill")
        checked = 0
        for holder in holders:
            for verb in verbs:
                for levels in (1, 2, 3, 5):
                    inner = f"gh pr -t {holder} {verb}" if not holder.startswith("#") else f"{holder}gh pr {verb}"
                    text = inner
                    for _ in range(levels):
                        text = "sh -c " + shlex.quote(text)
                    if not main_blocks(text):
                        continue
                    checked += 1
                    with self.subTest(text=text[:80]):
                        with self.assertRaises(git_guard.Blocked):
                            git_guard.check_pr_publish(text, str(self.clean), {})
        self.assertGreater(checked, 50)
        for levels in (1, 4):
            text = "gh pr -t $((1|2)) merge 12"
            for _ in range(levels):
                text = "sh -c " + shlex.quote(text)
            self.assertEqual(2, self.run_hook(text, self.verified).returncode)

    def test_a_quoted_operator_makes_the_gh_reading_textual(self) -> None:
        self.hook_codes(
            (
                ("gh >/dev/null pr -t '>' merge 12 --squash", self.clean, 2),
                ("gh pr >/dev/null -t '<' ready 12", self.clean, 2),
                ("gh >/dev/null pr -t '>' create --fill --head other", self.feature, 2),
                ("gh pr -t ';' merge 12", self.clean, 2),
                ("gh pr -t '|' ready 12", self.clean, 2),
                ("gh pr -R '(' merge 12", self.clean, 2),
                ("gh pr -t \\; merge 12", self.clean, 2),
                ("gh api --jq '>' -X >/dev/null PUT repos/o/r/pulls/12/merge", self.clean, 2),
                ("gh api --jq '>' -X >/dev/null POST repos/o/r/pulls", self.clean, 2),
                ("sh -c 'gh pr -t \"$(echo \"a;b\")\" merge 12'", self.clean, 2),
                # ordinary commands with a real redirection or a quoted word that holds an operator
                ("gh pr create --draft --fill >/dev/null", self.verified, 0),
                ("gh pr create --draft --fill --title 'a > b' 2>&1", self.verified, 0),
                ("gh pr create --draft --fill --body \"$(cat <<'EOF'\na; b | c\nEOF\n)\"", self.verified, 0),
            )
        )
        # the override lifts merge and ready, not the quoted-operator create
        self.assertEqual(0, self.run_hook("gh pr -t ';' merge 12", self.clean, env={"AITK_PR_READY": "1"}).returncode)
        result = self.run_hook("gh >/dev/null pr -t '>' create --fill", self.verified, env={"AITK_PR_READY": "1"})
        self.assertEqual(2, result.returncode)
        self.assertIn("as a command of its own", result.stderr)
        result = self.run_hook("gh >/dev/null pr -t '>' create --fill", self.verified)
        self.assertIn("as a command of its own", result.stderr)

    def test_a_real_redirection_behind_a_wrapper_is_no_quoted_operator(self) -> None:
        for command in (
            "setsid gh pr create --draft --fill >/dev/null",
            "uv run gh pr ready 12 --undo 2>&1",
            "op run -- gh pr create --draft --fill 2>/dev/null",
            "flock /tmp/x gh pr create --draft --fill </dev/null",
        ):
            with self.subTest(command=command):
                self.assertEqual(0, self.run_hook(command, self.verified).returncode)
        self.assertEqual(2, self.run_hook("setsid gh pr merge 12 >/dev/null", self.verified).returncode)
        self.assertEqual(2, self.run_hook("setsid gh pr -t '>' merge 12", self.verified).returncode)

    def test_a_substitution_is_one_word_of_its_command(self) -> None:
        self.hook_codes(
            (
                ("gh -R $(echo o/r) pr merge 12", self.clean, 2),
                ("gh pr -t $(echo x) merge 12", self.clean, 2),
                ("gh pr -R `echo o/r` ready 12", self.clean, 2),
                ("gh pr -R <(echo o/r) merge 12", self.clean, 2),
                ("gh -R $(echo o/r) pr create --fill", self.verified, 2),
                ("gh pr $(echo merge) 12", self.clean, 2),
                ("gh $(echo pr) merge 12", self.clean, 2),
                ("gh pr create --draft --fill --title=$(echo t) --draft=false", self.verified, 2),
                ("gh -R $(echo o/r) pr view 12", self.clean, 0),
                # no `$` at the end of a word is a substitution
                ('gh pr create --draft --fill --title "Fix regex ^foo$"', self.verified, 0),
                ("gh pr create --draft --fill --body 'ends with $'", self.verified, 0),
                # an unquoted substitution among the words grants no draft: it may print flags
                ("gh pr create --draft --fill --title $(echo t)", self.verified, 2),
            )
        )
        words = [c.argv for c in shell_tokens.commands("gh -R $(echo o/r) pr merge 12", str(self.clean)) if c.is_gh]
        self.assertEqual([["gh", "-R", "${}", "pr", "merge", "12"]], words)
        inner = [c.argv for c in shell_tokens.commands("gh -R $(echo o/r) pr merge 12", str(self.clean)) if c.name == "echo"]
        self.assertEqual([["echo", "o/r"]], inner)
        cut = [c for c in shell_tokens.commands("gh pr create --title $(echo", str(self.clean)) if c.is_gh]
        self.assertTrue(cut and cut[0].cut)

    def test_git_reads_its_own_words_without_redirections_or_substitutions(self) -> None:
        self.hook_codes(
            (
                ("git push --force 2>&1", self.clean, 2),
                ("git push -f >/dev/null", self.clean, 2),
                ("git push --force 2>&1 | tail -5", self.clean, 2),
                ("git push --force fork 2>&1", self.clean, 2),
                ("git push --force https://github.com/o/r.git", self.clean, 2),
                ("git push -f ../other-clone", self.clean, 2),
                (">/dev/null git push --force origin main", self.feature, 2),
                ("2>&1 git push --force origin main", self.feature, 2),
                ("git >/dev/null push --force origin main", self.feature, 2),
                ("git -C $(echo .) push --force origin main", self.feature, 2),
                ("git -c x=$(echo y) push --force origin main", self.feature, 2),
                ("git push --force 2>&1", self.feature, 0),
                ("git push --force origin feature >/dev/null", self.clean, 0),
                ("git push origin main 2>&1", self.clean, 0),
            )
        )

    def test_push_options_are_read_as_parse_options_does(self) -> None:
        main, feature = self.clean, self.feature
        for command, repo, expected in (
            ("git push --force -o ci.skip origin", main, 2),
            ("git push --force -oci.skip origin", main, 2),
            ("git push --force --push-option=ci.skip origin", main, 2),
            ("git push --force --push-option ci.skip origin", main, 2),
            ("git push --force --repo origin", main, 2),
            ("git push --force --receive-pack x origin", main, 2),
            ("git push --force --recurse-submodules no origin", main, 2),
            ("git push --force --recurse-submodules=no origin", main, 2),
            ("git push --force origin 'refs/heads/*:refs/heads/*'", feature, 2),
            ("git push origin '+refs/heads/*:refs/heads/*'", feature, 2),
            ("git push --delete origin 'refs/heads/*'", feature, 2),
            ("git push --force-w origin main", feature, 2),
            ("git push --force-wi=main origin main", feature, 2),
            ("git push --mirr", feature, 2),
            ("git push --mirror origin", feature, 2),
            ("git push --del origin main", feature, 2),
            ("git push --no-verif origin feature", feature, 2),
            # a value flag's word is its value, not a refspec or the repository
            ("git push -o main origin feature", main, 0),
            ("git push --force -o main origin feature", main, 0),
            ("git push --force --push-option main origin feature", main, 0),
            # a glob push that is no force, delete or `+` stays allowed
            ("git push origin 'refs/heads/*:refs/heads/*'", feature, 0),
            # an ambiguous prefix is an error in git: nothing is pushed, nothing to block
            ("git push --forc origin feature", feature, 0),
            ("git push --force --no-force origin main", main, 2),
        ):
            with self.subTest(command=command, repo=repo.name):
                self.assertEqual(expected, self.run_hook(command, repo).returncode)
        for name, expected in (
            ("force", ("force", False)), ("force-w", ("force-with-lease", False)),
            ("mirr", ("mirror", False)), ("del", ("delete", False)), ("forc", None), ("for", None),
            ("no-force", ("force", True)), ("no-veri", ("verify", True)),
        ):
            with self.subTest(option=name):
                self.assertEqual(expected, git_guard.resolve_push_option(name))

    def test_a_shell_payload_does_not_know_the_outer_shells_directory(self) -> None:
        for shell in ("sh -c", "bash -c", "eval"):
            self.hook_codes(
                (
                    (shell + ' "cd {feature} && git push --force origin $(git branch --show-current)"', self.clean, 2),
                    (shell + ' "git -C {feature} push --force origin $(git branch --show-current)"', self.clean, 2),
                    (shell + ' "cd {feature} && git push --force origin feature"', self.clean, 0),
                )
            )
        self.hook_codes(
            (
                ("git push --force origin $(git branch --show-current)", self.feature, 0),
                ("git push --force origin $(git branch --show-current)", self.clean, 2),
            )
        )

    def test_a_redirection_ahead_of_cd_does_not_hide_the_directory_change(self) -> None:
        self.hook_codes(
            (
                (">/dev/null cd {feature} && git push --force", self.clean, 0),
                (">/dev/null cd {main} && git push --force", self.feature, 2),
            )
        )

    def codes(self, cases: tuple) -> None:
        """(command, repo, expected exit code) with no placeholders to fill."""
        for command, repo, expected in cases:
            with self.subTest(command=command, repo=repo.name):
                result = self.run_hook(command, repo)
                self.assertEqual(expected, result.returncode, result.stderr)

    def test_a_substitution_that_expands_to_nothing_leaves_the_cd_a_command(self) -> None:
        self.hook_codes(
            (
                ("$(true) cd {main} && git push --force", self.feature, 2),
                ("X=1 $(true) cd {main} && git push --force", self.feature, 2),
                (">$(echo /dev/null) cd {main} && git push --force", self.feature, 2),
                ("`true` cd {main} && git push --force", self.feature, 2),
                ("if true; then X=$(true) cd {main}; fi; git push --force", self.feature, 2),
                ("command $(true) cd {main} && git push --force", self.feature, 2),
                ("$(true) $(true) cd {main} && git push --force", self.feature, 2),
                # `echo` is the command whatever the substitution prints: the cd is its argument
                ("echo $(true) cd {main}; git push --force", self.feature, 0),
                ("echo $(true) cd {feature}; git push --force", self.clean, 2),
                # assignments only before the substitution: the `cd` is the command, as before
                ("X=$(true) cd {feature} && git push --force", self.clean, 0),
                ("X=$(true) cd {main} && git push --force", self.feature, 2),
                # a prefix word's options do not end the prefix
                ("command -p $(true) cd {main} && git push --force", self.feature, 2),
                ("builtin -- $(true) cd {main}; git push --force", self.feature, 2),
                ("time -p $(true) cd {main} && git push --force", self.feature, 2),
                ("command $X -p cd {main} && git push --force", self.feature, 2),
                # a word may come out as nothing, or as `cd`, whatever its spelling
                ("${{X:-${{Y}}}} cd {main} && git push --force", self.feature, 2),
                ("${{X:-$(true)}} cd {main} && git push --force", self.feature, 2),
                ("{{,}} cd {main} && git push --force", self.feature, 2),
                ("${{X}}cd {main} && git push --force", self.feature, 2),
                ("$X'cd' {main} && git push --force", self.feature, 2),
                ("`true`cd {main} && git push --force", self.feature, 2),
                ("{{c,}}d {main} && git push --force", self.feature, 2),
            )
        )
        found = list(shell_tokens.commands("$(true) cd /tmp && gh pr create --draft --fill", "/"))
        self.assertIsNone(found[-1].workdir)
        found = list(shell_tokens.commands("echo $(true) cd /tmp; git status", "/"))
        self.assertEqual("/", found[-1].workdir)
        found = list(shell_tokens.commands("`true` cd /tmp; git status", "/"))
        self.assertIsNone(found[-1].workdir)
        found = list(shell_tokens.commands("X=$(true) cd /tmp && git status", "/"))
        self.assertEqual("/tmp", found[-1].workdir)

    def test_a_word_that_may_expand_to_nothing_leaves_the_next_word_the_command(self) -> None:
        self.hook_codes(
            (
                # an empty `$X` is no word: the `cd` or `git` after it is the command
                ("$X cd {main} && git push --force", self.feature, 2),
                ("${{X:-}} cd {main}; git push --force", self.feature, 2),
                ("$@ cd {main}; git push --force", self.feature, 2),
                ("$X $(true) cd {main}; git push --force", self.feature, 2),
                ("$X$(true) cd {main}; git push --force", self.feature, 2),
                # a descriptor ahead of the substitution is part of a redirection, not the command
                ("2>/dev/null $(true) cd {main}; git push --force", self.feature, 2),
                ("{{fd}}>/dev/null $(true) cd {main}; git push --force", self.feature, 2),
                ("2>/dev/null $X cd {main}; git push --force", self.feature, 2),
                ("$X git push --force origin main", self.clean, 2),
                ("env $X git push --force origin main", self.clean, 2),
                ("sudo $X git push --force origin main", self.clean, 2),
                ("$X $Y git push --force origin main", self.clean, 2),
                ("`true` git push --force origin main", self.clean, 2),
                ("`echo x` git push --force origin main", self.clean, 2),
                ("`true; true` git push --force origin main", self.clean, 2),
                ("`true; true` cd {main}; git push --force", self.feature, 2),
                ("`true; f; true` x", self.clean, 0),
                ("f() {{ git push --force origin main; }}; `true; f; true` x", self.clean, 2),
                ("$X Y=1 $(true) cd {main}; git push --force", self.feature, 2),
                ("$(echo x >&2) cd {main} && git push --force", self.feature, 2),
                ("$(echo ' ') cd {main} && git push --force", self.feature, 2),
                # what a substitution in command position prints runs as the command
                ("`echo gh pr merge 12`", self.clean, 2),
                ("$(echo gh pr merge 12)", self.clean, 2),
                ("$(echo gh pr merge 12 --subject) --help", self.clean, 2),
                ("`echo gh pr merge 12 --subject` --help", self.clean, 2),
                ("$(printf 'gh pr ready 12')", self.clean, 2),
                # with the words after it, past a word that may print nothing, and decoded
                ("`echo gh pr` merge 12", self.clean, 2),
                ("$(echo gh pr) merge 12", self.clean, 2),
                ("$(echo gh api -X PUT) repos/o/r/pulls/12/merge", self.clean, 2),
                ("eval \"$(echo gh pr) merge 12\"", self.clean, 2),
                ("$X $(echo gh pr merge 12)", self.clean, 2),
                ("$(true) $(echo gh pr merge 12)", self.clean, 2),
                ("$(echo -e '\\x67h pr merge 12')", self.clean, 2),
                ("$(printf '\\147h pr merge 12')", self.clean, 2),
                # what an `echo` of literal words prints is read as the command it makes
                ("$(echo gh) pr merge 12 --help", self.clean, 0),
                ("$(which gh) pr view 12", self.clean, 0),
                # git's name behind an expansion
                ("$GIT push --force origin main", self.clean, 2),
                ("${{GIT:-git}} push --force origin main", self.clean, 2),
                ("$(which git) push --force origin main", self.clean, 2),
                ("\"$(command -v git)\" push --force origin main", self.clean, 2),
                ("${{X}}git push --force origin main", self.clean, 2),
                ("git $X push --force origin main", self.clean, 2),
                ("$GIT status", self.clean, 0),
                # git's own words: a quoted separator in a value cuts nothing
                ("$GIT push -o 'a;b' --force origin main", self.clean, 2),
                ("$(which git) push -o 'a;b' --force origin main", self.clean, 2),
                ("$GIT push -o 'a&b' --delete origin main", self.clean, 2),
                ("$GIT push origin feature -o 'a;b'", self.clean, 0),
                # behind a command the guard does not know, a later `git` may be what it runs
                ("setsid git push --force origin main", self.clean, 2),
                ("caffeinate git push --force origin main", self.clean, 2),
                ("flock /tmp/x git push --force origin main", self.clean, 2),
                ("caffeinate -i git commit --no-verify -m x", self.clean, 2),
                ("echo git push --force origin main", self.clean, 0),
                ("brew list git && git status", self.clean, 0),
                # an assignment's backtick span, and nesting past the limit, fail closed
                ("a=`b c` git push --force origin main", self.feature, 2),
                ("a=`b c` git commit --no-verify -m x", self.clean, 2),
                ("`true x` " * 9 + "git push --force origin main", self.feature, 2),
                ("a=`date` git status", self.clean, 0),
                ("$(command -v gh) pr view 12", self.clean, 0),
                ("echo `echo gh pr merge 12`", self.clean, 0),
                # ordinary commands stay allowed
                ("$X git status", self.clean, 0),
                ("$X git push origin feature", self.clean, 0),
                ("$EDITOR notes.txt", self.clean, 0),
            )
        )
        found = list(shell_tokens.commands("$X cd /tmp; git status", "/"))
        self.assertIsNone(found[-1].workdir)

    def test_a_word_glued_to_a_substitution_gets_no_draft_help_or_undo_credit(self) -> None:
        body = "gh pr create --draft --fill --body \"$(cat <<'EOF'\nline; with | operators\nEOF\n)\""
        self.codes(
            (
                ("gh pr merge 12 -b $(echo x)--help", self.clean, 2),
                ("gh pr create --fill -t $(echo x)--draft", self.verified, 2),
                ("gh pr ready 12 -R $(echo o/r)--undo", self.clean, 2),
                ("gh api -X PUT repos/o/r/pulls/12/merge -f x=$(echo y)--help", self.clean, 2),
                # a heredoc body is one double-quoted word, not an unquoted substitution
                (body, self.verified, 0),
                ("gh pr merge 12 --help", self.clean, 0),
                ("gh pr create --draft --fill", self.verified, 0),
            )
        )

    def test_only_an_unquoted_backtick_opens_a_span(self) -> None:
        self.codes(
            (
                ("A='`' gh pr merge 12", self.clean, 2),
                ("gh -R 'a`b' pr merge 12", self.clean, 2),
                ("gh pr -t 'a`b' merge 12", self.clean, 2),
                ("A='`' gh pr create --fill", self.verified, 2),
                ("gh pr merge 12 -b `echo x` --help", self.clean, 2),
                ("gh pr create --title 'Handle a stray ` in titles' --draft --fill", self.verified, 0),
                ("gh pr create --draft --fill --title \"a ` b\"", self.verified, 0),
            )
        )
        self.assertFalse(shell_tokens.tokenize("gh pr create -t 'a ` b' --draft").backticks)
        self.assertTrue(shell_tokens.tokenize("gh pr create -t `echo b` --draft").backticks)

    def test_a_number_is_a_descriptor_only_when_glued_to_its_operator(self) -> None:
        self.hook_codes(
            (
                ("git push -o 5 >/dev/null --force origin main", self.feature, 2),
                ("gh pr create --draft --fill -t 5 >/dev/null --draft=false", self.verified, 2),
                ("git push 2>/dev/null --force origin main", self.feature, 2),
                ("git push 5>/dev/null --force origin main", self.feature, 2),
                ("git push 2>/dev/null origin feature", self.feature, 0),
                ("git push --force origin feature 2>&1", self.feature, 0),
                ("git push >&2 --force origin feature", self.feature, 0),
                ("git push &>/dev/null --force origin feature", self.feature, 0),
                ("git push 5>/dev/null --force origin feature", self.feature, 0),
                ("git push {{fd}}>/dev/null --force origin feature", self.feature, 0),
                ("git push -o 5 >/dev/null origin feature", self.feature, 0),
                ("gh pr create --draft --fill 2>&1", self.verified, 0),
            )
        )
        self.assertEqual(["git", "push", "-o", "5"], shell_tokens.tokenize("git push -o 5 >/dev/null")[:4])
        self.assertEqual(["git", "push", "-o", "5", "--force"], shell_tokens.drop_redirections(
            shell_tokens.tokenize("git push -o 5 >/dev/null --force")
        ))
        for text in ("a 2>&1 b", "a {fd}>x b", "a 5>x b", "a >&2 b", "a &>x b", "a 2>/dev/null b"):
            with self.subTest(text=text):
                self.assertEqual(["a", "b"], shell_tokens.drop_redirections(shell_tokens.tokenize(text)))
        self.assertEqual(["a", "2", "b"], shell_tokens.drop_redirections(shell_tokens.tokenize("a 2 >x b")))
        self.assertEqual(["a2", ">", "x"], shell_tokens.tokenize("a2>x"))
        self.assertEqual(["a", "5", "<", "(", "b", ")"], shell_tokens.tokenize("a 5<(b)"))

    def test_the_argv_reading_stays_when_a_quoted_operator_adds_the_text_reading(self) -> None:
        self.codes(
            (
                ("gh pr $V 12; find . -name x -exec ls {} \\;", self.clean, 2),
                ("$G pr merge 12; find . -name x -exec ls {} \\;", self.clean, 2),
                ("$G pr create --fill; find . -name x -exec ls {} \\;", self.verified, 2),
                ("gh pr m$X 12; echo '|'", self.clean, 2),
                ("gh api \"$URL\" -X PUT | cut -d '|' -f1", self.clean, 2),
                ("gh api graphql -f query=\"$Q\" | tr ';' ' '", self.clean, 2),
                ("gh api 5 >/dev/null -X PUT \"$URL\" | cat", self.clean, 2),
                ("gh pr -t ';' merge 12", self.clean, 2),
                ("gh pr -t 'a;b' merge 12", self.clean, 2),
                ("gh pr -t \\; merge 12", self.clean, 2),
                ("gh pr create --draft --fill; find . -name x -exec ls {} \\;", self.verified, 2),
                # a quoted `'>'` may be the word the argv reading dropped as a redirection
                ("G=gh; $G pr -t '>' merge 12", self.clean, 2),
                ("G=gh; $G pr -t '>' ready 12", self.clean, 2),
                ("G=gh; $G pr -t '>' create --fill", self.verified, 2),
                ("G=gh; $G api --jq '>' repos/o/r/pulls -f title=x -f head=b -f base=main", self.verified, 2),
            )
        )

    def test_a_shell_that_runs_a_script_the_guard_cannot_see_has_its_text_read(self) -> None:
        heredoc = "{shell} <<'EOF'\n{body}\nEOF"
        blocked = [
            heredoc.format(shell="bash", body="git push --force origin main"),
            heredoc.format(shell="bash", body="gh pr merge 12"),
            heredoc.format(shell="sh -s", body="gh pr ready 12"),
            heredoc.format(shell="bash -s -- x", body="git push -f origin main"),
            heredoc.format(shell="bash -", body="git push origin :main"),
            heredoc.format(shell="bash -o pipefail", body="git push origin +main"),
            heredoc.format(shell="env bash", body="git commit -am x"),
            heredoc.format(shell="bash", body="gh pr create --draft --fill"),
            heredoc.format(shell="bash", body="gh api repos/o/r/pulls -f title=x -f head=b -f base=main"),
            "sh <<< 'gh pr merge 12'",
            "nohup bash <<< 'git push --force origin main'",
            "echo 'gh pr merge 12' | sh",
            "printf 'git push --force origin main\\n' | bash",
            "cat <<'EOF' | bash\ngh pr merge 12\nEOF",
            "bash -c \"$(cat <<'EOF'\ngh pr merge 12\nEOF\n)\"",
            "eval \"$(cat <<'EOF'\ngh pr merge 12\nEOF\n)\"",
            "source /dev/stdin <<< 'gh pr merge 12'",
            ". <(echo gh pr merge 12)",
            "bash <(echo gh pr merge 12)",
            # a stdin that reaches a shell in a group, a subshell, a body, a payload or an fd
            "{ bash; } <<< 'gh pr merge 12'",
            "(bash) <<< 'gh pr merge 12'",
            "if true; then bash; fi <<< 'gh pr merge 12'",
            "echo 'gh pr merge 12' | (cd /tmp && bash)",
            "echo 'gh pr merge 12' | tee >(bash)",
            "bash 3<<< 'gh pr merge 12' <&3",
            heredoc.format(shell="bash -c 'exec sh'", body="git push --force origin main"),
            "bash --rcfile <(echo gh pr merge 12) -i",
            "b\\ash <<< 'gh pr merge 12'",
            "ash <<< 'gh pr merge 12'",
            heredoc.format(shell="bash", body="git com\\\nmit --no-verify -m x"),
            heredoc.format(shell="bash", body="git push origin $'+main'"),
            heredoc.format(shell="bash", body="git push -o 'a;b' --force origin main"),
            "echo 'git push --force origin main' | docker exec -i app bash",
            heredoc.format(shell="bash -euo pipefail", body="gh pr merge 12"),
            "bash /dev/fd/3 3<<< 'gh pr merge 12'",
            heredoc.format(shell="bash", body="git push \\\n  --force origin main"),
            heredoc.format(shell="bash", body="git push --de origin main"),
            heredoc.format(shell="bash", body="git push --mi origin"),
            "$SHELL <<< 'gh pr merge 12'",
            "B=bash; $B <<< 'gh pr merge 12'",
            heredoc.format(shell="$(which bash) -s", body="gh pr merge 12"),
        ]
        allowed = [
            "gh pr view 12 --json body -q .body > /dev/null <<'EOF'\nunused\nEOF",
            "python3 - <<'EOF'\nprint('gh pr merge 12')\nEOF",
            "curl -fsSL https://example.com/install.sh | bash",
            "bash scripts/x.sh",
            "bash -c 'echo hi'",
            heredoc.format(shell="bash", body="echo hi\ngit status"),
            heredoc.format(shell="bash", body="git push origin feature"),
            "cat <<'EOF' > notes.md\ngh pr merge 12\nEOF",
            "source .venv/bin/activate && true",
            "bash -c \"$X\"",
            # a shell's name as an argument reads no script, and only a substitution's text is read
            "docker exec -it app bash && git commit --allow-empty -m x",
            "brew list zsh && git commit --allow-empty -m x",
            "command -v bash >/dev/null && git commit --allow-empty -m x",
            "eval \"$(echo true)\" && git commit --allow-empty -m x",
            "ps aux | grep sh; git commit --allow-empty -m x",
            "git log -1 2>&1 | grep -v bash; git commit --allow-empty -m x",
            # an apostrophe in a comment opens no quote
            heredoc.format(shell="bash", body="# don't worry\ngit push origin feature\nrm -rf dist"),
        ]
        self.codes(tuple((command, self.clean, 2) for command in blocked) + tuple((command, self.clean, 0) for command in allowed))
        # the user's AITK_PR_READY=1 lifts a merge in such a script, not a force push or an unchecked PR
        env = {"AITK_PR_READY": "1"}
        for command, expected in (
            (heredoc.format(shell="bash", body="gh pr merge 12"), 0),
            (heredoc.format(shell="bash", body="git push --force origin main"), 2),
            (heredoc.format(shell="bash", body="gh pr create --fill"), 2),
        ):
            with self.subTest(command=command, env="AITK_PR_READY"):
                self.assertEqual(expected, self.run_hook(command, self.clean, env=env).returncode)

    def test_a_printing_command_still_runs_its_substitutions(self) -> None:
        self.codes(
            (
                ("echo $(gh pr -t ';' merge 12)", self.clean, 2),
                ("echo \"$(gh pr -t ';' merge 12)\"", self.clean, 2),
                ("echo `gh pr -t ';' merge 12`", self.clean, 2),
                ("cat <(gh pr -t ';' merge 12)", self.clean, 2),
                ("echo $(echo $(gh pr -t ';' ready 12))", self.clean, 2),
                ("echo '()' gh pr ready 12", self.clean, 0),
                ("echo \"$(date)\" ';'", self.clean, 0),
            )
        )

    def test_git_reads_its_words_as_written_beside_a_quoted_operator(self) -> None:
        self.codes(
            (
                ("git push -o '>' --force origin main", self.feature, 2),
                ("git push -o \\> --force origin main", self.feature, 2),
                ("git push --repo '>' --force origin main", self.feature, 2),
                ("git commit -m '>' --no-verify", self.clean, 2),
                # a quoted separator cut git's words: each real piece is read with it as a word
                ("git commit -m ';' --no-verify", self.clean, 2),
                ("git push -o '|' --force origin main", self.feature, 2),
                ("git push -o '(' --force origin main", self.feature, 2),
                ("git commit --allow-empty -m 'fix; thing'", self.clean, 0),
                ("git commit --allow-empty -m 'a (wip) b'", self.clean, 0),
                ("git push --force origin feature; echo '|'", self.feature, 0),
            )
        )
        nest = "git push --force origin main"
        for _ in range(10):
            nest = "sh -c " + shlex.quote(nest)
        self.codes(((nest, self.feature, 2),))

    def test_a_command_the_guard_does_not_know_may_run_git(self) -> None:
        self.hook_codes(
            (
                # a later word that may start git, behind an unknown command or an option's value
                ('find . git git git git git git git git -maxdepth 0 -exec git push --force origin main \\;', self.clean, 2),
                ('x git git git git git git git git git commit --no-verify -m x', self.clean, 2),
                ("setsid bash -c 'git push --force origin main'", self.clean, 2),
                ("flock /tmp/lock sh -c 'git push --force origin main'", self.clean, 2),
                ("uv run bash -c 'git commit --no-verify -m x'", self.clean, 2),
                ("/bin/sh -c 'git push --force origin main'", self.clean, 2),
                ('/bin/bash -c "git commit --no-verify -m x"', self.clean, 2),
                ("dash -c 'git push --force origin main'", self.clean, 2),
                ("/usr/bin/env bash -c 'git push --force origin main'", self.clean, 2),
                ('setsid env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x', self.clean, 2),
                ('setsid git-push --force origin main', self.clean, 2),
                ('setsid git-commit --no-verify -m x', self.clean, 2),
                ('setsid $GIT push --force origin main', self.clean, 2),
                ('setsid "$(which git)" push --force origin main', self.clean, 2),
                ('setsid ${{GIT:-git}} push --force origin main', self.clean, 2),
                ('exec -a echo git push --force origin main', self.clean, 2),
                ('env -P echo /usr/bin/git push --force origin main', self.clean, 2),
                ('xargs -J echo git push --force origin main', self.clean, 2),
                ('sudo --prompt echo git push --force origin main', self.clean, 2),
                ("sh -c 'git $*' _ push --force origin main", self.clean, 2),
                # a `git` word that starts no git command is an argument, even where the
                # directory is unknown; a printing command runs none
                ('cd "$D" && pytest -k git tests/test_x.py', self.clean, 0),
                ('cd "$D" && [ "$x" = git ] && echo y', self.clean, 0),
                ('cd "$D" && if [ "$VCS" = git ]; then echo y; fi', self.clean, 0),
                ('cd "$D" && apt-get install -y git curl', self.clean, 0),
                ('cd "$(dirname "$0")" && brew install git gh', self.clean, 0),
                ('cd "$D" && for t in git gh jq; do command -v $t; done', self.clean, 0),
                ('cd "$D" && find . -name git -type d', self.clean, 0),
                ('cd "$D" && mkdir -p src/git tests', self.clean, 0),
                ('cd "$D" && claude mcp add git -- uvx mcp-server-git', self.clean, 0),
                ('echo git push --force origin main', self.clean, 0),
                ('setsid git push origin feature', self.clean, 0),
            )
        )

    def test_staging_switching_and_config_are_read_as_git_would(self) -> None:
        self.hook_codes(
            (
                ('git stage -f PROJECT.md && git commit -m x', self.feature, 2),
                ('git update-index --add PROJECT.md && git commit -m x', self.feature, 2),
                ('F=PROJECT.md; git add -f $F && git commit -m x', self.feature, 2),
                ('git add -f PROJECT.{{md,md}} && git commit -m x', self.feature, 2),
                ('git checkout main && git push -f origin HEAD', self.feature, 2),
                ('git switch main && git push --force', self.feature, 2),
                ('git checkout -B main && git push -f origin HEAD', self.feature, 2),
                ('git push -f origin {{main,main}}', self.feature, 2),
                ('git push origin +mai{{n,n}}', self.feature, 2),
                ('git push -d origin {{main,main}}', self.feature, 2),
                ('git push origin :{{main,main}}', self.feature, 2),
                ('P=push; git $P --force origin main', self.feature, 2),
                ('git ${{S:-push}} --force origin main', self.feature, 2),
                ("sh -c 'git $*' _ push --force origin main", self.feature, 2),
                ('git -c remote.origin.push=+refs/heads/main:refs/heads/main push origin', self.feature, 2),
                ('git -c remote.origin.mirror=true push origin', self.feature, 2),
                ('git config remote.origin.push +refs/heads/main:refs/heads/main && git push origin', self.feature, 2),
                ('git send-pack --force origin main', self.feature, 2),
                ('$GIT push --no-verify origin feature', self.feature, 2),
                ("bash <<< 'git push --no-verify origin feature'", self.feature, 2),
                ("$GIT -c alias.x='push --force origin main' x", self.feature, 2),
                ('f() {{ git push --force origin main; }}; trap f EXIT', self.feature, 2),
                ('f() {{ git commit --no-verify -m x; }}; : `f`', self.feature, 2),
                ('f() {{ git push --force origin main; }}; F=f; $F', self.feature, 2),
                ("git push --prune origin 'refs/heads/*:refs/heads/*'", self.feature, 2),
                ('git merge --no-verify feature', self.feature, 2),
                ('git -c include.path=/tmp/x commit -m x', self.feature, 2),
                ('GIT_CONFIG_GLOBAL=/dev/null git commit -m x', self.feature, 2),
                ('git add -f README.md && git commit --allow-empty -m x', self.feature, 0),
                ('git checkout -- README.md && git push origin feature', self.feature, 0),
                ('git switch feature && git push origin feature', self.feature, 0),
                ('git push origin feature', self.feature, 0),
                ('git push origin {{feature,other}}', self.feature, 0),
                ('P=status; git $P', self.feature, 0),
                ('git config user.name x && git push origin feature', self.feature, 0),
                ('git merge --no-edit origin/main', self.feature, 0),
                ('git remote add fork https://example.com/x.git && git push fork feature', self.feature, 0),
                ("trap 'echo done' EXIT", self.feature, 0),
                ('git $X status', self.feature, 0),
                ('git push --prune origin feature', self.feature, 0),
            )
        )

    def test_git_answers_are_kept_for_one_command_only(self) -> None:
        import guard_base

        git_guard.evaluate("git push origin feature; git push origin feature", str(self.feature), {})
        self.assertEqual({}, guard_base.GIT_OUTPUTS)
        self.assertFalse(guard_base.CACHING[0])

    def test_graphql_names_stand_where_a_variable_can(self) -> None:
        self.codes(
            (
                (
                    "gh api graphql -f query=\"mutation(\\$M: ID!) { $M(input: {pullRequestId: \\$M}) "
                    "{ clientMutationId } }\" -f M=PR_x",
                    self.clean,
                    2,
                ),
                (
                    "gh api graphql -f query='mutation($M: ID!) { '\"$M\"'(input: {pullRequestId: $M}) "
                    "{ clientMutationId } }' -f M=PR_x",
                    self.clean,
                    2,
                ),
            )
        )

    def test_ordinary_commands_with_quotes_and_separators_are_not_blocked(self) -> None:
        self.codes(
            (
                (
                    "gh pr create --draft --fill --body \"$(git log --format='- %s' origin/main..HEAD | head -5)\"",
                    self.verified,
                    0,
                ),
                (
                    "gh pr edit 12 --body \"$(gh pr view 12 --json body -q '.body' | sed 's/old/new/')\"",
                    self.verified,
                    0,
                ),
                ("gh pr comment 12 --body \"$(echo 'ready to merge; thanks')\"", self.verified, 0),
                ("find . -name '*.md' -exec grep -l 'gh pr merge' {} \\;", self.verified, 0),
                ("gh pr list | cut -d '|' -f1; git merge --no-edit origin/main", self.verified, 0),
                ("echo '()' gh pr ready 12", self.verified, 0),
            )
        )

    def test_a_separator_inside_inner_double_quotes_is_the_only_doubt_in_a_substitution(self) -> None:
        doubtful = shell_tokens.quoted_substitution_separator
        for text in ('"$(echo "a;b")"', '"$(echo "a" "b|c")"', 'x "$(echo "a&b")" y'):
            with self.subTest(text=text):
                self.assertTrue(doubtful(text))
        for text in (
            "\"$(echo 'a;b')\"",
            "\"$(a | b)\"",
            "\"$(git log --format='- %s' o..H | head -5)\"",
            "'$(echo \"a;b\")'",
            "$(echo \"a;b\")",
        ):
            with self.subTest(text=text):
                self.assertFalse(doubtful(text))
        started = time.monotonic()
        self.assertFalse(doubtful('git status "' + "$(" * 5000 + '"'))
        self.assertLess(time.monotonic() - started, 1.0)

    def test_quoted_split_cuts_where_the_shell_does(self) -> None:
        split = git_guard.quoted_split
        self.assertEqual(["gh pr $(a; b) merge 12"], split("gh pr $(a; b) merge 12"))
        self.assertEqual(["gh pr `a; b` merge 12"], split("gh pr `a; b` merge 12"))
        self.assertEqual(["gh pr -t 'a;b' merge 12"], split("gh pr -t 'a;b' merge 12"))
        self.assertEqual(['gh pr -t "a;b" merge 12'], split('gh pr -t "a;b" merge 12'))
        self.assertEqual(["gh pr -t \\; merge 12"], split("gh pr -t \\; merge 12"))
        self.assertEqual(['gh pr -t "$(echo "a;b")" merge 12'], split('gh pr -t "$(echo "a;b")" merge 12'))
        self.assertEqual(["a", " b"], split("a; b"))
        self.assertEqual(["a >&2 b"], split("a >&2 b"))
        self.assertEqual(["a &>x b"], split("a &>x b"))


if __name__ == "__main__":
    unittest.main()
