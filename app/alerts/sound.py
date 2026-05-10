import queue
import threading

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class SoundPlayer:
    def beep(self, frequency: int = 1000, duration_ms: int = 350) -> None:
        if not HAS_WINSOUND:
            return
        threading.Thread(
            target=winsound.Beep,
            args=(frequency, duration_ms),
            daemon=True,
        ).start()


class TTSPlayer:
    """Черга + один воркер-потік. Якщо pyttsx3 не доступний — silent fallback."""

    def __init__(self, language_hint: str = "ru") -> None:
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=10)
        self._language_hint = language_hint
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        if not text:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def shutdown(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def _run(self) -> None:
        try:
            import pyttsx3
        except Exception:
            return

        try:
            engine = pyttsx3.init()
        except Exception:
            return

        self._configure_voice(engine)

        while True:
            text = self._queue.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass

    def _configure_voice(self, engine) -> None:
        try:
            voices = engine.getProperty("voices") or []
        except Exception:
            return
        hint = self._language_hint.lower()
        for v in voices:
            ident = (getattr(v, "id", "") or "").lower()
            name = (getattr(v, "name", "") or "").lower()
            if hint in ident or hint in name:
                try:
                    engine.setProperty("voice", v.id)
                except Exception:
                    pass
                return
