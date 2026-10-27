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
        extra["f_osc"] = 4.0
    if kind == "step_noise":
        extra.update(seed=7, f_ref=4.0)
    extra.update(kw)
    return H.canonical(kind, P_DESIGN, amplitude_fraction, transit_s=0.04, **extra)


@pytest.mark.parametrize("kind", H.KINDS)
@pytest.mark.parametrize("amplitude_fraction", [0.25, 1.0])
def test_peak_equals_the_cap(kind, amplitude_fraction):
    h = _canonical(kind, amplitude_fraction)
    cap = amplitude_fraction * 1.33 * P_DESIGN
    assert h.peak == pytest.approx(cap, rel=1e-12, abs=0.0)
    assert h.peak == float(h.pressure.max())
    if kind == "step":
        assert h.p_step == cap
    else:
        assert h.p_step == 0.5 * cap


def test_envelope_hits_one_minus_decay_fraction_at_decay_cycles():
    for f, cycles, fraction in ((1.0, 10.0, 0.8), (16.0, 10.0, 0.8), (4.0, 3.0, 0.5)):
        e = H.envelope(cycles / f, f, cycles, fraction)
        assert float(e) == pytest.approx(1.0 - fraction, rel=1e-12, abs=0.0)
    assert float(H.envelope(0.0, 4.0, 10.0, 0.8)) == 1.0
    with pytest.raises(ValueError):
        H.decay_rate(4.0, 10.0, 1.0)


def test_sine_first_positive_peak_is_the_cap_and_later_peaks_are_lower():
    h = _canonical("step_sine", f_osc=4.0)
    cap = 1.33 * P_DESIGN
    n_lead = int(round(h.lead_in_s * h.sample_freq))
    i_peak = int(np.argmax(h.pressure))
    # the first positive peak sits inside the first cycle after the lead-in
    assert n_lead < i_peak < n_lead + int(h.sample_freq / h.f_osc)
    assert h.pressure[i_peak] == pytest.approx(cap, rel=1e-12, abs=0.0)
    # ten cycles later the local peak is 20 % of the first one: the envelope multiplies
    # each period by the same factor and 4 Hz is a whole number of samples (250)
    period = int(round(h.sample_freq / h.f_osc))
    i10 = i_peak + 10 * period
    local = h.pressure[i10 - period // 2 : i10 + period // 2].max() - h.p_step
    assert local == pytest.approx(0.2 * (cap - h.p_step), rel=1e-9)
    assert h.decay_s == 10.0 / 4.0


def test_noise_is_reproducible_by_seed_and_differs_between_seeds():
    a = _canonical("step_noise", seed=3)
    b = _canonical("step_noise", seed=3)
    c = _canonical("step_noise", seed=4)
    assert np.array_equal(a.pressure, b.pressure)
    assert a.noise_rms == b.noise_rms
    assert not np.array_equal(a.pressure, c.pressure)
    assert a.seed == 3 and c.seed == 4
    assert a.f_cut == a.sample_freq / 2  # the default cut-off is the Nyquist frequency


def test_noise_rms_is_recorded_and_the_requested_rms_is_inert():
    a = _canonical("step_noise", seed=3, p_noise_rms=1.0)
    b = _canonical("step_noise", seed=3, p_noise_rms=1e5)
    assert np.allclose(a.pressure, b.pressure, rtol=1e-12, atol=0.0)
    n_lead = int(round(a.lead_in_s * a.sample_freq))
    noise = a.pressure[n_lead:] - a.p_step
    assert a.noise_rms == pytest.approx(math.sqrt(np.mean(noise**2)), rel=1e-12)
    assert 0.0 < a.noise_rms < a.p_cap - a.p_step


def test_noise_lowpass_removes_the_band_above_f_cut():
    h = _canonical("step_noise", seed=3, f_cut=50.0)
    n_lead = int(round(h.lead_in_s * h.sample_freq))
    noise = h.pressure[n_lead:] - h.p_step
    spectrum = np.abs(np.fft.rfft(noise))
    freqs = np.fft.rfftfreq(noise.shape[0], 1.0 / h.sample_freq)
    # the envelope (applied after the filter) smears the brick wall; the band above
    # 2 f_cut holds a small fraction of the amplitude that the unfiltered history has
    white = _canonical("step_noise", seed=3)
    noise_w = white.pressure[n_lead:] - white.p_step
    spectrum_w = np.abs(np.fft.rfft(noise_w))
    ratio = spectrum[freqs > 100.0].mean() / spectrum[freqs <= 50.0].mean()
    ratio_w = spectrum_w[freqs > 100.0].mean() / spectrum_w[freqs <= 50.0].mean()
    assert ratio < 1e-2 and ratio_w > 0.5
    assert h.f_cut == 50.0


@pytest.mark.parametrize("kind", H.KINDS)
def test_lead_in_is_zero_then_the_step(kind):
    h = _canonical(kind)
    n_lead = int(round(0.1 * h.sample_freq))
    assert n_lead == 100
    assert np.all(h.pressure[:n_lead] == 0.0)
    assert np.all(h.time[:n_lead] < 0.1)
    if kind == "step_noise":
        assert h.pressure[n_lead] != 0.0  # the first active sample already carries noise
    else:
        assert h.pressure[n_lead] == h.p_step  # sin(0) = 0
    if kind == "step":
        assert np.all(h.pressure[n_lead:] == h.p_step)


def test_durations_add_the_four_terms():
    s = _canonical("step")
    assert s.duration_s == pytest.approx(0.1 + 0.04 + 2.0)
    assert s.n_samples == round(s.duration_s * 1000)
    assert s.time.shape == s.pressure.shape == (s.n_samples,)
    sine = _canonical("step_sine", f_osc=1.0)
    assert sine.duration_s == pytest.approx(0.1 + 0.04 + 10.0 + 2.0)
    noise = _canonical("step_noise", f_ref=4.0)
    assert noise.duration_s == pytest.approx(0.1 + 0.04 + 2.5 + 2.0)


@pytest.mark.parametrize("kind", H.KINDS)
def test_params_round_trip_bitwise(kind):
    h = _canonical(kind, 0.25)
    params = h.params()
    assert set(params) == set(H.PARAM_KEYS)
    again = H.from_params(params)
    assert np.array_equal(again.pressure, h.pressure)
    assert np.array_equal(again.time, h.time)
    assert again.params() == params
    assert (again.peak, again.mean, again.rms, again.noise_rms) == (
        h.peak,
        h.mean,
        h.rms,
        h.noise_rms,
    )


def test_stats_and_force():
    h = _canonical("step")
    assert h.mean == pytest.approx(h.pressure.mean())
    assert h.rms == pytest.approx(math.sqrt(np.mean(h.pressure**2)))
    assert h.p_min == 0.0
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
        H.step_noise(1.0, 1.0, f_ref=4.0, p_cap=1.0)
    with pytest.raises(ValueError, match="unknown history parameters"):
        H.from_params({"kind": "step", "p_step": 1.0, "bogus": 1})
    with pytest.raises(ValueError, match="non-negative"):
        H.step(1.0, transit_s=-1.0)
