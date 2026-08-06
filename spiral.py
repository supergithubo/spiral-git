#!/usr/bin/env python3
"""Render daily activity as an Archimedean spiral, one loop per calendar year.

A Python port of the spiralize approach in jokergoo's "Spiral visualization of
daily git commits". Angle encodes day-of-year, so the same calendar date lines
up radially across every loop; radius encodes which year.

Three ways to show the day's count, matching the three the post compares:

  dots     -- dot area, spiral_points()
  heatmap  -- the ribbon filled per day by colour, spiral_rect()
  horizon  -- a horizon chart folded into the ribbon, spiral_horizon()

  ./.venv/bin/python spiral.py --in data/contributions.csv --out spiral.png
"""

import argparse
import csv
import datetime as dt
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

THEMES = {
    "dark": dict(bg="#0d1117", fg="#e6edf3", muted="#7d8590", band="#1c2128"),
    "light": dict(bg="#ffffff", fg="#1f2328", muted="#656d76", band="#eaeaea"),
}

# RColorBrewer "Spectral" reversed -- cool for quiet days, warm for busy ones.
# The ramp the post feeds to circlize::colorRamp2() for the heatmap.
SPECTRAL_R = [
    "#5E4FA2", "#3288BD", "#66C2A5", "#ABDDA4", "#E6F598", "#FFFFBF",
    "#FEE08B", "#FDAE61", "#F46D43", "#D53E4F", "#9E0142",
]

# RColorBrewer "Reds", 4-class: one colour per horizon band, palest lowest.
HORIZON_COLORS = ["#FEE5D9", "#FCAE91", "#FB6A4A", "#CB181D"]

# How many slices the horizon chart folds the value range into.
HORIZON_BANDS = 4

# Jan 1 sits at 3 o'clock and time runs clockwise, so every loop begins on the
# east axis -- which is what lets the year labels stack there as a ruler.
START_ANGLE = 0.0

# Fraction of the loop pitch filled by the ribbon; the remainder is the gap.
BAND_FRACTION = 0.62

# Year-label height as a fraction of the ribbon width. Digit cap-height is
# roughly 0.7 em, so past about 1.4 the glyphs spill over the gaps either side.
LABEL_BAND_RATIO = 0.85


def days_in_year(year):
    return 366 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 365


def read_counts(path, column):
    """Return {date: count} for every row, including zero-count days."""
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{path} has no rows")
    if column not in rows[0]:
        sys.exit(f"no '{column}' column in {path}; found {list(rows[0])}")
    return {
        dt.date.fromisoformat(r["date"]): int(r[column] or 0)
        for r in rows
    }


def calc_pt_size(value, cap, lo=1.0, hi=20.0):
    """Map a count onto a dot diameter in points.

    Follows the original: clamp at `cap` so a handful of 200-commit days do not
    flatten everything else, then scale linearly into [lo, hi].
    """
    if cap <= 0:
        return lo
    return lo + (hi - lo) * min(value, cap) / cap


def year_fraction(day, normalize_year=True):
    """Position within the year, in [0, 1).

    normalize_year divides by that year's actual length, so leap years do not
    slowly rotate February out of alignment across loops.
    """
    doy = day.timetuple().tm_yday - 1
    span = days_in_year(day.year) if normalize_year else 365
    return doy / span


def polar(t, progress, r0, loop_gap):
    """Cartesian point for a within-year fraction and a loop count."""
    r = r0 + progress * loop_gap
    theta = START_ANGLE - 2 * math.pi * t
    return r * math.cos(theta), r * math.sin(theta)


def spiral_xy(day, year0, r0, loop_gap, normalize_year=True):
    """Cartesian position for one date."""
    t = year_fraction(day, normalize_year)
    return polar(t, (day.year - year0) + t, r0, loop_gap)


def band_polygon(year, year0, r0, loop_gap, width, steps=400):
    """Vertices of the filled ribbon for one loop, out along it and back."""
    outer, inner = [], []
    for i in range(steps + 1):
        t = i / steps
        progress = (year - year0) + t
        outer.append(polar(t, progress, r0 + width / 2, loop_gap))
        inner.append(polar(t, progress, r0 - width / 2, loop_gap))
    return outer + inner[::-1]


