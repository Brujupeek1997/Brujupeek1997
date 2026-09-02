from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
DATA_PATH = ASSET_DIR / "profile-data.json"
USERNAME = os.environ.get("PROFILE_USERNAME", "Brujupeek1997")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
USER_AGENT = "Brujupeek-profile-readme-assets/1.0"

THEMES = {
    "dark": {
        "background": "#0d1117",
        "border": "#30363d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "accent": "#2f81f7",
        "levels": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
    "light": {
        "background": "#ffffff",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#656d76",
        "accent": "#0969da",
        "levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
}

LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#F1E05A",
    "TypeScript": "#3178C6",
    "CSS": "#663399",
    "HTML": "#E34C26",
    "C++": "#F34B7D",
    "C#": "#178600",
    "Kotlin": "#A97BFF",
    "Java": "#B07219",
    "Shell": "#89E051",
}


def request(url: str, accept: str) -> bytes:
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    if TOKEN and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(request(url, "application/vnd.github+json").decode("utf-8"))


def fetch_text(url: str) -> str:
    return request(url, "text/html,application/xhtml+xml").decode("utf-8", errors="replace")


def load_cached_data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def write_if_changed(path: Path, content: str) -> None:
    normalized = content.rstrip() + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == normalized:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized, encoding="utf-8", newline="\n")


def read_repository_data(cached: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = fetch_json(f"https://api.github.com/users/{USERNAME}")
        raw_repositories = fetch_json(
            f"https://api.github.com/users/{USERNAME}/repos?type=owner&sort=updated&per_page=100"
        )
        repositories: list[dict[str, Any]] = []
        for repository in raw_repositories:
            if repository.get("fork"):
                continue
            name = repository["name"]
            languages = fetch_json(repository["languages_url"])
            has_workflow = False
            try:
                workflow_files = fetch_json(
                    f"https://api.github.com/repos/{USERNAME}/{name}/contents/.github/workflows"
                )
                has_workflow = bool(workflow_files)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            repositories.append(
                {
                    "name": name,
                    "fork": False,
                    "has_pages": bool(repository.get("has_pages")),
                    "has_workflow": has_workflow,
                    "languages": languages,
                }
            )
        if len(raw_repositories) != int(profile["public_repos"]):
            raise ValueError("GitHub returned an incomplete repository list")
        return {
            **cached,
            "profile": {"login": profile["login"], "public_repos": profile["public_repos"]},
            "repositories": repositories,
        }
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"GitHub API unavailable; using the last verified repository snapshot: {error}")
        return cached


def read_contributions(data: dict[str, Any]) -> tuple[dict[str, Any], dict[date, int]]:
    try:
        contribution_html = fetch_text(f"https://github.com/users/{USERNAME}/contributions")
        total_match = re.search(
            r">\s*([\d,]+)\s+contributions?\s+in the last year",
            contribution_html,
            flags=re.IGNORECASE,
        )
        cells = re.findall(
            r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="([0-4])"[^>]*>',
            contribution_html,
        )
        if not cells:
            raise ValueError("No contribution cells were returned")
        levels = {date.fromisoformat(day): int(level) for day, level in cells}
        if total_match:
            data = {**data, "contributions_total": int(total_match.group(1).replace(",", ""))}
        return data, levels
    except (OSError, TypeError, ValueError) as error:
        print(f"Contribution calendar unavailable; keeping the existing activity cards: {error}")
        return data, {}


def text_element(
    x: float,
    y: float,
    value: object,
    color: str,
    size: int,
    weight: int = 400,
    anchor: str = "start",
) -> str:
    safe_value = html.escape(str(value))
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">'
        f"{safe_value}</text>"
    )


def svg_shell(width: int, height: int, theme: dict[str, Any], content: list[str], title: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
            f"  <title>{html.escape(title)}</title>",
            f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{theme["background"]}" stroke="{theme["border"]}"/>',
            f'  <rect x="18" y="18" width="4" height="28" rx="2" fill="{theme["accent"]}"/>',
            *[f"  {line}" for line in content],
            "</svg>",
        ]
    )


