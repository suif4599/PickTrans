from __future__ import annotations

from typing import Literal, Sequence

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QGuiApplication
from PyQt6.QtWidgets import (
	QComboBox,
	QHBoxLayout,
	QPlainTextEdit,
	QTextBrowser,
	QVBoxLayout,
	QWidget,
)


Placement = Literal["RB", "LB", "RT", "LT"]


def compute_popup_position(
	cursor_pos: QPoint,
	window_size: QSize,
	bounds: QRect,
	preferences: Sequence[Placement],
) -> QPoint:
	# Try preferred quadrants around cursor first; fallback clamps inside bounds.
	valid_preferences = [p for p in preferences if p in ("RB", "LB", "RT", "LT")]
	if not valid_preferences:
		valid_preferences = ["RB", "LB", "RT", "LT"]

	w = window_size.width()
	h = window_size.height()

	for pref in valid_preferences:
		if pref == "RB":
			x = cursor_pos.x()
			y = cursor_pos.y()
		elif pref == "LB":
			x = cursor_pos.x() - w
			y = cursor_pos.y()
		elif pref == "RT":
			x = cursor_pos.x()
			y = cursor_pos.y() - h
		else:  # LT
			x = cursor_pos.x() - w
			y = cursor_pos.y() - h

		candidate = QRect(x, y, w, h)
		if bounds.contains(candidate):
			return QPoint(x, y)

	clamped_x = min(max(cursor_pos.x(), bounds.left()), bounds.right() - w + 1)
	clamped_y = min(max(cursor_pos.y(), bounds.top()), bounds.bottom() - h + 1)
	return QPoint(clamped_x, clamped_y)


class MainWindow(QWidget):
	closed = pyqtSignal()
	engine_index_changed = pyqtSignal(int)

	def __init__(self, engines: Sequence[str], index: int = 0, parent: QWidget | None = None) -> None:
		super().__init__(parent)
		flags = Qt.WindowType.FramelessWindowHint
		if parent is None:
			flags |= Qt.WindowType.Window
		self.setWindowFlags(flags)
		self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
		self.resize(880, 460)

		self.engine_selector = QComboBox(self)
		self.engine_selector.currentIndexChanged.connect(self.engine_index_changed.emit)
		self.original_view = QPlainTextEdit(self)
		self.translation_view = QTextBrowser(self)

		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setStyleSheet("background-color: palette(window);")
		self.original_view.setReadOnly(True)
		self.original_view.setStyleSheet("background-color: palette(base); color: palette(text);")
		original_viewport = self.original_view.viewport()
		if original_viewport is not None:
			original_viewport.setStyleSheet("background-color: palette(base);")
		self.translation_view.setStyleSheet("background-color: palette(base); color: palette(text);")
		translation_viewport = self.translation_view.viewport()
		if translation_viewport is not None:
			translation_viewport.setStyleSheet("background-color: palette(base);")
		self.translation_view.setOpenExternalLinks(True)

		root_layout = QVBoxLayout(self)
		root_layout.setContentsMargins(2, 2, 2, 2)
		root_layout.setSpacing(2)
		root_layout.addWidget(self.engine_selector)

		content_layout = QHBoxLayout()
		content_layout.setSpacing(2)
		content_layout.addWidget(self.original_view, 1)
		content_layout.addWidget(self.translation_view, 1)
		root_layout.addLayout(content_layout, 1)

		self.update_engines(engines, index)
		if parent is None:
			self.center_on_screen()

	def update_engines(self, engines: Sequence[str], index: int) -> None:
		self.engine_selector.blockSignals(True)
		self.engine_selector.clear()
		self.engine_selector.addItems(list(engines))
		if self.engine_selector.count() > 0:
			safe_index = max(0, min(index, self.engine_selector.count() - 1))
			self.engine_selector.setCurrentIndex(safe_index)
		self.engine_selector.blockSignals(False)

	def set_original_text(self, text: str) -> None:
		self.original_view.setPlainText(text)

	def set_translation_html(self, html: str) -> None:
		self.translation_view.setHtml(html)

	def center_on_screen(self) -> None:
		screen = QGuiApplication.primaryScreen()
		if screen is None:
			return
		available = screen.availableGeometry()
		frame = self.frameGeometry()
		frame.moveCenter(available.center())
		self.move(frame.topLeft())

	def closeEvent(self, a0: QCloseEvent | None) -> None:
		self.closed.emit()
		super().closeEvent(a0)
