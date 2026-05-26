import os
import tempfile
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf

WAKE_ALIASES = (
    "hey jarvis",
    "jarvis",
    "hey davis",
    "hey travis",
    "okay jarvis",
    "hey jarvus",
    "hay jarvis",
)
WAKE_CHUNK_SECONDS = 2
COMMAND_SECONDS = 5
SAMPLE_RATE = 16000
SILENCE_RMS_THRESHOLD = 100

class VoiceListener:
    """
    Wake-word listener: sounddevice capture with robust Windows audio multi-channel check, 
    automatic downmixing, and ultra-fast cloud-hosted Groq Whisper API transcription.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(VoiceListener, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        wake_word_detected=None,
        command_callback=None,
        on_error=None,
        on_activity=None,
    ):
        if self._initialized:
            if wake_word_detected is not None:
                self.wake_word_detected = wake_word_detected
            if command_callback is not None:
                self.command_callback = command_callback
            if on_error is not None:
                self.on_error = on_error
            if on_activity is not None:
                self.on_activity = on_activity
            return

        self.wake_word_detected = wake_word_detected or (lambda: None)
        self.command_callback = command_callback or (lambda _text: None)
        self.on_error = on_error or (lambda _msg: None)
        self.on_activity = on_activity or (lambda _label, _detail="": None)
        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._whisper_ready = threading.Event()
        self._whisper_failed = False
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None
        self._rms_thread: threading.Thread | None = None
        self._input_device = None
        self._channels = 1
        self.available = False
        self.last_error: str | None = None
        self._initialized = True

    def _configure_sounddevice(self) -> None:
        sd.default.device = None
        sd.default.samplerate = SAMPLE_RATE
        print("[JARVIS] Available audio devices:", flush=True)
        print(sd.query_devices(), flush=True)

    def _init_microphone(self) -> bool:
        """Robust mic checks trying standard channel sizes to bypass Windows driver blocks."""
        for ch in [1, 2, 4]:
            try:
                self._configure_sounddevice()
                sd.check_input_settings(
                    samplerate=SAMPLE_RATE,
                    channels=ch,
                    dtype="int16",
                    device=self._input_device,
                )
                self._channels = ch
                self.available = True
                self.last_error = None
                print(f"[JARVIS mic] Successfully configured microphone with channels={ch}", flush=True)
                return True
            except Exception as e:
                print(f"[JARVIS mic] Input channels={ch} check failed: {e}", flush=True)
                continue
        
        self.available = False
        self.last_error = "No supported audio input channels found (tried 1, 2, 4)"
        self.on_activity("MIC ERROR", f"Unavailable: {self.last_error}")
        return False

    def _preload_whisper(self) -> None:
        try:
            self._get_whisper()
        except Exception as e:
            self._whisper_failed = True
            self.on_activity("WHISPER LOAD", f"Failed, using Groq/Google STT: {e}")
        finally:
            self._whisper_ready.set()

    def _get_whisper(self):
        if self._whisper_failed:
            raise RuntimeError("Whisper unavailable")
        if self._whisper_model is None:
            with self._whisper_lock:
                if self._whisper_model is None:
                    from faster_whisper import WhisperModel
                    self._whisper_model = WhisperModel(
                        "tiny",
                        device="cpu",
                        compute_type="int8",
                    )
        return self._whisper_model

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        samples = audio.astype(np.float32)
        return float(np.sqrt(np.mean(samples**2)))

    def _rms_monitor_loop(self) -> None:
        block = int(SAMPLE_RATE * 0.1)
        while self._running:
            try:
                chunk = sd.rec(
                    block,
                    samplerate=SAMPLE_RATE,
                    channels=self._channels,
                    dtype="int16",
                    device=self._input_device,
                )
                sd.wait()
                
                # Downmix if stereo/quad captured
                if self._channels > 1:
                    audio_data = chunk.mean(axis=1).astype(np.int16)
                else:
                    audio_data = chunk.flatten()
                
                level = self._rms(audio_data)
                print(f"[JARVIS mic] RMS level: {level:.1f}", flush=True)
            except Exception as e:
                self.on_activity("MIC RMS", f"RMS error: {e}")
            threading.Event().wait(2.0)

    def _record_to_wav(self, duration: float) -> str | None:
        try:
            frames = int(SAMPLE_RATE * duration)
            recording = sd.rec(
                frames,
                samplerate=SAMPLE_RATE,
                channels=self._channels,
                dtype="int16",
                device=self._input_device,
            )
            sd.wait()
            if not self._running:
                return None

            # Downmix to mono if multi-channel
            if self._channels > 1:
                audio = recording.mean(axis=1).astype(np.int16)
            else:
                audio = recording.flatten()

            rms = self._rms(audio)
            if rms < SILENCE_RMS_THRESHOLD:
                return None

            fd, path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_")
            os.close(fd)
            sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
            return path
        except Exception as e:
            self.on_activity("RECORD ERROR", str(e))
            return None

    def _transcribe_groq(self, wav_path: str) -> str:
        """Transcribe audio instantly using the high-performance Groq cloud Whisper API."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from environment")
        from groq import Groq
        client = Groq(api_key=api_key)
        with open(wav_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(wav_path), file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        return transcription.strip()

    def _transcribe_google(self, wav_path: str) -> str:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio).strip()

    def _transcribe_wav(self, wav_path: str, *, beam_size: int = 5) -> str:
        text = ""
        # 1. Try cloud-hosted Groq Whisper (blazingly fast & requires zero local resources)
        try:
            text = self._transcribe_groq(wav_path)
            if text:
                print(f"[JARVIS mic] Transcribed via Groq cloud: '{text}'", flush=True)
                self.on_activity("STT GROQ", "Groq transcribed successfully")
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
                return text
        except Exception as e:
            print(f"[JARVIS mic] Groq Whisper failed: {e}. Attempting fallbacks...", flush=True)

        # 2. Try local faster-whisper
        try:
            if not self._whisper_failed:
                self._whisper_ready.wait(timeout=5)  # wait up to 5s
                model = self._get_whisper()
                segments, _info = model.transcribe(
                    wav_path,
                    beam_size=beam_size,
                    language="en",
                    vad_filter=True,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if text:
                    print(f"[JARVIS mic] Transcribed via local Whisper: '{text}'", flush=True)
        except Exception as e:
            self._whisper_failed = True
            print(f"[JARVIS mic] local faster-whisper failed: {e}", flush=True)

        # 3. Google STT Fallback
        try:
            if not text:
                text = self._transcribe_google(wav_path)
                if text:
                    print(f"[JARVIS mic] Transcribed via Google STT: '{text}'", flush=True)
                    self.on_activity("STT FALLBACK", "Google STT fallback")
        except Exception as e:
            self.on_activity("TRANSCRIPTION ERROR", str(e))
            text = ""
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return text

    def _contains_wake_word(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        return any(alias in normalized for alias in WAKE_ALIASES)

    def _listen_loop(self) -> None:
        while self._running:
            try:
                if self._paused:
                    threading.Event().wait(0.2)
                    continue

                wav_path = self._record_to_wav(WAKE_CHUNK_SECONDS)
                if not wav_path or not self._running:
                    continue

                text = self._transcribe_wav(wav_path, beam_size=1)
                if not text or not self._contains_wake_word(text):
                    continue

                print("WAKE WORD DETECTED", flush=True)
                try:
                    self.wake_word_detected()
                except Exception as e:
                    self.on_activity("WAKE ERROR", str(e))

                if not self._running:
                    break

                self._paused = True
                command_wav = self._record_to_wav(COMMAND_SECONDS)
                
                if command_wav and self._running:
                    command_text = self._transcribe_wav(command_wav, beam_size=5)
                    if command_text:
                        self.command_callback(command_text)
                    else:
                        self.on_activity("COMMAND FAIL", "Could not understand command.")
                else:
                    self.on_activity("COMMAND FAIL", "No command recorded after wake word.")

                self._paused = False

            except OSError as e:
                self.available = False
                self.last_error = str(e)
                self.on_activity("MIC ERROR", f"OS Error: {e}")
                self._running = False
                break
            except Exception as e:
                self.on_activity("VOICE ERROR", str(e))
                continue

    def start(self) -> bool:
        if self._running:
            return self.available
        if not self._init_microphone():
            return False
        self._whisper_ready.clear()
        self._whisper_failed = False
        threading.Thread(target=self._preload_whisper, daemon=True).start()
        self._running = True
        self._paused = False
        self._rms_thread = threading.Thread(
            target=self._rms_monitor_loop, daemon=True, name="jarvis-mic-rms"
        )
        self._rms_thread.start()
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="jarvis-listener"
        )
        self._thread.start()
        print("[JARVIS] Voice listener started. Say 'Hey Jarvis'.", flush=True)
        return True

    def stop(self) -> None:
        self._running = False
        self._paused = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=WAKE_CHUNK_SECONDS + COMMAND_SECONDS + 4)
        self._thread = None

    def is_running(self) -> bool:
        return self._running and self.available

_global_listener = VoiceListener()
_global_listener.start()
