#!/bin/bash
#
# install-hooks.sh - Install Claude Code hooks
#
# Merges hook configurations into ~/.claude/settings.json.
# Separate from install.sh because hooks modify user-managed config.
#
# Usage: ./install-hooks.sh
#        ./install-hooks.sh --remove   # Remove toolkit hooks
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step() { echo -e "${BLUE}[STEP]${NC} $1"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="$HOME/.claude/settings.json"

usage() {
    cat <<EOF
Usage: ./install-hooks.sh [--remove|--help]

Installs toolkit hooks into ~/.claude/settings.json.

Options:
  --remove   Remove toolkit hooks
  --help     Show this help
EOF
}

if [[ "$#" -gt 1 ]]; then
    error "Too many arguments."
    usage
    exit 1
fi

case "${1:-}" in
    ""|--remove)
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        error "Unknown argument: $1"
        usage
        exit 1
        ;;
esac

# Check prerequisites
if ! command -v jq &>/dev/null; then
    error "jq is required but not installed."
    echo "  Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    exit 1
fi

if [[ ! -f "$SETTINGS" ]]; then
    error "~/.claude/settings.json not found. Run Claude Code at least once first."
    exit 1
fi

# Validate existing settings.json is valid JSON
if ! jq empty "$SETTINGS" 2>/dev/null; then
    error "~/.claude/settings.json is not valid JSON. Fix it manually first."
    exit 1
fi

echo ""
echo "========================================"
echo "  Claude Code Hooks Installer"
echo "========================================"
echo ""

# Handle --remove
if [[ "${1:-}" == "--remove" ]]; then
    step "Removing toolkit hooks..."

    BACKUP="$SETTINGS.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$SETTINGS" "$BACKUP"
    info "Backed up to: $BACKUP"

    # Remove PreToolUse and Stop entries that reference our hooks directory
    jq --arg repo "$REPO_DIR" '
        (if .hooks.PreToolUse then
            .hooks.PreToolUse |= [.[] | select(
                (.hooks // []) | all((.command // "") | contains($repo) | not)
            )] |
            if .hooks.PreToolUse == [] then del(.hooks.PreToolUse) else . end
        else . end) |
        (if .hooks.Stop then
            .hooks.Stop |= [.[] | select(
                (.hooks // []) | all((.command // "") | contains($repo) | not)
            )] |
            if .hooks.Stop == [] then del(.hooks.Stop) else . end
        else . end) |
        (if .hooks.PostToolUse then
            .hooks.PostToolUse |= [.[] | select(
                (.hooks // []) | all((.command // "") | contains($repo) | not)
            )] |
            if .hooks.PostToolUse == [] then del(.hooks.PostToolUse) else . end
        else . end) |
        if .hooks == {} then del(.hooks) else . end
    ' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

    info "Toolkit hooks removed."
    exit 0
fi

if ! command -v python3 &>/dev/null; then
    error "python3 is required but not installed."
    echo "  Install with: brew install python (macOS) or apt-get install python3 (Linux)"
    exit 1
fi

# Install hooks
step "Installing hooks..."

# Backup
BACKUP="$SETTINGS.bak-$(date +%Y%m%d-%H%M%S)"
cp "$SETTINGS" "$BACKUP"
info "Backed up to: $BACKUP"

# Build the new hook entries as JSON
HOOK_ENTRIES=$(cat <<HOOKJSON
[
  {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "bash \"$REPO_DIR/hooks/prevent-project-commit.sh\""}]
  },
  {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "bash \"$REPO_DIR/hooks/pre-push-validate.sh\""}]
  },
  {
    "matcher": "Bash",
    "if": "Bash(jest*|pytest*|npm test*|npx jest*|playwright*)",
    "hooks": [{"type": "command", "command": "bash \"$REPO_DIR/hooks/check-resources.sh\""}]
  }
]
HOOKJSON
)

STOP_HOOK_ENTRIES=$(cat <<HOOKJSON
[
  {
    "hooks": [{"type": "command", "command": "bash \"$REPO_DIR/hooks/check-plan-drift.sh\""}]
  }
]
HOOKJSON
)