def render_stats(data: dict[str, Any], theme: dict[str, Any]) -> str:
    repositories = data["repositories"]
    project_repositories = [
        repository
        for repository in repositories
        if repository.get("name", "").casefold() != USERNAME.casefold()
    ]
    metrics = [
        (len(repositories), "PUBLIC REPOS"),
        (data.get("contributions_total", 0), "12-MO CONTRIBS"),
        (sum(bool(repo.get("has_pages")) for repo in project_repositories), "GITHUB PAGES"),
        (sum(bool(repo.get("has_workflow")) for repo in project_repositories), "WITH ACTIONS"),
    ]
    content = [
        text_element(32, 31, "GitHub Snapshot", theme["text"], 17, 600),
        text_element(32, 50, "Public engineering footprint", theme["muted"], 11),
    ]
    for index, (value, label) in enumerate(metrics):
        x = 52 + index * 105
        content.append(text_element(x, 107, value, theme["accent"], 27, 700, "middle"))
        content.append(text_element(x, 129, label, theme["muted"], 10, 600, "middle"))
    content.append(text_element(24, 169, f"@{USERNAME}", theme["muted"], 10))
    return svg_shell(420, 190, theme, content, f"GitHub statistics for {USERNAME}")


def render_languages(data: dict[str, Any], theme: dict[str, Any]) -> str:
    totals: Counter[str] = Counter()
    for repository in data["repositories"]:
        if repository.get("name", "").casefold() == USERNAME.casefold():
            continue
        totals.update(repository.get("languages", {}))
    top_languages = totals.most_common(4)
    grand_total = sum(totals.values()) or 1
    content = [
        text_element(32, 31, "Project Languages", theme["text"], 17, 600),
        text_element(32, 50, "Top 4 · GitHub Linguist project code", theme["muted"], 11),
        '<defs><clipPath id="language-bar"><rect x="24" y="73" width="372" height="11" rx="5.5"/></clipPath></defs>',
        f'<rect x="24" y="73" width="372" height="11" fill="{theme["border"]}" clip-path="url(#language-bar)"/>',
    ]
    cursor = 24.0
    for language, byte_count in top_languages:
        segment_width = 372 * byte_count / grand_total
        color = LANGUAGE_COLORS.get(language, theme["accent"])
        content.append(
            f'<rect x="{cursor:.2f}" y="73" width="{segment_width:.2f}" height="11" fill="{color}" clip-path="url(#language-bar)"/>'
        )
        cursor += segment_width
    for index, (language, byte_count) in enumerate(top_languages):
        column = index % 2
        row = index // 2
        x = 24 + column * 196
        y = 118 + row * 29
        color = LANGUAGE_COLORS.get(language, theme["accent"])
        percentage = byte_count / grand_total * 100
        content.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{color}"/>')
        content.append(text_element(x + 17, y, language, theme["text"], 12, 600))
        content.append(text_element(x + 180, y, f"{percentage:.1f}%", theme["muted"], 11, 400, "end"))
    return svg_shell(420, 190, theme, content, f"Public repository languages for {USERNAME}")


def render_activity(data: dict[str, Any], levels: dict[date, int], theme: dict[str, Any]) -> str:
    if not levels:
        raise ValueError("Contribution levels are required to render activity")
    first_day = min(levels)
    last_day = max(levels)
    week_count = (last_day - first_day).days // 7 + 1
    if week_count > 53:
        first_day = date.fromordinal(last_day.toordinal() - (53 * 7 - 1))
        week_count = 53
    cell = 10
    gap = 3
    graph_x = 58
    graph_y = 77
    content = [
        text_element(32, 31, "Contribution Activity", theme["text"], 17, 600),
        text_element(
            32,
            50,
            f'{data.get("contributions_total", 0)} contributions · last 12 months',
            theme["muted"],
            11,
        ),
    ]
    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        content.append(text_element(46, graph_y + row * (cell + gap) + 9, label, theme["muted"], 9, 400, "end"))
    seen_months: set[tuple[int, int]] = set()
    for day, level in sorted(levels.items()):
        if day < first_day:
            continue
        week = (day - first_day).days // 7
        weekday = (day.weekday() + 1) % 7
        if week >= 53:
            continue
        x = graph_x + week * (cell + gap)
        y = graph_y + weekday * (cell + gap)
        content.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{theme["levels"][level]}"><title>{day.isoformat()} · level {level}</title></rect>'
        )
        month_key = (day.year, day.month)
        if day.day <= 7 and month_key not in seen_months:
            seen_months.add(month_key)
            content.append(text_element(x, 68, day.strftime("%b"), theme["muted"], 9))
    legend_x = 704
    content.append(text_element(legend_x - 8, 187, "Less", theme["muted"], 9, 400, "end"))
    for index, color in enumerate(theme["levels"]):
        content.append(f'<rect x="{legend_x + index * 13}" y="178" width="10" height="10" rx="2" fill="{color}"/>')
    content.append(text_element(legend_x + 73, 187, "More", theme["muted"], 9))
    return svg_shell(870, 205, theme, content, f"Contribution activity for {USERNAME}")


