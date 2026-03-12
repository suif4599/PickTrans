import json
import signal
import sys
import os
from engine.engine import EngineCollection, TranslationEngine
from gui.application import PickTransApplication
from gui.tray import TrayController
from hotkey_manager import HotkeyManagerInterface
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open("config.json", "r") as f:
    config = json.load(f)

engines = TranslationEngine.make_engines(config)
if not engines:
    print("No engines initialized successfully. Please check the warnings for details.")
    exit(1)
engine_collection = EngineCollection(engines)

iface = HotkeyManagerInterface(timeout_ms=500)
app = PickTransApplication(iface, engine_collection, **config.get("app", {}))

icon_path = os.path.join("gui", "icon.png")
app.qt_app.setWindowIcon(QIcon(icon_path))

tray = TrayController(
    app=app.qt_app,
    manager=iface,
    on_authenticated=app.activate_hotkey_support,
    icon_path=icon_path,
    config_path=os.path.abspath("config.json"),
    main_path=os.path.abspath(__file__),
)


def _handle_sigint(_signum, _frame) -> None:
    app.quit()


signal.signal(signal.SIGINT, _handle_sigint)

sigint_timer = QTimer()
sigint_timer.timeout.connect(lambda: None)
sigint_timer.start(200)

sys.exit(app.mainloop())
