#!/usr/bin/env python3
"""Update the GitHub stats block inside README.md (total commits, current and longest streak).

Standard library only. Run locally with `python generate_stats.py` or let the
GitHub Action in .github/workflows/update-stats.yml run it on a schedule.
Only the text between the STATS:START and STATS:END markers is rewritten.

Environment variables (all optional):
  GH_USER   GitHub username (default: yogesh0405)
  GH_TOKEN  token used for the commit search (raises the API rate limit)
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request

USER = os.environ.get("GH_USER", "yogesh0405")
TOKEN = os.environ.get("GH_TOKEN", "")
README = os.environ.get("README_PATH", "README.md")
FIRST_YEAR = 2016  # earliest year to look at; years with no activity are harmless


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "readme-stats", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def contribution_days(year):
    """Return {date: contribution_count} for one calendar year."""
    url = f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31"
    html = fetch(url)
    ids = {}
    for tag in re.findall(r"<td[^>]*>", html):
        d = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        i = re.search(r'id="(contribution-day-component-\d+-\d+)"', tag)
        if d and i:
            ids[i.group(1)] = d.group(1)
    days = {}
    for ref, text in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)', html):
        if ref not in ids:
            continue
        text = text.strip()
        m = re.match(r"(\d[\d,]*)\s+contribution", text)
        days[ids[ref]] = int(m.group(1).replace(",", "")) if m else 0
    return days


def total_commits():
    """Public commits authored by the user (GitHub commit search)."""
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.loads(fetch(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1", headers))
    return int(data["total_count"])


def streaks(days, today):
    dates = sorted(d for d in days if d <= today.isoformat())
    longest = (0, None, None)
    run, start = 0, None
    prev = None
    for d in dates:
        day = dt.date.fromisoformat(d)
        if days[d] > 0:
            if prev is not None and (day - prev).days == 1 and run > 0:
                run += 1
            else:
                run, start = 1, day
            if run > longest[0]:
                longest = (run, start, day)
        else:
            run = 0
        prev = day

    # current streak: walk back from today (or yesterday if today has no activity yet)
    cur_end = today if days.get(today.isoformat(), 0) > 0 else today - dt.timedelta(days=1)
    cur, d = 0, cur_end
    while days.get(d.isoformat(), 0) > 0:
        cur += 1
        d -= dt.timedelta(days=1)
    cur_range = (d + dt.timedelta(days=1), cur_end) if cur else (None, None)
    return (cur, *cur_range), longest


def fmt_range(a, b):
    if not a:
        return "No active streak"
    f = lambda x: f"{x.strftime('%b')} {x.day}" + (f", {x.year}" if x.year != dt.date.today().year else "")
    return f(a) if a == b else f"{f(a)} - {f(b)}"


START, END = "<!--STATS:START-->", "<!--STATS:END-->"
SPARK = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
MILESTONES = [50, 100, 250, 500, 750, 1000, 1500, 2500, 5000, 7500, 10000, 25000, 50000]


def bar(fraction, width=18):
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return "\u25b0" * filled + "\u25b1" * (width - filled)


def sparkline(days, today, length=30):
    counts = [days.get((today - dt.timedelta(days=i)).isoformat(), 0) for i in range(length - 1, -1, -1)]
    top = max(counts) or 1
    chars = [SPARK[0] if n == 0 else SPARK[max(1, round(n / top * 7))] for n in counts]
    return "".join(chars), sum(counts), sum(1 for n in counts if n)


def badge(label, value, color):
    label = label.replace(" ", "%20")
    return (f'<img src="https://img.shields.io/badge/{label}-{value}-{color}'
            f'?style=for-the-badge&labelColor=0f172a" alt="{label.replace("%20", " ")}: {value}"/>')


def build_block(days, commits, since, cur, longest, updated, today):
    c_len, c_a, c_b = cur
    l_len, l_a, l_b = longest
    past = {d: n for d, n in days.items() if d <= today.isoformat()}
    total_contrib = sum(past.values())
    active_days = sum(1 for n in past.values() if n)
    best_day = max(past.values()) if past else 0

    nxt = next((m for m in MILESTONES if m > commits), commits)
    commit_frac = commits / nxt if nxt else 1
    streak_frac = (c_len / l_len) if l_len else 0
    streak_pct = round(streak_frac * 100)

    def th(icon, label):
        return (f'<th width="33%" align="center">'
                f'<img src="./assets/icons/{icon}" width="20" height="20" align="absmiddle" alt=""/>&nbsp; {label}<br/>'
                f'<img src="./assets/spacer.svg" width="260" height="1" alt=""/>'
                f'</th>')

    return f"""{START}
<table width="100%">
<thead>
<tr>
{th("icon-commit.svg", "TOTAL COMMITS")}
{th("icon-streak.svg", "CURRENT STREAK")}
{th("icon-trophy.svg", "LONGEST STREAK")}
</tr>
</thead>
<tbody>
<tr>
<td width="33%" align="center"><h1>{commits:,}</h1><b>commits</b><br/><sub>public repositories {since}</sub></td>
<td width="33%" align="center"><h1>{c_len}</h1><b>days</b><br/><sub>{fmt_range(c_a, c_b)}</sub></td>
<td width="33%" align="center"><h1>{l_len}</h1><b>days</b><br/><sub>{fmt_range(l_a, l_b)}</sub></td>
</tr>
<tr>
<td width="33%" align="center"><code>{bar(commit_frac)}</code><br/><sub>{round(commit_frac * 100)}% of the way to {nxt:,} commits</sub></td>
<td width="33%" align="center"><code>{bar(streak_frac)}</code><br/><sub>{streak_pct}% of personal best</sub></td>
<td width="33%" align="center"><code>{bar(1.0)}</code><br/><sub>100% of personal best</sub></td>
</tr>
</tbody>
</table>

<p align="center">
{badge("CONTRIBUTIONS", f"{total_contrib:,}", "0d9488")}
{badge("ACTIVE DAYS", active_days, "d97706")}
{badge("BEST DAY", best_day, "0d9488")}
</p>

<p align="center"><sub>Auto-updated on {updated}</sub></p>
{END}"""


def main():
    today = dt.date.today()
    days = {}
    for year in range(FIRST_YEAR, today.year + 1):
        try:
            days.update(contribution_days(year))
        except urllib.error.URLError as exc:
            print(f"warning: could not read {year}: {exc}")
        time.sleep(0.4)
    if not days:
        raise SystemExit("No contribution data found; README left unchanged.")
    active = sorted(d for d, n in days.items() if n > 0)
    since = f"since {dt.date.fromisoformat(active[0]).strftime('%b %Y')}" if active else ""
    commits = total_commits()
    cur, longest = streaks(days, today)
    updated = today.strftime("%b %d, %Y").replace(" 0", " ")
    block = build_block(days, commits, since, cur, longest, updated, today)

    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"Markers {START} / {END} not found in {README}.")
    with open(README, "w", encoding="utf-8") as fh:
        fh.write(pattern.sub(lambda _m: block, text, count=1))
    print(f"commits={commits} current={cur[0]} longest={longest[0]} {since}")


if __name__ == "__main__":
    main()