#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=${1:-$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)}

printf '%s\n' "PGM installation is owned by the main deterministic installer."
exec "$ROOT/install.sh" --with-pgm
