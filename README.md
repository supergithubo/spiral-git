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

`contributions` is the green-squares number: commits **plus** issues opened,
pull requests opened, PR reviews submitted, and repositories created. It is
the sum GitHub itself renders on your profile.

`commits` is commit-only, reconstructed from the per-repository breakdown —
so it is a strict subset of `contributions`, and it is only complete when the
token carries `repo` scope (see [What actually
counts](#what-actually-counts)).

## Render

```sh
.venv/bin/python spiral.py --column commits --theme light --out out/commits.png
```

Two styles over the same geometry:

- **`modern`** (default) — Jan 1 at 12 o'clock, month names around the rim,
  dots carrying both size and a Spectral color ramp.
- **`classic`** — spiralize's own default rendering: Jan 1 at 3 o'clock, each
  loop a filled grey ribbon separated by background-colored gaps, monochrome
  dots sized by count only, year labels set vertically along the east axis,
  dashed month spokes and no month names.

```sh
.venv/bin/python spiral.py --style classic --theme light --out out/classic.png
```

| flag | default | notes |
|---|---|---|
| `--column` | `contributions` | or `commits` |
| `--style` | `modern` | or `classic` |
| `--theme` | `dark` | or `light` |
| `--cap` | `30` | floor for the dot-size ceiling; the actual cap is `max(cap, 0.9 × busiest day)`, so a few 200-commit days can't flatten everything else |
| `--max-pt` | `20` | largest dot diameter in points — drop it if your loops overlap |
| `--loop-gap` | `1.0` | radial distance between years; raise it for a long history |
| `--inner-radius` | per style | `2.2` for `modern`, `0.6` for `classic` |
| `--size` / `--dpi` | `11` / `160` | figure inches and resolution |
| `--no-normalize-year` | off | by default day-of-year is divided by that year's real length so leap years stay aligned; this turns that off |
| `--title` | auto | |

An SVG is written alongside any non-SVG output.

## Reading it

Jan 1 is at 12 o'clock and time runs clockwise. Years read outward — innermost
loop is your first year. A dot's area and color both encode the same number
(redundant on purpose; area alone is hard to judge, color alone loses the
small values against the background).

## What actually counts

These plots inherit GitHub's contribution rules wholesale — they are not a raw
`git log` over everything you've ever written.

**Forks are excluded.** GitHub only counts commits made in a standalone
repository; commits pushed to a fork never reach the contribution calendar, no
matter whose fork it is or what the token can see. If those commits later land
upstream through a pull request, the *PR* counts as one contribution — but the
individual commits still don't. There is no API flag that turns this off. If
your fork work matters to you, the only way to capture it is to clone the forks
and aggregate `git log --author=<you>` locally.

Two further exclusions from the same rule set: commits outside the default
branch (and `gh-pages`) don't count, and commits authored under an email that
isn't [linked to your account](https://github.com/settings/emails) don't count.

**Private repositories are included.** Their daily numbers land in the
`contributions` column like any other, they're just anonymized — GitHub reports
them as an opaque `restrictedContributionsCount` rather than naming the repo.
You can confirm this in the fetcher's per-year output: a year printed as
`2,119 contributions (45 commit-contribs, 2,061 private)` has the 2,061 private
ones *inside* the 2,119, otherwise the total would read 58.

This is why `--column contributions` is the honest default and `commits` is
not: the `commits` column is rebuilt from the per-repository breakdown, which
private repos only appear in when the token carries `repo` scope. Two
prerequisites for private work to show up at all:

1. A token with `repo` scope (needed only for the `commits` column — the
   `contributions` column works without it).
2. Profile → **Contribution settings → Include private contributions on my
   profile** switched on.

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
- Forks, non-default branches and unlinked commit emails are all excluded by
  GitHub before the data ever reaches us — see [What actually
  counts](#what-actually-counts). This mirrors your profile graph exactly; it
  is not a raw `git log` count.
