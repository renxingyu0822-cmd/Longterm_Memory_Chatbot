"""Background refresh loop for assets tracked by the local user."""

from __future__ import annotations

import logging
import os
import threading
import time

from market_service import service


class MarketTracker:
    def __init__(self):
        self.interval = max(15, int(os.getenv("MARKET_REFRESH_SECONDS", "60")))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="market-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        logger = logging.getLogger(__name__)
        while not self._stop.is_set():
            try:
                service.refresh_tracked()
            except Exception:
                logger.exception("Market refresh cycle failed")
            self._stop.wait(self.interval)


tracker = MarketTracker()

