"""Audio player under the transcript: play/pause, 5 s back, position, speed."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QToolButton

from doyoucopy.session import clock
from doyoucopy.ui import theme
from doyoucopy.ui.theme import Tokens

SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
BACK_S = 5.0


class PlayerBar(QFrame):
    position_changed = Signal(float)  # seconds, while playing or after a seek
    playing_changed = Signal(bool)

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self._t = tokens
        self.path: Path | None = None
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)

        self.play_button = QToolButton()
        self.play_button.setObjectName("IconButton")
        self.play_button.setToolTip("Lecture / pause (Ctrl+Espace)")
        self.play_button.clicked.connect(self.toggle)
        self.back_button = QToolButton()
        self.back_button.setObjectName("IconButton")
        self.back_button.setToolTip("Reculer de 5 s (Ctrl+←)")
        self.back_button.clicked.connect(self.back)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda ms: self.player.setPosition(ms))
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("mono", True)
        self.speed_combo = QComboBox()
        for speed in SPEEDS:
            self.speed_combo.addItem(f"{speed:g}×".replace(".", ","), speed)
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.speed_combo.setToolTip("Vitesse de lecture")
        self.speed_combo.currentIndexChanged.connect(
            lambda _: self.player.setPlaybackRate(self.speed_combo.currentData())
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)
        row.addWidget(self.back_button)
        row.addWidget(self.play_button)
        row.addWidget(self.slider, 1)
        row.addWidget(self.time_label)
        row.addWidget(self.speed_combo)
        self.set_tokens(tokens)
        self.hide()

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        self.back_button.setIcon(theme.icon("ph.arrow-counter-clockwise", tokens))
        self.back_button.setIconSize(QSize(17, 17))
        self._update_play_icon()

    # ---- control -------------------------------------------------------

    def load(self, path: Path | None) -> None:
        """The audio of the current transcript; None hides the player."""
        if path == self.path:
            self.setVisible(path is not None)
            return
        self.player.stop()
        self.path = path
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())
        self.slider.setValue(0)
        self.setVisible(path is not None)

    @property
    def playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle(self) -> None:
        if self.path is None:
            return
        if self.playing:
            self.player.pause()
        else:
            self.player.play()

    def back(self) -> None:
        self.seek(max(0.0, self.position() - BACK_S))

    def seek(self, seconds: float, play: bool = False) -> None:
        if self.path is None:
            return
        self.player.setPosition(int(seconds * 1000))
        self.position_changed.emit(seconds)
        if play and not self.playing:
            self.player.play()

    def position(self) -> float:
        return self.player.position() / 1000

    def stop(self) -> None:
        self.player.stop()

    # ---- player callbacks ------------------------------------------------

    def _on_position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{clock(ms / 1000)} / {clock(self.player.duration() / 1000)}")
        self.position_changed.emit(ms / 1000)

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, ms)
        self.time_label.setText(f"{clock(self.player.position() / 1000)} / {clock(ms / 1000)}")

    def _on_state(self, _state) -> None:
        self._update_play_icon()
        self.playing_changed.emit(self.playing)

    def _on_error(self, _error, message: str) -> None:
        self.time_label.setText("Audio illisible")
        self.time_label.setToolTip(message)

    def _update_play_icon(self) -> None:
        name = "ph.pause-fill" if self.playing else "ph.play-fill"
        self.play_button.setIcon(theme.icon(name, self._t))
        self.play_button.setIconSize(QSize(17, 17))
