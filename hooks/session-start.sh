#!/bin/bash
#
# session-start.sh — SessionStart hook for the AI Toolkit plugin
#
# Prints, as model-visible context, where the toolkit is installed and the
# always-on rules in rules/universal.md. Codex sets PLUGIN_ROOT (and
# CLAUDE_PLUGIN_ROOT for compatibility); Claude Code sets only
# CLAUDE_PLUGIN_ROOT. With neither set this is not a plugin session, and the
# hook prints nothing.
#
# On a fresh session it also warns when an install from before the plugin
# (v0.3 and earlier, `bin/aitk install`) is still in place: the managed
# guidance block in ~/.claude/CLAUDE.md or $CODEX_HOME/AGENTS.md, or a Claude
# Code settings hook that runs a toolkit hook script; and when v0.3's
# SKIP_PR_GATE is still set in the session environment. It only reads those
# files and never edits them. Always exits 0.

if [ -n "${PLUGIN_ROOT:-}" ]; then
    root=$PLUGIN_ROOT
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    root=$CLAUDE_PLUGIN_ROOT
else
    exit 0
fi

payload=""
[ -t 0 ] || payload=$(cat)

printf 'AI Toolkit is installed at `%s`; `<toolkit-root>` in its skills means that directory.\n\n' "$root"
cat "$root/rules/universal.md" 2>/dev/null

# Warn once, when the session starts (not on resume, clear or compact).
case $payload in
    *'"source"'*) [[ $payload =~ \"source\"[[:space:]]*:[[:space:]]*\"startup\" ]] || exit 0 ;;
esac
marker='# >>> ai-toolkit managed guidance >>>'
claude_dir=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
found=""
grep -qF -- "$marker" "$claude_dir/CLAUDE.md" 2>/dev/null && found="$found $claude_dir/CLAUDE.md"
grep -qF -- "$marker" "${CODEX_HOME:-$HOME/.codex}/AGENTS.md" 2>/dev/null &&
    found="$found ${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
grep -qE '/hooks/(prevent-project-commit|pre-push-validate|require-review-gate|check-plan-drift|observation-reminder)\.sh' \
    "$claude_dir/settings.json" 2>/dev/null && found="$found $claude_dir/settings.json"
if [ -n "$found" ]; then
    warning="AI Toolkit warning: an older \`bin/aitk install\` is still in place (${found# }), so the toolkit loads twice next to this plugin. Tell the user once: in that checkout, run \`git checkout 0.3.0 && ./install.sh --uninstall\` (README, Migrating)."
    printf '\n%s\n' "$warning"
    printf '%s\n' "$warning" >&2
fi
# v0.3 told users to start sessions with SKIP_PR_GATE=1 to skip its review gate.
# It lifts nothing now, and the PR gate has no off switch, so say so once.
if [ -n "${SKIP_PR_GATE+set}" ]; then
    warning="AI Toolkit warning: SKIP_PR_GATE is set in this session's environment. It switched off v0.3's review gate and does nothing now; the PR gate (scripts/verify.py) has no off switch. Tell the user once, so they can remove it from where their sessions start."
    printf '\n%s\n' "$warning"
    printf '%s\n' "$warning" >&2
fi
exit 0
