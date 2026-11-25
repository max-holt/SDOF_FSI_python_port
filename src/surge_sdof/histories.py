"""Canonical pressure histories for the junction-coupling sweep (Session 5b).

Three deterministic generators return a ``History``: a ``(time, pressure)`` pair sampled at
``sample_rate`` (default 1000 Hz) together with every generator parameter, so that a row of
the sweep CSV reproduces its history bitwise through ``from_params``. The solvers take a
*force* history: ``History.force(flow_area)`` is the pressure times the pipe's flow area.

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
  ``History.scaled_noise_rms``.

Common scaling (``canonical``): the owner's convention for the sweep. Every history peaks at
``peak_pressure_target = amplitude_fraction * 1.33 * design_pressure``: the step is a plain
step to the target; for ``step_sine`` the step is half the target and the oscillation
amplitude fills the rest so that the first positive peak of the enveloped sine hits the
target; for ``step_noise`` the step is half the target and the noise is scaled so that the
overall peak hits the target.

Duration: lead-in + a transit allowance (the caller's, for the elbow-to-elbow delay) + the
decay time (``envelope_decay_cycles / oscillation_frequency``, ``envelope_decay_cycles /
envelope_reference_frequency``; 0 for the plain step) + ``tail_s`` (default 2 s), rounded to
whole samples. The generators are pure numpy and know
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
    "peak_pressure_target",
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
STEP_TO_PEAK_RATIO = 0.5
"""The held step of the ``step_sine`` and ``step_noise`` sweep histories as a fraction of
their peak, dimensionless (``canonical``: the step holds ``0.5 cap``; docs/data_format.md
``p_step``). The sweep's convention; its basis is not recorded in the code or the documents."""
DEFAULT_ENVELOPE_DECAY_CYCLES = 10.0
"""Default cycles (of the oscillation or the noise reference frequency) over which the
envelope of ``step_sine`` and ``step_noise`` falls by its decay fraction.
The sweep's convention."""
DEFAULT_ENVELOPE_DECAY_FRACTION = 0.8
"""Default fall of that envelope over ``DEFAULT_ENVELOPE_DECAY_CYCLES``, dimensionless: it
reaches ``1 - 0.8 = 0.2`` of its start. The sweep's convention."""

PARAM_KEYS = (
    "history_type",
    "sample_rate",
    "lead_in_s",
    "transit_s",
    "tail_s",
    "step_pressure",
    "oscillation_amplitude",
    "oscillation_frequency",
    "requested_noise_rms",
    "noise_cutoff_frequency",
    "envelope_reference_frequency",
    "noise_seed",
    "envelope_decay_cycles",
    "envelope_decay_fraction",
    "peak_pressure_target",
)
"""The keys of ``History.params()``; ``from_params`` takes exactly these."""


