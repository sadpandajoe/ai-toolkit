#!/bin/bash
#
# Smoke tests for prevent-project-commit.sh.
#
# This is intentionally dependency-light: it runs the hook with synthetic
# PreToolUse payloads and checks only allow/block exit codes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/prevent-project-commit.sh"
TMP_DIR="$(mktemp -d)"
TMP_REL="${TMP_DIR#/}"
TMP_INDEX="$TMP_DIR/alt.index"
TMP_GLOBAL_CONFIG="$TMP_DIR/global.gitconfig"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

git -C "$TMP_DIR" init -q -b main
git -C "$TMP_DIR" config user.email test@example.com
git -C "$TMP_DIR" config user.name Test
git -C "$TMP_DIR" config alias.ci commit
git -C "$TMP_DIR" config alias.nv "commit --no-verify"
git -C "$TMP_DIR" config alias.nvshell "!git commit --no-verify"
git -C "$TMP_DIR" config alias.fpm "push --force origin main"
git -C "$TMP_DIR" config alias.fpshell "!f(){ git push --force origin main; }; f"
GIT_CONFIG_GLOBAL="$TMP_GLOBAL_CONFIG" git config --global alias.bad "commit --no-verify"
printf 'state\n' >"$TMP_DIR/PROJECT.md"
git -C "$TMP_DIR" add PROJECT.md

# Every toolkit workflow-state filename must be protected, including when a
# command selects a non-default index.
for state_file in PROJECT.md PROJECT_ARCHIVE.md PLAN.md WATCH.md CHERRY_PICK.md CI_FIX.md; do
    printf 'state\n' > "$TMP_DIR/$state_file"
    state_index="$TMP_DIR/${state_file}.index"
    GIT_INDEX_FILE="$state_index" git -C "$TMP_DIR" read-tree --empty
    GIT_INDEX_FILE="$state_index" git -C "$TMP_DIR" add "$state_file"
done

run_hook() {
    local command="$1"
    printf '{"tool_input":{"command":%s},"cwd":%s}\n' \
        "$(printf '%s' "$command" | jq -Rs .)" \
        "$(printf '%s' "$TMP_DIR" | jq -Rs .)" |
        "$HOOK" >/tmp/prevent-project-commit.out 2>/tmp/prevent-project-commit.err
}

expect_block() {
    local command="$1"
    local status
    set +e
    run_hook "$command"
    status=$?
    set -e

    if [[ "$status" -eq 0 ]]; then
        echo "FAIL expected block: $command" >&2
        exit 1
    fi
    if [[ "$status" -ne 2 ]]; then
        echo "FAIL expected exit 2: $command" >&2
        exit 1
    fi
}

expect_allow() {
    local command="$1"
    local status
    set +e
    run_hook "$command"
    status=$?
    set -e

    if [[ "$status" -ne 0 ]]; then
        echo "FAIL expected allow: $command" >&2
        cat /tmp/prevent-project-commit.err >&2 || true
        exit 1
    fi
}

expect_allow "echo --no-verify"
expect_allow "echo git commit --no-verify"
expect_block "git commit -m state"
expect_block "cd $TMP_DIR && git commit -m state"
expect_block "cd / && git -C $TMP_REL commit -m state"
expect_block "cd / && env -C $TMP_DIR git commit -m state"
expect_block "cd / && env --chdir=$TMP_DIR git commit -m state"
expect_block "env -C /tmp true; git commit -m state"
expect_block "cd / && GIT_DIR=$TMP_DIR/.git GIT_WORK_TREE=$TMP_DIR git commit -m state"
expect_block "git --work-tree=$TMP_DIR --git-dir=$TMP_DIR/.git commit -m state"
expect_block "git -c alias.ci=commit ci -m state"
expect_block "git ci -m state"
expect_block 'f(){ git "$@"; }; f commit -m state'
expect_block 'g=git; $g commit -m state'
for state_file in PROJECT.md PROJECT_ARCHIVE.md PLAN.md WATCH.md CHERRY_PICK.md CI_FIX.md; do
    expect_block "GIT_INDEX_FILE=$TMP_DIR/${state_file}.index git commit -m state"
done
git -C "$TMP_DIR" rm --cached -q PROJECT.md
GIT_INDEX_FILE="$TMP_INDEX" git -C "$TMP_DIR" add PROJECT.md
expect_block "GIT_INDEX_FILE=$TMP_INDEX git commit -m state"

