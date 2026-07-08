#!/bin/zsh
# Compiles launcher.c into build/ChatterBox.app. Re-run after recreating
# the venv with a different Python, or on a new machine.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .venv/pyvenv.cfg ]]; then
  echo "error: no .venv — run: uv venv --python 3.12 && uv pip install -e ." >&2
  exit 1
fi

# pyvenv.cfg's `home` points at the base interpreter's bin dir; libpython
# lives in the sibling lib dir. uv keeps an unversioned symlink
# (cpython-3.12-…) so the rpath survives patch upgrades.
home=$(sed -n 's/^home = //p' .venv/pyvenv.cfg)
pyroot=${home%/bin}

clang launcher.c \
  -o build/ChatterBox.app/Contents/MacOS/ChatterBox \
  -L"$pyroot/lib" -lpython3.12 -Wl,-rpath,"$pyroot/lib"

echo "built build/ChatterBox.app (libpython: $pyroot/lib)"
