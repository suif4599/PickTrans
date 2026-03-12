import sys
from threading import Thread
from typing import Callable, Literal, cast

from engine import EngineCollection
from gui.main_window import MainWindow, Placement, compute_popup_position
from hotkey_manager import HotkeyManagerInterface
from PyQt6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QClipboard, QCursor, QFocusEvent, QGuiApplication, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget


PlacementPriority = list[Literal["RB", "LB", "RT", "LT"]]


class FocusAnchorWindow(QWidget):
	"""A transparent fullscreen anchor used to place child popup under Wayland."""

	pointer_ready = pyqtSignal(object, object, str)
	outside_clicked = pyqtSignal(object)
	focus_lost = pyqtSignal()

	def __init__(self) -> None:
		super().__init__()
		self._capture_armed = False
		self.setWindowFlags(
			Qt.WindowType.FramelessWindowHint
			| Qt.WindowType.WindowStaysOnTopHint
			| Qt.WindowType.Tool
		)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
		self.setStyleSheet("background: transparent;")
		self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

	def show_on_screen(self) -> None:
		screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
		if screen is None:
			return
		self.setGeometry(screen.geometry())
		self.show()
		self.raise_()
		self.activateWindow()
		self.setFocus()

	def start_pointer_capture(self) -> None:
		self._capture_armed = True

	def keyPressEvent(self, a0: QKeyEvent | None) -> None:
		if a0 is not None and self._capture_armed and a0.key() == Qt.Key.Key_K:
			self._capture_armed = False
			cursor_in_anchor = self.mapFromGlobal(QCursor.pos())
			clipboard = QApplication.clipboard()
			selection_text = ""
			if clipboard is not None:
				selection_text = clipboard.text(mode=QClipboard.Mode.Selection).strip()
			self.pointer_ready.emit(cursor_in_anchor, self.rect(), selection_text)
			a0.accept()
			return
		super().keyPressEvent(a0)

	def mousePressEvent(self, a0: QMouseEvent | None) -> None:
		if a0 is not None and not self._capture_armed:
			self.outside_clicked.emit(a0.position().toPoint())
			a0.accept()
			return
		super().mousePressEvent(a0)

	def focusOutEvent(self, a0: QFocusEvent | None) -> None:
		self.focus_lost.emit()
		super().focusOutEvent(a0)


