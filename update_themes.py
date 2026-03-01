#!/usr/bin/env python3
"""
Scans stannorbvb-cmd's public repos for a preview.png.
Any repo that has one is treated as a theme and added to the README.
Repos are sorted by star count descending.
"""

import os
import re
import json
import urllib.request

USERNAME = "stannorbvb-cmd"
SKIP_REPOS = {USERNAME}  # skip the profile repo itself

# Descriptions for known themes — add yours here as you create new ones.
# Any repo without an entry gets a generic fallback.
DESCRIPTIONS = {
    "cpunk":     "Dark. Abrasive. Neon-lit. A theme for when the work feels like digging through corporate firewalls at 2am.",
    "synthetica":"Synthetic warmth. Analogue haze. The sound of a modular synth rendered in CSS.",
    "bardo":     "The space between. Muted tones, deliberate contrasts — designed for long sessions and clear thinking.",
    "akaito":    "Light, precise, uncompromising. A rare thing: a light theme that doesn't apologize for itself.",
}


def gh_get(path):
    url = f"https://api.github.com/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def has_preview(repo_name):
    try:
        gh_get(f"repos/{USERNAME}/{repo_name}/contents/preview.png")
        return True
    except Exception:
        return False


def get_themes():
    repos = gh_get(f"users/{USERNAME}/repos?per_page=100&type=public")
    themes = []
    for repo in repos:
        name = repo["name"]
        if name in SKIP_REPOS or repo.get("fork"):
            continue
        if has_preview(name):
            themes.append({
                "name": name,
                "stars": repo.get("stargazers_count", 0),
                "description": DESCRIPTIONS.get(name, f"A custom Omarchy theme."),
            })
    themes.sort(key=lambda t: t["stars"], reverse=True)
    return themes


def build_table(themes):
    rows = []
    for i in range(0, len(themes), 2):
        pair = themes[i:i+2]
        cells = ""
        for theme in pair:
            cells += f"""    <td width="50%">
      <h3><a href="https://github.com/{USERNAME}/{theme['name']}">{theme['name']}</a></h3>
      <p>{theme['description']}</p>
      <img src="https://raw.githubusercontent.com/{USERNAME}/{theme['name']}/main/preview.png" width="100%"/>
    </td>\n"""
        # pad with empty cell if odd number of themes
        if len(pair) == 1:
            cells += '    <td width="50%"></td>\n'
        rows.append(f"  <tr>\n{cells}  </tr>")
    return "## Themes\n\n<table>\n" + "\n".join(rows) + "\n</table>"


def update_readme(table):
    with open("README.md", "r") as f:
        content = f.read()

    # Replace everything between ## Themes and the next --- or ##
    new_content = re.sub(
        r"## Themes\n.*?(?=\n---|\n##)",
        table + "\n",
        content,
        flags=re.DOTALL,
    )

    with open("README.md", "w") as f:
        f.write(new_content)

    print(f"Updated README with {len(themes)} theme(s).")


if __name__ == "__main__":
    themes = get_themes()
    table = build_table(themes)
    update_readme(table)
