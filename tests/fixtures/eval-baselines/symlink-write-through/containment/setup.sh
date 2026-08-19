#!/usr/bin/env bash
# Containment setup for the symlink-write-through end_to_end_scenario fixture.
# Disposable repo + synthetic remote + scratch home, per PLAN.md's
# Containment rules.
set -euo pipefail

: "${SCRATCH_ROOT:?set SCRATCH_ROOT to a throwaway directory, never the toolkit repo or a real checkout}"

rm -rf "$SCRATCH_ROOT"
mkdir -p "$SCRATCH_ROOT/home"
mkdir -p "$SCRATCH_ROOT/state-store"

git init --bare -q "$SCRATCH_ROOT/origin.git"

git init -q "$SCRATCH_ROOT/repo"
cd "$SCRATCH_ROOT/repo"
git config user.name "eval-fixture"
git config user.email "eval-fixture@example.invalid"
git config commit.gpgsign false
git remote add origin "$SCRATCH_ROOT/origin.git"

mkdir -p src
cat > src/widget.py <<'EOF'
def widget_status():
    return "todo"
EOF
git add src/widget.py
git commit -q -m "base commit"
git push -q origin HEAD:main

# The real target lives outside the repo working tree, so a naive write
# through the un-resolved symlink path and a write to the real path are
# observably different files.
cat > "$SCRATCH_ROOT/state-store/PROJECT.md" <<'EOF'
# Current state

(placeholder — pre-scenario content)
EOF

# PROJECT.md in the scratch repo is a symlink to the real target, not a
# regular file — this is the condition under test.
ln -s "$SCRATCH_ROOT/state-store/PROJECT.md" PROJECT.md

echo "Scratch repo ready at $SCRATCH_ROOT/repo; PROJECT.md is a symlink to $SCRATCH_ROOT/state-store/PROJECT.md."
