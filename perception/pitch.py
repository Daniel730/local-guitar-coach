"""YIN pitch estimation (de Cheveigné & Kawahara, 2002).

Single deterministic pitch path: difference function -> cumulative mean
normalized difference -> absolute threshold -> parabolic interpolation.
No autocorrelation-as-separate-track; YIN alone yields frequency + confidence.
"""
from __future__ import annotations

import numpy as np


def yin_estimate(
    frame: np.ndarray,
    sr: int,
    fmin: float = 40.0,
    fmax: float = 2000.0,
    threshold: float = 0.1,
) -> tuple[float | None, float]:
    """Estimate the fundamental frequency of a single-channel frame.

    Returns (frequency_hz, confidence) where confidence is in [0, 1].
    frequency is None when no periodic component is found.
    """
    x = np.asarray(frame, dtype=np.float64).ravel()
    n = x.size
    if n < 4:
        return None, 0.0

    tau_max = int(min(n // 2, sr / fmin)) if fmin > 0 else n // 2
    tau_min = max(1, int(sr / fmax)) if fmax > 0 else 1
    if tau_max <= tau_min:
        return None, 0.0

    # Difference function d(tau) = sum (x[j] - x[j+tau])^2
    d = np.zeros(tau_max + 1)
    for tau in range(1, tau_max + 1):
        diff = x[: n - tau] - x[tau:n]
        d[tau] = float(np.dot(diff, diff))

    # Cumulative mean normalized difference.
    d_prime = np.ones(tau_max + 1)
    cumsum = 0.0
    for tau in range(1, tau_max + 1):
        cumsum += d[tau]
        d_prime[tau] = d[tau] / cumsum if cumsum > 0 else 1.0

    # Absolute threshold: first tau with d_prime below threshold, then descend
    # to the local minimum.
    tau_est = -1
    for tau in range(tau_min, tau_max + 1):
        if d_prime[tau] < threshold:
            while tau + 1 <= tau_max and d_prime[tau + 1] < d_prime[tau]:
                tau += 1
            tau_est = tau
            break

    if tau_est == -1:
        # No dip below threshold: no usable periodicity.
        return None, 0.0

    # Confidence from relative periodicity: how deep the dip is relative to the
    # average of the (non-trivial) cumulative mean. YIN's raw 1 - d_prime[tau]
    # over-trusts noise, so we measure the dip's depth against the background
    # level in the same window. Periodic signals produce a deep, narrow dip
    # (high relative depth); aperiodic signals stay near the average (low depth).
    window = d_prime[tau_min : tau_max + 1]
    mean_level = float(np.mean(window))
    dip = float(d_prime[tau_est])
    if mean_level <= 1e-9:
        return None, 0.0
    relative_depth = (mean_level - dip) / mean_level
    confidence = float(max(0.0, min(1.0, relative_depth)))

    # Parabolic interpolation for sub-sample accuracy.
    if 1 <= tau_est < tau_max:
        x0 = d_prime[tau_est - 1]
        x1 = d_prime[tau_est]
        x2 = d_prime[tau_est + 1]
        denom = x0 - 2.0 * x1 + x2
        if denom != 0:
            tau_est = tau_est + 0.5 * (x0 - x2) / denom

    if tau_est <= 0:
        return None, 0.0

    frequency = sr / tau_est
    if frequency < fmin * 0.5 or frequency > fmax * 2.0:
        return None, 0.0
    return float(frequency), confidence
