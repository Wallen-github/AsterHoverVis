#!/bin/zsh
# @File        : Run_AsterHoverVis.command
# @Time        : 2026/06/27 13:47:07
# @Author      : Hai-Shuo Wang
# @Version     : 1.0
# @Contact     : wallen1732@gmail.com

set -u

APP_DIR="${0:A:h}"
cd "$APP_DIR" || exit 1

export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export LC_CTYPE="UTF-8"

typeset -a PYTHON_CANDIDATES
PYTHON_CANDIDATES=()

if [[ -n "${ASTERHOVERVIS_PYTHON:-}" ]]; then
  PYTHON_CANDIDATES+=("$ASTERHOVERVIS_PYTHON")
fi
PYTHON_CANDIDATES+=(
  "$APP_DIR/.venv/bin/python"
  "/opt/anaconda3/bin/python"
  "/opt/anaconda3/bin/python3"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
  "/opt/local/bin/python3"
  "/usr/bin/python3"
)
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CANDIDATES+=("$(command -v python3)")
fi

PYTHON_BIN=""
QT_PLUGIN_ROOT=""

for CANDIDATE in "${PYTHON_CANDIDATES[@]}"; do
  [[ -x "$CANDIDATE" ]] || continue
  PLUGIN_PATH="$("$CANDIDATE" - <<'PY' 2>/dev/null
import importlib.util
import sys

required = ("PySide6", "pyvista", "pyvistaqt", "pyqtgraph", "numpy", "scipy")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    sys.exit(10)

from pathlib import Path

import PySide6
from PySide6.QtCore import QLibraryInfo

pyside_plugins = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
if (pyside_plugins / "platforms" / "libqcocoa.dylib").exists():
    print(pyside_plugins)
else:
    print(QLibraryInfo.path(QLibraryInfo.PluginsPath))
PY
)"
  if [[ $? -eq 0 && -n "$PLUGIN_PATH" ]]; then
    PYTHON_BIN="$CANDIDATE"
    QT_PLUGIN_ROOT="$PLUGIN_PATH"
    break
  fi
done

echo "Starting AsterHoverVis v0..."
echo "App directory: $APP_DIR"
echo

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Could not find a Python interpreter with the required UI packages."
  echo
  echo "Checked:"
  for CANDIDATE in "${PYTHON_CANDIDATES[@]}"; do
    echo "  $CANDIDATE"
  done
  echo
  echo "Install dependencies into the Python used by this launcher:"
  echo "  /opt/anaconda3/bin/python -m pip install -r requirements.txt"
  echo
  echo "Or set ASTERHOVERVIS_PYTHON to the desired interpreter path."
  echo
  echo "Press any key to close this window."
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

export QT_PLUGIN_PATH="$QT_PLUGIN_ROOT${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
if [[ -d "$QT_PLUGIN_ROOT/platforms" ]]; then
  export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_ROOT/platforms"
fi

echo "Python: $PYTHON_BIN"
echo "Qt plugins: $QT_PLUGIN_ROOT"
echo

if [[ "${ASTERHOVERVIS_CHECK_ONLY:-0}" == "1" ]]; then
  echo "Launcher check passed."
  exit 0
fi

"$PYTHON_BIN" -m smallbodyvis.app
STATUS=$?

if [[ $STATUS -ne 0 ]]; then
  echo
  echo "AsterHoverVis exited with status $STATUS."
  echo "If Python reports missing packages, run:"
  echo "  \"$PYTHON_BIN\" -m pip install -r requirements.txt"
  echo
  echo "Press any key to close this window."
  if [[ -t 0 ]]; then
    read -k 1
  fi
fi

exit $STATUS
