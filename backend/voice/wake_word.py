"""
Wake word detection (spec section 10) via `openwakeword` — free, offline,
runs entirely on-device (no audio ever leaves the machine just to check for
the wake word, which only matters once ALWAYS_LISTENING is enabled).

openWakeWord ships a fixed set of pretrained models (e.g. "hey jarvis",
"alexa"); a genuinely custom phrase like the spec's default "Hey Solution"
requires training a small custom model with their provided training
notebook. Until that's trained, `WAKE_WORD` in .env should be set to one of
openWakeWord's built-in phrases (closest available: "hey_jarvis") — this is
called out explicitly in README.md so it's not silently different from what
was configured.
"""

import numpy as np

from backend.core.config import get_settings

_BUILTIN_MODELS = {"hey_jarvis", "alexa", "hey_mycroft"}


class WakeWordDetector:
    def __init__(self):
        settings = get_settings()
        requested = settings.wake_word.lower().replace(" ", "_")
        self._model_name = requested if requested in _BUILTIN_MODELS else "hey_jarvis"
        self._sensitivity = settings.wake_word_sensitivity
        self._model = None

    def _load(self):
        if self._model is None:
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[self._model_name])
        return self._model

    def detect(self, audio_chunk: bytes) -> bool:
        """audio_chunk: 16-bit PCM mono audio at 16kHz, ~80ms frames recommended."""
        model = self._load()
        samples = np.frombuffer(audio_chunk, dtype=np.int16)
        predictions = model.predict(samples)
        score = predictions.get(self._model_name, 0.0)
        return score >= self._sensitivity


wake_word_detector = WakeWordDetector()
