#!/usr/bin/env python3
"""
JARVIS - Local AI Voice Assistant
Arch Linux / CachyOS + i3wm
Stack: OpenWakeWord → Whisper.cpp → Ollama → Piper TTS
"""

import os
import sys
import time
import queue
import threading
import subprocess
import signal
import logging
import json
from pathlib import Path

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "logs/jarvis.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("JARVIS")

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config/config.json"

DEFAULT_CONFIG = {
    "wake_word": "hey jarvis",
    "wake_word_threshold": 0.5,
    "whisper_model": "medium",          # tiny / base / small / medium
    "whisper_language": "en",
    "ollama_model": "llama3.2:3b",      # gaming mode default (fast load)
    "ollama_model_full": "qwen2.5:7b",  # desktop mode (better quality)
    "ollama_url": "http://localhost:11434",
    "ollama_keep_alive": "0",           # unload after each response
    "ollama_gpu_layers_gaming": 0,      # 0 = CPU only while gaming
    "ollama_gpu_layers_full": 99,       # all layers on GPU in desktop mode
    "piper_model": "en_US-lessac-high", # closest to Jarvis tone
    "piper_rate": 1.0,                  # speech speed multiplier
    "audio_device": None,               # None = system default
    "notification_duration": 4000,      # ms
    "gaming_mode": False,
    "log_conversations": True,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        return {**DEFAULT_CONFIG, **cfg}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    log.info("Created default config at %s", CONFIG_PATH)
    return DEFAULT_CONFIG.copy()


# ── Mode management ────────────────────────────────────────────────────────────
class ModeManager:
    """Toggle between gaming mode (CPU inference) and desktop mode (GPU inference)."""

    def __init__(self, config: dict):
        self.config = config
        self.gaming = config.get("gaming_mode", False)
        self._apply()

    def _apply(self):
        gpu_layers = (
            self.config["ollama_gpu_layers_gaming"]
            if self.gaming
            else self.config["ollama_gpu_layers_full"]
        )
        model = (
            self.config["ollama_model"]
            if self.gaming
            else self.config["ollama_model_full"]
        )
        os.environ["OLLAMA_NUM_GPU"] = str(gpu_layers)
        self._model = model
        mode_label = "GAMING (CPU inference)" if self.gaming else "DESKTOP (GPU inference)"
        log.info("Mode: %s | Model: %s | GPU layers: %s", mode_label, model, gpu_layers)
        notify(
            "JARVIS",
            f"{'🎮 Gaming mode' if self.gaming else '🤖 Desktop mode'} — {model}",
        )

    def toggle(self):
        self.gaming = not self.gaming
        self._apply()

    @property
    def model(self) -> str:
        return self._model


# ── Notification helper ────────────────────────────────────────────────────────
def notify(title: str, body: str, duration: int = 4000):
    try:
        subprocess.Popen(
            ["dunstify", "-t", str(duration), "-u", "low", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        log.debug("dunstify not found, skipping notification")


# ── Wake word detection ────────────────────────────────────────────────────────
class WakeWordListener:
    """Listens continuously for the wake word using OpenWakeWord."""

    def __init__(self, config: dict, callback):
        self.config = config
        self.callback = callback
        self._stop = threading.Event()

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            import numpy as np
            import pyaudio
            from openwakeword.model import Model

            oww = Model(
                wakeword_models=["hey_jarvis"],   # custom or built-in model
                inference_framework="onnx",
            )
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1280,
            )
            log.info("Wake word listener active — say '%s'", self.config["wake_word"])

            while not self._stop.is_set():
                chunk = stream.read(1280, exception_on_overflow=False)
                samples = np.frombuffer(chunk, dtype=np.int16)
                preds = oww.predict(samples)
                for name, score in preds.items():
                    if score >= self.config["wake_word_threshold"]:
                        log.info("Wake word detected (score=%.2f)", score)
                        self.callback()
                        oww.reset()
                        break

            stream.stop_stream()
            stream.close()
            audio.terminate()
        except ImportError as e:
            log.error("Missing dependency: %s — falling back to keyboard trigger", e)
            log.info("Press ENTER to trigger JARVIS (wake word unavailable)")
            while not self._stop.is_set():
                input()
                self.callback()


# ── Speech-to-text ─────────────────────────────────────────────────────────────
class Transcriber:
    """Records audio after wake word and transcribes with whisper.cpp."""

    def __init__(self, config: dict):
        self.config = config
        self.model = config["whisper_model"]
        self.language = config["whisper_language"]

    def listen_and_transcribe(self) -> str:
        """Record up to 10s of audio and return transcription."""
        import pyaudio
        import wave
        import tempfile

        notify("JARVIS", "Listening…", duration=2000)
        log.info("Recording audio…")

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        silence_threshold = 500
        silence_frames = 0
        max_silence = 30   # ~2 seconds of silence to stop
        max_frames = 150   # ~10 seconds max

        for _ in range(max_frames):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            import numpy as np
            samples = np.frombuffer(data, dtype=np.int16)
            if np.abs(samples).mean() < silence_threshold:
                silence_frames += 1
                if silence_frames >= max_silence and len(frames) > 20:
                    break
            else:
                silence_frames = 0

        stream.stop_stream()
        stream.close()
        audio.terminate()

        # Write to temp wav
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wf = wave.open(tmp.name, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))
            wf.close()
            wav_path = tmp.name

        text = self._whisper(wav_path)
        os.unlink(wav_path)
        return text.strip()

    def _whisper(self, wav_path: str) -> str:
        """Call whisper.cpp CLI."""
        try:
            result = subprocess.run(
                [
                    "whisper-cpp",
                    "--model", f"ggml-{self.model}.bin",
                    "--language", self.language,
                    "--output-txt",
                    "--no-timestamps",
                    wav_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            # whisper-cpp outputs transcript to stdout
            return result.stdout.strip()
        except FileNotFoundError:
            # Fallback: python openai-whisper
            log.warning("whisper-cpp not found, trying openai-whisper…")
            try:
                import whisper
                model = whisper.load_model(self.model)
                result = model.transcribe(wav_path, language=self.language)
                return result["text"]
            except ImportError:
                log.error("No whisper backend available")
                return ""


# ── LLM (Ollama) ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are JARVIS, a concise and helpful AI assistant running locally on an Arch Linux desktop.
You help with system control, information, and tasks.
Keep responses SHORT — under 3 sentences unless detail is specifically requested.
You can control the desktop via i3wm. When a user wants to launch an app, adjust volume, switch workspaces,
or run a command, output a JSON action block like:
{"action": "launch", "app": "firefox"}
{"action": "i3", "cmd": "workspace 2"}
{"action": "volume", "level": 50}
{"action": "brightness", "level": 70}
{"action": "notify", "title": "JARVIS", "body": "Done!"}
Otherwise respond conversationally."""


class Brain:
    """Sends prompt to Ollama and streams the response."""

    def __init__(self, config: dict, mode_manager: ModeManager):
        self.config = config
        self.mode = mode_manager
        self.history = []   # conversation history

    def think(self, user_text: str) -> str:
        import urllib.request
        import json

        self.history.append({"role": "user", "content": user_text})

        payload = {
            "model": self.mode.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + self.history,
            "stream": False,
            "keep_alive": self.config["ollama_keep_alive"],
        }

        try:
            req = urllib.request.Request(
                f"{self.config['ollama_url']}/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            reply = data["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})
            # keep history bounded
            if len(self.history) > 20:
                self.history = self.history[-20:]
            return reply
        except Exception as e:
            log.error("Ollama error: %s", e)
            return "Sorry, I couldn't reach the language model. Is Ollama running?"

    def clear_history(self):
        self.history = []


# ── Skill router ───────────────────────────────────────────────────────────────
class SkillRouter:
    """Parses action blocks from LLM output and executes them."""

    def __init__(self, config: dict):
        self.config = config

    def execute(self, reply: str) -> str:
        """Extract action JSON from reply, execute it, return spoken text."""
        import re, json

        # Find JSON action blocks
        matches = re.findall(r'\{[^}]+\}', reply)
        spoken = re.sub(r'\{[^}]+\}', '', reply).strip()

        for m in matches:
            try:
                action = json.loads(m)
                self._run_action(action)
            except json.JSONDecodeError:
                pass

        return spoken or "Done."

    def _run_action(self, action: dict):
        kind = action.get("action", "")

        if kind == "launch":
            app = action.get("app", "")
            log.info("Launching: %s", app)
            subprocess.Popen([app], start_new_session=True)

        elif kind == "i3":
            cmd = action.get("cmd", "")
            log.info("i3-msg: %s", cmd)
            subprocess.run(["i3-msg", cmd], capture_output=True)

        elif kind == "volume":
            level = action.get("level", 50)
            log.info("Volume: %s%%", level)
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])

        elif kind == "brightness":
            level = action.get("level", 70)
            log.info("Brightness: %s%%", level)
            subprocess.run(["brightnessctl", "set", f"{level}%"])

        elif kind == "notify":
            notify(action.get("title", "JARVIS"), action.get("body", ""))

        else:
            log.warning("Unknown action: %s", kind)


# ── Text-to-speech ─────────────────────────────────────────────────────────────
class Speaker:
    """Synthesises and plays speech via Piper TTS."""

    def __init__(self, config: dict):
        self.config = config
        self.model = config["piper_model"]

    def say(self, text: str):
        if not text:
            return
        log.info("Speaking: %s", text[:80])
        try:
            # Piper: echo text | piper --model <model> --output-raw | aplay
            piper_proc = subprocess.Popen(
                ["piper", "--model", self.model, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            aplay_proc = subprocess.Popen(
                ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            piper_proc.stdin.write(text.encode())
            piper_proc.stdin.close()
            piper_proc.wait()
            aplay_proc.wait()
        except FileNotFoundError:
            # Fallback to espeak-ng
            log.warning("piper not found, using espeak-ng")
            subprocess.run(["espeak-ng", "-s", "160", "-p", "40", text])


# ── Main orchestrator ──────────────────────────────────────────────────────────
class Jarvis:
    def __init__(self):
        self.config = load_config()
        self.mode = ModeManager(self.config)
        self.transcriber = Transcriber(self.config)
        self.brain = Brain(self.config, self.mode)
        self.router = SkillRouter(self.config)
        self.speaker = Speaker(self.config)
        self._busy = threading.Event()

    def on_wake(self):
        if self._busy.is_set():
            log.info("Already processing, ignoring wake word")
            return
        self._busy.set()
        try:
            text = self.transcriber.listen_and_transcribe()
            if not text:
                self.speaker.say("I didn't catch that.")
                return

            log.info("You said: %s", text)

            # Handle meta-commands locally
            lower = text.lower()
            if any(k in lower for k in ["gaming mode", "game mode"]):
                self.mode.toggle()
                self.speaker.say(
                    "Switching to gaming mode. GPU resources freed for your game."
                    if self.mode.gaming
                    else "Switching to desktop mode. Full GPU inference restored."
                )
                return
            if "clear history" in lower or "forget everything" in lower:
                self.brain.clear_history()
                self.speaker.say("Conversation history cleared.")
                return
            if "shut down" in lower and "jarvis" in lower:
                self.speaker.say("Goodbye.")
                os.kill(os.getpid(), signal.SIGTERM)
                return

            # LLM → skill router → TTS
            notify("JARVIS", f""{text}"")
            reply = self.brain.think(text)
            log.info("JARVIS: %s", reply)
            spoken = self.router.execute(reply)
            self.speaker.say(spoken)

            if self.config["log_conversations"]:
                self._log_conv(text, reply)
        finally:
            self._busy.clear()

    def _log_conv(self, user: str, jarvis: str):
        log_file = Path(__file__).parent / "logs/conversations.log"
        with open(log_file, "a") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
            f.write(f"YOU: {user}\n")
            f.write(f"JARVIS: {jarvis}\n")

    def run(self):
        log.info("JARVIS initialising…")
        notify("JARVIS", "Online and ready.", duration=3000)
        self.speaker.say("JARVIS online.")

        listener = WakeWordListener(self.config, self.on_wake)
        listener.start()

        def shutdown(sig, frame):
            log.info("Shutting down…")
            listener.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        log.info("Ready. Waiting for wake word…")
        signal.pause()


if __name__ == "__main__":
    Jarvis().run()
