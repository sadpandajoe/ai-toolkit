#!/bin/bash
#
# session-start.sh — SessionStart hook for the AI Toolkit plugin
#
# Prints, as model-visible context, the always-on rules that
# interfaces/guidance.json lists and a one-line pointer to the provider
# binding. Codex sets PLUGIN_ROOT (and CLAUDE_PLUGIN_ROOT for compatibility);
# Claude Code sets only CLAUDE_PLUGIN_ROOT. With neither set this is not a
# plugin session, and the hook prints nothing.
#
# On a fresh session it also warns when an older `bin/aitk install` is still in
# place: the managed guidance block in ~/.claude/CLAUDE.md or
# $CODEX_HOME/AGENTS.md, or a Claude Code settings hook that runs a toolkit
# hook script. It only reads those files and never edits them. Always exits 0.

if [ -n "${PLUGIN_ROOT:-}" ]; then
    provider=codex
    root=$PLUGIN_ROOT
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    provider=claude
    root=$CLAUDE_PLUGIN_ROOT
else
    exit 0
fi

payload=""
[ -t 0 ] || payload=$(cat)

printf 'AI Toolkit is installed at `%s`; `bin/aitk` in its rules and skills means `%s/bin/aitk`.\n' "$root" "$root"
if [ "$provider" = claude ]; then
    printf 'Claude capability bindings: read `%s/config/providers/claude.md` before using a shared capability (`fresh_subagent`, `independent_review`, `routed_subagent`, and the rest).\n' "$root"
else
    printf 'Codex capability bindings: read `%s/config/providers/codex.md` before delegating, planning, creating worktrees, scheduling, or requesting independent review.\n' "$root"
fi

# The always-on list: every "rules/*.md" string inside always_on_rules.
sed -n '/"always_on_rules"/,/]/p' "$root/interfaces/guidance.json" 2>/dev/null \
    | grep -o '"[^"]*\.md"' | tr -d '"' | while IFS= read -r rule; do
        case $rule in /* | *..*) continue ;; esac
        [ -f "$root/$rule" ] || continue
        printf '\n'
        cat "$root/$rule"
    done

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
grep -qE '/hooks/(prevent-project-commit|pre-push-validate|require-review-gate|check-resources|check-plan-drift|observation-reminder|agent-setup-edit-reminder)\.sh' \
    "$claude_dir/settings.json" 2>/dev/null && found="$found $claude_dir/settings.json"
if [ -n "$found" ]; then
    warning="AI Toolkit warning: an older \`bin/aitk install\` is still in place (${found# }), so the toolkit loads twice next to this plugin. Tell the user once: run \`bin/aitk uninstall\` from that checkout (docs/MIGRATION.md)."
    printf '\n%s\n' "$warning"
    printf '%s\n' "$warning" >&2
fi
exit 0
