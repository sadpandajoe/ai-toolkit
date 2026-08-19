#!/usr/bin/env bash
# Containment setup for the state-ownership end_to_end_scenario fixture.
# Disposable repo + synthetic remote + scratch home, per PLAN.md's
# Containment rules.
set -euo pipefail

: "${SCRATCH_ROOT:?set SCRATCH_ROOT to a throwaway directory, never the toolkit repo or a real checkout}"

rm -rf "$SCRATCH_ROOT"
mkdir -p "$SCRATCH_ROOT/home"

git init --bare -q "$SCRATCH_ROOT/origin.git"

git init -q "$SCRATCH_ROOT/repo"
cd "$SCRATCH_ROOT/repo"
git config user.name "eval-fixture"
git config user.email "eval-fixture@example.invalid"
git config commit.gpgsign false
git remote add origin "$SCRATCH_ROOT/origin.git"

mkdir -p src
for name in alpha beta gamma delta epsilon; do
  cat > "src/${name}.py" <<EOF
def ${name}_status():
    return "todo"
EOF
done
git add src
git commit -q -m "base commit: five modules each returning a placeholder status"
git push -q origin HEAD:main

echo "Scratch repo ready at $SCRATCH_ROOT/repo (main pushed to origin)."
