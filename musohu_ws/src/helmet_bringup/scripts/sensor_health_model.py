"""Receive-rate health measured with a steady clock, independent of UTC steps."""
from collections import deque
import math


class RateWindow:
    def __init__(self, expected_hz, started_at, window_s=10.0, warmup_s=5.0,
                 stale_s=2.0, target_tolerance=0.05, healthy_tolerance=0.10):
        values = (expected_hz, window_s, warmup_s, stale_s,
                  target_tolerance, healthy_tolerance)
        if (not all(math.isfinite(v) for v in values) or expected_hz <= 0
                or window_s <= 0 or not 0 <= warmup_s <= window_s or stale_s <= 0
                or not 0 <= target_tolerance <= healthy_tolerance < 1):
            raise ValueError('Invalid rate health settings')
        self.expected_hz = expected_hz
        self.started_at = started_at
        self.window_s, self.warmup_s, self.stale_s = window_s, warmup_s, stale_s
        self.target_tolerance, self.healthy_tolerance = target_tolerance, healthy_tolerance
        self.events = deque()
        self.first_seen = self.last_seen = None
        self.count = 0

    def receive(self, now):
        if self.first_seen is None:
            self.first_seen = now
        self.last_seen = now
        self.count += 1
        self.events.append(now)
        self._trim(now)

    def _trim(self, now):
        while self.events and self.events[0] < now - self.window_s:
            self.events.popleft()

    def snapshot(self, now, enabled=True):
        self._trim(now)
        age = None if self.last_seen is None else max(0.0, now - self.last_seen)
        elapsed = 0 if self.first_seen is None else max(0.0, now - self.first_seen)
        rate = None
        if self.first_seen is not None and elapsed > 0:
            rate = (len(self.events) / self.window_s if elapsed >= self.window_s
                    else max(0, len(self.events) - 1) / elapsed)
        deviation = None if rate is None else 100 * (rate / self.expected_hz - 1)
        result = dict(expected_hz=self.expected_hz, observed_hz=rate,
                      deviation_percent=deviation, last_message_age_s=age,
                      messages=self.count, window_s=self.window_s,
                      target_met=False, healthy=False)
        if not enabled:
            status, reason = 'disabled', 'Sensor disabled in this launch'
        elif age is None:
            status = 'starting' if now - self.started_at < self.warmup_s else 'missing'
            reason = 'Waiting for messages'
        elif age >= self.stale_s:
            status, reason = 'missing', 'No recent messages'
        elif elapsed < self.warmup_s:
            status, reason = 'starting', 'Measuring receive rate'
        elif rate is None or len(self.events) < 2:
            status, reason = 'missing', 'Too few messages to measure rate'
        else:
            error = abs(rate / self.expected_hz - 1)
            healthy = error <= self.healthy_tolerance + 1e-9
            target = error <= self.target_tolerance + 1e-9
            status = 'healthy' if healthy else 'unhealthy'
            reason = (f'Within {100*self.target_tolerance:g}% target' if target else
                      f'Within {100*self.healthy_tolerance:g}% healthy tolerance'
                      if healthy else 'Receive rate outside healthy tolerance')
            result.update(healthy=healthy, target_met=target)
        result.update(status=status, reason=reason)
        return result
