#!/bin/bash
#
# agent-setup-edit-reminder.sh — provider-neutral PostToolUse hook
#
# Injects a system reminder when an agent edits AI Toolkit setup
# files (skills, commands, rules, CLAUDE.md, hooks). Reminds the model to
# load and apply the agent-setup-maintainer skill's principles before
# continuing.
#
# Fail-open: exits 0 on any unexpected state.
#

set -euo pipefail
trap 'exit 0' ERR

INPUT=$(cat)

if ! command -v jq &>/dev/null; then
    exit 0
fi

# The `set -e` + `trap ... ERR` above is the fail-open safety net; jq
# soft-fails to empty via `// empty`, handled by the matchers below.
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
PATCH=$(echo "$INPUT" | jq -r '.tool_input.patch // .tool_input.input // empty' 2>/dev/null)

case "$TOOL_NAME" in
    Edit|Write|MultiEdit|NotebookEdit|apply_patch) ;;
    *) exit 0 ;;
esac

if [[ -z "$FILE_PATH" && -z "$PATCH" ]]; then
    exit 0
fi

# Path-suffix matchers: no hardcoded toolkit dir name or user home, so
# the hook is portable across clones and also fires on installed
# symlink paths (~/.claude/skills -> repo skills, etc.).
MATCH=0
if [[ "$TOOL_NAME" == "apply_patch" ]]; then
    if echo "$PATCH" | grep -qE '(^|/)(skills/[^/]+/(SKILL\.md|lessons\.md|rules\.md|gotchas\.md|references/)|commands/[^/]+\.md|rules/[^/]+\.md|config/(CLAUDE|AGENTS)\.md|hooks/)'; then
        MATCH=1
    fi
else
    case "$FILE_PATH" in
        */skills/*/SKILL.md) MATCH=1 ;;
        */skills/*/lessons.md) MATCH=1 ;;
        */skills/*/rules.md) MATCH=1 ;;
        */skills/*/gotchas.md) MATCH=1 ;;
        */skills/*/references/*) MATCH=1 ;;
        */commands/*.md) MATCH=1 ;;
        */rules/*.md) MATCH=1 ;;
        */config/CLAUDE.md|*/config/AGENTS.md) MATCH=1 ;;
        */hooks/*) MATCH=1 ;;
        "$HOME/.claude/CLAUDE.md"|"${CODEX_HOME:-$HOME/.codex}/AGENTS.md") MATCH=1 ;;
    esac
fi

if [[ $MATCH -eq 0 ]]; then
    exit 0
fi

cat <<'EOF'
{"systemMessage": "You just edited an AI Toolkit setup file. Load the agent-setup-maintainer skill and apply its principles: shared skills are canonical, descriptions are classifiers, rules stay short, adapters contain no workflow logic, and edits stay surgical."}
EOF

exit 0
