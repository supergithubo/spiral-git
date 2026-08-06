#!/usr/bin/env python3
"""Render daily activity as an Archimedean spiral, one loop per calendar year.

A Python port of the spiralize approach in jokergoo's "Spiral visualization of
daily git commits". Angle encodes day-of-year, so the same calendar date lines
up radially across every loop; radius encodes which year. Dot area and color
both encode the day's count.

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
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D

# RColorBrewer "Spectral", reversed so low counts are cool and high are warm --
# the same ramp the original post feeds to circlize::colorRamp2().
SPECTRAL_R = [
    "#5E4FA2", "#3288BD", "#66C2A5", "#ABDDA4", "#E6F598", "#FFFFBF",
    "#FEE08B", "#FDAE61", "#F46D43", "#D53E4F", "#9E0142",
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

THEMES = {
    "dark": dict(bg="#0d1117", fg="#e6edf3", muted="#7d8590", grid="#21262d"),
    "light": dict(bg="#ffffff", fg="#1f2328", muted="#656d76", grid="#d8dee4"),
}



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


def spiral_xy(day, year0, r0, loop_gap, normalize_year=True):
    """Cartesian position for one date.

    normalize_year rescales day-of-year by that year's actual length, so leap
    years do not slowly rotate February out of alignment across loops.
    """
    doy = day.timetuple().tm_yday - 1
    span = days_in_year(day.year) if normalize_year else 365
    t = doy / span
    progress = (day.year - year0) + t
    r = r0 + progress * loop_gap
    # Jan 1 at 12 o'clock, time running clockwise.
    theta = math.pi / 2 - 2 * math.pi * t
    return r * math.cos(theta), r * math.sin(theta), r, t


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

    cmap = LinearSegmentedColormap.from_list("spectral_r", SPECTRAL_R)
    norm = Normalize(vmin=0, vmax=cap)

    # Month spokes, drawn under the data.
    for m in range(12):
        frac = (dt.date(year1, m + 1, 1).timetuple().tm_yday - 1) / days_in_year(year1)
        theta = math.pi / 2 - 2 * math.pi * frac
        # Start outside the hub -- spokes run to the centre turn the middle of
        # the plot into a starburst that competes with the data.
        ax.plot(
            [r0 * 0.92 * math.cos(theta), (r_max + gap * 0.35) * math.cos(theta)],
            [r0 * 0.92 * math.sin(theta), (r_max + gap * 0.35) * math.sin(theta)],
            color=theme["grid"], lw=0.7, zorder=0,
        )
        # Label at the midpoint of the month, not on the spoke itself.
        mid = frac + (1 / 24)
        mt = math.pi / 2 - 2 * math.pi * mid
        lr = r_max + gap * 1.05
        ax.text(
            lr * math.cos(mt), lr * math.sin(mt), MONTHS[m],
            ha="center", va="center", color=theme["muted"],
            fontsize=args.size * 1.15, family="DejaVu Sans",
        )

    # A faint guide curve so empty stretches still read as a continuous year.
    guide_x, guide_y = [], []
    cursor = days[0]
    while cursor <= days[-1]:
        x, y, _, _ = spiral_xy(cursor, year0, r0, gap, args.normalize_year)
        guide_x.append(x)
        guide_y.append(y)
        cursor += dt.timedelta(days=1)
    ax.plot(guide_x, guide_y, color=theme["grid"], lw=0.8, zorder=1)

    xs, ys, sizes, vals = [], [], [], []
    for day in days:
        v = counts[day]
        if v <= 0:
            continue
        x, y, _, _ = spiral_xy(day, year0, r0, gap, args.normalize_year)
        xs.append(x)
        ys.append(y)
        # scatter's `s` is area in points^2, so square the diameter.
        sizes.append(calc_pt_size(v, cap, args.min_pt, args.max_pt) ** 2)
        vals.append(v)

    ax.scatter(
        xs, ys, s=sizes, c=vals, cmap=cmap, norm=norm,
        linewidths=0, alpha=0.92, zorder=3,
    )

    # Year labels ride just inside each loop, on the Jan-1 spoke.
    for year in range(year0, year1 + 1):
        r = r0 + (year - year0) * gap
        ax.text(
            0, r + gap * 0.30, str(year),
            ha="center", va="bottom", color=theme["fg"],
            fontsize=args.size * 1.0, family="DejaVu Sans", zorder=4,
            bbox=dict(boxstyle="round,pad=0.18", fc=theme["bg"], ec="none", alpha=0.85),
        )

    # Size legend -- the color bar alone hides that area is also encoding.
    ticks = [t for t in (1, 5, 10, 25, 50, 100) if t <= cap]
    if not ticks or ticks[-1] < cap * 0.6:
        ticks.append(int(cap))
    handles = [
        Line2D(
            [], [], marker="o", linestyle="none",
            markersize=calc_pt_size(t, cap, args.min_pt, args.max_pt),
            markerfacecolor=cmap(norm(t)), markeredgewidth=0,
            label=f"{t}" + ("+" if t >= cap else ""),
        )
        for t in ticks
    ]
    # Sits fully outside the axes -- inside the corner it lands on the month
    # ring, and the largest swatch is big enough to cover a real data point.
    leg = ax.legend(
        handles=handles, loc="center left", bbox_to_anchor=(1.0, 0.5),
        frameon=False, labelspacing=1.6, handletextpad=1.4, borderpad=1.0,
        title=f"{args.column}/day", fontsize=args.size * 1.0,
        title_fontsize=args.size * 1.1,
    )
    for text in leg.get_texts():
        text.set_color(theme["muted"])
    leg.get_title().set_color(theme["muted"])

    total = sum(counts.values())
    ax.set_title(
        args.title or f"{args.column} per day, {year0}\u2013{year1}",
        color=theme["fg"], fontsize=args.size * 1.9, pad=args.size * 2.2,
        family="DejaVu Sans",
    )
    fig.text(
        0.5, 0.035,
        f"{total:,} {args.column} across {len(active):,} active days "
        f"\u00b7 one loop = one year \u00b7 dots capped at {int(cap)}",
        ha="center", color=theme["muted"], fontsize=args.size * 1.0,
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
    ap.add_argument("--theme", default="dark", choices=list(THEMES))
    ap.add_argument("--title")
    ap.add_argument("--cap", type=float, default=30.0,
                    help="floor for the dot-size ceiling (default 30, as in the post)")
    ap.add_argument("--min-pt", type=float, default=1.0)
    ap.add_argument("--max-pt", type=float, default=20.0)
    ap.add_argument("--inner-radius", type=float, default=2.2)
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