@dataclass(frozen=True)
class History:
    """A generated pressure history with its parameters and statistics.

    Attributes
    ----------
    history_type : str
        ``"step"``, ``"step_sine"`` or ``"step_noise"``.
    time : numpy.ndarray
        float64, shape ``(sample_count,)``: sample times, s, ``arange(n) / sample_rate``.
    pressure : numpy.ndarray
        float64, the same shape: pressure, Pa.
    sample_rate, lead_in_s, transit_s, tail_s : float
        The sample rate (Hz) and the three duration terms (s) the generator received.
    step_pressure : float
        Held step pressure, Pa.
    oscillation_amplitude, oscillation_frequency : float or None
        Sine amplitude (Pa) and frequency (Hz); ``step_sine`` only.
    requested_noise_rms, noise_cutoff_frequency, envelope_reference_frequency, noise_seed, \
peak_pressure_target : float / int / None
        ``step_noise`` only: the requested white-noise RMS (Pa, inert after the peak
        scaling), the low-pass cut-off (Hz, resolved), the envelope's reference frequency
        (Hz), the RNG seed and the peak target (Pa).
    envelope_decay_cycles, envelope_decay_fraction : float or None
        Envelope parameters (``step_sine`` and ``step_noise``).
    decay_s : float
        The decay term of the duration, s (0 for ``step``).
    duration_s : float
        ``lead_in_s + transit_s + decay_s + tail_s``, s.
    sample_count : int
        ``round(duration_s * sample_rate)``.
    pressure_max, pressure_min, pressure_mean, pressure_rms : float
        ``max``, ``min``, mean and RMS of ``pressure`` over the whole history, Pa.
    scaled_noise_rms : float or None
        RMS of the scaled noise component over the active window (after the lead-in), Pa;
        ``step_noise`` only.
    version : str
        ``HISTORIES_VERSION``.
    """

    history_type: str
    time: np.ndarray = field(repr=False, compare=False)
    pressure: np.ndarray = field(repr=False, compare=False)
    sample_rate: float
    lead_in_s: float
    transit_s: float
    tail_s: float
    step_pressure: float
    oscillation_amplitude: float | None
    oscillation_frequency: float | None
    requested_noise_rms: float | None
    noise_cutoff_frequency: float | None
    envelope_reference_frequency: float | None
    noise_seed: int | None
    envelope_decay_cycles: float | None
    envelope_decay_fraction: float | None
    peak_pressure_target: float | None
    decay_s: float
    duration_s: float
    sample_count: int
    pressure_max: float
    pressure_min: float
    pressure_mean: float
    pressure_rms: float
    scaled_noise_rms: float | None
    version: str = HISTORIES_VERSION

    def params(self) -> dict:
        """The generator parameters, enough for ``from_params`` to rebuild the same arrays
        bitwise.

        Returns
        -------
        dict
            Keyed by ``PARAM_KEYS``; a parameter the generator does not take is None.
        """
        return {key: getattr(self, key) for key in PARAM_KEYS}

    def force(self, flow_area: float) -> np.ndarray:
        """The force history the solvers take.

        Parameters
        ----------
        flow_area : float
            Internal cross-sectional area of the pipe, m².

        Returns
        -------
        numpy.ndarray
            float64, shape ``(sample_count,)``: ``pressure * flow_area``, N.
        """
        return self.pressure * float(flow_area)


# ------------------------------------------------------------------ building blocks


def peak_pressure_target(design_pressure: float, amplitude_fraction: float = 1.0) -> float:
    """The peak pressure of the sweep's common scaling.

    Parameters
    ----------
    design_pressure : float
        Design pressure, Pa.
    amplitude_fraction : float, optional
        The peak as a fraction of ``PEAK_TO_DESIGN_PRESSURE_RATIO * design_pressure``
        (default 1).

    Returns
    -------
    float
        ``amplitude_fraction * PEAK_TO_DESIGN_PRESSURE_RATIO * design_pressure``, Pa.
    """
    return float(amplitude_fraction) * PEAK_TO_DESIGN_PRESSURE_RATIO * float(design_pressure)


def decay_rate(
    frequency: float, envelope_decay_cycles: float, envelope_decay_fraction: float
) -> float:
    """The decay rate of the exponential envelope.

    Parameters
    ----------
    frequency : float
        The frequency whose cycles the decay is counted in, Hz.
    envelope_decay_cycles : float
        Cycles over which the envelope falls by ``envelope_decay_fraction``.
    envelope_decay_fraction : float
        The fall, dimensionless, in ``[0, 1)``.

    Returns
    -------
    float
        ``lambda``, 1/s, with ``exp(-lambda envelope_decay_cycles / frequency) == 1 -
        envelope_decay_fraction``.

    Raises
    ------
    ValueError
        ``envelope_decay_fraction`` outside ``[0, 1)``, or ``frequency`` /
        ``envelope_decay_cycles`` not positive.
    """
    frequency = float(frequency)
    envelope_decay_cycles = float(envelope_decay_cycles)
    envelope_decay_fraction = float(envelope_decay_fraction)
    if not 0.0 <= envelope_decay_fraction < 1.0:
        raise ValueError(
            f"envelope_decay_fraction must be in [0, 1), got {envelope_decay_fraction!r}"
        )
    if frequency <= 0.0 or envelope_decay_cycles <= 0.0:
        raise ValueError("frequency and envelope_decay_cycles must be positive")
    return -math.log(1.0 - envelope_decay_fraction) * frequency / envelope_decay_cycles


