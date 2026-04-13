import time
import threading


class BandwidthLimiter:
    def __init__(self, rate_bytes_per_sec):
        self.rate = rate_bytes_per_sec
        self.tokens = rate_bytes_per_sec
        self.last_time = time.time()
        self.lock = threading.Lock()

    def consume(self, bytes_count):
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_time

                self.tokens += elapsed * self.rate
                self.tokens = min(self.tokens, self.rate)
                self.last_time = now

                if self.tokens >= bytes_count:
                    self.tokens -= bytes_count
                    return

            time.sleep(0.01)