def cell_polygon(day, year0, r0, loop_gap, band_w, lo, hi,
                 normalize_year=True, steps=2):
    """Polygon covering one day's angular slice of the ribbon.

    `lo` and `hi` are fractions of the band width measured from its inner
    edge, so the full ribbon is 0..1 and a horizon band is 0..frac. A couple of
    angular steps keep the outer edge from visibly chording, since one day is
    only about a degree.
    """
    doy = day.timetuple().tm_yday - 1
    span = days_in_year(day.year) if normalize_year else 365
    base = day.year - year0
    off_lo = -band_w / 2 + lo * band_w
    off_hi = -band_w / 2 + hi * band_w
    outer, inner = [], []
    for i in range(steps + 1):
        t = (doy + i / steps) / span
        progress = base + t
        outer.append(polar(t, progress, r0 + off_hi, loop_gap))
        inner.append(polar(t, progress, r0 + off_lo, loop_gap))
    return outer + inner[::-1]


def draw_dots(ax, days, counts, cap, args, theme, geom):
    """Dot area encodes the count -- spiralize's spiral_points()."""
    r0, gap, band_w = geom
    xs, ys, sizes = [], [], []
    for day in days:
        v = counts[day]
        if v <= 0:
            continue
        x, y = spiral_xy(day, days[0].year, r0, gap, args.normalize_year)
        xs.append(x)
        ys.append(y)
        # scatter's `s` is area in points^2, so square the diameter.
        sizes.append(calc_pt_size(v, cap, args.min_pt, args.max_pt) ** 2)
    ax.scatter(xs, ys, s=sizes, color=theme["fg"], linewidths=0,
               alpha=0.9, zorder=3)


def draw_heatmap(ax, days, counts, cap, args, theme, geom):
    """Colour fills the full ribbon width per day -- spiral_rect().

    Zero days are left undrawn so the ribbon shows through as background,
    which is what separates a quiet stretch from a low-but-nonzero one.
    """
    r0, gap, band_w = geom
    cmap = LinearSegmentedColormap.from_list("spectral_r", SPECTRAL_R)
    norm = Normalize(vmin=0, vmax=cap)
    polys, colors = [], []
    for day in days:
        v = counts[day]
        if v <= 0:
            continue
        polys.append(cell_polygon(day, days[0].year, r0, gap, band_w, 0.0, 1.0,
                                  args.normalize_year))
        colors.append(cmap(norm(min(v, cap))))
    ax.add_collection(PolyCollection(polys, facecolors=colors, edgecolors="none",
                                     zorder=3))
    return cmap, norm


def horizon_breaks(peak, bands=HORIZON_BANDS):
    """Edges of the horizon slices, e.g. [0, 15, 30, 46, 61]."""
    step = peak / bands
    return [round(i * step) for i in range(bands + 1)]


def draw_horizon(ax, days, counts, peak, args, theme, geom):
    """A horizon chart folded into the ribbon -- spiral_horizon().

    Every slice of the value range is drawn from the same inner baseline and
    rescaled to the full ribbon height, so a day in the top slice reads as a
    full-height bar in the darkest colour. Slices are laid down palest first
    and the darker ones paint over them.
    """
    r0, gap, band_w = geom
    edges = horizon_breaks(peak)
    for i in range(HORIZON_BANDS):
        lo_v, hi_v = edges[i], edges[i + 1]
        span = hi_v - lo_v
        if span <= 0:
            continue
        polys = []
        for day in days:
            v = counts[day]
            if v <= lo_v:
                continue
            frac = min(v - lo_v, span) / span
            polys.append(cell_polygon(day, days[0].year, r0, gap, band_w,
                                      0.0, frac, args.normalize_year))
        if polys:
            ax.add_collection(PolyCollection(
                polys, facecolors=HORIZON_COLORS[i], edgecolors="none",
                zorder=3 + i))
    return edges


