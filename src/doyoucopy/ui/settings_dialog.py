"""All the settings, by section. Every change is written to Settings at once and
reported with `changed(name)`; the main window applies what needs applying
(theme, model reload, hotkey…)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from doyoucopy import export, i18n
from doyoucopy.config import Settings
from doyoucopy.core import model_download
from doyoucopy.core.models import MODELS
from doyoucopy.desktop import packaging, shortcuts
from doyoucopy.dictation import autostart
from doyoucopy.dictation.hotkey import parse_hotkey
from doyoucopy.gpu import rocm_env
from doyoucopy.i18n import N_, number, tr
from doyoucopy.ui.widgets.segmented import SegmentedControl

LANGUAGES = [
    (None, N_("Détection automatique")),
    ("fr", N_("Français")),
    ("en", N_("Anglais")),
    ("de", N_("Allemand")),
    ("es", N_("Espagnol")),
    ("it", N_("Italien")),
    ("pt", N_("Portugais")),
    ("nl", N_("Néerlandais")),
    ("pl", N_("Polonais")),
    ("ru", N_("Russe")),
    ("ar", N_("Arabe")),
    ("zh", N_("Chinois")),
    ("ja", N_("Japonais")),
]
COMPUTE_LABELS = {
    "auto": N_("Automatique"),
    "float16": N_("float16 : précision complète (recommandé sur GPU)"),
    "bfloat16": N_("bfloat16 : précision complète"),
    "int8_float16": N_("int8_float16 : moins de mémoire vidéo"),
    "int8": N_("int8 : le plus léger (recommandé sur processeur)"),
    "int8_float32": "int8_float32",
    "float32": N_("float32 : le plus lent, référence"),
}
PAGES = (
    N_("Général"),
    N_("Transcription"),
    N_("Silences"),
    N_("Dictée"),
    N_("Mode Direct"),
    N_("Exports"),
    N_("Historique"),
    N_("Modèles"),
    N_("Matériel"),
)


class SettingsDialog(QDialog):
    changed = Signal(str)  # name of the Settings field that changed
    vocabulary_requested = Signal()
    install_runtime_requested = Signal()
    reset_requested = Signal()
    history_clear_requested = Signal()
    restart_requested = Signal()  # to apply a new interface language

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        microphones: list[str] | None = None,
        device_description: str = "",
        hardware_status: Callable[[], tuple[str, bool]] | None = None,
        hook=None,
        history_dir: Path | None = None,
        diagnostics: Callable[[], str] | None = None,
        logs_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.hook = hook
        self._history_dir = history_dir
        self._diagnostics = diagnostics
        self._logs_dir = logs_dir
        self._microphones = microphones or []
        self._device_description = device_description
        self._hardware_status = hardware_status or (lambda: ("", False))
        self.setWindowTitle(tr("Réglages"))
        self.resize(780, 600)
        self.setMinimumSize(680, 480)

        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(170)
        self.pages = QStackedWidget()
        for title, build in zip(  # noqa: B905 (one builder per page title)
            PAGES,
            (
                self._general,
                self._transcription,
                self._silences,
                self._dictation,
                self._live,
                self._exports,
                self._history,
                self._models,
                self._hardware,
            ),
        ):
            self.nav.addItem(tr(title))
            self.pages.addWidget(self._page(tr(title), build))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        close = QPushButton(tr("Fermer"))
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(close)
        right = QVBoxLayout()
        right.addWidget(self.pages, 1)
        right.addLayout(footer)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(16)
        layout.addWidget(self.nav)
        layout.addLayout(right, 1)

    def show_page(self, title: str) -> None:
        self.nav.setCurrentRow(PAGES.index(title))

    # ---- helpers -------------------------------------------------------

    def _page(self, title: str, build: Callable[[QVBoxLayout], None]) -> QScrollArea:
        content = QWidget()
        content.setObjectName("SettingsPage")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 0, 12, 12)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("SettingsTitle")
        layout.addWidget(heading)
        build(layout)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section(layout: QVBoxLayout, title: str) -> QFormLayout:
        label = QLabel(title.upper())
        label.setObjectName("SettingsSection")
        layout.addSpacing(10)
        layout.addWidget(label)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        return form

    @staticmethod
    def _hint(text: str, warning: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SettingsWarning" if warning else "SettingsHint")
        label.setWordWrap(True)
        return label

    def _set(self, name: str, value) -> None:
        if getattr(self.settings, name) == value:
            return
        setattr(self.settings, name, value)
        self.changed.emit(name)

    def _check(self, name: str, text: str, tooltip: str = "") -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(bool(getattr(self.settings, name)))
        box.setToolTip(tooltip)
        box.toggled.connect(lambda value: self._set(name, value))
        setattr(self, f"{name}_check", box)
        return box

    def _combo(self, name: str, items: list[tuple[object, str]]) -> QComboBox:
        combo = QComboBox()
        for value, label in items:
            combo.addItem(label, value)
        combo.setCurrentIndex(max(0, combo.findData(getattr(self.settings, name))))
        combo.currentIndexChanged.connect(lambda _: self._set(name, combo.currentData()))
        setattr(self, f"{name}_combo", combo)
        return combo

    def _spin(self, name: str, low, high, step, suffix: str = "", decimals: int = 0) -> QSpinBox:
        spin = QDoubleSpinBox() if decimals else QSpinBox()
        if decimals:
            spin.setDecimals(decimals)
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setValue(getattr(self.settings, name))
        spin.valueChanged.connect(lambda value: self._set(name, value))
        setattr(self, f"{name}_spin", spin)
        return spin

    # ---- pages ---------------------------------------------------------

    def _general(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Apparence"))
        themes = SegmentedControl([("auto", tr("Système")), ("dark", tr("Sombre")), ("light", tr("Clair"))])
        themes.set_value(self.settings.theme)
        themes.changed.connect(lambda value: self._set("theme", value))
        self.theme_control = themes
        form.addRow(tr("Thème"), themes)
        form.addRow(tr("Taille du texte"), self._spin("transcript_font_size", 9, 24, 1, " pt"))
        form.addRow("", self._check("show_timestamps", tr("Afficher l'horodatage de chaque segment")))
        self._interface_language(form)

        form = self._section(layout, tr("Micro"))
        mic = QComboBox()
        mic.addItem(tr("Micro par défaut de Windows"), None)
        for name in self._microphones:
            mic.addItem(name, name)
        mic.setCurrentIndex(max(0, mic.findData(self.settings.input_device)))
        mic.currentIndexChanged.connect(lambda _: self._set("input_device", mic.currentData()))
        self.input_device_combo = mic
        form.addRow(tr("Entrée"), mic)

        form = self._section(layout, tr("Démarrage"))
        form.addRow("", self._check("close_to_tray", tr("Rester dans la zone de notification à la fermeture")))
        startup = QCheckBox(tr("Démarrer avec Windows (dans la zone de notification)"))
        startup.setChecked(autostart.is_enabled())
        startup.toggled.connect(self._autostart_toggled)
        self.autostart_check = startup
        form.addRow("", startup)

        # Not settings: the state is the files themselves, also created by the installer.
        # The Microsoft Store package has its own Start menu entry, and writes no .lnk.
        self.shortcut_checks: dict[str, QCheckBox] = {}
        kinds = () if packaging.is_packaged() else ((shortcuts.DESKTOP, tr("Sur le Bureau")), (shortcuts.START_MENU, tr("Dans le menu Démarrer")))
        if kinds:
            form = self._section(layout, tr("Raccourcis"))
        for kind, label in kinds:
            check = QCheckBox(label)
            check.setChecked(shortcuts.exists(kind))
            check.setEnabled(shortcuts.available())
            check.setToolTip(shortcuts.describe(kind))
            check.toggled.connect(lambda enabled, kind=kind: self._shortcut_toggled(kind, enabled))
            self.shortcut_checks[kind] = check
            form.addRow("", check)

        reset = QPushButton(tr("Rétablir les réglages par défaut…"))
        reset.clicked.connect(self._confirm_reset)
        layout.addSpacing(16)
        layout.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)

    def _interface_language(self, form: QFormLayout) -> None:
        """Applied at the next start: every window would have to be rebuilt otherwise."""
        # Each language in its own name, so that it can be found whatever the current one.
        combo = self._combo("ui_language", [("auto", tr("Système")), *i18n.CHOICES[1:]])
        form.addRow(tr("Langue de l'interface"), combo)
        self.restart_hint = self._hint(tr("La nouvelle langue s'appliquera au prochain démarrage de DoYouCopy."))
        restart = QPushButton(tr("Redémarrer maintenant"))
        restart.clicked.connect(self.restart_requested)
        self.restart_button = restart
        form.addRow("", self.restart_hint)
        form.addRow("", restart)
        combo.currentIndexChanged.connect(lambda _: self._update_restart_hint())
        self._update_restart_hint()

    def _update_restart_hint(self) -> None:
        pending = i18n.resolve(self.settings.ui_language) != i18n.language()
        self.restart_hint.setVisible(pending)
        self.restart_button.setVisible(pending)

    def _transcription(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Langue"))
        form.addRow(tr("Langue parlée"), self._combo("language", [(code, tr(name)) for code, name in LANGUAGES]))
        form.addRow(
            "",
            self._check(
                "multilingual",
                tr("Plusieurs langues dans le même audio"),
                tr("La langue est redétectée à chaque segment (réunions bilingues, citations)."),
            ),
        )
        task = self._combo("task", [("transcribe", tr("Transcrire dans la langue parlée")), ("translate", tr("Traduire en anglais"))])
        form.addRow(tr("Résultat"), task)
        self.translate_warning = self._hint(
            tr("Le modèle Turbo n'a pas été entraîné pour traduire : choisissez le modèle Précis."), warning=True
        )
        form.addRow("", self.translate_warning)
        task.currentIndexChanged.connect(lambda _: self._update_translate_warning())
        self._update_translate_warning()

        form = self._section(layout, tr("Contexte et vocabulaire"))
        prompt = QPlainTextEdit(self.settings.initial_prompt)
        prompt.setPlaceholderText(tr("Ex. : Réunion de l'équipe produit sur DoYouCopy, avec Claire et Karim."))
        prompt.setFixedHeight(72)
        prompt.textChanged.connect(lambda: self._set("initial_prompt", prompt.toPlainText()))
        self.initial_prompt_edit = prompt
        form.addRow(tr("Contexte"), prompt)
        form.addRow("", self._hint(tr("Le sujet, des noms, un style d'écriture : le modèle s'en inspire.")))
        vocabulary = QPushButton(tr("Mots à favoriser et remplacements…"))
        vocabulary.clicked.connect(self.vocabulary_requested)
        form.addRow("", vocabulary)

        form = self._section(layout, tr("Qualité et vitesse"))
        form.addRow(
            tr("Recherche"),
            self._combo(
                "beam_size",
                [(0, tr("Selon le modèle")), (1, tr("Rapide (1 hypothèse)")), (3, tr("Équilibrée (3)")), (5, tr("Précise (5)")), (8, tr("Maximale (8)"))],
            ),
        )
        form.addRow(
            tr("Texte précédent"),
            self._combo(
                "condition_previous",
                [("auto", tr("Selon le modèle")), ("on", tr("Utilisé comme contexte")), ("off", tr("Ignoré (évite les boucles)"))],
            ),
        )
        form.addRow(
            tr("Fichiers"),
            self._combo("batch_size", [(0, tr("Segment par segment")), (8, tr("Par lots de 8 (GPU)")), (16, tr("Par lots de 16 (GPU)"))]),
        )
        form.addRow(
            "",
            self._hint(
                tr(
                    "Par lots : jusqu'à 3 à 4 fois plus rapide sur une carte graphique, le texte arrive par blocs. "
                    "Nécessite le filtre des silences."
                )
            ),
        )

    def _update_translate_warning(self) -> None:
        self.translate_warning.setVisible(self.settings.task == "translate" and self.settings.model_key == "turbo")

    def _silences(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Filtre des silences (VAD)"))
        form.addRow("", self._check("vad_filter", tr("Ignorer les silences (fichiers et enregistrements)")))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(20, 80)
        slider.setValue(round(self.settings.vad_threshold * 100))
        value = QLabel(f"{self.settings.vad_threshold:.2f}")
        value.setProperty("mono", True)

        def on_slide(position: int) -> None:
            value.setText(f"{position / 100:.2f}")
            self._set("vad_threshold", position / 100)

        slider.valueChanged.connect(on_slide)
        self.vad_slider = slider
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel(tr("Sensible")))
        row.addWidget(slider, 1)
        row.addWidget(QLabel(tr("Strict")))
        row.addWidget(value)
        form.addRow(tr("Détection de la voix"), row)
        form.addRow(tr("Pause minimale"), self._spin("vad_min_silence_ms", 100, 3000, 100, " ms"))
        form.addRow("", self._hint(tr("Seuil bas : capte les voix faibles mais aussi du bruit. Seuil haut : ignore les murmures.")))

        form = self._section(layout, tr("Hallucinations"))
        form.addRow(
            "",
            self._check(
                "skip_silence_hallucinations",
                tr("Supprimer le texte inventé pendant les longs silences"),
                tr("Whisper « invente » parfois des phrases (« Merci d'avoir regardé ») sur du silence."),
            ),
        )
        form.addRow(tr("Seuil « pas de parole »"), self._spin("no_speech_threshold", 0.3, 0.95, 0.05, decimals=2))
        form.addRow(tr("Pénalité de répétition"), self._spin("repetition_penalty", 1.0, 1.5, 0.05, decimals=2))
        form.addRow("", self._hint(tr("Au-dessus de 1, le modèle répète moins les mêmes mots en boucle.")))

    def _dictation(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Raccourci"))
        hotkey = QKeySequenceEdit(QKeySequence.fromString(self.settings.dictation_hotkey))
        hotkey.setMaximumSequenceLength(1)
        for line in hotkey.findChildren(QLineEdit):
            line.setPlaceholderText(tr("Appuyez sur un raccourci"))
        hotkey.editingFinished.connect(self._hotkey_edited)
        self.hotkey_edit = hotkey
        form.addRow(tr("Raccourci"), hotkey)
        self.hotkey_error = self._hint("", warning=True)
        self.hotkey_error.hide()
        form.addRow("", self.hotkey_error)
        modes = SegmentedControl([("hold", tr("Maintenir")), ("toggle", tr("Basculer"))])
        modes.set_value(self.settings.dictation_mode)
        modes.changed.connect(lambda value: self._set("dictation_mode", value))
        self.dictation_mode_control = modes
        form.addRow(tr("Mode"), modes)
        form.addRow("", self._check("dictation_enabled", tr("Dictée active")))

        form = self._section(layout, tr("Texte dicté"))
        form.addRow(
            tr("Sortie"),
            self._combo("dictation_output", [("paste", tr("Coller dans l'application active")), ("clipboard", tr("Copier seulement"))]),
        )
        form.addRow("", self._check("dictation_trailing_space", tr("Ajouter un espace après le texte")))
        form.addRow("", self._check("voice_commands", tr("Commandes vocales de ponctuation (« virgule », « à la ligne »…)")))
        form.addRow("", self._check("dictation_sounds", tr("Signal sonore au début et à la fin")))

    def _hotkey_edited(self) -> None:
        text = self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not text:
            return
        try:
            hotkey = parse_hotkey(text)
        except ValueError as exc:
            self.hotkey_error.setText(str(exc))
            self.hotkey_error.show()
            self.hotkey_edit.setKeySequence(QKeySequence.fromString(self.settings.dictation_hotkey))
            return
        self.hotkey_error.hide()
        self._set("dictation_hotkey", hotkey.text)

    def _live(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Réactivité"))
        form.addRow(tr("Intervalle entre passes"), self._spin("live_step_s", 0.5, 3.0, 0.25, " s", decimals=2))
        form.addRow(tr("Silence de fin de phrase"), self._spin("live_endpoint_s", 0.4, 2.0, 0.1, " s", decimals=1))
        form.addRow(
            "",
            self._hint(
                tr(
                    "Intervalle court : texte plus réactif, mais davantage de calcul (à éviter sur processeur). "
                    "Silence de fin court : les phrases sont validées plus tôt."
                )
            ),
        )

    def _exports(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Export rapide (Ctrl+S)"))
        form.addRow(
            tr("Format"), self._combo("default_export", [(e.suffix, f"{tr(e.label)} ({e.suffix})") for e in export.exporters()])
        )
        form = self._section(layout, tr("Sous-titres (SRT, WebVTT)"))
        form.addRow(tr("Caractères par ligne"), self._spin("subtitle_max_chars", 20, 80, 1))
        form.addRow(tr("Lignes par sous-titre"), self._spin("subtitle_max_lines", 1, 3, 1))
        form.addRow("", self._hint(tr("Norme habituelle : 42 caractères, 2 lignes. Réseaux sociaux verticaux : 20 à 30, 1 ligne.")))

    def _history(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Enregistrement automatique"))
        form.addRow("", self._check("history_enabled", tr("Garder chaque transcription dans l'historique")))
        form.addRow(
            "",
            self._check(
                "history_dictation",
                tr("Garder aussi le texte des dictées (raccourci global)"),
                tr("Retrouvez vos dictées dans l'historique, marquées « Dictée »."),
            ),
        )
        form = self._section(layout, tr("Audio"))
        form.addRow(
            "",
            self._check(
                "history_keep_audio",
                tr("Conserver l'audio des enregistrements (micro et Direct)"),
                tr("Pour réécouter un passage ou le retranscrire avec un autre modèle. FLAC, environ 60 Mo par heure."),
            ),
        )
        days = self._spin("history_audio_days", 0, 3650, 1, tr(" jours"))
        days.setSpecialValueText(tr("Jamais"))
        form.addRow(tr("Supprimer l'audio après"), days)
        form.addRow("", self._hint(tr("Le texte est toujours conservé. Les fichiers importés ne sont pas copiés.")))

        form = self._section(layout, tr("Données"))
        if self._history_dir is not None:
            folder = QPushButton(tr("Ouvrir le dossier"))
            folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(packaging.real_path(self._history_dir)))))
            form.addRow("", folder)
        erase = QPushButton(tr("Tout effacer…"))
        erase.clicked.connect(self._confirm_history_clear)
        erase.setEnabled(self._history_dir is not None)
        self.history_clear_button = erase
        form.addRow("", erase)
        form.addRow("", self._hint(tr("Tout reste sur ce PC, dans votre profil Windows.")))

    def _confirm_history_clear(self) -> None:
        answer = QMessageBox.question(
            self, tr("Effacer l'historique"), tr("Effacer toutes les transcriptions et leur audio ? C'est définitif.")
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history_clear_requested.emit()

    def _models(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Modèle utilisé"))
        model = self._combo("model_key", [(k, tr("{model} · {size} Go").format(model=tr(s.label), size=number(s.size_gb))) for k, s in MODELS.items()])
        model.currentIndexChanged.connect(lambda _: self._update_translate_warning())
        form.addRow(tr("Modèle"), model)
        self.model_description = self._hint("")
        form.addRow("", self.model_description)
        model.currentIndexChanged.connect(lambda _: self._describe_model())
        self._describe_model()

        form = self._section(layout, tr("Modèles téléchargés"))
        self.models_box = QVBoxLayout()
        form.addRow(self.models_box)
        self._refresh_models()

        form = self._section(layout, tr("Emplacement"))
        folder = QLineEdit(self.settings.models_dir)
        folder.setReadOnly(True)
        self.models_dir_edit = folder
        browse = QPushButton(tr("Changer…"))
        browse.clicked.connect(self._choose_models_dir)
        row = QHBoxLayout()
        row.addWidget(folder, 1)
        row.addWidget(browse)
        form.addRow(tr("Dossier"), row)
        form.addRow(
            "",
            self._check(
                "allow_download",
                tr("Télécharger automatiquement un modèle manquant"),
                tr("Désactivé : DoYouCopy n'accède jamais au réseau (mode hors ligne strict)."),
            ),
        )

    def _describe_model(self) -> None:
        spec = MODELS.get(self.settings.model_key)
        self.model_description.setText(tr(spec.description) if spec else "")

    def _refresh_models(self) -> None:
        _clear_layout(self.models_box)
        models_dir = Path(self.settings.models_dir)
        for key, spec in MODELS.items():
            size = model_download.installed_size(models_dir, spec.model_name)
            status = tr("{size} Go sur le disque").format(size=number(size / 1e9)) if size else tr("Non téléchargé")
            row = QHBoxLayout()
            name = QLabel(tr(spec.label))
            state = QLabel(status)
            state.setObjectName("SettingsHint")
            row.addWidget(name, 1)
            row.addWidget(state)
            if size:
                delete = QPushButton(tr("Supprimer"))
                delete.setEnabled(key != self.settings.model_key)
                delete.setToolTip(tr("Le modèle utilisé ne peut pas être supprimé.") if key == self.settings.model_key else "")
                delete.clicked.connect(lambda _=False, s=spec: self._delete_model(s))
                row.addWidget(delete)
            self.models_box.addLayout(row)

    def _delete_model(self, spec) -> None:
        answer = QMessageBox.question(
            self,
            tr("Supprimer le modèle"),
            tr("Supprimer {model} ? Il sera retéléchargé si vous le choisissez à nouveau.").format(model=tr(spec.label)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            model_download.discard(Path(self.settings.models_dir), spec.model_name)
            self._refresh_models()

    def _choose_models_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Dossier des modèles"), self.settings.models_dir)
        if folder:
            self.models_dir_edit.setText(str(Path(folder)))
            self._set("models_dir", str(Path(folder)))
            self._refresh_models()

    def _hardware(self, layout: QVBoxLayout) -> None:
        form = self._section(layout, tr("Calcul"))
        devices = SegmentedControl([("auto", tr("Automatique")), ("gpu", tr("Carte graphique")), ("cpu", tr("Processeur"))])
        devices.set_value(self.settings.device)
        devices.changed.connect(self._device_changed)
        self.device_control = devices
        form.addRow(tr("Calculer sur"), devices)
        self.compute_combo = QComboBox()
        self.compute_combo.currentIndexChanged.connect(
            lambda _: self.compute_combo.currentData() and self._set("compute_type", self.compute_combo.currentData())
        )
        form.addRow(tr("Précision"), self.compute_combo)
        threads = self._spin("cpu_threads", 0, os.cpu_count() or 64, 1)
        threads.setSpecialValueText(tr("Automatique"))
        form.addRow(tr("Threads processeur"), threads)
        form.addRow(
            "",
            self._hint(
                tr(
                    "Appliqué tout de suite : le modèle est rechargé (quelques secondes), "
                    "après la transcription en cours s'il y en a une."
                )
            ),
        )
        self._fill_compute_types()

        form = self._section(layout, tr("État"))
        self.device_label = QLabel(self._device_description)
        self.device_label.setProperty("mono", True)
        form.addRow(tr("Utilisé"), self.device_label)
        status, can_install = self._hardware_status()
        self.hardware_label = self._hint(status)
        form.addRow(tr("Carte"), self.hardware_label)
        self.install_button = QPushButton(tr("Installer l'accélération graphique…"))
        self.install_button.clicked.connect(self.install_runtime_requested)
        self.install_button.setVisible(can_install)
        form.addRow("", self.install_button)

        form = self._section(layout, tr("Diagnostic"))
        copy = QPushButton(tr("Copier les informations de diagnostic"))
        copy.clicked.connect(self._copy_diagnostics)
        copy.setEnabled(self._diagnostics is not None)
        self.diagnostics_button = copy
        logs = QPushButton(tr("Ouvrir le dossier des journaux"))
        logs.clicked.connect(self._open_logs)
        logs.setEnabled(self._logs_dir is not None)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(logs)
        row.addStretch()
        form.addRow(row)
        self.diagnostics_status = self._hint(
            tr(
                "Machine, carte graphique, versions, réglages et dernières erreurs, à joindre à un signalement. "
                "Aucune transcription ni aucun mot du vocabulaire n'y figure : relisez-le avant de l'envoyer."
            )
        )
        form.addRow(self.diagnostics_status)

    def _device_changed(self, value: str) -> None:
        self._set("device", value)
        self._fill_compute_types()

    def _fill_compute_types(self) -> None:
        device = "cpu" if self.settings.device == "cpu" else "cuda"
        types = rocm_env.supported_compute_types(device) or rocm_env.supported_compute_types("cpu")
        combo = self.compute_combo
        combo.blockSignals(True)
        combo.clear()
        for value in ("auto", *types):
            combo.addItem(tr(COMPUTE_LABELS.get(value, value)), value)
        index = combo.findData(self.settings.compute_type)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)
        if index < 0 and self.settings.compute_type != "auto":
            self._set("compute_type", "auto")

    def set_device_description(self, text: str) -> None:
        self._device_description = text
        self.device_label.setText(text)

    def set_device_description_from_load(self, _key: str, description: str) -> None:
        self.set_device_description(description)

    def _copy_diagnostics(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            text = self._diagnostics()
        finally:
            QApplication.restoreOverrideCursor()
        QGuiApplication.clipboard().setText(text)
        self.diagnostics_button.setText(tr("Copié dans le presse-papiers ✓"))

    def _open_logs(self) -> None:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(packaging.real_path(self._logs_dir))))

    # ---- general actions -------------------------------------------------

    def _autostart_toggled(self, enabled: bool) -> None:
        if not autostart.set_enabled(enabled):
            self._revert(self.autostart_check, enabled)
            message = tr("Impossible de modifier le démarrage automatique.")
            if enabled and packaging.is_packaged():
                message += tr(" Vérifiez qu'il n'est pas désactivé dans Paramètres Windows > Applications > Démarrage.")
            QMessageBox.warning(self, tr("Démarrage avec Windows"), message)

    def _shortcut_toggled(self, kind: str, enabled: bool) -> None:
        if not shortcuts.set_enabled(kind, enabled):
            self._revert(self.shortcut_checks[kind], enabled)
            if enabled:
                message = tr("Impossible de créer le raccourci dans {place}.")
            else:
                message = tr("Impossible de supprimer le raccourci dans {place}.")
            QMessageBox.warning(self, tr("Raccourci"), message.format(place=shortcuts.describe(kind)))

    @staticmethod
    def _revert(check: QCheckBox, attempted: bool) -> None:
        """The checkbox shows what is really in place, not what was asked."""
        check.blockSignals(True)
        check.setChecked(not attempted)
        check.blockSignals(False)

    def _confirm_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Rétablir les réglages"),
            tr("Rétablir tous les réglages par défaut ? Le vocabulaire et le dossier des modèles sont conservés."),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.reset_requested.emit()
            self.accept()

    def showEvent(self, event) -> None:
        if self.hook is not None:
            self.hook.suspend()  # typing a new shortcut must not trigger the current one
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if self.hook is not None:
            self.hook.resume()
        super().hideEvent(event)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
