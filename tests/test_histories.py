"""Session 5b: the canonical pressure histories (``surge_sdof.histories``)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from surge_sdof import histories as H

P_DESIGN = 78.83e5  # Pa, the 10 in pipe


def _canonical(kind, amplitude_fraction=1.0, **kw):
    extra = {}
    if kind == "step_sine":
        extra["oscillation_frequency"] = 4.0
    if kind == "step_noise":
        extra.update(noise_seed=7, envelope_reference_frequency=4.0)
    extra.update(kw)
    return H.canonical(kind, P_DESIGN, amplitude_fraction, transit_s=0.04, **extra)


@pytest.mark.parametrize("kind", H.HISTORY_TYPES)
@pytest.mark.parametrize("amplitude_fraction", [0.25, 1.0])
def test_peak_equals_the_cap(kind, amplitude_fraction):
    h = _canonical(kind, amplitude_fraction)
    cap = amplitude_fraction * 1.33 * P_DESIGN
    assert h.pressure_max == pytest.approx(cap, rel=1e-12, abs=0.0)
    assert h.pressure_max == float(h.pressure.max())
    if kind == "step":
        assert h.step_pressure == cap
    else:
        assert h.step_pressure == 0.5 * cap


def test_envelope_hits_one_minus_decay_fraction_at_decay_cycles():
    for f, cycles, fraction in ((1.0, 10.0, 0.8), (16.0, 10.0, 0.8), (4.0, 3.0, 0.5)):
        e = H.envelope(cycles / f, f, cycles, fraction)
        assert float(e) == pytest.approx(1.0 - fraction, rel=1e-12, abs=0.0)
    assert float(H.envelope(0.0, 4.0, 10.0, 0.8)) == 1.0
    with pytest.raises(ValueError):
        H.decay_rate(4.0, 10.0, 1.0)


def test_sine_first_positive_peak_is_the_cap_and_later_peaks_are_lower():
    h = _canonical("step_sine", oscillation_frequency=4.0)
    cap = 1.33 * P_DESIGN
    n_lead = int(round(h.lead_in_s * h.sample_rate))
    i_peak = int(np.argmax(h.pressure))
    # the first positive peak sits inside the first cycle after the lead-in
    assert n_lead < i_peak < n_lead + int(h.sample_rate / h.oscillation_frequency)
    assert h.pressure[i_peak] == pytest.approx(cap, rel=1e-12, abs=0.0)
    # ten cycles later the local peak is 20 % of the first one: the envelope multiplies
    # each period by the same factor and 4 Hz is a whole number of samples (250)
    period = int(round(h.sample_rate / h.oscillation_frequency))
    i10 = i_peak + 10 * period
    local = h.pressure[i10 - period // 2 : i10 + period // 2].max() - h.step_pressure
    assert local == pytest.approx(0.2 * (cap - h.step_pressure), rel=1e-9)
    assert h.decay_s == 10.0 / 4.0


def test_noise_is_reproducible_by_seed_and_differs_between_seeds():
    a = _canonical("step_noise", noise_seed=3)
    b = _canonical("step_noise", noise_seed=3)
    c = _canonical("step_noise", noise_seed=4)
    assert np.array_equal(a.pressure, b.pressure)
    assert a.scaled_noise_rms == b.scaled_noise_rms
    assert not np.array_equal(a.pressure, c.pressure)
    assert a.noise_seed == 3 and c.noise_seed == 4
    assert (
        a.noise_cutoff_frequency == a.sample_rate / 2
    )  # the default cut-off is the Nyquist frequency


def test_noise_rms_is_recorded_and_the_requested_rms_is_inert():
    a = _canonical("step_noise", noise_seed=3, requested_noise_rms=1.0)
    b = _canonical("step_noise", noise_seed=3, requested_noise_rms=1e5)
    assert np.allclose(a.pressure, b.pressure, rtol=1e-12, atol=0.0)
    n_lead = int(round(a.lead_in_s * a.sample_rate))
    noise = a.pressure[n_lead:] - a.step_pressure
    assert a.scaled_noise_rms == pytest.approx(math.sqrt(np.mean(noise**2)), rel=1e-12)
    assert 0.0 < a.scaled_noise_rms < a.peak_pressure_target - a.step_pressure


def test_noise_lowpass_removes_the_band_above_f_cut():
    h = _canonical("step_noise", noise_seed=3, noise_cutoff_frequency=50.0)
    n_lead = int(round(h.lead_in_s * h.sample_rate))
    noise = h.pressure[n_lead:] - h.step_pressure
    spectrum = np.abs(np.fft.rfft(noise))
    freqs = np.fft.rfftfreq(noise.shape[0], 1.0 / h.sample_rate)
    # the envelope (applied after the filter) smears the brick wall; the band above
    # 2 f_cut holds a small fraction of the amplitude that the unfiltered history has
    white = _canonical("step_noise", noise_seed=3)
    noise_w = white.pressure[n_lead:] - white.step_pressure
    spectrum_w = np.abs(np.fft.rfft(noise_w))
    ratio = spectrum[freqs > 100.0].mean() / spectrum[freqs <= 50.0].mean()
    ratio_w = spectrum_w[freqs > 100.0].mean() / spectrum_w[freqs <= 50.0].mean()
    assert ratio < 1e-2 and ratio_w > 0.5
    assert h.noise_cutoff_frequency == 50.0


@pytest.mark.parametrize("kind", H.HISTORY_TYPES)
def test_lead_in_is_zero_then_the_step(kind):
    h = _canonical(kind)
    n_lead = int(round(0.1 * h.sample_rate))
    assert n_lead == 100
    assert np.all(h.pressure[:n_lead] == 0.0)
    assert np.all(h.time[:n_lead] < 0.1)
    if kind == "step_noise":
        assert h.pressure[n_lead] != 0.0  # the first active sample already carries noise
    else:
        assert h.pressure[n_lead] == h.step_pressure  # sin(0) = 0
    if kind == "step":
        assert np.all(h.pressure[n_lead:] == h.step_pressure)


def test_durations_add_the_four_terms():
    s = _canonical("step")
    assert s.duration_s == pytest.approx(0.1 + 0.04 + 2.0)
    assert s.sample_count == round(s.duration_s * 1000)
    assert s.time.shape == s.pressure.shape == (s.sample_count,)
    sine = _canonical("step_sine", oscillation_frequency=1.0)
    assert sine.duration_s == pytest.approx(0.1 + 0.04 + 10.0 + 2.0)
    noise = _canonical("step_noise", envelope_reference_frequency=4.0)
    assert noise.duration_s == pytest.approx(0.1 + 0.04 + 2.5 + 2.0)


@pytest.mark.parametrize("kind", H.HISTORY_TYPES)
def test_params_round_trip_bitwise(kind):
    h = _canonical(kind, 0.25)
    params = h.params()
    assert set(params) == set(H.PARAM_KEYS)
    again = H.from_params(params)
    assert np.array_equal(again.pressure, h.pressure)
    assert np.array_equal(again.time, h.time)
    assert again.params() == params
    assert (
        again.pressure_max,
        again.pressure_mean,
        again.pressure_rms,
        again.scaled_noise_rms,
    ) == (
        h.pressure_max,
        h.pressure_mean,
        h.pressure_rms,
        h.scaled_noise_rms,
    )


def test_stats_and_force():
    h = _canonical("step")
    assert h.pressure_mean == pytest.approx(h.pressure.mean())
    assert h.pressure_rms == pytest.approx(math.sqrt(np.mean(h.pressure**2)))
    assert h.pressure_min == 0.0
    area = 0.052
    assert np.array_equal(h.force(area), h.pressure * area)
    assert h.version == H.HISTORIES_VERSION


def test_rejections():
    with pytest.raises(ValueError, match="kind"):
        H.canonical("ramp", P_DESIGN, 1.0)
    with pytest.raises(ValueError, match="f_osc"):
        H.canonical("step_sine", P_DESIGN, 1.0)
    with pytest.raises(ValueError, match="seed"):
        H.canonical("step_noise", P_DESIGN, 1.0)
    with pytest.raises(ValueError, match="p_cap"):
        H.step_noise(1.0, 1.0, envelope_reference_frequency=4.0, peak_pressure_target=1.0)
    with pytest.raises(ValueError, match="unknown history parameters"):
        H.from_params({"history_type": "step", "step_pressure": 1.0, "bogus": 1})
    with pytest.raises(ValueError, match="non-negative"):
        H.step(1.0, transit_s=-1.0)
