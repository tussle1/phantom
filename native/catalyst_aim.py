"""Catalyst's aim movement curve adapted to Phantom's foreground-gated input.

Reference: nul1ex/catalyst commit 2060cede08d8de7af9fc85c93ccb6eb0cd442e2f,
project/core/features/impl/combat/legit.cpp, legit::aimbot. Used with the
repository owner's permission. Target selection and visibility are Phantom's;
this module does not implement Catalyst's hitboxes, tracing or weapon state.
"""
from __future__ import annotations

import math
import random


def _round_away(value):
    # C++ std::round rounds halfway values away from zero, unlike Python round.
    return math.floor(value + .5) if value >= 0 else math.ceil(value - .5)


class CatalystMovement:
    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.reset()

    def reset(self):
        self.error = [0.0, 0.0]

    def step(self, delta, sensitivity, yaw, pitch, smoothing):
        if not all(math.isfinite(v) for v in (*delta, sensitivity, yaw, pitch, smoothing)) or \
                sensitivity <= 0 or yaw <= 0 or pitch <= 0 or not 1 <= smoothing <= 100:
            self.reset()
            return (0, 0)
        dx, dy = delta
        length = math.hypot(dx, dy)
        scales = (sensitivity*yaw, sensitivity*pitch)
        if not math.isfinite(length) or not all(math.isfinite(x) and x > 0 for x in scales):
            self.reset()
            return (0, 0)
        if length < .001:
            self.reset()
            return (0, 0)
        if smoothing > 1:
            distance = min(1.0, length / 10.0)
            ease = 1.0 - distance * distance
            factor = (.3 + ease * .7) / smoothing
            def normal(mean, sigma, low, high):
                return max(low, min(high, self.rng.gauss(mean, sigma)))
            factor *= normal(1., .06, .85, 1.15)
            dx *= factor * normal(1., .02, .95, 1.05)
            dy *= factor * normal(.97, .03, .90, 1.04)
            if .3 < length < 2. and self.rng.random() < .15:
                overshoot = normal(1.2, .08, 1.05, 1.4)
                dx *= overshoot
                dy *= overshoot
        counts = []
        # Phantom retains separate configurable yaw and pitch calibration.
        for i, (wanted, degrees_per_count) in enumerate(((-dy, scales[0]),
                                                          (dx, scales[1]))):
            desired = wanted + self.error[i]
            raw = desired / degrees_per_count
            # Bound each emitted event and avoid carrying a large clipped residual.
            limited = max(-250., min(250., raw))
            count = _round_away(limited)
            self.error[i] = desired - count*degrees_per_count if raw == limited else 0.0
            counts.append(count)
        return tuple(counts)