def envelope(
    time_since_lead_in,
    frequency: float,
    envelope_decay_cycles: float,
    envelope_decay_fraction: float,
) -> np.ndarray:
    """The exponential envelope over the time since the lead-in.

    Parameters
    ----------
    time_since_lead_in : array_like
        ``tau``, s.
    frequency, envelope_decay_cycles, envelope_decay_fraction : float
        As ``decay_rate``.

    Returns
    -------
    numpy.ndarray
        float64, the shape of ``time_since_lead_in``, dimensionless:
        ``exp(-decay_rate(...) * tau)``, 1 at ``tau = 0`` and ``1 -
        envelope_decay_fraction`` at ``tau = envelope_decay_cycles / frequency``.
    """
    return np.exp(
        -decay_rate(frequency, envelope_decay_cycles, envelope_decay_fraction)
        * np.asarray(time_since_lead_in, dtype=float)
    )


def _duration(lead_in_s: float, transit_s: float, decay_s: float, tail_s: float) -> float:
    """The history's duration, s: the sum of the four duration terms (s), each checked
    non-negative (``ValueError`` names the first that is not)."""
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
    """The sample times (s, float64, shape ``(sample_count,)``) and the number of lead-in
    (zero) samples of a history of ``duration_s`` (s) at ``sample_rate`` (Hz).

    Raises
    ------
    ValueError
        ``sample_rate`` not positive, or no sample after the lead-in.
    """
    if sample_rate <= 0.0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate!r}")
    sample_count = int(round(duration_s * sample_rate))
    lead_in_sample_count = int(round(lead_in_s * sample_rate))
    if lead_in_sample_count >= sample_count:
        raise ValueError("the history has no sample after the lead-in")
    return np.arange(sample_count) / sample_rate, lead_in_sample_count


def _stats(pressure: np.ndarray) -> tuple[float, float, float, float]:
    """Maximum, minimum, mean and RMS of a pressure history (Pa), as Python floats."""
    return (
        float(pressure.max()),
        float(pressure.min()),
        float(pressure.mean()),
        float(math.sqrt(float(np.mean(pressure * pressure)))),
    )


_KIND_SPECIFIC_PARAMS = (
    "oscillation_amplitude",
    "oscillation_frequency",
    "requested_noise_rms",
    "noise_cutoff_frequency",
    "envelope_reference_frequency",
    "noise_seed",
    "envelope_decay_cycles",
    "envelope_decay_fraction",
    "peak_pressure_target",
)
"""The ``History`` parameters only some generators set; ``_history`` defaults them to None."""


def _history(
    history_type, time, pressure, decay_s, duration_s, scaled_noise_rms=None, **params
) -> History:
    """The ``History`` of a generated pressure: its statistics, and ``params`` with every
    kind-specific parameter the generator does not set as None."""
    params = {**dict.fromkeys(_KIND_SPECIFIC_PARAMS), **params}
    pressure_max, pressure_min, pressure_mean, pressure_rms = _stats(pressure)
    return History(
        history_type=history_type,
        time=time,
        pressure=pressure,
        decay_s=float(decay_s),
        duration_s=float(duration_s),
        sample_count=int(time.shape[0]),
        pressure_max=pressure_max,
        pressure_min=pressure_min,
        pressure_mean=pressure_mean,
        pressure_rms=pressure_rms,
        scaled_noise_rms=scaled_noise_rms,
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
        sample_rate=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        step_pressure=step_pressure,
    )


