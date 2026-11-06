#!/bin/sh
#
# install.sh — link the Codex agents, which a Codex plugin cannot ship, and
# add a hook-trust check to Codex's personal AGENTS.md.
#
# Everything else installs as a plugin (README, Install):
#   claude plugin marketplace add <this checkout> && claude plugin install ai-toolkit@ai-toolkit
#   codex plugin marketplace add <this checkout> && codex plugin add ai-toolkit@ai-toolkit
#
# Usage: ./install.sh [--uninstall]
#
# Idempotent and non-destructive: it links agents/codex/*.toml into
# ${CODEX_HOME:-~/.codex}/agents/, leaves any file there that is not its own
# link untouched (and says so), and --uninstall removes only links that point
# into this checkout.
#
# Codex runs plugin hooks only after the user trusts them in /hooks. Until
# then neither the rules nor the git guard reach a session, and nothing says
# so. The marked block it keeps in ${CODEX_HOME:-~/.codex}/AGENTS.md tells the
# model how to notice; the rest of that file is never touched, and
# --uninstall removes only the block.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET=${CODEX_HOME:-$HOME/.codex}/agents
AGENTS_FILE=${CODEX_HOME:-$HOME/.codex}/AGENTS.md
BEGIN='# >>> ai-toolkit hook check >>>'
END='# <<< ai-toolkit hook check <<<'
CHECK='AI Toolkit is installed as a Codex plugin. Its session-start hook puts a section headed "AI Toolkit Rules" in your context. If that section is missing, Codex has not trusted the plugin'"'"'s hooks, so its git guard is not running either: before any commit, push or pull request, tell the user to trust the ai-toolkit hooks in /hooks.'

# Remove the marked block from AGENTS.md, writing through a symlink in place.
remove_check() {
    [ -f "$AGENTS_FILE" ] && grep -qxF -- "$BEGIN" "$AGENTS_FILE" || return 0
    tmp=$(mktemp "${TMPDIR:-/tmp}/aitk-agents.XXXXXX")
    awk -v b="$BEGIN" -v e="$END" '$0 == b { skip = 1; next } skip && $0 == e { skip = 0; next } !skip' \
        "$AGENTS_FILE" >"$tmp" && cat "$tmp" >"$AGENTS_FILE"
    rm -f "$tmp"
}

case "${1:-}" in
    --uninstall)
        for link in "$TARGET"/*.toml; do
            [ -L "$link" ] || continue
            case $(readlink "$link") in
                "$ROOT"/agents/codex/*) rm "$link" && echo "removed $link" ;;
            esac
        done
        if [ -f "$AGENTS_FILE" ] && grep -qxF -- "$BEGIN" "$AGENTS_FILE"; then
            remove_check && echo "removed the hook check from $AGENTS_FILE"
        fi
        exit 0
        ;;
    "") ;;
    *)
        sed -n '3,21p' "$0"
        exit 2
        ;;
esac

mkdir -p "$TARGET"
for agent in "$ROOT"/agents/codex/*.toml; do
    link=$TARGET/$(basename "$agent")
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$agent" ]; then
        continue
    fi
    if [ -e "$link" ] || [ -L "$link" ]; then
        echo "skipped $link: a different file is already there" >&2
        continue
    fi
    ln -s "$agent" "$link" && echo "linked $link"
done

block=$(printf '%s\n%s\n%s' "$BEGIN" "$CHECK" "$END")
if [ -f "$AGENTS_FILE" ] && awk -v b="$BEGIN" -v e="$END" '$0 == b { on = 1 } on { print } $0 == e { exit }' \
    "$AGENTS_FILE" | grep -qxF -- "$CHECK"; then
    :
else
    remove_check
    mkdir -p "$(dirname -- "$AGENTS_FILE")"
    if [ -s "$AGENTS_FILE" ] && [ -n "$(tail -c 1 "$AGENTS_FILE")" ]; then
        printf '\n' >>"$AGENTS_FILE"
    fi
    printf '%s\n' "$block" >>"$AGENTS_FILE" && echo "added the hook check to $AGENTS_FILE"
fi

if grep -qF '# >>> ai-toolkit managed guidance >>>' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null; then
    echo "note: an older bin/aitk install is still in place; run 'git checkout 0.3.0 && ./install.sh --uninstall' in that checkout first" >&2
fi
