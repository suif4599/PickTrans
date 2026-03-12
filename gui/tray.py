from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from hotkey_manager import HotkeyManagerInterface
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor, QDesktopServices, QIcon, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QLineEdit,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


SERVICE_NAME = "picktrans.service"


class AuthenticateOverlay(QWidget):
    def __init__(self, on_submit: Callable[[str], None], parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background: transparent;")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Input password and press Enter")
        self.password_input.setFixedWidth(360)
        self.password_input.setStyleSheet(
            "QLineEdit {"
            "background-color: palette(base);"
            "color: palette(text);"
            "border: 1px solid palette(mid);"
            "border-radius: 18px;"
            "padding: 8px 12px;"
            "}"
        )
        self.password_input.returnPressed.connect(self._submit)
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.activated.connect(self._cancel)

        root_layout.addWidget(self.password_input, alignment=Qt.AlignmentFlag.AlignCenter)

    def show_on_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.password_input.setFocus()

    def mousePressEvent(self, a0) -> None:
        if a0 is None:
            return
        if not self.password_input.geometry().contains(a0.position().toPoint()):
            self._cancel()
            a0.accept()
            return
        super().mousePressEvent(a0)

    def focusOutEvent(self, a0) -> None:
        self._cancel()
        super().focusOutEvent(a0)

    def _submit(self) -> None:
        password = self.password_input.text()
        self.hide()
        self._on_submit(password)

    def _cancel(self) -> None:
        self.hide()


class TrayController:
    def __init__(
        self,
        *,
        app,
        manager: HotkeyManagerInterface,
        on_authenticated: Callable[[], None],
        icon_path: str,
        config_path: str,
        main_path: str,
    ) -> None:
        self._app = app
        self._manager = manager
        self._on_authenticated = on_authenticated
        self._icon_path = str(Path(icon_path).resolve())
        self._config_path = str(Path(config_path).resolve())
        self._main_path = str(Path(main_path).resolve())
        self._project_root = str(Path(self._main_path).resolve().parent)
        self._service_mode = self._is_service_process()

        self._tray = QSystemTrayIcon(QIcon(self._icon_path), self._app)
        self._tray.setToolTip("PickTrans")
        self._menu = QMenu()

        self._action_auth = QAction("Authenticate", self._menu)
        self._action_auth.triggered.connect(self._on_authenticate)

        service_text = "Restart Service" if self._service_mode else "Register Service"
        self._action_service = QAction(service_text, self._menu)
        self._action_service.triggered.connect(self._on_service)

        self._action_config = QAction("Config", self._menu)
        self._action_config.triggered.connect(self._on_config)

        self._action_quit = QAction("Quit", self._menu)
        self._action_quit.triggered.connect(self._on_quit)

        self._menu.addAction(self._action_auth)
        self._menu.addAction(self._action_service)
        self._menu.addAction(self._action_config)
        self._menu.addSeparator()
        self._menu.addAction(self._action_quit)

        self._tray.setContextMenu(self._menu)
        self._tray.show()
        self._auth_overlay: AuthenticateOverlay | None = None

    def _show_message(self, title: str, body: str) -> None:
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _show_error(self, title: str, body: str) -> None:
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Critical, 5000)

    def _on_authenticate(self) -> None:
        def submit(password: str) -> None:
            if not password:
                self._show_error("Authenticate", "Password is empty")
                return
            try:
                result = self._manager.authenticate(password)
                if result is False:
                    self._show_error("Authenticate", "Authentication failed")
                    return
                self._on_authenticated()
                self._show_message("Authenticate", "Authentication succeeded")
            except Exception as exc:
                self._show_error("Authenticate", f"Authentication failed: {exc}")

        if self._auth_overlay is None:
            self._auth_overlay = AuthenticateOverlay(on_submit=submit)
        self._auth_overlay.show_on_screen()

    def _on_service(self) -> None:
        try:
            if self._service_mode:
                self._restart_service()
                self._show_message("Service", "Service restarted")
            else:
                self._register_service()
                # Hand over execution to systemd user service instance.
                self._tray.hide()
                self._app.quit()
        except Exception as exc:
            self._show_error("Service", str(exc))

    def _on_config(self) -> None:
        from PyQt6.QtCore import QUrl

        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(self._config_path))
        if not ok:
            self._show_error("Config", "Failed to open config.json")

    def _on_quit(self) -> None:
        self._tray.hide()
        self._app.quit()

    def _register_service(self) -> None:
        service_dir = Path.home() / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True, exist_ok=True)
        service_path = service_dir / SERVICE_NAME

        conda_exe = self._resolve_conda_executable()
        conda_env = self._resolve_conda_env_name()

        exec_start = (
            f"{shlex.quote(conda_exe)} run -n {shlex.quote(conda_env)} "
            f"python {shlex.quote(self._main_path)}"
        )

        content = (
            "[Unit]\n"
            "Description=PickTrans User Service\n"
            "After=default.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={self._project_root}\n"
            f"ExecStart={exec_start}\n"
            "Restart=always\n"
            "RestartSec=2\n"
            "Environment=PYTHONUNBUFFERED=1\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        service_path.write_text(content, encoding="utf-8")

        self._run_systemctl(["--user", "daemon-reload"])
        self._run_systemctl(["--user", "enable", "--now", SERVICE_NAME])

    def _restart_service(self) -> None:
        self._run_systemctl(["--user", "restart", SERVICE_NAME])

    @staticmethod
    def _is_service_process() -> bool:
        try:
            try:
                import psutil
            except ImportError:
                return False

            current = psutil.Process()
            parent = current.parent()
            tree: list[str] = [current.name()]
            while parent:
                tree.append(parent.name())
                parent = parent.parent()

            if "conda" not in tree:
                return False
            idx = tree.index("conda")
            if idx + 1 < len(tree) and tree[idx + 1] == "systemd":
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def _run_systemctl(args: list[str]) -> None:
        cmd = ["systemctl", *args]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "systemctl failed"
            raise RuntimeError(stderr)

    def _resolve_conda_executable(self) -> str:
        from_env = os.getenv("CONDA_EXE")
        if from_env and Path(from_env).exists():
            return from_env

        from_path = shutil.which("conda")
        if from_path:
            return from_path

        py_path = Path(os.path.realpath(sys.executable))
        # /opt/anaconda3/envs/<name>/bin/python -> /opt/anaconda3/bin/conda
        if "envs" in py_path.parts:
            env_idx = py_path.parts.index("envs")
            if env_idx > 0:
                root = Path(*py_path.parts[:env_idx])
                candidate = root / "bin" / "conda"
                if candidate.exists():
                    return str(candidate)

        # /opt/anaconda3/bin/python -> /opt/anaconda3/bin/conda
        candidate = py_path.parent / "conda"
        if candidate.exists():
            return str(candidate)

        raise RuntimeError("Cannot locate conda executable")

    def _resolve_conda_env_name(self) -> str:
        current = os.getenv("CONDA_DEFAULT_ENV")
        if current:
            return current

        py_path = Path(os.path.realpath(sys.executable))
        parts = py_path.parts
        if "envs" in parts:
            env_idx = parts.index("envs")
            if env_idx + 1 < len(parts):
                return parts[env_idx + 1]

        # Fallback to base environment in common conda layouts.
        if py_path.parent.name == "bin":
            return "base"

        raise RuntimeError("Cannot infer current conda environment name")
