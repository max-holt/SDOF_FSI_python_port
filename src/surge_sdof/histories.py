"""Canonical pressure histories for the junction-coupling sweep (Session 5b).

Three deterministic generators return a ``History``: a ``(time, pressure)`` pair sampled at
``sample_freq`` (default 1000 Hz) together with every generator parameter, so that a row of
the sweep CSV reproduces its history bitwise through ``from_params``. The solvers take a
*force* history: ``History.force(fluid_area)`` is the pressure times the pipe's fluid area.

* ``step(step_pressure)``: pressure 0 for the lead-in (``lead_in_s``, default 0.1 s), then
  ``step_pressure`` held to the end.
* ``step_sine(step_pressure, oscillation_amplitude, oscillation_frequency,
  envelope_decay_cycles, envelope_decay_fraction)``: the step plus ``oscillation_amplitude
  sin(2 pi oscillation_frequency tau)`` under an exponential envelope, ``tau`` counted from
  the first held sample. The envelope is ``exp(-lambda tau)`` with ``lambda`` chosen so that
  it equals ``1 - envelope_decay_fraction`` after ``envelope_decay_cycles`` cycles
  (``envelope``).
* ``step_noise(step_pressure, requested_noise_rms, noise_cutoff_frequency, noise_seed,
  envelope_decay_cycles, envelope_decay_fraction, envelope_reference_frequency,
  peak_pressure_target)``: the step plus Gaussian white noise
  (``numpy.random.default_rng(noise_seed)``, RMS ``requested_noise_rms``) low-passed at
  ``noise_cutoff_frequency`` (an FFT brick wall; the default, the Nyquist frequency, filters
  nothing), under the same envelope defined on the period ``1 /
  envelope_reference_frequency``, then peak-scaled so that ``max(pressure) ==
  peak_pressure_target``. The requested RMS drops out of the result (the scaling is a
  ratio); the RMS of the scaled noise over the active window is recorded as
  ``History.noise_rms``.

``History`` keeps the short field names (``p_step``, ``f_osc``, ``p_cap``, ...: the
``PARAM_KEYS``, which are also sweep columns) until the public API session; ``canonical`` and
``from_params`` keep their keywords until then too.

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
    "HISTORY_TYPES",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_LEAD_IN_S",
    "DEFAULT_TAIL_S",
    "PEAK_TO_DESIGN_PRESSURE_RATIO",
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

HISTORY_TYPES = ("step", "step_sine", "step_noise")
DEFAULT_SAMPLE_RATE = 1000.0
DEFAULT_LEAD_IN_S = 0.1
DEFAULT_TAIL_S = 2.0
# For Ben to confirm: the basis of 1.33 (set by the lead author on 22 Oct 2026).
PEAK_TO_DESIGN_PRESSURE_RATIO = 1.33
"""The sweep's peak pressure as a multiple of the design pressure, dimensionless:
``p_cap = amplitude_fraction * PEAK_TO_DESIGN_PRESSURE_RATIO * p_design``. Set by the lead
author on 22 Oct 2026."""

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
    """``amplitude_fraction * PEAK_TO_DESIGN_PRESSURE_RATIO * p_design``, Pa."""
    return float(amplitude_fraction) * PEAK_TO_DESIGN_PRESSURE_RATIO * float(p_design)


def decay_rate(
    frequency: float, envelope_decay_cycles: float, envelope_decay_fraction: float
) -> float:
    """The envelope rate ``lambda`` (1/s) with ``exp(-lambda decay_cycles / f) ==
    1 - decay_fraction``.

    Raises
    ------
    ValueError
        ``envelope_decay_fraction`` outside ``[0, 1)``, or ``frequency`` / ``envelope_decay_cycles`` not positive.
    """
    frequency = float(frequency)
    envelope_decay_cycles = float(envelope_decay_cycles)
    envelope_decay_fraction = float(envelope_decay_fraction)
    if not 0.0 <= envelope_decay_fraction < 1.0:
        raise ValueError(f"decay_fraction must be in [0, 1), got {envelope_decay_fraction!r}")
    if frequency <= 0.0 or envelope_decay_cycles <= 0.0:
        raise ValueError("f and decay_cycles must be positive")
    return -math.log(1.0 - envelope_decay_fraction) * frequency / envelope_decay_cycles


def envelope(
    time_since_lead_in,
    frequency: float,
    envelope_decay_cycles: float,
    envelope_decay_fraction: float,
) -> np.ndarray:
    """``exp(-decay_rate(f, decay_cycles, decay_fraction) * tau)``: 1 at ``tau = 0``,
    ``1 - decay_fraction`` at ``tau = decay_cycles / f``."""
    return np.exp(
        -decay_rate(frequency, envelope_decay_cycles, envelope_decay_fraction)
        * np.asarray(time_since_lead_in, dtype=float)
    )


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


def _axis(duration_s: float, sample_rate: float, lead_in_s: float):
    """``(time, n_lead)``: the sample times and the number of lead-in (zero) samples."""
    if sample_rate <= 0.0:
        raise ValueError(f"sample_freq must be positive, got {sample_rate!r}")
    sample_count = int(round(duration_s * sample_rate))
    lead_in_sample_count = int(round(lead_in_s * sample_rate))
    if lead_in_sample_count >= sample_count:
        raise ValueError("the history has no sample after the lead-in")
    return np.arange(sample_count) / sample_rate, lead_in_sample_count


def _stats(pressure: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(pressure.max()),
        float(pressure.min()),
        float(pressure.mean()),
        float(math.sqrt(float(np.mean(pressure * pressure)))),
    )


def _history(
    history_type, time, pressure, decay_s, duration_s, noise_rms=None, **params
) -> History:
    peak, p_min, mean, rms = _stats(pressure)
    return History(
        kind=history_type,
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
    step_pressure: float,
    *,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """Pressure 0 for the lead-in, then ``step_pressure`` held.

    Parameters
    ----------
    step_pressure : float
        Held pressure, Pa.
    sample_rate : float, optional
        Sample rate, Hz (default 1000).
    lead_in_s, transit_s, tail_s : float, optional
        Duration terms, s: the zero lead-in (default 0.1), the caller's transit allowance
        (default 0) and the tail (default 2).

    Returns
    -------
    History
    """
    step_pressure = float(step_pressure)
    sample_rate = float(sample_rate)
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    duration_s = _duration(lead_in_s, transit_s, 0.0, tail_s)
    time, lead_in_sample_count = _axis(duration_s, sample_rate, lead_in_s)
    pressure = np.zeros_like(time)
    pressure[lead_in_sample_count:] = step_pressure
    return _history(
        "step",
        time,
        pressure,
        0.0,
        duration_s,
        sample_freq=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=step_pressure,
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


def _sine_shape(
    time,
    lead_in_sample_count,
    oscillation_frequency,
    envelope_decay_cycles,
    envelope_decay_fraction,
) -> np.ndarray:
    """The unit enveloped sine: 0 over the lead-in, ``sin(2 pi f tau) envelope(tau)`` after,
    ``time_since_lead_in`` from the first held sample."""
    time_since_lead_in = time[lead_in_sample_count:] - time[lead_in_sample_count]
    unit_sine = np.zeros_like(time)
    unit_sine[lead_in_sample_count:] = np.sin(
        2.0 * np.pi * oscillation_frequency * time_since_lead_in
    ) * envelope(
        time_since_lead_in, oscillation_frequency, envelope_decay_cycles, envelope_decay_fraction
    )
    return unit_sine


def step_sine(
    step_pressure: float,
    oscillation_amplitude: float,
    oscillation_frequency: float,
    envelope_decay_cycles: float = 10.0,
    envelope_decay_fraction: float = 0.8,
    *,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus ``p_osc sin(2 pi f_osc tau)`` under the exponential envelope.

    Parameters
    ----------
    step_pressure : float
        Held pressure, Pa.
    oscillation_amplitude : float
        Sine amplitude before the envelope, Pa.
    oscillation_frequency : float
        Sine frequency, Hz.
    envelope_decay_cycles, envelope_decay_fraction : float, optional
        The envelope falls by ``envelope_decay_fraction`` (default 0.8), to ``1 - decay_fraction``
        (0.2 by default), after ``envelope_decay_cycles`` (default 10) cycles of ``oscillation_frequency``.
    sample_rate, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``decay_cycles / f_osc``.

    Returns
    -------
    History
    """
    step_pressure, oscillation_amplitude, oscillation_frequency = (
        float(step_pressure),
        float(oscillation_amplitude),
        float(oscillation_frequency),
    )
    envelope_decay_cycles, envelope_decay_fraction = (
        float(envelope_decay_cycles),
        float(envelope_decay_fraction),
    )
    sample_rate = float(sample_rate)
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    decay_s = envelope_decay_cycles / oscillation_frequency
    duration_s = _duration(lead_in_s, transit_s, decay_s, tail_s)
    time, lead_in_sample_count = _axis(duration_s, sample_rate, lead_in_s)
    pressure = np.zeros_like(time)
    pressure[lead_in_sample_count:] = step_pressure
    pressure = pressure + oscillation_amplitude * _sine_shape(
        time,
        lead_in_sample_count,
        oscillation_frequency,
        envelope_decay_cycles,
        envelope_decay_fraction,
    )
    return _history(
        "step_sine",
        time,
        pressure,
        decay_s,
        duration_s,
        sample_freq=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=step_pressure,
        p_osc=oscillation_amplitude,
        f_osc=oscillation_frequency,
        p_noise_rms=None,
        f_cut=None,
        f_ref=None,
        seed=None,
        decay_cycles=envelope_decay_cycles,
        decay_fraction=envelope_decay_fraction,
        p_cap=None,
    )


