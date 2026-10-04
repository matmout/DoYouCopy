"""Universal dictation: hotkey -> microphone -> transcription -> text in the active app."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from mywhisper.audio.recorder import MicRecorder
from mywhisper.config import Settings
from mywhisper.core.textproc import postprocess
from mywhisper.core.types import SAMPLE_RATE, TranscribeOptions
from mywhisper.dictation import inject, sounds

log = logging.getLogger(__name__)

MIN_RECORDING_S = 0.3

IDLE, RECORDING, TRANSCRIBING = "idle", "recording", "transcribing"


class DictationController(QObject):
    """State machine idle -> recording -> transcribing -> idle.

    Collaborators are injected so the whole cycle runs in tests without a keyboard
    hook, a microphone or a GPU.
    """

    state_changed = Signal(str)
    dictated = Signal(str)  # final text, after post-processing

    def __init__(
        self,
        settings: Settings,
        worker,
        hook=None,
        overlay=None,
        recorder: MicRecorder | None = None,
        paster: inject.Paster | None = None,
        is_app_busy: Callable[[], bool] = lambda: False,
        play_sound: Callable = sounds.play,
        foreground_is_own: Callable[[], bool] = inject.foreground_is_own_process,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.worker = worker
        self.hook = hook
        self.overlay = overlay
        self.recorder = recorder or MicRecorder(settings.input_device)
        self.paster = paster or inject.Paster(self)
        self.is_app_busy = is_app_busy
        self.play_sound = play_sound
        self.foreground_is_own = foreground_is_own
        self.state = IDLE
        self._job = 0

        if hook is not None:
            hook.pressed.connect(self.on_pressed)
            hook.released.connect(self.on_released)
            hook.escape.connect(self.cancel)
        worker.dictation_finished.connect(self._on_finished)
        worker.dictation_failed.connect(self._on_failed)

    # ---- hotkey --------------------------------------------------------

    def on_pressed(self) -> None:
        if not self.settings.dictation_enabled:
            return
        if self.state == IDLE:
            self.start()
        elif self.state == RECORDING and self.settings.dictation_mode == "toggle":
            self.stop()

    def on_released(self) -> None:
        if self.state == RECORDING and self.settings.dictation_mode == "hold":
            self.stop()

    # ---- cycle ---------------------------------------------------------

    def start(self) -> None:
        if self.state != IDLE:
            return
        if self.is_app_busy():
            self._message("MyWhisper est occupé", error=True)
            return
        self.recorder.device_name = self.settings.input_device
        try:
            self.recorder.start()
        except Exception as exc:
            log.exception("Microphone start failed")
            self._message(f"Micro indisponible : {exc}", error=True)
            return
        self._set_state(RECORDING)
        self._sound(sounds.START)
        if self.overlay is not None:
            self.overlay.show_listening(lambda: self.recorder.level)

    def stop(self) -> None:
        if self.state != RECORDING:
            return
        audio = self.recorder.stop()
        self._sound(sounds.STOP)
        if audio.size < MIN_RECORDING_S * SAMPLE_RATE:
            self._set_state(IDLE)
            self._message("Trop court")
            return
        self._job += 1
        self._set_state(TRANSCRIBING)
        if self.overlay is not None:
            self.overlay.show_transcribing()
        options = TranscribeOptions(
            language=self.settings.language,
            vad_filter=True,
            hotwords=self.settings.hotwords_prompt(),
        )
        self.worker.dictate(audio, options, self._job)

    def cancel(self) -> None:
        if self.state == RECORDING:
            self.recorder.stop()
        elif self.state != TRANSCRIBING:
            return
        self._job += 1  # a result still on its way will be ignored
        self._set_state(IDLE)
        self._message("Dictée annulée")

    # ---- results -------------------------------------------------------

    def _on_finished(self, job: int, text: str, language: str) -> None:
        if job != self._job or self.state != TRANSCRIBING:
            return
        self._set_state(IDLE)
        text = postprocess(
            text, language, self.settings.replacements, voice_commands=self.settings.voice_commands
        )
        if not text:
            self._message("Rien entendu")
            return
        if self.settings.dictation_output == "paste" and not self.foreground_is_own():
            self.paster.paste(text)
            self._message("Texte inséré")
        else:
            self.paster.copy(text)
            self._message("Copié dans le presse-papiers")
        self.dictated.emit(text)

    def _on_failed(self, job: int, message: str) -> None:
        if job != self._job:
            return
        self._set_state(IDLE)
        self._message(message, error=True)

    # ---- helpers -------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self.state = state
        if self.hook is not None:
            self.hook.set_escape_armed(state != IDLE)
        self.state_changed.emit(state)

    def _message(self, text: str, error: bool = False) -> None:
        if self.overlay is not None:
            self.overlay.show_message(text, error=error)

    def _sound(self, samples) -> None:
        if self.settings.dictation_sounds:
            self.play_sound(samples)

    def shutdown(self) -> None:
        if self.state == RECORDING:
            self.recorder.stop()
        self.state = IDLE
        if self.hook is not None:
            self.hook.uninstall()
        if self.overlay is not None:
            self.overlay.dismiss()
