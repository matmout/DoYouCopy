from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mywhisper.config import Settings


class VocabularyDialog(QDialog):
    """Favoured words, replacements and spoken punctuation, written back to Settings on OK."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Vocabulaire")
        self.resize(520, 560)

        hotwords_title = QLabel("Mots à favoriser")
        hotwords_title.setObjectName("PopoverTitle")
        hotwords_hint = QLabel("Noms propres, sigles, jargon : un par ligne.")
        hotwords_hint.setProperty("muted", True)
        self.hotwords_edit = QPlainTextEdit("\n".join(settings.hotwords))
        self.hotwords_edit.setPlaceholderText("ROCm\nCTranslate2\nMme Dupuis")

        replacements_title = QLabel("Remplacements")
        replacements_title.setObjectName("PopoverTitle")
        replacements_hint = QLabel("Mots entiers, sans tenir compte de la casse. /motif/ pour une expression régulière.")
        replacements_hint.setProperty("muted", True)
        replacements_hint.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Entendu", "Écrire"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for heard, written in (r for r in settings.replacements if len(r) >= 2):
            self._add_row(heard, written)
        add_button = QPushButton("Ajouter")
        add_button.clicked.connect(lambda: self._add_row("", "", edit=True))
        remove_button = QPushButton("Supprimer")
        remove_button.clicked.connect(self._remove_rows)
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(add_button)
        buttons_row.addWidget(remove_button)
        buttons_row.addStretch()

        self.voice_check = QCheckBox("Commandes vocales de ponctuation dans la dictée")
        self.voice_check.setToolTip(
            "« virgule », « point final », « point d'interrogation », « à la ligne », "
            "« nouveau paragraphe », « ouvrez les guillemets »…  (en anglais : comma, full stop, new line…)"
        )
        self.voice_check.setChecked(settings.voice_commands)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(hotwords_title)
        layout.addWidget(hotwords_hint)
        layout.addWidget(self.hotwords_edit, 1)
        layout.addSpacing(10)
        layout.addWidget(replacements_title)
        layout.addWidget(replacements_hint)
        layout.addWidget(self.table, 2)
        layout.addLayout(buttons_row)
        layout.addSpacing(10)
        layout.addWidget(self.voice_check)
        layout.addSpacing(6)
        layout.addWidget(box)

    def _add_row(self, heard: str, written: str, edit: bool = False) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(heard))
        self.table.setItem(row, 1, QTableWidgetItem(written))
        if edit:
            self.table.setCurrentCell(row, 0)
            self.table.editItem(self.table.item(row, 0))

    def _remove_rows(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def replacements(self) -> list[list[str]]:
        rules = []
        for row in range(self.table.rowCount()):
            heard, written = (self.table.item(row, col) for col in (0, 1))
            heard_text = heard.text().strip() if heard else ""
            if heard_text:
                rules.append([heard_text, written.text() if written else ""])
        return rules

    def accept(self) -> None:
        self.settings.hotwords = [w.strip() for w in self.hotwords_edit.toPlainText().splitlines() if w.strip()]
        self.settings.replacements = self.replacements()
        self.settings.voice_commands = self.voice_check.isChecked()
        super().accept()
