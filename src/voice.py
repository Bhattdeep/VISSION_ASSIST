"""
voice.py — Thread-safe, reliable text-to-speech.

Key behaviours
--------------
1. Fresh pyttsx3 engine per utterance — fixes Windows SAPI5 COM stall bug.

2. Queue flood prevention:
   - While speaking, NEW messages of same or lower priority are DISCARDED.
     (The pipeline fires every alert_delay seconds; if speech takes longer
      than alert_delay, without this guard the queue fills with stale
      messages and speech never stops.)
   - CRITICAL messages always preempt — queue is cleared and new message
     jumps to front.

3. Deduplication: if the exact same text is already waiting in the queue,
   it is not added again.
"""

import threading
import queue as _queue
import time

PRIORITY_CRITICAL = 0
PRIORITY_WARNING  = 1
PRIORITY_INFO     = 2


def _speak_once(text: str, rate: int, volume: float):
    """Speak one utterance with a fresh engine (thread-safe on Windows)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate",   rate)
        engine.setProperty("volume", volume)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        print(f"[Voice] TTS error: {exc}")


class VoiceEngine:
    """
    Priority queue TTS engine.  Each utterance runs in its own thread
    so the Windows COM event loop never stalls.
    """

    def __init__(self, rate: int = 185, volume: float = 1.0):
        self.rate     = rate
        self.volume   = volume

        self._queue        = _queue.PriorityQueue(maxsize=4)
        self._thread       = threading.Thread(target=self._worker, daemon=True)
        self._running      = False
        self._busy         = False
        self._current_pri  = PRIORITY_INFO   # priority of what is currently speaking
        self._recent_texts = {}
        self._dedupe_window_sec = 8.0

    def start(self):
        self._running = True
        self._thread.start()

    def speak(self, text: str, priority: int = PRIORITY_WARNING):
        if not self._running:
            return

        now = time.time()
        self._recent_texts = {
            msg: ts for msg, ts in self._recent_texts.items()
            if (now - ts) < self._dedupe_window_sec
        }
        if text in self._recent_texts:
            return

        # ── flood guard ──────────────────────────────────────────────
        # If we are currently speaking something of equal or higher
        # priority (lower number), discard this new message entirely.
        # CRITICAL always goes through.
        if self._busy and priority > PRIORITY_CRITICAL:
            if priority >= self._current_pri:
                return   # discard — currently speaking same/higher priority

        # ── deduplication ────────────────────────────────────────────
        # Peek at queue contents; skip if identical text is already waiting
        with self._queue.mutex:
            for _, queued_text in list(self._queue.queue):
                if queued_text == text:
                    return

        # ── critical preemption ──────────────────────────────────────
        if priority == PRIORITY_CRITICAL:
            # Drain lower-priority items to make room
            with self._queue.mutex:
                self._queue.queue = [
                    item for item in self._queue.queue
                    if item[0] == PRIORITY_CRITICAL
                ]

        try:
            self._queue.put_nowait((priority, text))
            self._recent_texts[text] = now
        except _queue.Full:
            pass   # queue saturated; drop gracefully

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait((-1, None))
        except _queue.Full:
            pass

    def is_speaking(self) -> bool:
        return self._busy

    def _worker(self):
        while self._running:
            try:
                priority, text = self._queue.get(timeout=0.3)
            except _queue.Empty:
                continue

            if text is None:
                break

            self._busy        = True
            self._current_pri = priority
            try:
                t = threading.Thread(
                    target=_speak_once,
                    args=(text, self.rate, self.volume),
                    daemon=True,
                )
                t.start()
                t.join(timeout=15)
            finally:
                self._busy = False