def _sine_shape(
    time,
    lead_in_sample_count,
    oscillation_frequency,
    envelope_decay_cycles,
    envelope_decay_fraction,
) -> np.ndarray:
    """The unit enveloped sine on the sample times ``time`` (s): 0 over the lead-in,
    ``sin(2 pi oscillation_frequency tau) envelope(tau)`` after, ``tau`` counted from the
    first held sample; dimensionless, the shape of ``time``."""
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
    envelope_decay_cycles: float = DEFAULT_ENVELOPE_DECAY_CYCLES,
    envelope_decay_fraction: float = DEFAULT_ENVELOPE_DECAY_FRACTION,
    *,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus a sine of ``oscillation_amplitude`` under the exponential envelope.

    Parameters
    ----------
    step_pressure : float
        Held pressure, Pa.
    oscillation_amplitude : float
        Sine amplitude before the envelope, Pa.
    oscillation_frequency : float
        Sine frequency, Hz.
    envelope_decay_cycles, envelope_decay_fraction : float, optional
        The envelope falls by ``envelope_decay_fraction`` (default 0.8), to ``1 -
        envelope_decay_fraction`` (0.2 by default), after ``envelope_decay_cycles`` (default
        10) cycles of ``oscillation_frequency``.
    sample_rate, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``envelope_decay_cycles / oscillation_frequency``.

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
        sample_rate=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        step_pressure=step_pressure,
        oscillation_amplitude=oscillation_amplitude,
        oscillation_frequency=oscillation_frequency,
        envelope_decay_cycles=envelope_decay_cycles,
        envelope_decay_fraction=envelope_decay_fraction,
    )


def _lowpass(noise: np.ndarray, sample_rate: float, noise_cutoff_frequency: float) -> np.ndarray:
    """The noise low-passed by an FFT brick wall: every bin above ``noise_cutoff_frequency``
    (Hz) zeroed; a cut-off at or above the Nyquist frequency returns ``noise`` unchanged."""
    if noise_cutoff_frequency >= sample_rate / 2.0:
        return noise
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(noise.shape[0], 1.0 / sample_rate)
    spectrum[freqs > noise_cutoff_frequency] = 0.0
    return np.fft.irfft(spectrum, n=noise.shape[0])


def _scaled_to_peak(
    noise: np.ndarray, step_pressure: float, peak_pressure_target: float
) -> np.ndarray:
    """``noise`` scaled so that ``step_pressure + noise`` peaks at ``peak_pressure_target``:
    times ``(peak_pressure_target - step_pressure) / max(noise)``; Pa.

    Raises
    ------
    ValueError
        ``noise`` has no positive sample.
    """
    noise_max = float(noise.max())
    if not noise_max > 0.0:
        raise ValueError("the enveloped noise has no positive sample to scale on")
    return noise * ((peak_pressure_target - step_pressure) / noise_max)


