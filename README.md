# spiral-git

Your entire GitHub history as a spiral — one loop per calendar year, angle =
day-of-year, dot size and color = that day's activity. A Python port of
[jokergoo's spiralize post](https://jokergoo.github.io/2022/02/03/spiral-visualization-of-daily-git-commits/),
pointed at a whole account instead of a single local repo.

Because angle is day-of-year, the same calendar date sits on the same radial
line in every loop — so seasonal habits (the December lull, the September
restart) show up as spokes, which a linear heatmap can't show you.

## Setup

```sh
uv venv .venv && uv pip install --python .venv/bin/python matplotlib requests
```

(`uv` rather than `python -m venv` because Ubuntu ships 3.12 without
`ensurepip`. If you'd rather, `sudo apt install python3.12-venv` and use
stdlib venv.)

## Token

`fetch_contributions.py` reads `GITHUB_TOKEN`. Mint one at
<https://github.com/settings/tokens>:

- **Classic token** — tick `read:user`. Add `repo` if you want commits in
  private repositories counted.
- **Fine-grained token** — no extra permissions needed for public data; grant
  read access to specific repos for private counts.

```sh
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Two settings on GitHub's side affect what comes back, and neither is something
the token can override:

1. Profile → **Contribution settings → Include private contributions on my
   profile.** Off, and private work is returned only as an opaque
   `restrictedContributionsCount` total, not as daily numbers.
2. Commits only count toward the calendar if the commit email is
   [linked to your account](https://github.com/settings/emails). Work committed
   under a stale `user.email` is invisible here — check the per-year totals the
   fetcher prints against your profile graph before trusting the picture.

## Run

```sh
export GITHUB_TOKEN=...
.venv/bin/python fetch_contributions.py            # -> data/contributions.csv
.venv/bin/python spiral.py --out out/spiral.png    # -> out/spiral.png + .svg
```

Or `./run.sh`, which does both.

Fetch options:

| flag | effect |
|---|---|
| `--user LOGIN` | someone else's public history (default: the token's owner) |
| `--since 2018` | skip early years |
| `--out PATH` | CSV destination |

The CSV has three columns — `date`, `contributions`, `commits`.
`contributions` is the green-squares number (commits + PRs + issues +
reviews); `commits` is commit-only, reconstructed from the per-repository
breakdown.

## Render

```sh
.venv/bin/python spiral.py --column commits --theme light --out out/commits.png
```

| flag | default | notes |
|---|---|---|
| `--column` | `contributions` | or `commits` |
| `--theme` | `dark` | or `light` |
| `--cap` | `30` | floor for the dot-size ceiling; the actual cap is `max(cap, 0.9 × busiest day)`, so a few 200-commit days can't flatten everything else |
| `--max-pt` | `20` | largest dot diameter in points — drop it if your loops overlap |
| `--loop-gap` | `1.0` | radial distance between years; raise it for a long history |
| `--inner-radius` | `2.2` | size of the hole in the middle |
| `--size` / `--dpi` | `11` / `160` | figure inches and resolution |
| `--no-normalize-year` | off | by default day-of-year is divided by that year's real length so leap years stay aligned; this turns that off |
| `--title` | auto | |

An SVG is written alongside any non-SVG output.

## Reading it

Jan 1 is at 12 o'clock and time runs clockwise. Years read outward — innermost
loop is your first year. A dot's area and color both encode the same number
(redundant on purpose; area alone is hard to judge, color alone loses the
small values against the background).

## Caveats

- The calendar API returns at most one year per call, so the fetcher makes one
  request per year of your account's life. A 10-year account is 10 requests —
  nowhere near the 5000/hr limit.
- **The `commits` column needs `repo` scope.** Without it, GitHub returns your
  private activity only as an anonymous `restrictedContributionsCount` — the
  daily totals are still correct, but the per-repository breakdown that
  `commits` is built from comes back nearly empty. If the fetcher's per-year
  output shows a large `private` number next to a small `commit-contribs`
  number, that's what happened: use `--column contributions`, or re-mint the
  token with `repo` and re-run.
- Commit-only counts also undercount a repository with more than 100 active
  days in a single year; the fetcher prints a warning naming any repo-year
  affected. The `contributions` column is exact regardless.
- Forked-repo commits and commits to non-default branches follow GitHub's own
  contribution rules, which exclude some of them. This mirrors your profile
  graph — it is not a raw `git log` count.