POSTTOOL_HOOK_ENTRIES=$(cat <<HOOKJSON
[
  {
    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
    "hooks": [{"type": "command", "command": "bash \"$REPO_DIR/hooks/agent-setup-edit-reminder.sh\""}]
  }
]
HOOKJSON
)

# Merge: remove existing toolkit hooks (by repo path), then append new ones
# This makes the operation idempotent
jq --argjson new_hooks "$HOOK_ENTRIES" --argjson new_stop_hooks "$STOP_HOOK_ENTRIES" --argjson new_posttool_hooks "$POSTTOOL_HOOK_ENTRIES" --arg repo "$REPO_DIR" '
    # Initialize hook arrays if they do not exist
    .hooks //= {} |
    .hooks.PreToolUse //= [] |
    .hooks.Stop //= [] |
    .hooks.PostToolUse //= [] |
    # Remove any existing entries that reference our repo (idempotent re-run)
    .hooks.PreToolUse |= [.[] | select(
        (.hooks // []) | all((.command // "") | contains($repo) | not)
    )] |
    .hooks.Stop |= [.[] | select(
        (.hooks // []) | all((.command // "") | contains($repo) | not)
    )] |
    .hooks.PostToolUse |= [.[] | select(
        (.hooks // []) | all((.command // "") | contains($repo) | not)
    )] |
    # Append new entries
    .hooks.PreToolUse += $new_hooks |
    .hooks.Stop += $new_stop_hooks |
    .hooks.PostToolUse += $new_posttool_hooks |
    # Drop empty arrays for cleanliness
    (if .hooks.Stop == [] then del(.hooks.Stop) else . end) |
    (if .hooks.PostToolUse == [] then del(.hooks.PostToolUse) else . end)
' "$SETTINGS" > "$SETTINGS.tmp"

# Validate the output is valid JSON before replacing
if ! jq empty "$SETTINGS.tmp" 2>/dev/null; then
    error "Generated invalid JSON. Restoring from backup."
    cp "$BACKUP" "$SETTINGS"
    rm -f "$SETTINGS.tmp"
    exit 1
fi

mv "$SETTINGS.tmp" "$SETTINGS"

# Verify
step "Verifying..."

HOOK_COUNT=$(jq '.hooks.PreToolUse | length' "$SETTINGS" 2>/dev/null)
STOP_COUNT=$(jq '(.hooks.Stop // []) | length' "$SETTINGS" 2>/dev/null)
POSTTOOL_COUNT=$(jq '(.hooks.PostToolUse // []) | length' "$SETTINGS" 2>/dev/null)
TOTAL_KEYS=$(jq 'keys | length' "$SETTINGS" 2>/dev/null)
BACKUP_KEYS=$(jq 'keys | length' "$BACKUP" 2>/dev/null)

info "Hooks installed: $HOOK_COUNT PreToolUse + $STOP_COUNT Stop + $POSTTOOL_COUNT PostToolUse entries"
info "Settings keys preserved: $TOTAL_KEYS (was $BACKUP_KEYS)"

if [[ "$TOTAL_KEYS" -lt "$BACKUP_KEYS" ]]; then
    warn "Settings keys decreased — check $BACKUP for the original."
fi

echo ""
echo "========================================"
echo "  Hooks Installed!"
echo "========================================"
echo ""
info "Hooks:"
echo "  prevent-project-commit  — Blocks unsafe git flags, main/master force-pushes, and local workflow state commits"
echo "  pre-push-validate       — Runs repository-pinned lint and targeted tests before git push"
echo "  check-resources         — Warns when tests run with constrained resources"
echo "  check-plan-drift        — Warns at turn end when PLAN.md outpaces PROJECT.md"
echo "  agent-setup-edit-reminder — Reminds to load agent-setup-maintainer when an agent-setup file is edited"
echo ""
info "To remove: ./install-hooks.sh --remove"
echo ""