def size_ticks(cap, want=4):
    """Evenly stepped round values spanning the size scale.

    spiralize's legend runs a single step repeated (5, 10, 15, 20) rather than
    an ad-hoc set, so pick the round step nearest cap/want and walk it up.
    """
    if cap <= 0:
        return [1]
    raw = cap / want
    mag = 10 ** math.floor(math.log10(raw))
    # On a tie prefer the coarser step, which yields fewer, cleaner rows.
    step = min((abs(m * mag - raw), -m * mag, m * mag) for m in (1, 2, 2.5, 5, 10))[2]
    step = max(step, 1)  # counts are integers, so never step in fractions
    ticks, v = [], step
    while v <= cap + 1e-9 and len(ticks) < 6:
        ticks.append(int(v) if float(v).is_integer() else round(v, 1))
        v += step
    return ticks or [max(1, int(cap))]


def legend_block(ax, handles, caption, args, theme, handlelength=1.0,
                 handleheight=0.7):
    """Top-left inside the frame, as in spiralize's own output.

    Rows packed tight enough that consecutive swatches nearly touch, swatches
    in a narrow column, and a bold two-line title carrying the caption.
    """
    leg = ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.0),
        frameon=False, labelspacing=0.35, handletextpad=0.4,
        handlelength=handlelength, handleheight=handleheight,
        borderpad=0.0, borderaxespad=0.0,
        title=caption,
        fontsize=args.size * 1.25, title_fontsize=args.size * 1.25,
    )
    leg.get_title().set_ha("left")
    leg.get_title().set_fontweight("bold")
    leg._legend_box.align = "left"
    for text in leg.get_texts():
        text.set_color(theme["fg"])
    leg.get_title().set_color(theme["fg"])
    return leg


def colorbar_block(fig, ax, cmap, norm, cap, caption, args, theme):
    """Continuous scale for the heatmap, sat where the size legend would go."""
    cax = ax.inset_axes([0.005, 0.64, 0.022, 0.20])
    bar = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    bar.set_ticks(size_ticks(cap))
    bar.outline.set_visible(False)
    cax.tick_params(length=2, width=0.6, pad=3, labelsize=args.size * 1.25,
                    colors=theme["fg"])
    ax.text(
        0.0, 0.955, caption, transform=ax.transAxes, ha="left", va="top",
        color=theme["fg"], fontweight="bold", fontsize=args.size * 1.25,
        family="DejaVu Sans",
    )
    return bar