def render_mobile_activity(data: dict[str, Any], levels: dict[date, int], theme: dict[str, Any]) -> str:
    if not levels:
        raise ValueError("Contribution levels are required to render activity")
    first_day = min(levels)
    last_day = max(levels)
    week_count = (last_day - first_day).days // 7 + 1
    if week_count > 53:
        first_day = date.fromordinal(last_day.toordinal() - (53 * 7 - 1))
    cell = 9
    gap = 2
    graph_x = 52
    graph_y = (82, 191)
    content = [
        text_element(32, 31, "Contribution Activity", theme["text"], 17, 600),
        text_element(
            32,
            50,
            f'{data.get("contributions_total", 0)} contributions · last 12 months',
            theme["muted"],
            11,
        ),
    ]
    for section_y in graph_y:
        for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
            content.append(
                text_element(43, section_y + row * (cell + gap) + 8, label, theme["muted"], 10, 400, "end")
            )
    seen_months: set[tuple[int, int]] = set()
    for day, level in sorted(levels.items()):
        if day < first_day:
            continue
        week = (day - first_day).days // 7
        if week >= 53:
            continue
        section = 0 if week < 27 else 1
        section_week = week if section == 0 else week - 27
        weekday = (day.weekday() + 1) % 7
        x = graph_x + section_week * (cell + gap)
        y = graph_y[section] + weekday * (cell + gap)
        content.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{theme["levels"][level]}"><title>{day.isoformat()} · level {level}</title></rect>'
        )
        month_key = (day.year, day.month)
        if day.day <= 7 and month_key not in seen_months:
            seen_months.add(month_key)
            content.append(text_element(x, graph_y[section] - 10, day.strftime("%b"), theme["muted"], 9))
    legend_x = 297
    content.append(text_element(legend_x - 8, 294, "Less", theme["muted"], 9, 400, "end"))
    for index, color in enumerate(theme["levels"]):
        content.append(f'<rect x="{legend_x + index * 11}" y="286" width="9" height="9" rx="2" fill="{color}"/>')
    content.append(text_element(legend_x + 61, 294, "More", theme["muted"], 9))
    return svg_shell(420, 310, theme, content, f"Mobile contribution activity for {USERNAME}")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    data = read_repository_data(load_cached_data())
    data["repositories"] = sorted(
        data["repositories"],
        key=lambda repository: repository["name"].casefold(),
    )
    data, contribution_levels = read_contributions(data)
    write_if_changed(DATA_PATH, json.dumps(data, indent=2, sort_keys=True))
    for theme_name, theme in THEMES.items():
        write_if_changed(ASSET_DIR / f"stats-{theme_name}.svg", render_stats(data, theme))
        write_if_changed(ASSET_DIR / f"languages-{theme_name}.svg", render_languages(data, theme))
        if contribution_levels:
            write_if_changed(
                ASSET_DIR / f"activity-{theme_name}.svg",
                render_activity(data, contribution_levels, theme),
            )
            write_if_changed(
                ASSET_DIR / f"activity-mobile-{theme_name}.svg",
                render_mobile_activity(data, contribution_levels, theme),
            )


if __name__ == "__main__":
    main()
