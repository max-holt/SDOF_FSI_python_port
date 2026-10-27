"""Canonical pressure histories for the junction-coupling sweep (Session 5b).

Three deterministic generators return a ``History``: a ``(time, pressure)`` pair sampled at
``sample_freq`` (default 1000 Hz) together with every generator parameter, so that a row of
the sweep CSV reproduces its history bitwise through ``from_params``. The solvers take a
*force* history: ``History.force(fluid_area)`` is the pressure times the pipe's fluid area.

* ``step(p_step)``: pressure 0 for the lead-in (``lead_in_s``, default 0.1 s), then
  ``p_step`` held to the end.
* ``step_sine(p_step, p_osc, f_osc, decay_cycles, decay_fraction)``: the step plus
  ``p_osc sin(2 pi f_osc tau)`` under an exponential envelope, ``tau`` counted from the first
  held sample. The envelope is ``exp(-lambda tau)`` with ``lambda`` chosen so that it equals
  ``1 - decay_fraction`` after ``decay_cycles`` cycles (``envelope``).
* ``step_noise(p_step, p_noise_rms, f_cut, seed, decay_cycles, decay_fraction, f_ref,
  p_cap)``: the step plus Gaussian white noise (``numpy.random.default_rng(seed)``, RMS
  ``p_noise_rms``) low-passed at ``f_cut`` (an FFT brick wall; the default, the Nyquist
  frequency, filters nothing), under the same envelope defined on the period ``1 / f_ref``,
  then peak-scaled so that ``max(pressure) == p_cap``. The requested ``p_noise_rms`` drops
  out of the result (the scaling is a ratio); the RMS of the scaled noise over the active
  window is recorded as ``History.noise_rms``.

Common scaling (``canonical``): the owner's convention for the sweep. Every history peaks at
``p_cap = amplitude_fraction * 1.33 * p_design``: the step is a plain step to the cap; for
``step_sine`` the step is ``0.5 p_cap`` and ``p_osc`` fills the rest so that the first positive
peak of the enveloped sine hits the cap; for ``step_noise`` the step is ``0.5 p_cap`` and the
noise is scaled so that the overall peak hits the cap.

Duration: lead-in + a transit allowance (the caller's, for the elbow-to-elbow delay) + the
decay time (``decay_cycles / f_osc``, ``decay_cycles / f_ref``; 0 for the plain step) +
``tail_s`` (default 2 s), rounded to whole samples. The generators are pure numpy and know
nothing about the solvers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "HISTORIES_VERSION",
    "KINDS",
    "DEFAULT_SAMPLE_FREQ",
    "DEFAULT_LEAD_IN_S",
    "DEFAULT_TAIL_S",
    "P_CAP_FACTOR",
    "History",
    "p_cap",
    "decay_rate",
    "envelope",
    "step",
    "step_sine",
    "step_noise",
    "canonical",
    "from_params",
]

HISTORIES_VERSION = "5b.1"
"""Version of the generators; a change to any waveform or scaling rule bumps it."""

KINDS = ("step", "step_sine", "step_noise")
DEFAULT_SAMPLE_FREQ = 1000.0
DEFAULT_LEAD_IN_S = 0.1
DEFAULT_TAIL_S = 2.0
P_CAP_FACTOR = 1.33
"""``P_CAP = 1.33 * p_design`` (the owner's convention)."""

PARAM_KEYS = (
    "kind",
    "sample_freq",
    "lead_in_s",
    "transit_s",
    "tail_s",
    "p_step",
    "p_osc",
    "f_osc",
    "p_noise_rms",
    "f_cut",
    "f_ref",
    "seed",
    "decay_cycles",
    "decay_fraction",
    "p_cap",
)
"""The keys of ``History.params()``; ``from_params`` takes exactly these."""


@dataclass(frozen=True)
class History:
    """A generated pressure history with its parameters and statistics.

    Attributes
    ----------
    kind : str
        ``"step"``, ``"step_sine"`` or ``"step_noise"``.
    time : numpy.ndarray
        Sample times, s, ``arange(n) / sample_freq``.
    pressure : numpy.ndarray
        Pressure, Pa, the same length.
    sample_freq, lead_in_s, transit_s, tail_s : float
        The sampling rate (Hz) and the three duration terms (s) the generator received.
    p_step : float
        Held step pressure, Pa.
    p_osc, f_osc : float or None
        Sine amplitude (Pa) and frequency (Hz); ``step_sine`` only.
    p_noise_rms, f_cut, f_ref, seed, p_cap : float / int / None
        ``step_noise`` only: the requested white-noise RMS (Pa, inert after the peak
        scaling), the low-pass cut-off (Hz, resolved), the envelope's reference frequency
        (Hz), the RNG seed and the peak target (Pa).
    decay_cycles, decay_fraction : float or None
        Envelope parameters (``step_sine`` and ``step_noise``).
    decay_s : float
        The decay term of the duration, s (0 for ``step``).
    duration_s : float
        ``lead_in_s + transit_s + decay_s + tail_s``, s.
    n_samples : int
        ``round(duration_s * sample_freq)``.
    peak, p_min, mean, rms : float
        ``max``, ``min``, mean and RMS of ``pressure`` over the whole history, Pa.
    noise_rms : float or None
        RMS of the scaled noise component over the active window (after the lead-in), Pa;
        ``step_noise`` only.
    version : str
        ``HISTORIES_VERSION``.
    """

    kind: str
    time: np.ndarray = field(repr=False, compare=False)
    pressure: np.ndarray = field(repr=False, compare=False)
    sample_freq: float
    lead_in_s: float
    transit_s: float
    tail_s: float
    p_step: float
    p_osc: float | None
    f_osc: float | None
    p_noise_rms: float | None
    f_cut: float | None
    f_ref: float | None
    seed: int | None
    decay_cycles: float | None
    decay_fraction: float | None
    p_cap: float | None
    decay_s: float
    duration_s: float
    n_samples: int
    peak: float
    p_min: float
    mean: float
    rms: float
    noise_rms: float | None
    version: str = HISTORIES_VERSION

    def params(self) -> dict:
        """The generator parameters (``PARAM_KEYS``), enough for ``from_params`` to rebuild
        the same arrays bitwise."""
        return {key: getattr(self, key) for key in PARAM_KEYS}

    def force(self, fluid_area: float) -> np.ndarray:
        """The force history the solvers take: ``pressure * fluid_area``, N."""
        return self.pressure * float(fluid_area)


# ------------------------------------------------------------------ building blocks


def p_cap(p_design: float, amplitude_fraction: float = 1.0) -> float:
    """``amplitude_fraction * P_CAP_FACTOR * p_design``, Pa."""
    return float(amplitude_fraction) * P_CAP_FACTOR * float(p_design)


def decay_rate(f: float, decay_cycles: float, decay_fraction: float) -> float:
    """The envelope rate ``lambda`` (1/s) with ``exp(-lambda decay_cycles / f) ==
    1 - decay_fraction``.

    Raises
    ------
    ValueError
        ``decay_fraction`` outside ``[0, 1)``, or ``f`` / ``decay_cycles`` not positive.
    """
    f = float(f)
    decay_cycles = float(decay_cycles)
    decay_fraction = float(decay_fraction)
    if not 0.0 <= decay_fraction < 1.0:
        raise ValueError(f"decay_fraction must be in [0, 1), got {decay_fraction!r}")
    if f <= 0.0 or decay_cycles <= 0.0:
        raise ValueError("f and decay_cycles must be positive")
    return -math.log(1.0 - decay_fraction) * f / decay_cycles


def envelope(tau, f: float, decay_cycles: float, decay_fraction: float) -> np.ndarray:
    """``exp(-decay_rate(f, decay_cycles, decay_fraction) * tau)``: 1 at ``tau = 0``,
    ``1 - decay_fraction`` at ``tau = decay_cycles / f``."""
    return np.exp(-decay_rate(f, decay_cycles, decay_fraction) * np.asarray(tau, dtype=float))


def _duration(lead_in_s: float, transit_s: float, decay_s: float, tail_s: float) -> float:
    for name, value in (
        ("lead_in_s", lead_in_s),
        ("transit_s", transit_s),
        ("decay_s", decay_s),
        ("tail_s", tail_s),
    ):
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative, got {value!r}")
    return lead_in_s + transit_s + decay_s + tail_s


def _axis(duration_s: float, sample_freq: float, lead_in_s: float):
    """``(time, n_lead)``: the sample times and the number of lead-in (zero) samples."""
    if sample_freq <= 0.0:
        raise ValueError(f"sample_freq must be positive, got {sample_freq!r}")
    n = int(round(duration_s * sample_freq))
    n_lead = int(round(lead_in_s * sample_freq))
    if n_lead >= n:
        raise ValueError("the history has no sample after the lead-in")
    return np.arange(n) / sample_freq, n_lead


def _stats(pressure: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(pressure.max()),
        float(pressure.min()),
        float(pressure.mean()),
        float(math.sqrt(float(np.mean(pressure * pressure)))),
    )


def _history(kind, time, pressure, decay_s, duration_s, noise_rms=None, **params) -> History:
    peak, p_min, mean, rms = _stats(pressure)
    return History(
        kind=kind,
        time=time,
        pressure=pressure,
        decay_s=float(decay_s),
        duration_s=float(duration_s),
        n_samples=int(time.shape[0]),
        peak=peak,
        p_min=p_min,
        mean=mean,
        rms=rms,
        noise_rms=noise_rms,
        **params,
    )


# ------------------------------------------------------------------ generators


def step(
    p_step: float,
    *,
    sample_freq: float = DEFAULT_SAMPLE_FREQ,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """Pressure 0 for the lead-in, then ``p_step`` held.

    Parameters
    ----------
    p_step : float
        Held pressure, Pa.
    sample_freq : float, optional
        Sample rate, Hz (default 1000).
    lead_in_s, transit_s, tail_s : float, optional
        Duration terms, s: the zero lead-in (default 0.1), the caller's transit allowance
        (default 0) and the tail (default 2).

    Returns
    -------
    History
    """
    p_step = float(p_step)
    sample_freq = float(sample_freq)
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    duration_s = _duration(lead_in_s, transit_s, 0.0, tail_s)
    time, n_lead = _axis(duration_s, sample_freq, lead_in_s)
    pressure = np.zeros_like(time)
    pressure[n_lead:] = p_step
    return _history(
        "step",
        time,
        pressure,
        0.0,
        duration_s,
        sample_freq=sample_freq,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=p_step,
        p_osc=None,
        f_osc=None,
        p_noise_rms=None,
        f_cut=None,
        f_ref=None,
        seed=None,
        decay_cycles=None,
        decay_fraction=None,
        p_cap=None,
    )


def _sine_shape(time, n_lead, f_osc, decay_cycles, decay_fraction) -> np.ndarray:
    """The unit enveloped sine: 0 over the lead-in, ``sin(2 pi f tau) envelope(tau)`` after,
    ``tau`` from the first held sample."""
    tau = time[n_lead:] - time[n_lead]
    u = np.zeros_like(time)
    u[n_lead:] = np.sin(2.0 * np.pi * f_osc * tau) * envelope(
        tau, f_osc, decay_cycles, decay_fraction
    )
    return u


def step_sine(
    p_step: float,
    p_osc: float,
    f_osc: float,
    decay_cycles: float = 10.0,
    decay_fraction: float = 0.8,
    *,
    sample_freq: float = DEFAULT_SAMPLE_FREQ,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus ``p_osc sin(2 pi f_osc tau)`` under the exponential envelope.

    Parameters
    ----------
    p_step : float
        Held pressure, Pa.
    p_osc : float
        Sine amplitude before the envelope, Pa.
    f_osc : float
        Sine frequency, Hz.
    decay_cycles, decay_fraction : float, optional
        The envelope reaches ``1 - decay_fraction`` (default 0.2) after ``decay_cycles``
        (default 10) cycles of ``f_osc``.
    sample_freq, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``decay_cycles / f_osc``.

    Returns
    -------
    History
    """
    p_step, p_osc, f_osc = float(p_step), float(p_osc), float(f_osc)
    decay_cycles, decay_fraction = float(decay_cycles), float(decay_fraction)
    sample_freq = float(sample_freq)
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    decay_s = decay_cycles / f_osc
    duration_s = _duration(lead_in_s, transit_s, decay_s, tail_s)
    time, n_lead = _axis(duration_s, sample_freq, lead_in_s)
    pressure = np.zeros_like(time)
    pressure[n_lead:] = p_step
    pressure = pressure + p_osc * _sine_shape(time, n_lead, f_osc, decay_cycles, decay_fraction)
    return _history(
        "step_sine",
        time,
        pressure,
        decay_s,
        duration_s,
        sample_freq=sample_freq,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=p_step,
        p_osc=p_osc,
        f_osc=f_osc,
        p_noise_rms=None,
        f_cut=None,
        f_ref=None,
        seed=None,
        decay_cycles=decay_cycles,
        decay_fraction=decay_fraction,
        p_cap=None,
    )


def _lowpass(w: np.ndarray, sample_freq: float, f_cut: float) -> np.ndarray:
    """FFT brick-wall low-pass: every bin above ``f_cut`` zeroed; a cut-off at or above the
    Nyquist frequency returns ``w`` unchanged."""
    if f_cut >= sample_freq / 2.0:
        return w
    spectrum = np.fft.rfft(w)
    freqs = np.fft.rfftfreq(w.shape[0], 1.0 / sample_freq)
    spectrum[freqs > f_cut] = 0.0
    return np.fft.irfft(spectrum, n=w.shape[0])


def step_noise(
    p_step: float,
    p_noise_rms: float,
    f_cut: float | None = None,
    seed: int = 0,
    decay_cycles: float = 10.0,
    decay_fraction: float = 0.8,
    *,
    f_ref: float,
    p_cap: float,
    sample_freq: float = DEFAULT_SAMPLE_FREQ,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus enveloped, low-passed Gaussian noise, peak-scaled to ``p_cap``.

    The noise is drawn with ``numpy.random.default_rng(seed).standard_normal`` over the
    active window (every sample after the lead-in), scaled to ``p_noise_rms``, low-passed at
    ``f_cut``, multiplied by the envelope defined on ``f_ref``, and finally scaled by
    ``(p_cap - p_step) / max(noise)`` so that ``max(pressure) == p_cap``. Because the last
    step is a ratio, ``p_noise_rms`` has no effect on the result; it is kept as the
    generator's input and the resulting RMS of the noise over the active window is
    ``History.noise_rms``.

    Parameters
    ----------
    p_step : float
        Held pressure, Pa.
    p_noise_rms : float
        Requested white-noise RMS before the scaling, Pa (inert, see above).
    f_cut : float or None, optional
        Low-pass cut-off, Hz; None (default) is the Nyquist frequency ``sample_freq / 2``
        (no filtering).
    seed : int, optional
        RNG seed (default 0).
    decay_cycles, decay_fraction : float, optional
        As ``step_sine``, on the period ``1 / f_ref``.
    f_ref : float, keyword-only
        Reference frequency of the envelope, Hz.
    p_cap : float, keyword-only
        The peak the scaled history reaches, Pa (``> p_step``).
    sample_freq, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``decay_cycles / f_ref``.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        ``p_cap <= p_step``, or an enveloped noise whose maximum is not positive.
    """
    p_step, p_noise_rms, f_ref, p_cap = (
        float(p_step),
        float(p_noise_rms),
        float(f_ref),
        float(p_cap),
    )
    sample_freq = float(sample_freq)
    f_cut = sample_freq / 2.0 if f_cut is None else float(f_cut)
    seed = int(seed)
    decay_cycles, decay_fraction = float(decay_cycles), float(decay_fraction)
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    if p_cap <= p_step:
        raise ValueError(f"p_cap ({p_cap!r}) must exceed p_step ({p_step!r})")
    decay_s = decay_cycles / f_ref
    duration_s = _duration(lead_in_s, transit_s, decay_s, tail_s)
    time, n_lead = _axis(duration_s, sample_freq, lead_in_s)
    tau = time[n_lead:] - time[n_lead]
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(tau.shape[0]) * p_noise_rms
    w = _lowpass(w, sample_freq, f_cut)
    w = w * envelope(tau, f_ref, decay_cycles, decay_fraction)
    w_max = float(w.max())
    if not w_max > 0.0:
        raise ValueError("the enveloped noise has no positive sample to scale on")
    noise = w * ((p_cap - p_step) / w_max)
    pressure = np.zeros_like(time)
    pressure[n_lead:] = p_step + noise
    noise_rms = float(math.sqrt(float(np.mean(noise * noise))))
    return _history(
        "step_noise",
        time,
        pressure,
        decay_s,
        duration_s,
        noise_rms=noise_rms,
        sample_freq=sample_freq,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=p_step,
        p_osc=None,
        f_osc=None,
        p_noise_rms=p_noise_rms,
        f_cut=f_cut,
        f_ref=f_ref,
        seed=seed,
        decay_cycles=decay_cycles,
        decay_fraction=decay_fraction,
        p_cap=p_cap,
    )


# ------------------------------------------------------------------ the sweep's scaling


def canonical(
    kind: str,
    p_design: float,
    amplitude_fraction: float,
    *,
    f_osc: float | None = None,
    seed: int | None = None,
    f_ref: float | None = None,
    f_cut: float | None = None,
    p_noise_rms: float = 1.0,
    decay_cycles: float = 10.0,
    decay_fraction: float = 0.8,
    sample_freq: float = DEFAULT_SAMPLE_FREQ,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """A history of ``kind`` under the sweep's common scaling: peak ``amplitude_fraction *
    1.33 * p_design``.

    ``"step"`` is a plain step to the cap. ``"step_sine"`` (needs ``f_osc``) holds
    ``0.5 cap`` and sets ``p_osc`` so that the first positive peak of the enveloped sine
    hits the cap. ``"step_noise"`` (needs ``seed`` and ``f_ref``) holds ``0.5 cap`` and
    scales the noise so that the overall peak hits the cap. The returned ``History.params()``
    rebuilds the same arrays through ``from_params``.

    Parameters
    ----------
    kind : str
        One of ``KINDS``.
    p_design : float
        Design pressure, Pa.
    amplitude_fraction : float
        Peak as a fraction of ``1.33 * p_design``.
    f_osc, seed, f_ref, f_cut, p_noise_rms, decay_cycles, decay_fraction
        Passed to the generator (see each one).
    sample_freq, lead_in_s, transit_s, tail_s : float, optional
        As the generators.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        Unknown ``kind`` or a missing frequency / seed.
    """
    cap = p_cap(p_design, amplitude_fraction)
    common = {
        "sample_freq": sample_freq,
        "lead_in_s": lead_in_s,
        "transit_s": transit_s,
        "tail_s": tail_s,
    }
    if kind == "step":
        return step(cap, **common)
    if kind == "step_sine":
        if f_osc is None:
            raise ValueError("step_sine needs f_osc")
        p_step = 0.5 * cap
        probe = step_sine(0.0, 1.0, f_osc, decay_cycles, decay_fraction, **common)
        p_osc = (cap - p_step) / probe.peak
        return step_sine(p_step, p_osc, f_osc, decay_cycles, decay_fraction, **common)
    if kind == "step_noise":
        if seed is None or f_ref is None:
            raise ValueError("step_noise needs seed and f_ref")
        return step_noise(
            0.5 * cap,
            p_noise_rms,
            f_cut,
            seed,
            decay_cycles,
            decay_fraction,
            f_ref=f_ref,
            p_cap=cap,
            **common,
        )
    raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")


def from_params(params: dict) -> History:
    """Rebuild a history from ``History.params()`` (the ``PARAM_KEYS``; a key missing or
    None is the generator's default where it has one).

    Raises
    ------
    ValueError
        Unknown ``kind``, or a key outside ``PARAM_KEYS``.
    """
    unknown = set(params) - set(PARAM_KEYS)
    if unknown:
        raise ValueError(f"unknown history parameters {sorted(unknown)}")
    p = {key: params.get(key) for key in PARAM_KEYS}
    common = {
        "sample_freq": DEFAULT_SAMPLE_FREQ if p["sample_freq"] is None else p["sample_freq"],
        "lead_in_s": DEFAULT_LEAD_IN_S if p["lead_in_s"] is None else p["lead_in_s"],
        "transit_s": 0.0 if p["transit_s"] is None else p["transit_s"],
        "tail_s": DEFAULT_TAIL_S if p["tail_s"] is None else p["tail_s"],
    }
    kind = p["kind"]
    if kind == "step":
        return step(p["p_step"], **common)
    if kind == "step_sine":
        return step_sine(
            p["p_step"], p["p_osc"], p["f_osc"], p["decay_cycles"], p["decay_fraction"], **common
        )
    if kind == "step_noise":
        return step_noise(
            p["p_step"],
            p["p_noise_rms"],
            p["f_cut"],
            p["seed"],
            p["decay_cycles"],
            p["decay_fraction"],
            f_ref=p["f_ref"],
            p_cap=p["p_cap"],
            **common,
        )
    raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