def build(counts, args, theme):
    """Draw the whole figure and return it.

    Everything shared sits here -- ribbons, month spokes, year labels, limits.
    Only the middle of the function varies by --style, dispatching to one of
    the draw_* helpers and its matching legend.
    """
    days = sorted(counts)
    year0, year1 = days[0].year, days[-1].year
    n_loops = year1 - year0 + 1

    active = [v for v in counts.values() if v > 0]
    if not active:
        sys.exit("every day is zero -- nothing to plot")
    cap = max(args.cap, max(active) * 0.9)

    r0 = args.inner_radius
    gap = args.loop_gap
    r_max = r0 + n_loops * gap

    fig, ax = plt.subplots(figsize=(args.size, args.size), dpi=args.dpi)
    fig.patch.set_facecolor(theme["bg"])
    ax.set_facecolor(theme["bg"])
    ax.set_aspect("equal")
    ax.axis("off")

    # Filled ribbon per loop, drawn first so everything else sits on top. The
    # gaps between ribbons are just background showing through.
    band_w = gap * BAND_FRACTION
    for year in range(year0, year1 + 1):
        ax.add_patch(
            plt.Polygon(
                band_polygon(year, year0, r0, gap, band_w),
                closed=True, facecolor=theme["band"], edgecolor="none",
                zorder=0,
            )
        )

    # Dashed month spokes, running from the centre out past the last loop.
    for m in range(12):
        frac = (dt.date(year1, m + 1, 1).timetuple().tm_yday - 1) / days_in_year(year1)
        theta = START_ANGLE - 2 * math.pi * frac
        outer = r_max + gap * 0.35
        ax.plot(
            [0.0, outer * math.cos(theta)], [0.0, outer * math.sin(theta)],
            color=theme["muted"], lw=0.7, zorder=1,
            linestyle=(0, (6, 4)), alpha=0.55,
        )

    geom = (r0, gap, band_w)
    total = sum(counts.values())
    caption = f"{args.column}\n(in total {total:,})"
    peak = max(active)

    if args.style == "dots":
        draw_dots(ax, days, counts, cap, args, theme, geom)
        handles = [
            Line2D(
                [], [], marker="o", linestyle="none",
                markersize=calc_pt_size(t, cap, args.min_pt, args.max_pt),
                markerfacecolor=theme["fg"], markeredgewidth=0,
                label=f"{t}" + ("+" if t >= cap else ""),
            )
            for t in size_ticks(cap)
        ]
        legend_block(ax, handles, caption, args, theme)
    elif args.style == "heatmap":
        cmap, norm = draw_heatmap(ax, days, counts, cap, args, theme, geom)
        colorbar_block(fig, ax, cmap, norm, cap, caption, args, theme)
    else:
        edges = draw_horizon(ax, days, counts, peak, args, theme, geom)
        # Darkest slice on top, the way the post's legend reads.
        handles = [
            Patch(facecolor=HORIZON_COLORS[i], edgecolor="none",
                  label=f"[{edges[i]}, {edges[i + 1]}]")
            for i in reversed(range(HORIZON_BANDS))
        ]
        legend_block(ax, handles, caption, args, theme,
                     handlelength=1.3, handleheight=1.3)

    # The legend title carries the caption, so a heading appears only on ask.
    if args.title:
        ax.set_title(
            args.title, color=theme["fg"], fontsize=args.size * 1.9,
            pad=args.size * 2.2, family="DejaVu Sans",
        )

    lim = r_max + gap * 1.6
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)

    # Year labels go on last, sized against the ribbon rather than against the
    # figure: rotated 90 degrees their glyph height runs radially, so anything
    # wider than the band spills over the gaps either side. Measuring the
    # drawn transform keeps that true whatever --size/--dpi/--loop-gap are.
    fig.canvas.draw()
    px_per_unit = abs(ax.transData.transform((band_w, 0))[0]
                      - ax.transData.transform((0, 0))[0])
    band_pt = px_per_unit * 72.0 / fig.dpi
    for year in range(year0, year1 + 1):
        r = r0 + (year - year0) * gap
        ax.text(
            r * math.cos(START_ANGLE), r * math.sin(START_ANGLE), str(year),
            ha="center", va="center", rotation=90, color=theme["fg"],
            fontsize=band_pt * LABEL_BAND_RATIO, family="DejaVu Sans", zorder=4,
        )
    return fig


def main():
    """Parse flags, render, and write the PNG plus an SVG twin."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="infile", default="data/contributions.csv")
    ap.add_argument("--out", default="spiral.png")
    ap.add_argument("--column", default="contributions",
                    choices=["contributions", "commits"])
    ap.add_argument("--theme", default="light", choices=list(THEMES))
    ap.add_argument("--style", default="dots",
                    choices=["dots", "heatmap", "horizon"],
                    help="dots = area-scaled points; heatmap = the ribbon "
                         "coloured per day; horizon = a folded horizon chart")
    ap.add_argument("--title")
    ap.add_argument("--cap", type=float, default=30.0,
                    help="floor for the dot-size ceiling (default 30, as in the post)")
    ap.add_argument("--min-pt", type=float, default=1.0)
    ap.add_argument("--max-pt", type=float, default=20.0)
    ap.add_argument("--inner-radius", type=float, default=0.6)
    ap.add_argument("--loop-gap", type=float, default=1.0)
    ap.add_argument("--size", type=float, default=11.0, help="figure size in inches")
    ap.add_argument("--dpi", type=int, default=160)
    ap.add_argument("--no-normalize-year", dest="normalize_year",
                    action="store_false")
    ap.add_argument("--no-svg", dest="svg", action="store_false",
                    help="skip the SVG twin; each one is roughly 1 MB of "
                         "individual scatter or cell elements")
    args = ap.parse_args()

    counts = read_counts(args.infile, args.column)
    fig = build(counts, args, THEMES[args.theme])

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print(f"wrote {args.out}", file=sys.stderr)

    stem, ext = os.path.splitext(args.out)
    if args.svg and ext.lower() != ".svg":
        fig.savefig(stem + ".svg", facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"wrote {stem}.svg", file=sys.stderr)


if __name__ == "__main__":
    main()
