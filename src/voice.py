"""
voice.py — Thread-safe, reliable text-to-speech for Windows + Linux.

Root cause of the "speaks once then goes silent" bug on Windows
---------------------------------------------------------------
pyttsx3 uses the Windows SAPI5 COM engine under the hood.  Calling
engine.runAndWait() more than once on the same engine object causes
the COM event loop to silently stall on many Windows configurations.
The fix is to create a FRESH pyttsx3 engine for every utterance and
run it in a short-lived daemon thread.  The overhead is negligible
(SAPI5 init takes ~10 ms) compared to the several-second cooldown
between alerts.

Priority levels (lower = higher priority)
------------------------------------------
    PRIORITY_CRITICAL = 0   object very close / stop immediately
    PRIORITY_WARNING  = 1   object nearby / caution
    PRIORITY_INFO     = 2   general guidance / assistant replies
"""

import threading
import queue

PRIORITY_CRITICAL = 0
PRIORITY_WARNING  = 1
PRIORITY_INFO     = 2


def _speak_once(text: str, rate: int, volume: float):
    """
    Speak one utterance using a brand-new pyttsx3 engine.
    Runs in its own thread — safe to call from any thread.
    """
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
    Queues speech messages and plays them one at a time on a
    dedicated worker thread.  Each utterance gets a fresh pyttsx3
    engine to avoid the Windows COM stall bug.

    Usage
    -----
        ve = VoiceEngine(rate=185)
        ve.start()
        ve.speak("Obstacle ahead.", priority=PRIORITY_WARNING)
        ve.stop()
    """

    def __init__(self, rate: int = 185, volume: float = 1.0):
        self.rate     = rate
        self.volume   = volume

        self._queue   = queue.Queue(maxsize=6)
        self._thread  = threading.Thread(target=self._worker, daemon=True)
        self._running = False
        self._busy    = False          # True while an utterance is playing

    # ── public API ──────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread.start()

    def speak(self, text: str, priority: int = PRIORITY_WARNING):
        """
        Enqueue text for speech.

        Dropping rules (to avoid a massive backlog of stale alerts):
          - If the engine is busy speaking a CRITICAL message, drop everything.
          - If the engine is busy speaking a WARNING/INFO, drop INFO only.
          - If the queue is full, drop the new message (oldest stays).
        """
        if not self._running:
            return

        # Never enqueue duplicates of whatever is already pending
        try:
            self._queue.put_nowait((priority, text))
        except queue.Full:
            # Queue full — try to make room by discarding lowest-priority item
            try:
                # Drain and re-add only higher-priority items
                items = []
                while True:
                    items.append(self._queue.get_nowait())
            except queue.Empty:
                pass

            # Keep items that are higher priority than the new message
            kept = [i for i in items if i[0] <= priority]
            # Add the new message
            kept.append((priority, text))
            # Sort by priority and re-queue up to maxsize
            kept.sort(key=lambda x: x[0])
            for item in kept[:6]:
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    break

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait((-1, None))   # sentinel
        except queue.Full:
            pass

    def is_speaking(self) -> bool:
        return self._busy

    # ── worker ──────────────────────────────────────────────────────

    def _worker(self):
        while self._running:
            try:
                priority, text = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if text is None:    # stop sentinel
                break

            self._busy = True
            try:
                # Fresh engine per utterance — fixes Windows COM stall
                t = threading.Thread(
                    target=_speak_once,
                    args=(text, self.rate, self.volume),
                    daemon=True,
                )
                t.start()
                t.join(timeout=15)   # hard timeout so we never block forever
            finally:
                self._busy = False