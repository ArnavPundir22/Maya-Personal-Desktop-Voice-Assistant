#!/usr/bin/env python3
"""
Maya AI Desktop Assistant — Ubuntu Edition v2.0
Launch script.
"""
import sys
import os
import types

# Ensure DISPLAY is set for X11/Wayland
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'

# Suppress mouseinfo tkinter requirement (optional pyautogui dependency)
try:
    import tkinter
except ImportError:
    stub = types.ModuleType('mouseinfo')
    stub.MouseInfoWindow = None
    sys.modules['mouseinfo'] = stub

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from devin.gui import MayaWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Maya AI Assistant")

    # Set icon if available
    icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MayaWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