def _lowpass(noise: np.ndarray, sample_rate: float, noise_cutoff_frequency: float) -> np.ndarray:
    """FFT brick-wall low-pass: every bin above ``noise_cutoff_frequency`` zeroed; a cut-off at or above the
    Nyquist frequency returns ``noise`` unchanged."""
    if noise_cutoff_frequency >= sample_rate / 2.0:
        return noise
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(noise.shape[0], 1.0 / sample_rate)
    spectrum[freqs > noise_cutoff_frequency] = 0.0
    return np.fft.irfft(spectrum, n=noise.shape[0])


def step_noise(
    step_pressure: float,
    requested_noise_rms: float,
    noise_cutoff_frequency: float | None = None,
    noise_seed: int = 0,
    envelope_decay_cycles: float = 10.0,
    envelope_decay_fraction: float = 0.8,
    *,
    envelope_reference_frequency: float,
    peak_pressure_target: float,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus enveloped, low-passed Gaussian noise, peak-scaled to ``peak_pressure_target``.

    The noise is drawn with ``numpy.random.default_rng(seed).standard_normal`` over the
    active window (every sample after the lead-in), scaled to ``requested_noise_rms``, low-passed at
    ``noise_cutoff_frequency``, multiplied by the envelope defined on ``envelope_reference_frequency``, and finally scaled by
    ``(p_cap - p_step) / max(noise)`` so that ``max(pressure) == p_cap``. Because the last
    step is a ratio, ``requested_noise_rms`` has no effect on the result; it is kept as the
    generator's input and the resulting RMS of the noise over the active window is
    ``History.noise_rms``.

    Parameters
    ----------
    step_pressure : float
        Held pressure, Pa.
    requested_noise_rms : float
        Requested white-noise RMS before the scaling, Pa (inert, see above).
    noise_cutoff_frequency : float or None, optional
        Low-pass cut-off, Hz; None (default) is the Nyquist frequency ``sample_freq / 2``
        (no filtering).
    noise_seed : int, optional
        RNG seed (default 0).
    envelope_decay_cycles, envelope_decay_fraction : float, optional
        As ``step_sine``, on the period ``1 / f_ref``.
    envelope_reference_frequency : float, keyword-only
        Reference frequency of the envelope, Hz.
    peak_pressure_target : float, keyword-only
        The peak the scaled history reaches, Pa (``> p_step``).
    sample_rate, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``decay_cycles / f_ref``.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        ``p_cap <= p_step``, or an enveloped noise whose maximum is not positive.
    """
    step_pressure, requested_noise_rms, envelope_reference_frequency, peak_pressure_target = (
        float(step_pressure),
        float(requested_noise_rms),
        float(envelope_reference_frequency),
        float(peak_pressure_target),
    )
    sample_rate = float(sample_rate)
    noise_cutoff_frequency = (
        sample_rate / 2.0 if noise_cutoff_frequency is None else float(noise_cutoff_frequency)
    )
    noise_seed = int(noise_seed)
    envelope_decay_cycles, envelope_decay_fraction = (
        float(envelope_decay_cycles),
        float(envelope_decay_fraction),
    )
    lead_in_s, transit_s, tail_s = float(lead_in_s), float(transit_s), float(tail_s)
    if peak_pressure_target <= step_pressure:
        raise ValueError(f"p_cap ({peak_pressure_target!r}) must exceed p_step ({step_pressure!r})")
    decay_s = envelope_decay_cycles / envelope_reference_frequency
    duration_s = _duration(lead_in_s, transit_s, decay_s, tail_s)
    time, lead_in_sample_count = _axis(duration_s, sample_rate, lead_in_s)
    time_since_lead_in = time[lead_in_sample_count:] - time[lead_in_sample_count]
    rng = np.random.default_rng(noise_seed)
    noise = rng.standard_normal(time_since_lead_in.shape[0]) * requested_noise_rms
    noise = _lowpass(noise, sample_rate, noise_cutoff_frequency)
    noise = noise * envelope(
        time_since_lead_in,
        envelope_reference_frequency,
        envelope_decay_cycles,
        envelope_decay_fraction,
    )
    noise_max = float(noise.max())
    if not noise_max > 0.0:
        raise ValueError("the enveloped noise has no positive sample to scale on")
    scaled_noise = noise * ((peak_pressure_target - step_pressure) / noise_max)
    pressure = np.zeros_like(time)
    pressure[lead_in_sample_count:] = step_pressure + scaled_noise
    noise_rms = float(math.sqrt(float(np.mean(scaled_noise * scaled_noise))))
    return _history(
        "step_noise",
        time,
        pressure,
        decay_s,
        duration_s,
        noise_rms=noise_rms,
        sample_freq=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        p_step=step_pressure,
        p_osc=None,
        f_osc=None,
        p_noise_rms=requested_noise_rms,
        f_cut=noise_cutoff_frequency,
        f_ref=envelope_reference_frequency,
        seed=noise_seed,
        decay_cycles=envelope_decay_cycles,
        decay_fraction=envelope_decay_fraction,
        p_cap=peak_pressure_target,
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
    sample_freq: float = DEFAULT_SAMPLE_RATE,
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
        One of ``HISTORY_TYPES``.
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
    peak_pressure_target = p_cap(p_design, amplitude_fraction)
    shared_arguments = {
        "sample_rate": sample_freq,
        "lead_in_s": lead_in_s,
        "transit_s": transit_s,
        "tail_s": tail_s,
    }
    if kind == "step":
        return step(peak_pressure_target, **shared_arguments)
    if kind == "step_sine":
        if f_osc is None:
            raise ValueError("step_sine needs f_osc")
        p_step = 0.5 * peak_pressure_target
        unit_sine_history = step_sine(
            0.0, 1.0, f_osc, decay_cycles, decay_fraction, **shared_arguments
        )
        p_osc = (peak_pressure_target - p_step) / unit_sine_history.peak
        return step_sine(p_step, p_osc, f_osc, decay_cycles, decay_fraction, **shared_arguments)
    if kind == "step_noise":
        if seed is None or f_ref is None:
            raise ValueError("step_noise needs seed and f_ref")
        return step_noise(
            0.5 * peak_pressure_target,
            p_noise_rms,
            f_cut,
            seed,
            decay_cycles,
            decay_fraction,
            envelope_reference_frequency=f_ref,
            peak_pressure_target=peak_pressure_target,
            **shared_arguments,
        )
    raise ValueError(f"kind must be one of {HISTORY_TYPES}, got {kind!r}")


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
    parameter_values = {key: params.get(key) for key in PARAM_KEYS}
    shared_arguments = {
        "sample_rate": DEFAULT_SAMPLE_RATE
        if parameter_values["sample_freq"] is None
        else parameter_values["sample_freq"],
        "lead_in_s": DEFAULT_LEAD_IN_S
        if parameter_values["lead_in_s"] is None
        else parameter_values["lead_in_s"],
        "transit_s": 0.0
        if parameter_values["transit_s"] is None
        else parameter_values["transit_s"],
        "tail_s": DEFAULT_TAIL_S
        if parameter_values["tail_s"] is None
        else parameter_values["tail_s"],
    }
    kind = parameter_values["kind"]
    if kind == "step":
        return step(parameter_values["p_step"], **shared_arguments)
    if kind == "step_sine":
        return step_sine(
            parameter_values["p_step"],
            parameter_values["p_osc"],
            parameter_values["f_osc"],
            parameter_values["decay_cycles"],
            parameter_values["decay_fraction"],
            **shared_arguments,
        )
    if kind == "step_noise":
        return step_noise(
            parameter_values["p_step"],
            parameter_values["p_noise_rms"],
            parameter_values["f_cut"],
            parameter_values["seed"],
            parameter_values["decay_cycles"],
            parameter_values["decay_fraction"],
            envelope_reference_frequency=parameter_values["f_ref"],
            peak_pressure_target=parameter_values["p_cap"],
            **shared_arguments,
        )
    raise ValueError(f"kind must be one of {HISTORY_TYPES}, got {kind!r}")
