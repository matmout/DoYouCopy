from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton


class SegmentedControl(QFrame):
    """Exclusive choice between a few options, styled by #Segmented in the theme."""

    changed = Signal(object)  # data of the selected option

    def __init__(self, options: list[tuple[object, str]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._data: dict[int, object] = {}
        for index, (data, label) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self._group.addButton(button, index)
            self._data[index] = data
            layout.addWidget(button)
        self._group.idClicked.connect(lambda i: self.changed.emit(self._data[i]))
        if options:
            self._group.button(0).setChecked(True)

    def value(self):
        return self._data.get(self._group.checkedId())

    def set_value(self, data) -> None:
        """Selects silently (no changed signal)."""
        for index, value in self._data.items():
            if value == data:
                self._group.button(index).setChecked(True)
                return

    def buttons(self) -> list[QPushButton]:
        return self._group.buttons()
