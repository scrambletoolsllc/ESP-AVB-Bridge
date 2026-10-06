"""Experimental relative FTM clock model; no servo or absolute epoch claim."""
from dataclasses import dataclass
from collections import deque
from statistics import median

PS_PER_US = 1_000_000
REMOTE_PERIOD = 1 << 48
MAC_PERIOD = (1 << 32) * PS_PER_US


def extend_near(value, anchor, period, maximum_distance):
    if not 0 <= value < period or not 0 <= maximum_distance < period // 2:
        raise ValueError('invalid truncated timestamp or extension budget')
    delta = (value - anchor + period // 2) % period - period // 2
    if abs(delta) > maximum_distance:
        raise ValueError('ambiguous or stale timestamp')
    return anchor + delta


def fine_mac_ticks(mac_us, timer_phase, offset_lower, offset_upper,
                   coarse_uncertainty_us=2):
    """Reconstruct 40 MHz MAC ticks near a fresh coarse MAC read.

    All phase inputs belong to one timer generation. The caller must bound
    read separation and reject a reset; this helper cannot establish that.
    """
    if not 0 <= mac_us < 1 << 32 or not 0 <= timer_phase < 60000:
        raise ValueError('invalid coarse MAC or timer phase')
    if not 0 <= offset_upper - offset_lower <= 40:
        raise ValueError('invalid calibration interval')
    if not 0 <= coarse_uncertainty_us < 700:
        raise ValueError('coarse uncertainty cannot select a unique cycle')
    phase = (timer_phase + offset_lower) % 60000
    lower = extend_near(phase, mac_us * 40, 60000,
                        (coarse_uncertainty_us + 1) * 40)
    return lower, lower + offset_upper - offset_lower


@dataclass(frozen=True)
class Entry:
    token: int
    rssi: int
    rtt: int
    t1: int
    t2: int
    t3: int
    t4: int
    ppm: int = 0


@dataclass(frozen=True)
class Report:
    generation: int
    attempt: int
    peer: str
    before_us: int
    mac_us: int
    after_us: int
    dropped: int
    entries: tuple


def integer_median(values):
    ordered = sorted(values)
    middle = len(ordered)//2
    return (ordered[middle] + ordered[(len(ordered)-1)//2])//2


class RelativeModel:
    """Fit remote-minus-local correction, predict before adding each report."""
    def __init__(self, window=32, minimum=8):
        if not 2 <= minimum <= window:
            raise ValueError('invalid model window')
        self.window = window
        self.minimum = minimum
        self.history = deque(maxlen=window)
        self.identity = None
        self.previous = None
        self.segment = 0

    def reset(self, identity):
        self.history.clear()
        self.previous = None
        self.identity = identity
        self.segment += 1

    def fit(self):
        if len(self.history) < self.minimum:
            return None
        local_anchor, remote_anchor = self.history[0]
        elapsed = [local-local_anchor for local, remote in self.history]
        corrections = [(remote-remote_anchor)-(local-local_anchor)
                       for local, remote in self.history]
        average_elapsed = sum(elapsed) / len(elapsed)
        average_correction = sum(corrections) / len(corrections)
        variance = sum((value-average_elapsed)**2 for value in elapsed)
        if not variance:
            raise ValueError('zero clock-model span')
        slope = sum((elapsed_value-average_elapsed)*(correction-average_correction)
                    for elapsed_value, correction in zip(elapsed, corrections)) / variance
        if abs(slope) > 200e-6:
            raise ValueError('implausible relative rate')
        return local_anchor, remote_anchor, slope, average_correction-slope*average_elapsed

    def observe(self, report):
        identity = report.generation, report.peer
        if identity != self.identity:
            self.reset(identity)
        if not 0 <= report.after_us-report.before_us <= 50:
            raise ValueError('wide callback MAC read bracket')
        valid = [entry for entry in report.entries if 0 < entry.rtt <= 0x7fffffff]
        if not valid:
            raise ValueError('no valid RTT entries')
        pairs = []
        previous = self.previous
        wraps = 0
        for entry in valid:
            if not (0 <= entry.t1 < REMOTE_PERIOD and 0 <= entry.t4 < REMOTE_PERIOD
                    and 0 <= entry.t2 < 1 << 64 and 0 <= entry.t3 < 1 << 64):
                raise ValueError('timestamp outside documented width')
            local_turnaround = entry.t3-entry.t2
            if not 0 < local_turnaround < 10_000 * PS_PER_US:
                raise ValueError('invalid local turnaround')
            remote_turnaround = (entry.t4-entry.t1) % REMOTE_PERIOD
            if not 0 < remote_turnaround < 10_000 * PS_PER_US:
                raise ValueError('invalid remote turnaround')
            local_midpoint = (entry.t2+entry.t3)//2
            if previous is None:
                remote_t1 = entry.t1
            else:
                local_gap = local_midpoint-previous[0]
                if not 0 < local_gap <= 2_000_000 * PS_PER_US:
                    raise ValueError('nonmonotonic or stale local timestamp')
                expected_midpoint = previous[1]+local_gap
                remote_t1 = extend_near(entry.t1,
                    expected_midpoint-remote_turnaround//2, REMOTE_PERIOD,
                    2_000 * PS_PER_US)
                if remote_t1 <= previous[2]:
                    raise ValueError('nonmonotonic responder timestamp')
                wraps += remote_t1//REMOTE_PERIOD-previous[2]//REMOTE_PERIOD
            remote_midpoint = remote_t1+remote_turnaround//2
            previous = local_midpoint, remote_midpoint, remote_t1
            pairs.append((local_midpoint, remote_midpoint))
        callback_mac = extend_near(report.mac_us*PS_PER_US, valid[-1].t3,
                                   MAC_PERIOD, 500_000*PS_PER_US)
        age = callback_mac-valid[-1].t3
        if not -PS_PER_US <= age <= 500_000*PS_PER_US:
            raise ValueError('stale report or inconsistent local epoch')
        fit = self.fit()
        errors = []
        if fit:
            local_anchor, remote_anchor, slope, intercept = fit
            for local, remote in pairs:
                elapsed = local-local_anchor
                errors.append((remote-remote_anchor)-elapsed-(intercept+slope*elapsed))
            if abs(median(errors)) > 20_000 * 1000:
                raise ValueError('clock innovation exceeds 20 us')
        # One median phase observation per report avoids overweighting a burst.
        local_center = integer_median([local for local, remote in pairs])
        correction = integer_median([remote-local for local, remote in pairs])
        self.history.append((local_center, local_center+correction))
        self.previous = previous
        return dict(segment=self.segment, entries=len(pairs), responder_wraps=wraps,
                    predicted_errors_ns=[error/1000 for error in errors],
                    remote_rate_ppm=fit[2]*1e6 if fit else None,
                    callback_age_us=age/PS_PER_US)
