#!/bin/bash
#
# plugin-proof.sh — the phase 5 plugin proof, one provider at a time
#
# Installs this checkout as a plugin into a scratch HOME and checks, with real
# model turns, that:
#   1. the always-on rules reach the model (it quotes a line of rules/universal.md);
#   2. the native agents and the PGM skill are available;
#   3. a session reaches the toolkit's bin/aitk and runs `aitk list`;
#   4. the git guard blocks `git commit --no-verify` in a session;
#   5. an edit in the checkout reaches a new session after the plugin updates.
# Each answer is saved under <scratch>/out/ next to a PASS or CHECK line; read
# the CHECK lines yourself, since a model's wording varies.
#
# Usage: scripts/plugin-proof.sh claude|codex [--home DIR]
#   --home DIR  reuse a scratch HOME you already logged in to (the default is a
#               new one; log in there first with `HOME=DIR claude` or
#               `HOME=DIR codex login`, or export the provider's API key)
#
# It never touches your real HOME: the plugin, its settings and the copy of
# this checkout it edits all live in the scratch HOME. Codex runs plugin hooks
# only after you trust them in /hooks, so the Codex run stops once and asks you
# to do that. It spends a few model turns per provider.

set -u
provider=${1:-}
case $provider in claude | codex) shift ;; *) sed -n '3,23p' "$0"; exit 2 ;; esac
scratch=""
if [ "${1:-}" = --home ]; then scratch=${2:?--home needs a directory}; fi
[ -n "$scratch" ] || scratch=$(mktemp -d "${TMPDIR:-/tmp}/aitk-proof.XXXXXX")
source_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
command -v "$provider" >/dev/null 2>&1 || { echo "$provider CLI not found" >&2; exit 2; }

export HOME=$scratch
unset CLAUDE_CONFIG_DIR CLAUDE_PLUGIN_ROOT PLUGIN_ROOT
export CODEX_HOME=$HOME/.codex
checkout=$HOME/checkout
repo=$HOME/repo
out=$HOME/out
mkdir -p "$out" "$CODEX_HOME"
echo "scratch HOME: $HOME"

# A copy of this checkout, so check 5 can edit it, and a project to work in.
rm -rf "$checkout" && mkdir -p "$checkout"
(cd "$source_root" && tar --exclude=.git --exclude=build --exclude=__pycache__ -cf - .) | tar -C "$checkout" -xf -
rm -rf "$repo" && mkdir -p "$repo"
git -C "$repo" init -q && git -C "$repo" -c user.name=proof -c user.email=proof@example.com commit -q --allow-empty -m base

ask() { # ask <name> <prompt>: one non-interactive model turn in the project
    if [ "$provider" = claude ]; then
        (cd "$repo" && claude -p "$2" --allowedTools "Bash(aitk *)" "Bash(git *)" "Bash($checkout/bin/aitk *)") >"$out/$1.txt" 2>&1
    else
        (cd "$repo" && codex exec --sandbox workspace-write "$2") >"$out/$1.txt" 2>&1
    fi
}
result() { # result <PASS|CHECK|FAIL> <check> <detail>
    printf '%-5s %s: %s\n' "$1" "$2" "$3" | tee -a "$out/summary.txt"
}

update_plugin() {
    if [ "$provider" = claude ]; then
        claude plugin marketplace update ai-toolkit && claude plugin update ai-toolkit@ai-toolkit
    else
        codex plugin add ai-toolkit@ai-toolkit
    fi
}

if [ "$provider" = claude ]; then
    claude plugin marketplace add "$checkout" && claude plugin install ai-toolkit@ai-toolkit || exit 1
    claude plugin list
else
    codex plugin marketplace add "$checkout" && codex plugin add ai-toolkit@ai-toolkit || exit 1
    # Codex plugins cannot ship agents: link them as install.sh will (HK-13).
    mkdir -p "$CODEX_HOME/agents"
    for agent in "$checkout"/agents/codex/*.toml; do ln -sf "$agent" "$CODEX_HOME/agents/"; done
    echo
    echo "Trust the plugin hooks now: in another terminal run"
    echo "  cd '$repo' && HOME='$HOME' CODEX_HOME='$CODEX_HOME' codex"
    echo "then open /hooks, trust every ai-toolkit hook, and quit. Press Enter here when done."
    read -r _ </dev/tty
fi

# 1. The always-on rules reach the model.
line=$(sed -n 's/^- \*\*\(.*\)\*\*.*/\1/p' "$checkout/rules/universal.md" | head -1)
ask rules "Quote, word for word, the bold text of the first bullet in the AI Toolkit universal rules you were given at the start of this session. Output only the quote."
if grep -qF -- "$line" "$out/rules.txt"; then result PASS rules "quoted: $line"; else result FAIL rules "expected: $line (see out/rules.txt)"; fi

# 2. The native agents and the PGM skill.
ask roster "List, one per line, the names of every subagent and every skill available to you whose name contains aitk or pgm. Output only the names."
missing=""
for name in aitk-implementer aitk-debugger aitk-planner aitk-tester pgm; do
    grep -q -- "$name" "$out/roster.txt" || missing="$missing $name"
done
if [ -z "$missing" ]; then result CHECK roster "all named; confirm in out/roster.txt"; else result FAIL roster "missing:$missing"; fi

# 3. A session reaches bin/aitk.
ask aitk "Run the AI Toolkit's bin/aitk with the arguments 'list --json' using your shell tool (the session context says where the toolkit is installed), then print the command output verbatim."
if grep -q '"command": *"list"' "$out/aitk.txt"; then result PASS aitk "list output returned"; else result FAIL aitk "no list output (see out/aitk.txt)"; fi

# 4. The git guard blocks --no-verify.
before=$(git -C "$repo" rev-list --count HEAD)
echo proof >"$repo/proof.txt" && git -C "$repo" add proof.txt
ask guard "Run exactly this shell command once and report its output: git commit --no-verify -m proof"
after=$(git -C "$repo" rev-list --count HEAD)
# The guard's own words, so a sandbox refusal does not pass for the hook.
if [ "$before" = "$after" ] && grep -qF "violates global pre-commit rules" "$out/guard.txt"; then
    result PASS guard "the git guard blocked it; no new commit"
else
    result FAIL guard "commits before=$before after=$after (see out/guard.txt)"
fi

# 5. An edit in the checkout reaches a new session after the plugin updates.
marker="Proof marker $(date +%s)"
printf '\n- %s.\n' "$marker" >>"$checkout/rules/universal.md"
update_plugin >"$out/update.txt" 2>&1
ask edit "Quote, word for word, the line in your AI Toolkit universal rules that starts with 'Proof marker'. Output only the quote."
if grep -qF -- "$marker" "$out/edit.txt"; then result PASS edit "new session quoted the edit"; else result FAIL edit "edit not seen (see out/edit.txt, out/update.txt)"; fi

echo
echo "Summary in $out/summary.txt. Record it in the phase PR; remove $HOME when done."