expect_block "git commit --no-verify -m bad"
expect_block "git commit --no-verif -m bad"
expect_block "git commit --no-veri -m bad"
expect_block "/usr/bin/git commit --no-verify -m bad"
expect_block "git --no-pager commit --no-verify -m bad"
expect_block "command git commit --no-verify -m bad"
expect_block "env FOO=bar git commit --no-verify -m bad"
expect_block "( git commit --no-verify -m bad )"
expect_block "if git commit --no-verify -m bad; then echo ok; fi"
expect_block "for x in 1; do git commit --no-verify -m bad; done"
expect_block "sudo git commit --no-verify -m bad"
expect_block "bash -lc 'git commit --no-verify -m bad'"
expect_block "bash -lc -- 'git commit --no-verify -m bad'"
expect_block "sh -c 'git commit --no-verify -m bad'"
expect_block "sh -c -- 'git commit --no-verify -m bad'"
expect_block "sh -c 'git \"\$1\" --no-verify -m bad' x commit"
expect_block 'sh -c "git \"\$1\" --no-verify -m bad" x commit'
expect_block "zsh -c 'git commit --no-verify -m bad'"
expect_block "zsh -c -- 'git commit --no-verify -m bad'"
expect_block "sh -c 'git \"\$@\"' sh commit --no-verify -m bad"
expect_block 'sh -c "git \"\$@\"" sh commit --no-verify -m bad'
expect_block "bash -lc 'f(){ git commit --no-verify -m bad; }; f'"
expect_block 'f(){ git "$@"; }; f commit --no-verify -m bad'
expect_block 'function f { git "$@"; }; f commit --no-verify -m bad'
expect_block 'function f() { git "$@"; }; f commit --no-verify -m bad'
expect_block 'bash -lc '\''f(){ git "$@"; }; f commit --no-verify -m bad'\'''
expect_block 'bash -lc '\''function f { git "$@"; }; f commit --no-verify -m bad'\'''
expect_block 'g=git; $g commit --no-verify -m bad'
expect_block "eval 'git commit --no-verify -m bad'"
expect_block "git\${IFS}commit --no-verify -m bad"
expect_block "git\${IFS} commit --no-verify -m bad"
expect_block "git -c user.name=Test commit -n -m bad"
expect_block "git -c alias.nv='commit --no-verify' nv -m bad"
expect_block "git -c alias.nvshell='!git commit --no-verify' nvshell -m bad"
expect_block "git -c alias.a='!git nv' -c alias.nv='commit --no-verify' a --allow-empty -m bad"
expect_block "git -c alias.outer='!git -c alias.inner=\"commit --no-verify\" inner' outer --allow-empty -m bad"
expect_block "git nv -m bad"
expect_block "git nvshell -m bad"
expect_block "GIT_CONFIG_GLOBAL=$TMP_GLOBAL_CONFIG git bad -m bypass"
expect_block "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify' git nv -m bad"
expect_block "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify'; git nv -m bad"
expect_block "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null; git commit -m bad"
expect_block "A='commit --no-verify' git --config-env=alias.nv=A nv -m bad"
expect_block "export A='commit --no-verify'; git --config-env=alias.nv=A nv -m bad"
expect_block "git -c core.hooksPath=/dev/null commit -m bad"
expect_block "git -c commit.gpgsign=false commit -m bad"
expect_block "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m bad"
expect_block "HP=/dev/null git --config-env=core.hooksPath=HP commit -m bad"
expect_block "GS=false git --config-env=commit.gpgsign=GS commit -m bad"
expect_block "git -C $TMP_DIR commit --no-verify -m bad"
expect_block "git commit -nm bad"
expect_allow "git commit -m 'mention -n flag'"
expect_allow "git commit -mnope"
expect_block "git commit --no-gpg-sign -m bad"
expect_block "git commit --no-gpg-sig -m bad"
expect_block "git commit --no-g -m bad"

expect_block "git push -f"
expect_block "( git push -f )"
expect_block "( git push --force )"
expect_block "( git push -f origin )"
expect_block "git -C $TMP_DIR push -f"
expect_block "git push -f origin"
expect_block "git push --force-w origin main"
expect_block "git push --force-wi origin main"
expect_block "git push --force-with origin main"
expect_block "git push --force-with-l origin main"
expect_block "git push --force-with-le origin main"
expect_block "git push --force-with-lea origin main"
expect_block "git push --force-with-leas origin main"
expect_block "git push -f origin main"
expect_block "git push -uf origin main"
expect_block "git push --force-with-lease=refs/heads/main origin main"
expect_block "git push -f origin HEAD"
expect_block "git push --force --all origin"
expect_block "git push --mirror --force origin"
expect_block "git push --no-verify origin feature"
expect_block "git push --no-verif origin feature"
expect_block "git push --no-veri origin feature"
expect_block "git -c alias.fpm='push --force origin main' fpm"
expect_block "git -c alias.fpshell='!f(){ git push --force origin main; }; f' fpshell"
expect_block "git fpm"
expect_block "git fpshell"
expect_block "git -c core.hooksPath=/dev/null push origin feature"
expect_block "git push origin :main"
expect_block "git push --delete origin main"
expect_block "git push --del origin main"
expect_block "git push --force origin :"
expect_block "git push origin +:"
expect_block "git push origin +main"
expect_block "git push origin +HEAD:main"
expect_allow "git push -uf origin feature"
expect_allow "git push --force-with-lease origin feature"

expect_block 'echo `git commit --no-verify -m bad`'
expect_block ': "$(git commit --no-verify -m bad)"'
expect_block 'cat <(git commit --no-verify -m bad)'
expect_block ': "$(git${IFS}commit --no-verify -m bad)"'
expect_block 'echo `git${IFS}commit --no-verify -m bad`'
expect_block 'cat <(git${IFS}commit --no-verify -m bad)'
expect_block ': "$(git -c core.hooksPath=/dev/null commit -m bad)"'
expect_block ': "$(g=git; $g commit --no-verify -m bad)"'

echo "prevent-project-commit hook tests passed"
