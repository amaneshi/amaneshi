#!/usr/bin/env python3
"""Regenerate the stat cards in assets/ from live GitHub data.

Needs an authenticated `gh` CLI (repo + read:org scopes) so private and
organization repositories are counted. Only aggregates are written out;
no private repository names end up in the generated files.

    python3 scripts/gen_stats.py
"""
import collections
import concurrent.futures
import datetime
import json
import pathlib
import subprocess

OWNERS = {"amaneshi", "grassbusinesslabs", "amadev-net"}
ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FIRST_YEAR = 2017

# GitHub linguist colors for the languages that show up here.
LANG_COLORS = {
    "Go": "#00ADD8", "TypeScript": "#3178c6", "Vue": "#41b883", "PHP": "#4F5D95",
    "C#": "#178600", "JavaScript": "#f1e05a", "HTML": "#e34c26", "SCSS": "#c6538c",
    "CSS": "#663399", "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Python": "#3572A5",
    "Java": "#b07219", "C++": "#f34b7d", "Solidity": "#AA6746", "Shell": "#89e051",
}
OTHER_COLOR = "#8b949e"

STYLE = """
<style>
  .t { font: 600 15px 'Segoe UI', Ubuntu, sans-serif; fill: #1f2328; }
  .l { font: 400 12px 'Segoe UI', Ubuntu, sans-serif; fill: #59636e; }
  .v { font: 600 12px 'Segoe UI', Ubuntu, sans-serif; fill: #1f2328; }
  .bg { fill: #ffffff; stroke: #d1d9e0; }
  .track { fill: #eff2f5; }
  .bar { fill: #00ADD8; }
  @media (prefers-color-scheme: dark) {
    .t, .v { fill: #f0f6fc; }
    .l { fill: #9198a1; }
    .bg { fill: #0d1117; stroke: #3d444d; }
    .track { fill: #151b23; }
  }
</style>
"""


def gh(*args):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def own_repos():
    pages = gh("api", "--paginate", "--slurp",
               "/user/repos?per_page=100&affiliation=owner,organization_member")
    return [r for page in pages for r in page
            if r["owner"]["login"] in OWNERS and not r["fork"] and not r["archived"]]


def language_bytes(repos):
    total = collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for langs in pool.map(lambda r: gh("api", f"/repos/{r['full_name']}/languages"), repos):
            total.update(langs)
    return total


def contributions_by_year():
    years = {}
    for y in range(FIRST_YEAR, datetime.date.today().year + 1):
        q = ('{viewer{contributionsCollection(from:"%d-01-01T00:00:00Z",to:"%d-12-31T23:59:59Z")'
             '{contributionCalendar{totalContributions}}}}' % (y, y))
        data = gh("api", "graphql", "-f", f"query={q}")
        years[y] = data["data"]["viewer"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    return years


def languages_svg(lang_bytes, top=8):
    common = lang_bytes.most_common()
    shown, rest = common[:top], sum(b for _, b in common[top:])
    if rest:
        shown.append(("Other", rest))
    total = sum(b for _, b in shown)
    w, pad = 400, 20
    rows = (len(shown) + 1) // 2
    h = 78 + rows * 24
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           STYLE,
           f'<rect class="bg" x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6"/>',
           f'<text class="t" x="{pad}" y="32">Languages across my repositories</text>',
           f'<clipPath id="c"><rect x="{pad}" y="46" width="{w-2*pad}" height="8" rx="4"/></clipPath>',
           '<g clip-path="url(#c)">']
    x = pad
    for name, b in shown:
        seg = (w - 2 * pad) * b / total
        out.append(f'<rect x="{x:.2f}" y="46" width="{seg + 0.5:.2f}" height="8" '
                   f'fill="{LANG_COLORS.get(name, OTHER_COLOR)}"/>')
        x += seg
    out.append('</g>')
    for i, (name, b) in enumerate(shown):
        cx = pad + (i % 2) * (w - 2 * pad) / 2
        cy = 80 + (i // 2) * 24
        out.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{LANG_COLORS.get(name, OTHER_COLOR)}"/>')
        out.append(f'<text class="l" x="{cx + 16}" y="{cy}">{name} '
                   f'<tspan class="v">{100 * b / total:.1f}%</tspan></text>')
    out.append('</svg>')
    return "\n".join(out)


def activity_svg(years):
    w, pad, top, bottom = 400, 20, 52, 30
    items = list(years.items())
    h = 200
    chart_h = h - top - bottom
    peak = max(years.values()) or 1
    slot = (w - 2 * pad) / len(items)
    bar_w = slot * 0.6
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           STYLE,
           f'<rect class="bg" x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6"/>',
           f'<text class="t" x="{pad}" y="32">Contributions per year</text>',
           f'<text class="l" x="{w - pad}" y="32" text-anchor="end">{sum(years.values()):,} total</text>']
    for i, (year, n) in enumerate(items):
        x = pad + i * slot + (slot - bar_w) / 2
        bh = max(2, chart_h * n / peak)
        y = top + chart_h - bh
        out.append(f'<rect class="track" x="{x:.1f}" y="{top}" width="{bar_w:.1f}" height="{chart_h}" rx="3"/>')
        out.append(f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="3">'
                   f'<title>{year}: {n} contributions</title></rect>')
        if n:
            out.append(f'<text class="v" x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle">{n}</text>')
        out.append(f'<text class="l" x="{x + bar_w / 2:.1f}" y="{h - 12}" text-anchor="middle">'
                   f"'{str(year)[2:]}</text>")
    out.append('</svg>')
    return "\n".join(out)


def main():
    ASSETS.mkdir(exist_ok=True)
    repos = own_repos()
    langs = language_bytes(repos)
    years = contributions_by_year()
    (ASSETS / "languages.svg").write_text(languages_svg(langs))
    (ASSETS / "activity.svg").write_text(activity_svg(years))
    print(f"{len(repos)} repos, top languages: {[l for l, _ in langs.most_common(8)]}")
    print(f"contributions: {years}")


if __name__ == "__main__":
    main()
