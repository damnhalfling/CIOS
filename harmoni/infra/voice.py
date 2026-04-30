"""Voice Manager — STT (speech-to-text) and TTS (text-to-speech).

STT: whisper.cpp via CLI (local, offline, fast)
TTS: piper via CLI (local, offline, natural)

Both are optional. If not installed, voice features are silently disabled.
The system works identically via text input.

Voice rules:
- voice_mode="full" → speak the summary
- voice_mode="brief" → speak "Pronto. Está na tela."
- Never speak technical commands (ls, grep, nmcli)
- Never read long content aloud
- Short answers (< 100 chars) → speak directly
- Confirmations → speak the question
"""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Brief responses by language
_BRIEF = {
    "pt": "Pronto. Está na tela.",
    "en": "Done. It's on screen.",
}


class VoiceManager:
    """Manages STT and TTS for the Harmoni system."""

    def __init__(self) -> None:
        self._tts_available = self._check_tts()
        self._stt_available = self._check_stt()
        self._speaking = False
        self._listening = False
        self._tts_process: Optional[subprocess.Popen] = None
        self._lang = self._detect_lang()

        if self._tts_available:
            logger.info("TTS available (piper)")
        if self._stt_available:
            logger.info("STT available (whisper)")

    # ═══════════════════════════════════════════════════════════════════════
    #  DETECTION
    # ═══════════════════════════════════════════════════════════════════════

    def _check_tts(self) -> bool:
        """Check if piper TTS is available."""
        return shutil.which("piper") is not None

    def _check_stt(self) -> bool:
        """Check if whisper CLI is available."""
        # Check for whisper.cpp CLI or openai-whisper
        return (shutil.which("whisper-cpp") is not None or
                shutil.which("whisper") is not None)

    def _detect_lang(self) -> str:
        for var in ("LANG", "LC_MESSAGES", "LC_ALL"):
            val = os.environ.get(var, "")
            if val.lower().startswith("pt"):
                return "pt"
        return "en"

    @property
    def tts_available(self) -> bool:
        return self._tts_available

    @property
    def stt_available(self) -> bool:
        return self._stt_available

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    @property
    def is_listening(self) -> bool:
        return self._listening

    # ═══════════════════════════════════════════════════════════════════════
    #  TTS (Text → Speech)
    # ═══════════════════════════════════════════════════════════════════════

    def speak(self, text: str, voice_mode: str = "full") -> None:
        """Speak text asynchronously. Never blocks the UI.

        Args:
            text: the humanized summary to speak
            voice_mode: "full" = speak text, "brief" = speak short confirmation
        """
        if not self._tts_available or not text:
            return

        # Determine what to say
        if voice_mode == "brief":
            to_say = _BRIEF.get(self._lang, _BRIEF["en"])
        else:
            # For full mode, cap at ~150 chars to keep it natural
            to_say = text[:150]
            # Clean up for speech: remove emojis, special chars
            to_say = self._clean_for_speech(to_say)

        if not to_say.strip():
            return

        # Speak in background thread
        threading.Thread(
            target=self._speak_sync, args=(to_say,), daemon=True
        ).start()

    def _speak_sync(self, text: str) -> None:
        """Synchronous TTS execution."""
        self._speaking = True
        try:
            # Stop any current speech
            self.stop_speaking()

            # Use piper for TTS
            # piper reads from stdin and outputs WAV to stdout
            # We pipe it to aplay for playback
            self._tts_process = subprocess.Popen(
                f'echo "{text}" | piper --output-raw | aplay -r 22050 -f S16_LE -c 1 -q',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._tts_process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.stop_speaking()
        except Exception as e:
            logger.debug("TTS failed: %s", e)
        finally:
            self._speaking = False
            self._tts_process = None

    def stop_speaking(self) -> None:
        """Interrupt current speech."""
        if self._tts_process:
            try:
                self._tts_process.terminate()
                self._tts_process.wait(timeout=2)
            except Exception:
                try:
                    self._tts_process.kill()
                except Exception:
                    pass
            self._tts_process = None
        self._speaking = False

    def _clean_for_speech(self, text: str) -> str:
        """Clean text for natural speech output."""
        import re
        # Remove emojis and special symbols
        text = re.sub(r'[⚠✓✗🧹💡→🔇⚡•]', '', text)
        # Remove markdown-like formatting
        text = re.sub(r'[*_`#]', '', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove paths
        text = re.sub(r'/[\w/.-]+', '', text)
        return text

    # ═══════════════════════════════════════════════════════════════════════
    #  STT (Speech → Text)
    # ═══════════════════════════════════════════════════════════════════════

    def listen(self, duration: float = 5.0) -> Optional[str]:
        """Record audio and transcribe to text.

        Args:
            duration: max recording time in seconds

        Returns:
            Transcribed text, or None if failed/empty
        """
        if not self._stt_available:
            return None

        self._listening = True
        try:
            return self._listen_sync(duration)
        finally:
            self._listening = False

    def _listen_sync(self, duration: float) -> Optional[str]:
        """Synchronous STT: record + transcribe."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            # Record audio using arecord
            rec = subprocess.run(
                ["arecord", "-d", str(int(duration)), "-f", "S16_LE",
                 "-r", "16000", "-c", "1", "-q", wav_path],
                timeout=duration + 3,
                capture_output=True,
            )
            if rec.returncode != 0:
                return None

            # Transcribe with whisper
            if shutil.which("whisper-cpp"):
                result = subprocess.run(
                    ["whisper-cpp", "-m",
                     "/usr/share/whisper-cpp/models/ggml-base.bin",
                     "-f", wav_path, "--no-timestamps", "-l", "auto"],
                    capture_output=True, text=True, timeout=30,
                )
            elif shutil.which("whisper"):
                result = subprocess.run(
                    ["whisper", wav_path, "--model", "base",
                     "--language", "auto", "--output_format", "txt"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                return None

            if result.returncode == 0:
                text = result.stdout.strip()
                # Clean whisper output
                text = text.replace("[BLANK_AUDIO]", "").strip()
                return text if text else None

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug("STT failed: %s", e)
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass

        return None

    def listen_async(self, callback, duration: float = 5.0) -> None:
        """Record and transcribe in background, call callback with result.

        Args:
            callback: function(text: Optional[str]) called when done
            duration: max recording time
        """
        def run():
            text = self.listen(duration)
            callback(text)

        threading.Thread(target=run, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════

    def close(self) -> None:
        """Clean up resources."""
        self.stop_speaking()
