#!/usr/bin/env python3
"""Pull daily contribution counts for a GitHub account via the GraphQL API.

The contributionsCollection endpoint is the data behind the green-squares
calendar on a profile page. It accepts at most a one-year window per call, so
we walk year by year from account creation to today.

Writes a tidy CSV: date,contributions,commits

  contributions -- the calendar number (commits + PRs + issues + reviews)
  commits       -- commit-only daily counts, reconstructed per repository

Auth: set GITHUB_TOKEN to a classic PAT with `read:user` (add `repo` to have
private contributions counted). Fine-grained tokens work too but must grant
read access to the repositories you want reflected.
"""

import argparse
import csv
import datetime as dt
import os
import sys
import time
from collections import defaultdict

import requests

API = "https://api.github.com/graphql"

VIEWER_Q = """
query { viewer { login createdAt } }
"""

USER_Q = """
query($login: String!) { user(login: $login) { login createdAt } }
"""

# One year of calendar days plus the per-repository commit breakdown. The
# calendar is authoritative for "did anything happen that day"; the repository
# breakdown is what lets us separate commits from issues/PRs/reviews.
YEAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner }
        contributions(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes { occurredAt commitCount }
        }
      }
    }
  }
}
"""


class GitHubError(RuntimeError):
    pass


def gql(session, query, variables=None, retries=4):
    """POST a GraphQL query, retrying on secondary rate limits and 5xx."""
    for attempt in range(retries):
        resp = session.post(
            API, json={"query": query, "variables": variables or {}}, timeout=30
        )
        if resp.status_code in (403, 429):
            # Secondary rate limit. Respect Retry-After when GitHub sends one.
            wait = int(resp.headers.get("Retry-After", 2 ** (attempt + 3)))
            print(f"  rate limited, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 401:
            raise GitHubError(
                "401 Unauthorized -- GITHUB_TOKEN is missing, expired, or lacks "
                "the read:user scope."
            )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise GitHubError("; ".join(e["message"] for e in payload["errors"]))
        return payload["data"]
    raise GitHubError(f"gave up after {retries} attempts")


def year_windows(created, until):
    """Yield (from, to) ISO timestamps in <=1y chunks, oldest first.

    Windows are cut on calendar-year boundaries so each spiral loop maps to one
    civil year rather than to an arbitrary anniversary of the signup date.
    """
    for year in range(created.year, until.year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(
            until, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        )
        if start <= end:
            yield start.isoformat().replace("+00:00", "Z"), end.isoformat().replace(
                "+00:00", "Z"
            )


def collect(session, login, created, until):
    calendar = {}
    commits = defaultdict(int)
    truncated_repos = set()

    for frm, to in year_windows(created, until):
        label = frm[:4]
        data = gql(session, YEAR_Q, {"login": login, "from": frm, "to": to})
        cc = data["user"]["contributionsCollection"]

        for week in cc["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                calendar[day["date"]] = day["contributionCount"]

        for repo in cc["commitContributionsByRepository"]:
            name = repo["repository"]["nameWithOwner"]
            for node in repo["contributions"]["nodes"]:
                day = node["occurredAt"][:10]
                commits[day] += node["commitCount"]
            if repo["contributions"]["pageInfo"]["hasNextPage"]:
                # >100 distinct commit-days in one repo in one year. Rare, and
                # paging it needs a per-repo query GitHub does not expose on
                # this connection, so flag it rather than silently undercount.
                truncated_repos.add(f"{name} ({label})")

        total = cc["contributionCalendar"]["totalContributions"]
        private = cc["restrictedContributionsCount"]
        print(
            f"  {label}: {total:>5} contributions "
            f"({cc['totalCommitContributions']} commit-contribs, "
            f"{private} private)",
            file=sys.stderr,
        )

    if truncated_repos:
        print(
            "\nWARNING: commit-only counts are undercounted for these "
            "repo-years (>100 active days each):",
            file=sys.stderr,
        )
        for r in sorted(truncated_repos):
            print(f"  - {r}", file=sys.stderr)
        print(
            "The `contributions` column is unaffected; prefer it if this "
            "matters.\n",
            file=sys.stderr,
        )

    return calendar, commits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="login to fetch (default: the token's owner)")
    ap.add_argument("--out", default="data/contributions.csv")
    ap.add_argument("--since", type=int, help="earliest year to include")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set. See README.md for how to mint one.")

    session = requests.Session()
    session.headers.update(
        {"Authorization": f"bearer {token}", "User-Agent": "spiral-git"}
    )

    if args.user:
        user = gql(session, USER_Q, {"login": args.user})["user"]
        if user is None:
            sys.exit(f"no such user: {args.user}")
    else:
        user = gql(session, VIEWER_Q)["viewer"]

    login = user["login"]
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    if args.since:
        created = max(created, dt.datetime(args.since, 1, 1, tzinfo=dt.timezone.utc))
    until = dt.datetime.now(dt.timezone.utc)

    print(f"{login}: {created.date()} -> {until.date()}", file=sys.stderr)
    calendar, commits = collect(session, login, created, until)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "contributions", "commits"])
        for day in sorted(calendar):
            w.writerow([day, calendar[day], commits.get(day, 0)])

    active = sum(1 for v in calendar.values() if v)
    print(
        f"\nwrote {args.out}: {len(calendar)} days, {active} active, "
        f"{sum(calendar.values())} contributions, {sum(commits.values())} commits",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
