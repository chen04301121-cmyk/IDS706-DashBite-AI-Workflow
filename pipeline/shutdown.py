"""Cooperative shutdown for the four polling workers, including container PID 1."""
from contextlib import contextmanager
import signal
import time


class Shutdown:
    def __init__(self):
        self.requested = False

    def request(self, signum, frame):
        # Only set a flag: do not raise through a CSV/checkpoint write or acquire
        # locks from a signal handler. Finish the current iteration normally.
        self.requested = True

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.requested:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))


@contextmanager
def graceful_shutdown():
    """Install handlers during the main-thread loop and restore them on exit."""
    stop = Shutdown()
    previous = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, stop.request)
        yield stop
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
