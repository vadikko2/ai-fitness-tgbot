from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

from fitness_bot.service.ports.speech_to_text import SpeechToText

logger = logging.getLogger(__name__)


class StubSpeechToText(SpeechToText):
    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        raise NotImplementedError("SpeechToText provider is not configured")


class FakeSpeechToText(SpeechToText):
    """Deterministic adapter for tests — no ASR models required."""

    def __init__(self, transcript: str = "тестовая фраза") -> None:
        self.transcript = transcript
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        self.calls.append((audio, content_type))
        return self.transcript


class SherpaOnnxSpeechToText(SpeechToText):
    """Offline ASR via sherpa-onnx (zipformer transducer). Defaults suit Russian models."""

    def __init__(
        self,
        *,
        model_dir: str | Path,
        encoder: str = "encoder.int8.onnx",
        decoder: str = "decoder.int8.onnx",
        joiner: str = "joiner.int8.onnx",
        tokens: str = "tokens.txt",
        num_threads: int = 1,
        sample_rate: int = 16_000,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._encoder = self._model_dir / encoder
        self._decoder = self._model_dir / decoder
        self._joiner = self._model_dir / joiner
        self._tokens = self._model_dir / tokens
        # The Apps env may still request more threads; this process runs on one core.
        if num_threads != 1:
            logger.info("clamping sherpa ONNX threads from %s to 1", num_threads)
        self._num_threads = 1
        self._sample_rate = sample_rate
        self._recognizer = None
        self._load_lock = asyncio.Lock()
        # One voice at a time. Two concurrent decodes would each take num_threads cores.
        self._infer_lock = asyncio.Lock()

    def _load_recognizer(self):
        missing = [
            path.name for path in (self._encoder, self._decoder, self._joiner, self._tokens) if not path.is_file()
        ]
        if missing:
            names = ", ".join(missing)
            raise FileNotFoundError(
                f"Sherpa-onnx model files missing under {self._model_dir}: {names}. "
                "Run `make download-stt-model` and set SHERPA_MODEL_DIR (see example.env).",
            )
        import sherpa_onnx

        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(self._encoder),
            decoder=str(self._decoder),
            joiner=str(self._joiner),
            tokens=str(self._tokens),
            num_threads=self._num_threads,
            sample_rate=self._sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
        )

    async def _get_recognizer(self):
        if self._recognizer is not None:
            return self._recognizer
        async with self._load_lock:
            if self._recognizer is None:
                self._recognizer = await asyncio.to_thread(self._load_recognizer)
        return self._recognizer

    @staticmethod
    def _audio_to_float32_mono(audio: bytes, *, sample_rate: int) -> tuple[np.ndarray, int]:
        """Decode Telegram OGG/Opus (or other ffmpeg formats) to mono float32 PCM."""
        if not audio:
            raise ValueError("empty audio payload")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError(
                "ffmpeg is required to decode Telegram voice messages. "
                "Install ffmpeg or use the docker/dev image which includes it.",
            )
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "pipe:1",
            ],
            input=audio,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
            raise ValueError(f"failed to decode audio via ffmpeg: {detail or 'unknown error'}")
        samples = np.frombuffer(result.stdout, dtype=np.float32).copy()
        if samples.size == 0:
            raise ValueError("decoded audio is empty")
        return samples, sample_rate

    def _recognize_sync(self, recognizer, samples: np.ndarray, sample_rate: int) -> str:
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        recognizer.decode_stream(stream)
        text = (stream.result.text or "").strip()
        return text

    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        _ = content_type  # Telegram voice is typically audio/ogg; ffmpeg sniffs the container.
        async with self._infer_lock:
            samples, rate = await asyncio.to_thread(
                self._audio_to_float32_mono,
                audio,
                sample_rate=self._sample_rate,
            )
            recognizer = await self._get_recognizer()
            return await asyncio.to_thread(self._recognize_sync, recognizer, samples, rate)


def build_speech_to_text(
    *,
    model_dir: str,
    encoder: str,
    decoder: str,
    joiner: str,
    tokens: str,
    num_threads: int,
    sample_rate: int,
) -> SpeechToText:
    if not model_dir.strip():
        logger.info("SHERPA_MODEL_DIR is empty; using StubSpeechToText")
        return StubSpeechToText()
    return SherpaOnnxSpeechToText(
        model_dir=model_dir.strip(),
        encoder=encoder.strip() or "encoder.int8.onnx",
        decoder=decoder.strip() or "decoder.int8.onnx",
        joiner=joiner.strip() or "joiner.int8.onnx",
        tokens=tokens.strip() or "tokens.txt",
        num_threads=num_threads,
        sample_rate=sample_rate,
    )
