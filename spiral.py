#!/usr/bin/env python3
"""Render daily activity as an Archimedean spiral, one loop per calendar year.

A Python port of the spiralize approach in jokergoo's "Spiral visualization of
daily git commits". Angle encodes day-of-year, so the same calendar date lines
up radially across every loop; radius encodes which year. Dot area encodes the
day's count.

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
from matplotlib.lines import Line2D

THEMES = {
    "dark": dict(bg="#0d1117", fg="#e6edf3", muted="#7d8590", band="#1c2128"),
    "light": dict(bg="#ffffff", fg="#1f2328", muted="#656d76", band="#eaeaea"),
}

# Jan 1 sits at 3 o'clock and time runs clockwise, so every loop begins on the
# east axis -- which is what lets the year labels stack there as a ruler.
START_ANGLE = 0.0

# Fraction of the loop pitch filled by the ribbon; the remainder is the gap.
BAND_FRACTION = 0.62


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


def size_ticks(cap):
    """Round legend values that span the size scale without crowding it."""
    candidates = [1, 2, 5, 10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200]
    ticks = [t for t in candidates if t <= cap]
    if not ticks:
        return [max(1, int(cap))]
    while len(ticks) > 6:
        ticks = ticks[::2] if len(ticks) > 8 else ticks[1:]
    if ticks[-1] < cap * 0.7:
        ticks.append(int(cap))
    return ticks


def build(counts, args, theme):
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

    xs, ys, sizes = [], [], []
    for day in days:
        v = counts[day]
        if v <= 0:
            continue
        x, y = spiral_xy(day, year0, r0, gap, args.normalize_year)
        xs.append(x)
        ys.append(y)
        # scatter's `s` is area in points^2, so square the diameter.
        sizes.append(calc_pt_size(v, cap, args.min_pt, args.max_pt) ** 2)

    ax.scatter(xs, ys, s=sizes, color=theme["fg"], linewidths=0,
               alpha=0.9, zorder=3)

    # Year labels set vertically along the axis each loop starts on.
    for year in range(year0, year1 + 1):
        r = r0 + (year - year0) * gap
        ax.text(
            r * math.cos(START_ANGLE), r * math.sin(START_ANGLE), str(year),
            ha="center", va="center", rotation=90, color=theme["fg"],
            fontsize=args.size * 0.95, family="DejaVu Sans", zorder=4,
            bbox=dict(boxstyle="square,pad=0.10", fc=theme["bg"],
                      ec="none", alpha=0.75),
        )

    total = sum(counts.values())
    handles = [
        Line2D(
            [], [], marker="o", linestyle="none",
            markersize=calc_pt_size(t, cap, args.min_pt, args.max_pt),
            markerfacecolor=theme["fg"], markeredgewidth=0,
            label=f"{t}" + ("+" if t >= cap else ""),
        )
        for t in size_ticks(cap)
    ]
    # Top-left inside the frame, as in spiralize's own output.
    leg = ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(-0.02, 1.02),
        frameon=False, labelspacing=1.2, handletextpad=1.0,
        title=f"{args.column}\n(in total {total:,})",
        fontsize=args.size * 1.05, title_fontsize=args.size * 1.15,
    )
    leg.get_title().set_ha("left")
    leg.get_title().set_fontweight("bold")
    for text in leg.get_texts():
        text.set_color(theme["fg"])
    leg.get_title().set_color(theme["fg"])

    # The legend title carries the caption, so a heading appears only on ask.
    if args.title:
        ax.set_title(
            args.title, color=theme["fg"], fontsize=args.size * 1.9,
            pad=args.size * 2.2, family="DejaVu Sans",
        )

    lim = r_max + gap * 1.6
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    return fig


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="infile", default="data/contributions.csv")
    ap.add_argument("--out", default="spiral.png")
    ap.add_argument("--column", default="contributions",
                    choices=["contributions", "commits"])
    ap.add_argument("--theme", default="light", choices=list(THEMES))
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
    args = ap.parse_args()

    counts = read_counts(args.infile, args.column)
    fig = build(counts, args, THEMES[args.theme])

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print(f"wrote {args.out}", file=sys.stderr)

    stem, ext = os.path.splitext(args.out)
    if ext.lower() != ".svg":
        fig.savefig(stem + ".svg", facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"wrote {stem}.svg", file=sys.stderr)


if __name__ == "__main__":
    main()
