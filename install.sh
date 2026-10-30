#!/bin/sh
#
# install.sh — link the Codex agents, which a Codex plugin cannot ship.
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

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET=${CODEX_HOME:-$HOME/.codex}/agents

case "${1:-}" in
    --uninstall)
        [ -d "$TARGET" ] || exit 0
        for link in "$TARGET"/*.toml; do
            [ -L "$link" ] || continue
            case $(readlink "$link") in
                "$ROOT"/agents/codex/*) rm "$link" && echo "removed $link" ;;
            esac
        done
        exit 0
        ;;
    "") ;;
    *)
        sed -n '3,15p' "$0"
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

if grep -qF '# >>> ai-toolkit managed guidance >>>' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null; then
    echo "note: an older bin/aitk install is still in place; run 'git checkout 0.3.0 && ./install.sh --uninstall' in that checkout first" >&2
fi