class PickTransApplication(QObject):
	_show_window_requested = pyqtSignal(int, object)
	_close_window_requested = pyqtSignal()

	def __init__(
		self,
		manager: HotkeyManagerInterface,
		engines: EngineCollection,
		width: int | float = 880,
		height: int | float = 460,
		on_popup_exit: Callable[[], None] | None = None,
		placement_preferences: PlacementPriority | None = None,
		trigger_hotkey: str = "Double(LEFTCTRL)",
		exit_hotkey: str = "ESC",
	) -> None:
		super().__init__()
		app_instance = QApplication.instance()
		self.qt_app: QApplication = (
			cast(QApplication, app_instance) if app_instance is not None else QApplication(sys.argv)
		)
		self.anchor = FocusAnchorWindow()
		self.anchor.pointer_ready.connect(self._on_pointer_ready)
		self.anchor.outside_clicked.connect(self._on_anchor_clicked)
		self.anchor.focus_lost.connect(self._on_anchor_focus_lost)
		self.window: MainWindow | None = None
		self._pending_popup_request: tuple[int, list[Placement]] | None = None
		self._show_window_requested.connect(self._show_window)
		self._close_window_requested.connect(self._close_popup)
		self._manager = manager
		self._engines = engines
		self._popup_width_cfg = width
		self._popup_height_cfg = height
		self._current_source_text = ""
		self._on_popup_exit = on_popup_exit
		self._trigger_hotkey = trigger_hotkey
		self._exit_hotkey = exit_hotkey
		self._hotkeys_registered = False
		self._hotkey_loop_started = False
		self._placement_preferences: PlacementPriority = placement_preferences or ["RB", "LB", "RT", "LT"]
		self._hotkey_thread: Thread | None = None

	def activate_hotkey_support(self) -> None:
		self.register_hotkeys()
		self.start_hotkey_loop()

	def register_hotkeys(self) -> None:
		if self._hotkeys_registered:
			return
		self._manager.register_hotkey(
			self._trigger_hotkey,
			lambda: self._show_window_requested.emit(-1, self._placement_preferences),
			pass_through=True,
		)
		self._manager.register_hotkey(
			self._exit_hotkey,
			lambda: self._close_window_requested.emit(),
			pass_through=True,
		)
		self._hotkeys_registered = True

	def start_hotkey_loop(self) -> None:
		if self._hotkey_loop_started:
			return
		self._hotkey_thread = Thread(target=self._manager.mainloop, daemon=True)
		self._hotkey_thread.start()
		self._hotkey_loop_started = True

	def callback(
		self,
		index: int = -1,
		placement_preferences: list[Placement] | None = None,
	) -> None:
		preferences = placement_preferences or self._placement_preferences
		self._show_window_requested.emit(index, preferences)

	def get_callback(self) -> Callable[[int], None]:
		return lambda index: self.callback(index=index, placement_preferences=None)

	def mainloop(self) -> int:
		return self.qt_app.exec()

	def quit(self) -> None:
		self.qt_app.quit()

	def _show_window(self, index: int, placement_preferences: list[Placement]) -> None:
		self._pending_popup_request = (index, placement_preferences)
		self.anchor.show_on_screen()
		self.anchor.start_pointer_capture()
		self.qt_app.processEvents()
		try:
			# Wayland: injected key provides trusted serial for input-bound operations.
			self._manager.inject("K", before_ms=100, block=False)
		except Exception:
			cursor_in_anchor = self.anchor.mapFromGlobal(QCursor.pos())
			clipboard = QApplication.clipboard()
			selection_text = ""
			if clipboard is not None:
				selection_text = clipboard.text(mode=QClipboard.Mode.Selection).strip()
			self._on_pointer_ready(cursor_in_anchor, self.anchor.rect(), selection_text)

	def _on_pointer_ready(self, cursor_in_anchor: QPoint, bounds: QRect, selection_text: str) -> None:
		if self._pending_popup_request is None:
			return
		requested_index, placement_preferences = self._pending_popup_request
		self._pending_popup_request = None

		engine_names = self._engines.names()
		if not engine_names:
			self.anchor.hide()
			return

		if self.window is None:
			self.window = MainWindow(engines=engine_names, index=0, parent=self.anchor)
			self.window.engine_index_changed.connect(self._on_engine_index_changed)
			self.window.closed.connect(self._on_popup_closed)
		else:
			self.window.setParent(self.anchor)

		popup_size = self._resolve_popup_size(bounds)
		self.window.resize(popup_size)

		self._current_source_text = selection_text
		if self._current_source_text:
			self.window.set_original_text(self._current_source_text)
		else:
			self.window.set_original_text("Primary Selection is empty")

		if self._current_source_text:
			if requested_index < 0:
				used_index, translated_html = self._engines.translate(self._current_source_text)
				target_index = used_index if used_index >= 0 else 0
			else:
				target_index = max(0, min(requested_index, len(engine_names) - 1))
				translated_html = self._engines.translate(self._current_source_text, target_index)
		else:
			target_index = 0 if requested_index < 0 else max(0, min(requested_index, len(engine_names) - 1))
			translated_html = ""

		self.window.update_engines(engine_names, target_index)
		self.window.set_translation_html(translated_html)

		position = compute_popup_position(
			cursor_pos=cursor_in_anchor,
			window_size=self.window.size(),
			bounds=bounds,
			preferences=placement_preferences,
		)
		self.window.move(position)

		self.window.show()
		self.window.raise_()
		self.window.activateWindow()

	def _resolve_popup_size(self, bounds: QRect) -> QSize:
		default_width = self.window.width() if self.window is not None else 880
		default_height = self.window.height() if self.window is not None else 460

		width_cfg = self._popup_width_cfg
		height_cfg = self._popup_height_cfg

		width = self._resolve_dimension(width_cfg, bounds.width(), default_width)
		height = self._resolve_dimension(height_cfg, bounds.height(), default_height)
		return QSize(width, height)

	@staticmethod
	def _resolve_dimension(value: object, total: int, fallback: int) -> int:
		if isinstance(value, int) and not isinstance(value, bool):
			resolved = value
		elif isinstance(value, float):
			resolved = int(total * value)
		else:
			resolved = fallback
		resolved = max(1, resolved)
		return min(resolved, total)

	def _on_engine_index_changed(self, engine_index: int) -> None:
		if self.window is None or not self.window.isVisible():
			return
		if not self._current_source_text:
			return
		translated_html = self._engines.translate(self._current_source_text, engine_index)
		self.window.set_translation_html(translated_html)

	def _close_popup(self) -> None:
		self._pending_popup_request = None
		if self.window is not None and self.window.isVisible():
			self.window.close()
		else:
			self.anchor.hide()
			self._on_popup_closed()

	def _on_anchor_clicked(self, position: QPoint) -> None:
		if self.window is None or not self.window.isVisible():
			return
		if not self.window.geometry().contains(position):
			self._close_popup()

	def _on_anchor_focus_lost(self) -> None:
		# Defer focus check to avoid false close during internal focus transitions.
		QTimer.singleShot(0, self._close_if_focus_left)

	def _close_if_focus_left(self) -> None:
		if self.window is None or not self.window.isVisible():
			return
		active = self.qt_app.activeWindow()
		combo_view = self.window.engine_selector.view()
		combo_popup = combo_view.window() if combo_view is not None else None
		related = {
			self.anchor,
			self.window,
			combo_popup,
		}
		if active in related:
			return
		if active is not None and (
			self.anchor.isAncestorOf(active) or self.window.isAncestorOf(active)
		):
			return
		self._close_popup()

	def _on_popup_closed(self) -> None:
		self.anchor.hide()
		if self._on_popup_exit is not None:
			self._on_popup_exit()
