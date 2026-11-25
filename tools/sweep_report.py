"""The plots and the report of a junction-coupling sweep CSV (``tools/sweep_jc.py plot``).

Part of ``tools/sweep_jc.py`` (review session R.8, plan 5.12), moved verbatim; no test runs
it (``docs/review/charter.md``), so it takes rename-only edits (ruling 24).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from surge_sdof import export

# ------------------------------------------------------------------ plots


LENGTH_COLOURS = {3.0: "#2a78d6", 6.0: "#eb6834", 12.0: "#1baf7a", 24.0: "#eda100", 48.0: "#e87ba4"}
LENGTH_MARKERS = {3.0: "o", 6.0: "s", 12.0: "^", 24.0: "D", 48.0: "v"}
SIZE_MARKERS = {10: "o", 12: "s", 16: "^", 18: "D"}
AMP_STYLES = {0.25: ":", 0.5: "--", 1.0: "-"}
SOLVER_INK = {"lumped": "#52514e", "jc": "#0b0b0b"}
HISTORY_LABELS = {"step": "step", "step_sine": "step + sine", "step_noise": "step + noise"}


def _f(v):
    return None if v in ("", None) else float(v)


def _load(path: Path) -> list[dict]:
    _, rows = export.read_csv(path)
    for r in rows:
        for k in (
            "size_in",
            "span_length",
            "natural_frequency",
            "oscillation_frequency",
            "amplitude_fraction",
            "friction_coefficient",
            "max_static_equivalent_force_ratio",
            "max_velocity_ratio",
            "daf_lumped",
            "daf_jc",
            "force_per_length_diameter_squared_lumped",
            "force_per_length_diameter_squared_jc",
            "wall_time_lumped",
            "wall_time_jc",
        ):
            r[k] = _f(r[k])
        r["noise_seed"] = int(r["noise_seed"]) if r["noise_seed"] else None
        r["size_in"] = int(r["size_in"])
    return rows


def _history_variants(rows):
    """(history_type, f_osc) panels: the noise seeds are folded into one variant."""
    seen = []
    for r in rows:
        key = (
            r["history_type"],
            r["oscillation_frequency"] if r["history_type"] == "step_sine" else None,
        )
        if key not in seen:
            seen.append(key)
    order = {"step": 0, "step_sine": 1, "step_noise": 2}
    return sorted(seen, key=lambda k: (order[k[0]], k[1] or 0))


def _variant_label(key):
    kind, f_osc = key
    return f"{HISTORY_LABELS[kind]} {f_osc:g} Hz" if kind == "step_sine" else HISTORY_LABELS[kind]


def _select(rows, **match):
    out = []
    for r in rows:
        ok = True
        for k, v in match.items():
            if k == "variant":
                kind, f_osc = v
                ok = r["history_type"] == kind and (
                    kind != "step_sine" or r["oscillation_frequency"] == f_osc
                )
            elif r[k] != v:
                ok = False
            if not ok:
                break
        if ok:
            out.append(r)
    return out


def _series(rows, column, envelope="max"):
    """``(freqs, values)`` of ``column`` vs natFreq; several rows at one frequency (noise seeds)
    are reduced by ``envelope`` (the pointwise max over seeds, the owner's envelope) or
    ``min``."""
    by_f = {}
    for r in rows:
        if r[column] is None:
            continue
        by_f.setdefault(r["natural_frequency"], []).append(r[column])
    freqs = sorted(by_f)
    red = max if envelope == "max" else min
    return freqs, [red(by_f[f]) for f in freqs]


def _style_axes(ax):
    ax.set_xscale("log")
    ax.grid(True, which="major", color="#e6e5e1", linewidth=0.6)
    ax.grid(True, which="minor", color="#f1f0ec", linewidth=0.4)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e", labelsize=8)


def _freq_ticks(ax, freqs):
    from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter

    ticks = sorted(set(freqs))
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks], fontsize=7)


def plot_ratio(rows, column, ylabel, out_png: Path, title: str, mu_on: float):
    """Figure 1: JC / lumped ratio vs natFreq, one line per length, one panel per (size,
    history variant, amplitude), friction on (``mu_on``)."""
    import matplotlib.pyplot as plt

    sizes = sorted({r["size_in"] for r in rows})
    amps = sorted({r["amplitude_fraction"] for r in rows})
    variants = _history_variants(rows)
    ncol = len(variants)
    nrow = len(sizes) * len(amps)
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(3.2 * ncol, 2.6 * nrow), squeeze=False, sharey=True
    )
    all_freqs = sorted({r["natural_frequency"] for r in rows})
    for i, (size, amp) in enumerate((s, a) for s in sizes for a in amps):
        for j, variant in enumerate(variants):
            ax = axes[i][j]
            _style_axes(ax)
            ax.axhline(1.0, color="#c3c2b7", linewidth=0.8)
            ax.axhspan(0.95, 1.05, color="#e6e5e1", alpha=0.5, linewidth=0)
            ax.axhline(0.8, color="#c3c2b7", linewidth=0.6, linestyle="--")
            for L in sorted(LENGTH_COLOURS):
                sel = _select(
                    rows,
                    size_in=size,
                    amplitude_fraction=amp,
                    variant=variant,
                    span_length=L,
                    friction_coefficient=mu_on,
                )
                freqs, vals = _series(sel, column)
                if not freqs:
                    continue
                ax.plot(
                    freqs,
                    vals,
                    color=LENGTH_COLOURS[L],
                    marker=LENGTH_MARKERS[L],
                    markersize=4,
                    linewidth=1.6,
                    label=f"L = {L:g} m",
                )
            _freq_ticks(ax, all_freqs)
            ax.set_title(
                f"{size} in · {_variant_label(variant)} · amplitude {amp:g}",
                fontsize=8,
                color="#0b0b0b",
            )
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=8, color="#52514e")
            if i == nrow - 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles, labels = axes[0][0].get_legend_handles_labels()
    for row_axes in axes:
        for ax in row_axes:
            h, lab = ax.get_legend_handles_labels()
            if len(lab) > len(labels):
                handles, labels = h, lab
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=len(labels),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(f"{title} (mu = {mu_on:g}; band ±5 %, dashed 0.8)", fontsize=10, color="#0b0b0b")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_daf(rows, out_png: Path, mu_on: float):
    """Figure 2: effective DAF ``F / (p_peak A)`` of both solvers vs natFreq, one line per
    length (colour), amplitude as line style, lumped hollow / JC filled markers, one panel
    per (size, history variant), friction on."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    sizes = sorted({r["size_in"] for r in rows})
    amps = sorted({r["amplitude_fraction"] for r in rows})
    variants = _history_variants(rows)
    fig, axes = plt.subplots(
        len(sizes),
        len(variants),
        figsize=(3.2 * len(variants), 2.8 * len(sizes)),
        squeeze=False,
        sharey=True,
    )
    all_freqs = sorted({r["natural_frequency"] for r in rows})
    for i, size in enumerate(sizes):
        for j, variant in enumerate(variants):
            ax = axes[i][j]
            _style_axes(ax)
            ax.axhline(2.0, color="#c3c2b7", linewidth=0.8, linestyle="--")
            for L in sorted(LENGTH_COLOURS):
                for amp in amps:
                    sel = _select(
                        rows,
                        size_in=size,
                        amplitude_fraction=amp,
                        variant=variant,
                        span_length=L,
                        friction_coefficient=mu_on,
                    )
                    for solver, fill in (("lumped", "none"), ("jc", LENGTH_COLOURS[L])):
                        freqs, vals = _series(sel, f"daf_{solver}")
                        if not freqs:
                            continue
                        ax.plot(
                            freqs,
                            vals,
                            color=LENGTH_COLOURS[L],
                            linestyle=AMP_STYLES.get(amp, "-"),
                            marker=LENGTH_MARKERS[L],
                            markersize=4,
                            markerfacecolor=fill,
                            linewidth=1.2 if solver == "jc" else 0.9,
                            alpha=1.0 if solver == "jc" else 0.7,
                        )
            _freq_ticks(ax, all_freqs)
            ax.set_title(f"{size} in · {_variant_label(variant)}", fontsize=8, color="#0b0b0b")
            if j == 0:
                ax.set_ylabel("F_eq / (p_peak A)", fontsize=8, color="#52514e")
            if i == len(sizes) - 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles = [
        Line2D([], [], color=LENGTH_COLOURS[L], marker=LENGTH_MARKERS[L], label=f"L = {L:g} m")
        for L in sorted(LENGTH_COLOURS)
    ]
    handles += [
        Line2D([], [], color="#52514e", linestyle=AMP_STYLES.get(a, "-"), label=f"amplitude {a:g}")
        for a in amps
    ]
    handles += [
        Line2D(
            [],
            [],
            color="#52514e",
            marker="o",
            markerfacecolor="none",
            linestyle="",
            label="lumped",
        ),
        Line2D([], [], color="#52514e", marker="o", linestyle="", label="JC"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(len(handles), 6),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(f"Effective DAF of both solvers (mu = {mu_on:g}; dashed: DAF = 2)", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_collapse(rows, out_png: Path, mu_on: float, amp: float):
    """Figure 3: ``F_eq / (L d²)`` vs natFreq for every size and length on one panel per
    history variant (colour = length, marker = size, lumped hollow / JC filled)."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    variants = _history_variants(rows)
    sizes = sorted({r["size_in"] for r in rows})
    fig, axes = plt.subplots(
        2, len(variants), figsize=(3.2 * len(variants), 5.6), squeeze=False, sharey=True
    )
    all_freqs = sorted({r["natural_frequency"] for r in rows})
    for k, solver in enumerate(("lumped", "jc")):
        for j, variant in enumerate(variants):
            ax = axes[k][j]
            _style_axes(ax)
            ax.set_yscale("log")
            for size in sizes:
                for L in sorted(LENGTH_COLOURS):
                    sel = _select(
                        rows,
                        size_in=size,
                        amplitude_fraction=amp,
                        variant=variant,
                        span_length=L,
                        friction_coefficient=mu_on,
                    )
                    freqs, vals = _series(sel, f"force_per_length_diameter_squared_{solver}")
                    if not freqs:
                        continue
                    ax.plot(
                        freqs,
                        vals,
                        color=LENGTH_COLOURS[L],
                        marker=SIZE_MARKERS[size],
                        markersize=4,
                        markerfacecolor=LENGTH_COLOURS[L] if solver == "jc" else "none",
                        linewidth=1.0,
                    )
            _freq_ticks(ax, all_freqs)
            ax.set_title(f"{solver} · {_variant_label(variant)} · amplitude {amp:g}", fontsize=8)
            if j == 0:
                ax.set_ylabel("F_eq / (L d²), N/m³", fontsize=8, color="#52514e")
            if k == 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles = [
        Line2D([], [], color=LENGTH_COLOURS[L], label=f"L = {L:g} m")
        for L in sorted(LENGTH_COLOURS)
    ]
    handles += [
        Line2D([], [], color="#52514e", marker=SIZE_MARKERS[s], linestyle="", label=f"{s} in")
        for s in sizes
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(len(handles), 7),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(
        f"Mass-collapse test: F_eq / (L d²) (mu = {mu_on:g}, amplitude {amp:g}; d = OD)",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


FREQ_BANDS = (
    (0.0, 4.0, "≤ 4 Hz"),
    (4.0, 8.0, "4 – 8 Hz"),
    (8.0, 16.0, "8 – 16 Hz"),
    (16.0, 1e9, "> 16 Hz"),
)


def _band(f):
    for lo, hi, name in FREQ_BANDS:
        if lo < f <= hi:
            return name
    return "> 16 Hz"


def ratio_table(rows, column, mu_on: float) -> list[str]:
    """Markdown: per history type, by frequency band × length, the count of cases with the
    ratio within 5 % of 1 (negligible) / below 0.8 (essential) / the rest, friction on, all
    sizes and amplitudes pooled."""
    lines = []
    for variant in _history_variants(rows):
        sel = [
            r
            for r in _select(rows, variant=variant, friction_coefficient=mu_on)
            if r[column] is not None
        ]
        lengths = sorted({r["span_length"] for r in sel})
        lines.append(
            f"**{_variant_label(variant)}** — `{column}`, mu = {mu_on:g}; cell = negligible (|r − 1| ≤ 5 %) / essential (r < 0.8) / other, of n cases; min r"
        )
        lines.append("")
        lines.append("| band | " + " | ".join(f"L = {L:g} m" for L in lengths) + " |")
        lines.append("|---|" + "---|" * len(lengths))
        for _lo, _hi, band in FREQ_BANDS:
            cells = []
            for L in lengths:
                vals = [
                    r[column]
                    for r in sel
                    if r["span_length"] == L and _band(r["natural_frequency"]) == band
                ]
                if not vals:
                    cells.append("–")
                    continue
                neg = sum(abs(v - 1) <= 0.05 for v in vals)
                ess = sum(v < 0.8 for v in vals)
                cells.append(
                    f"{neg} / {ess} / {len(vals) - neg - ess} of {len(vals)}; min {min(vals):.2f}"
                )
            lines.append(f"| {band} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def amplitude_table(rows, mu_on: float) -> list[str]:
    """Markdown: the friction (amplitude) dependence as the ratio of the low-amplitude to the
    high-amplitude effective DAF, per history type and solver, by frequency band (all sizes
    and lengths pooled: median and range)."""
    amps = sorted({r["amplitude_fraction"] for r in rows})
    if len(amps) < 2:
        return ["(one amplitude only: no amplitude dependence to report)", ""]
    lo_amp, hi_amp = amps[0], amps[-1]
    lines = [
        f"**Amplitude dependence** — DAF(amplitude {lo_amp:g}) / DAF(amplitude {hi_amp:g}), mu = {mu_on:g}, median [min – max] over sizes and lengths (n pairs)",
        "",
    ]
    lines.append("| history | solver | " + " | ".join(b[2] for b in FREQ_BANDS) + " |")
    lines.append("|---|---|" + "---|" * len(FREQ_BANDS))
    for variant in _history_variants(rows):
        for solver in ("lumped", "jc"):
            cells = []
            for _lo, _hi, band in FREQ_BANDS:
                pairs = []
                low = _select(
                    rows, variant=variant, friction_coefficient=mu_on, amplitude_fraction=lo_amp
                )
                high = {
                    (r["size_in"], r["span_length"], r["natural_frequency"], r["noise_seed"]): r
                    for r in _select(
                        rows, variant=variant, friction_coefficient=mu_on, amplitude_fraction=hi_amp
                    )
                }
                for r in low:
                    key = (r["size_in"], r["span_length"], r["natural_frequency"], r["noise_seed"])
                    other = high.get(key)
                    if other is None or _band(r["natural_frequency"]) != band:
                        continue
                    a, b = r[f"daf_{solver}"], other[f"daf_{solver}"]
                    if a is not None and b is not None and b:
                        pairs.append(a / b)
                if pairs:
                    cells.append(
                        f"{float(np.median(pairs)):.2f} [{min(pairs):.2f} – {max(pairs):.2f}] ({len(pairs)})"
                    )
                else:
                    cells.append("–")
            lines.append(f"| {_variant_label(variant)} | {solver} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def collapse_spread(rows, mu_on: float, amp: float) -> list[str]:
    """Markdown: per history variant and solver, the spread of ``F_eq / (L d²)`` across sizes
    and lengths at each natural frequency (max / min), the visual collapse stated as numbers."""
    lines = [
        f"**Collapse spread** — max / min of F_eq / (L d²) over sizes and lengths at one natural frequency, mu = {mu_on:g}, amplitude {amp:g} (median over frequencies [max])",
        "",
    ]
    lines.append("| history | lumped | JC |")
    lines.append("|---|---|---|")
    for variant in _history_variants(rows):
        cells = []
        for solver in ("lumped", "jc"):
            sel = [
                r
                for r in _select(
                    rows, variant=variant, friction_coefficient=mu_on, amplitude_fraction=amp
                )
                if r[f"force_per_length_diameter_squared_{solver}"] is not None
            ]
            by_f = {}
            for r in sel:
                by_f.setdefault(r["natural_frequency"], []).append(
                    r[f"force_per_length_diameter_squared_{solver}"]
                )
            spreads = [max(v) / min(v) for v in by_f.values() if len(v) > 1 and min(v) > 0]
            cells.append(
                f"{float(np.median(spreads)):.2f} [{max(spreads):.2f}]" if spreads else "–"
            )
        lines.append(f"| {_variant_label(variant)} | {cells[0]} | {cells[1]} |")
    lines.append("")
    return lines


def write_doc(rows, csv_path: Path, pngs: dict, doc_path: Path, mu_on: float, amp: float) -> None:
    n_err = sum(1 for r in rows if r["error"])
    sizes = sorted({r["size_in"] for r in rows})
    tier = rows[0]["tier"]
    subset = rows[0]["subset"]
    sha = rows[0]["git_sha"]
    cpu = rows[0]["cpu"]
    t_l = [r["wall_time_lumped"] for r in rows if r["wall_time_lumped"] is not None]
    t_j = [r["wall_time_jc"] for r in rows if r["wall_time_jc"] is not None]
    rel = lambda p: os.path.relpath(p, doc_path.parent)  # noqa: E731
    lines = [
        "# Junction-coupling sweep (Session 5b)",
        "",
        f"Source: `{rel(csv_path)}` — tier {tier}{' (' + subset + ')' if subset else ''}, {len(rows)} rows "
        f"({n_err} with errors), sizes {', '.join(f'{s} in' for s in sizes)}, git `{sha}`, CPU {cpu}. "
        f"Generated by `tools/sweep_jc.py plot`; the column definitions are in `docs/data_format.md` "
        f'("sweep CSV (Session 5b)"). Both solvers run with the fixed-path defaults (F-1, F-2, F-4), '
        f"`restrainFreqRatio = 1`, `gap = 0`, `stepQTY = 40`, celerity 1237 m/s, damping 0.5 %, "
        f"E = 195 GPa; the pressure histories are `surge_sdof.histories.canonical` at 1000 Hz, peak "
        f"`amplitude_fraction × 1.33 × p_design`. Frequency axes are the absolute natural frequency "
        f"(the lumped `natFreq`, modelled with the contained fluid). Where several noise seeds exist, "
        f"a plotted point is the pointwise max over seeds (the envelope); the per-seed rows stay in the CSV.",
        "",
        f"Run time per solver (this CSV): lumped mean {np.mean(t_l):.3f} s (max {max(t_l):.3f} s), "
        f"JC mean {np.mean(t_j):.3f} s (max {max(t_j):.3f} s), {len(rows)} cases.",
        "",
        "## 1. JC / lumped ratio of the equivalent static force and of the peak velocity",
        "",
        f"One line per span length, one panel per (size, history type, amplitude), friction on (mu = {mu_on:g}). "
        "The grey band is ±5 % of 1; the dashed line is 0.8.",
        "",
        f"![ratio_f_eq]({rel(pngs['max_static_equivalent_force_ratio'])})",
        "",
        f"![ratio_v_peak]({rel(pngs['max_velocity_ratio'])})",
        "",
        "## 2. Effective DAF F_eq / (p_peak A), lumped and JC",
        "",
        f"One panel per (size, history type), colour = length, line style = amplitude, hollow markers lumped and filled JC, mu = {mu_on:g}. The dashed line is DAF = 2.",
        "",
        f"![daf]({rel(pngs['daf'])})",
        "",
        "## 3. Mass-collapse test: F_eq / (L d²)",
        "",
        f"All sizes and lengths on one panel per history type (top row lumped, bottom row JC), amplitude {amp:g}, mu = {mu_on:g}, d = OD. "
        "The spread table below states numerically what the panels show: a ratio near 1 means the curves of the different sizes and lengths fall on one line.",
        "",
        f"![collapse]({rel(pngs['collapse'])})",
        "",
        *collapse_spread(rows, mu_on, amp),
        "## 4. Where JC is negligible and where it is essential",
        "",
        "Counts of cases per frequency band and span length (sizes and amplitudes pooled; noise seeds counted separately).",
        "",
        *ratio_table(rows, "max_static_equivalent_force_ratio", mu_on),
        *ratio_table(rows, "max_velocity_ratio", mu_on),
        *amplitude_table(rows, mu_on),
    ]
    if n_err:
        lines += ["## Errors", "", "| case | error |", "|---|---|"]
        lines += [f"| {r['case_id']} | {r['error']} |" for r in rows if r["error"]]
        lines.append("")
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
