#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf '%s\n' "AI Toolkit requires Python 3.11 or newer (cannot find $PYTHON)." >&2
    exit 2
fi
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    printf '%s\n' "AI Toolkit requires Python 3.11 or newer." >&2
    exit 2
fi

case "${1:-}" in
    --uninstall)
        shift
        exec "$ROOT/bin/aitk" uninstall "$@"
        ;;
    --rollback)
        shift
        exec "$ROOT/bin/aitk" rollback "$@"
        ;;
    --with-pgm)
        shift
        exec "$ROOT/bin/aitk" install --with-pgm "$@"
        ;;
    "")
        exec "$ROOT/bin/aitk" install
        ;;
    *)
        exec "$ROOT/bin/aitk" install "$@"
        ;;
esac
