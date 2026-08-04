import time


class SystemClock:
    """The real clock, the only Clock a running deployment ever uses."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, duration: float) -> None:
        time.sleep(duration)
