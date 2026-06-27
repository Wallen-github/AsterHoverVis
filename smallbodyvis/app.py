'''
@File        : smallbodyvis/app.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Application entry point.
'''

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from smallbodyvis.ui.main_window import MainWindow
    except ImportError as exc:
        print(
            "AsterHoverVis UI dependencies are missing.\n"
            "Install them with:\n\n"
            "  python3 -m pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1680, 980)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
