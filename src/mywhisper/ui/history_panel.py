"""Side panel of the history: past transcriptions, full-text search, favourites."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
)

from mywhisper.session import clock
from mywhisper.storage.history import KIND_LABELS, Entry, HistoryStore
from mywhisper.ui import theme
from mywhisper.ui.theme import Tokens

SEARCH_DELAY_MS = 150
PANEL_WIDTH = 270


class HistoryPanel(QFrame):
    opened = Signal(int)  # entry id
    deleted = Signal(int)  # entry id
    renamed = Signal(int, str)  # entry id, new title

    def __init__(self, store: HistoryStore, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.store = store
        self.current_id: int | None = None

        title = QLabel("Historique")
        title.setObjectName("PanelTitle")
        self.favorites_button = QToolButton()
        self.favorites_button.setObjectName("IconButton")
        self.favorites_button.setCheckable(True)
        self.favorites_button.setToolTip("Favoris seulement")
        self.favorites_button.toggled.connect(lambda _: self.refresh())
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.favorites_button)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher dans les transcriptions")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self._search_timer.start())

        self.list = QListWidget()
        self.list.setObjectName("HistoryList")
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemActivated.connect(self._activated)
        self.list.itemClicked.connect(self._activated)
        QShortcut(QKeySequence.StandardKey.Delete, self.list, self._delete_selected)
        QShortcut(QKeySequence("F2"), self.list, self._rename_selected)

        self.empty = QLabel("")
        self.empty.setProperty("muted", True)
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 10, 14)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.search)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self.set_tokens(tokens)
        self.refresh()

    def set_tokens(self, tokens: Tokens) -> None:
        self.favorites_button.setIcon(theme.icon("ph.star", tokens))
        self.favorites_button.setIconSize(QSize(17, 17))

    # ---- content -------------------------------------------------------

    def refresh(self) -> None:
        query = self.search.text()
        entries = self.store.list(query, favorites_only=self.favorites_button.isChecked())
        self.list.clear()
        for entry in entries:
            item = QListWidgetItem(self._label(entry, bool(query.strip())))
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setToolTip(entry.source or entry.title)
            self.list.addItem(item)
            if entry.id == self.current_id:
                item.setSelected(True)
        if entries:
            self.empty.hide()
        else:
            self.empty.setText(
                "Aucun résultat." if query.strip() else "Vos transcriptions apparaîtront ici, enregistrées automatiquement."
            )
            self.empty.show()

    @staticmethod
    def _label(entry: Entry, searching: bool) -> str:
        star = "★ " if entry.favorite else ""
        details = [entry.date_label(), KIND_LABELS.get(entry.kind, entry.kind)]
        if entry.duration:
            details.append(clock(entry.duration))
        if entry.audio_path:
            details.append("audio")
        lines = [f"{star}{entry.title}", " · ".join(details)]
        if searching and entry.snippet:
            lines.append(entry.snippet.replace("\n", " "))
        return "\n".join(lines)

    def select(self, entry_id: int | None) -> None:
        self.current_id = entry_id
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == entry_id)

    # ---- actions -------------------------------------------------------

    def _entry_id(self, item: QListWidgetItem | None) -> int | None:
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _activated(self, item: QListWidgetItem) -> None:
        entry_id = self._entry_id(item)
        if entry_id is not None:
            self.opened.emit(entry_id)

    def _context_menu(self, position) -> None:
        item = self.list.itemAt(position)
        entry_id = self._entry_id(item)
        if entry_id is None:
            return
        entry = self.store.get(entry_id)
        if entry is None:
            return
        menu = QMenu(self)
        menu.addAction("Ouvrir", lambda: self.opened.emit(entry_id))
        menu.addAction("Renommer…", lambda: self.rename(entry_id))
        menu.addAction(
            "Retirer des favoris" if entry.favorite else "Ajouter aux favoris",
            lambda: self.set_favorite(entry_id, not entry.favorite),
        )
        menu.addSeparator()
        menu.addAction("Supprimer…", lambda: self.delete(entry_id))
        menu.exec(self.list.viewport().mapToGlobal(position))

    def _rename_selected(self) -> None:
        entry_id = self._entry_id(self.list.currentItem())
        if entry_id is not None:
            self.rename(entry_id)

    def _delete_selected(self) -> None:
        entry_id = self._entry_id(self.list.currentItem())
        if entry_id is not None:
            self.delete(entry_id)

    def rename(self, entry_id: int, title: str | None = None) -> None:
        entry = self.store.get(entry_id)
        if entry is None:
            return
        if title is None:
            title, ok = QInputDialog.getText(self, "Renommer", "Titre", text=entry.title)
            if not ok:
                return
        self.store.rename(entry_id, title)
        self.refresh()
        self.renamed.emit(entry_id, self.store.get(entry_id).title)

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        self.store.set_favorite(entry_id, favorite)
        self.refresh()

    def delete(self, entry_id: int, confirm: bool = True) -> None:
        if confirm:
            answer = QMessageBox.question(
                self, "Supprimer", "Supprimer cette transcription de l'historique, avec son audio ?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.store.delete(entry_id)
        if entry_id == self.current_id:
            self.current_id = None
        self.refresh()
        self.deleted.emit(entry_id)