def step_noise(
    step_pressure: float,
    requested_noise_rms: float,
    noise_cutoff_frequency: float | None = None,
    noise_seed: int = 0,
    envelope_decay_cycles: float = DEFAULT_ENVELOPE_DECAY_CYCLES,
    envelope_decay_fraction: float = DEFAULT_ENVELOPE_DECAY_FRACTION,
    *,
    envelope_reference_frequency: float,
    peak_pressure_target: float,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """The step plus enveloped, low-passed Gaussian noise, peak-scaled to ``peak_pressure_target``.

    The noise is drawn with ``numpy.random.default_rng(noise_seed).standard_normal`` over
    the active window (every sample after the lead-in), scaled to ``requested_noise_rms``,
    low-passed at ``noise_cutoff_frequency``, multiplied by the envelope defined on
    ``envelope_reference_frequency``, and finally scaled by ``(peak_pressure_target -
    step_pressure) / max(noise)`` so that ``max(pressure) == peak_pressure_target``. Because
    the last step is a ratio, ``requested_noise_rms`` has no effect on the result; it is kept as the
    generator's input and the resulting RMS of the noise over the active window is
    ``History.scaled_noise_rms``.

    Parameters
    ----------
    step_pressure : float
        Held pressure, Pa.
    requested_noise_rms : float
        Requested white-noise RMS before the scaling, Pa (inert, see above).
    noise_cutoff_frequency : float or None, optional
        Low-pass cut-off, Hz; None (default) is the Nyquist frequency ``sample_rate / 2``
        (no filtering).
    noise_seed : int, optional
        RNG seed (default 0).
    envelope_decay_cycles, envelope_decay_fraction : float, optional
        As ``step_sine``, on the period ``1 / envelope_reference_frequency``.
    envelope_reference_frequency : float, keyword-only
        Reference frequency of the envelope, Hz.
    peak_pressure_target : float, keyword-only
        The peak the scaled history reaches, Pa (``> step_pressure``).
    sample_rate, lead_in_s, transit_s, tail_s : float, optional
        As ``step``; the duration adds ``envelope_decay_cycles /
        envelope_reference_frequency``.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        ``peak_pressure_target <= step_pressure``, or an enveloped noise whose maximum is
        not positive.
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
        raise ValueError(
            f"peak_pressure_target ({peak_pressure_target!r}) must exceed step_pressure "
            f"({step_pressure!r})"
        )
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
    scaled_noise = _scaled_to_peak(noise, step_pressure, peak_pressure_target)
    pressure = np.zeros_like(time)
    pressure[lead_in_sample_count:] = step_pressure + scaled_noise
    scaled_noise_rms = float(math.sqrt(float(np.mean(scaled_noise * scaled_noise))))
    return _history(
        "step_noise",
        time,
        pressure,
        decay_s,
        duration_s,
        scaled_noise_rms=scaled_noise_rms,
        sample_rate=sample_rate,
        lead_in_s=lead_in_s,
        transit_s=transit_s,
        tail_s=tail_s,
        step_pressure=step_pressure,
        requested_noise_rms=requested_noise_rms,
        noise_cutoff_frequency=noise_cutoff_frequency,
        envelope_reference_frequency=envelope_reference_frequency,
        noise_seed=noise_seed,
        envelope_decay_cycles=envelope_decay_cycles,
        envelope_decay_fraction=envelope_decay_fraction,
        peak_pressure_target=peak_pressure_target,
    )


# ------------------------------------------------------------------ the sweep's scaling


def canonical(
    history_type: str,
    design_pressure: float,
    amplitude_fraction: float,
    *,
    oscillation_frequency: float | None = None,
    noise_seed: int | None = None,
    envelope_reference_frequency: float | None = None,
    noise_cutoff_frequency: float | None = None,
    requested_noise_rms: float = 1.0,
    envelope_decay_cycles: float = DEFAULT_ENVELOPE_DECAY_CYCLES,
    envelope_decay_fraction: float = DEFAULT_ENVELOPE_DECAY_FRACTION,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    lead_in_s: float = DEFAULT_LEAD_IN_S,
    transit_s: float = 0.0,
    tail_s: float = DEFAULT_TAIL_S,
) -> History:
    """A history of ``history_type`` under the sweep's common scaling: peak
    ``amplitude_fraction * 1.33 * design_pressure`` (``PEAK_TO_DESIGN_PRESSURE_RATIO``).

    ``"step"`` is a plain step to the target. ``"step_sine"`` (needs
    ``oscillation_frequency``) holds ``0.5`` of the target and sets the oscillation amplitude
    so that the first positive peak of the enveloped sine hits the target. ``"step_noise"``
    (needs ``noise_seed`` and ``envelope_reference_frequency``) holds ``0.5`` of the target
    and scales the noise so that the overall peak hits the target. The returned
    ``History.params()`` rebuilds the same arrays through ``from_params``.

    Parameters
    ----------
    history_type : str
        One of ``HISTORY_TYPES``.
    design_pressure : float
        Design pressure, Pa.
    amplitude_fraction : float
        Peak as a fraction of ``1.33 * design_pressure``.
    oscillation_frequency, noise_seed, envelope_reference_frequency, \
noise_cutoff_frequency, requested_noise_rms, envelope_decay_cycles, envelope_decay_fraction
        Passed to the generator (see each one): frequencies in Hz, the RMS in Pa.
    sample_rate, lead_in_s, transit_s, tail_s : float, optional
        As the generators.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        Unknown ``history_type`` or a missing frequency / seed (the message names the
        parameter).
    """
    target_pressure = peak_pressure_target(design_pressure, amplitude_fraction)
    shared_arguments = {
        "sample_rate": sample_rate,
        "lead_in_s": lead_in_s,
        "transit_s": transit_s,
        "tail_s": tail_s,
    }
    if history_type == "step":
        return step(target_pressure, **shared_arguments)
    if history_type == "step_sine":
        if oscillation_frequency is None:
            raise ValueError("step_sine needs oscillation_frequency")
        step_pressure = STEP_TO_PEAK_RATIO * target_pressure
        unit_sine_history = step_sine(
            0.0,
            1.0,
            oscillation_frequency,
            envelope_decay_cycles,
            envelope_decay_fraction,
            **shared_arguments,
        )
        oscillation_amplitude = (target_pressure - step_pressure) / unit_sine_history.pressure_max
        return step_sine(
            step_pressure,
            oscillation_amplitude,
            oscillation_frequency,
            envelope_decay_cycles,
            envelope_decay_fraction,
            **shared_arguments,
        )
    if history_type == "step_noise":
        if noise_seed is None or envelope_reference_frequency is None:
            raise ValueError("step_noise needs noise_seed and envelope_reference_frequency")
        return step_noise(
            STEP_TO_PEAK_RATIO * target_pressure,
            requested_noise_rms,
            noise_cutoff_frequency,
            noise_seed,
            envelope_decay_cycles,
            envelope_decay_fraction,
            envelope_reference_frequency=envelope_reference_frequency,
            peak_pressure_target=target_pressure,
            **shared_arguments,
        )
    raise ValueError(f"history_type must be one of {HISTORY_TYPES}, got {history_type!r}")


def from_params(params: dict) -> History:
    """Rebuild a history from its parameters, bitwise.

    Parameters
    ----------
    params : dict
        ``History.params()``, keyed by ``PARAM_KEYS``; a key missing or None is the
        generator's default where it has one. Units as ``History``.

    Returns
    -------
    History

    Raises
    ------
    ValueError
        Unknown ``history_type``, or a key outside ``PARAM_KEYS``.
    """
    unknown = set(params) - set(PARAM_KEYS)
    if unknown:
        raise ValueError(f"unknown history parameters {sorted(unknown)}")
    parameter_values = {key: params.get(key) for key in PARAM_KEYS}
    shared_arguments = {
        "sample_rate": DEFAULT_SAMPLE_RATE
        if parameter_values["sample_rate"] is None
        else parameter_values["sample_rate"],
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
    history_type = parameter_values["history_type"]
    if history_type == "step":
        return step(parameter_values["step_pressure"], **shared_arguments)
    if history_type == "step_sine":
        return step_sine(
            parameter_values["step_pressure"],
            parameter_values["oscillation_amplitude"],
            parameter_values["oscillation_frequency"],
            parameter_values["envelope_decay_cycles"],
            parameter_values["envelope_decay_fraction"],
            **shared_arguments,
        )
    if history_type == "step_noise":
        return step_noise(
            parameter_values["step_pressure"],
            parameter_values["requested_noise_rms"],
            parameter_values["noise_cutoff_frequency"],
            parameter_values["noise_seed"],
            parameter_values["envelope_decay_cycles"],
            parameter_values["envelope_decay_fraction"],
            envelope_reference_frequency=parameter_values["envelope_reference_frequency"],
            peak_pressure_target=parameter_values["peak_pressure_target"],
            **shared_arguments,
        )
    raise ValueError(f"history_type must be one of {HISTORY_TYPES}, got {history_type!r}")
