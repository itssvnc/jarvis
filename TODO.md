# JARVIS — Known Issues & TODO


### 1. No sound output
- Piper generates `/tmp/jarvis_tts.wav` but `pw-play` can't find it
- Error: `sndfile: failed to open audio file "/tmp/jarvis_tts.wav"`
- Piper subprocess may be failing silently before writing the file
- **Fix to try:** Add error checking after piper subprocess, print stderr to confirm file is written before pw-play is called
- May need to use `--output-file` with absolute path and confirm file exists before playing

### 2. Ollama running 100% on CPU (no GPU)
- `ollama ps` confirms: `100% CPU` for both models
- GPU utilization stays at 10-20% max
- Root cause: ollama-cuda not installed, or CUDA not available to Ollama
- **Fix:** `yay -R ollama && yay -S ollama-cuda`
- Verify CUDA: `nvcc --version` — if missing: `yay -S cuda`
- Until fixed: use `llama3.2:3b` to reduce CPU load

### 3. Whisper running on CPU (slow, ~15 seconds per transcription)
- Warnings: "Performing inference on CPU when CUDA is available"
- Root cause: VRAM is full (Ollama taking ~4.6GB) so Whisper can't fit
- **Fix A (short term):** Switch Ollama to 3B model to free VRAM for Whisper
- **Fix B (long term):** Fix Ollama GPU issue above — once Ollama uses GPU efficiently,
  remove `device="cpu"` from `whisper.load_model()` call in jarvis.py line ~255
- whisper.cpp CLI would also solve this — faster and lower VRAM than openai-whisper

### 4. Wake word triggering on JARVIS's own responses / background noise
- Scores of 0.75-0.95 triggering immediately after a response
- **Fix:** Add a cooldown after each response before re-enabling wake word listener
- Raise `wake_word_threshold` from 0.5 to 0.7 in config.json
- Add `_busy` lock to block wake word during TTS playback

### 5. Noisy ALSA log output
- Dozens of ALSA lib errors on every startup (harmless but clutters terminal)
- **Fix:** Redirect ALSA stderr to /dev/null at startup:
  Add to jarvis.py top: `os.environ["ALSA_LOG_LEVEL"] = "none"`
  Or suppress at launch: `python jarvis.py 2>/dev/null` (loses real errors too)
  Better: filter ALSA lines in logging config

### 6. Whisper mishearing silence as "Thanks for watching" / "you"
- Common Whisper hallucination on silence or background noise
- **Fix:** Add minimum audio energy threshold before sending to Whisper
- Filter out transcriptions under 3 words or matching known hallucinations:
  `HALLUCINATIONS = ["thanks for watching", "you", "thank you"]`

---

## ✅ Working
- Wake word detection (OpenWakeWord, score ~0.88-1.00)
- Speech recognition pipeline (slow but functional)
- Ollama LLM responses (CPU, slow)
- App launching (firefox confirmed working)
- i3-msg integration
- Conversation logging to logs/conversations.log

---

## 📋 Priority Order
1. Fix sound output (pw-play / piper file issue)
2. Fix Ollama GPU (ollama-cuda)
3. Fix wake word re-trigger cooldown
4. Reduce Whisper hallucinations
5. Clean up ALSA log noise
