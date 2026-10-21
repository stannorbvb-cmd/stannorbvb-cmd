#!/usr/bin/env python3
"""
Renders the animated ASCII widgets for the GitHub profile README.

    python scripts/render.py            # live data (needs GITHUB_TOKEN)
    python scripts/render.py --demo     # sample data, no network

Every widget is written twice — assets/<name>-dark.svg and assets/<name>-light.svg —
and the README picks one with <picture> so it follows the viewer's GitHub theme.
All animation is CSS/SMIL inside the SVG (GitHub strips JS), and every animation
rests on its final frame, so `prefers-reduced-motion` simply shows the still.
"""
from __future__ import annotations

import base64, io, json, math, os, random, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = Path(__file__).resolve().parent / "fonts"

# ─────────────────────────────────────────────────────────────── config ──
# Edit freely — this is everything the widgets say about you.
USER = os.environ.get("GH_USER", "stannorbvb-cmd")
PROMPT_USER, PROMPT_HOST = "nor", "dazai"
TAGLINE = "web designer  ·  linux ricer  ·  omarchy themes"

FETCH_SYSTEM = [
    ("os", "arch linux"),
    ("wm", "hyprland · omarchy"),
    ("shell", "zsh · bash"),
    ("editor", "neovim"),
    ("term", "ghostty · kitty"),
    ("host", "thinkpad"),
]
FETCH_WEB = [
    ("stack", "html · css · js · php"),
    ("cms", "wordpress · elementor"),
    ("agents", "opencode · claude code"),
]
FETCH_IDENTITY = [
    ("user", "nor"),
    ("alias", "dazai"),
    ("craft", "web design · theming"),
    ("base", "the himalaya"),
]
THEMES = ["bardo", "synthetica", "cpunk", "akaito", "axionmorph", "omarchy-root-yaru-theme"]
SITES = 9
TZ_LABEL, TZ_OFFSET = "ist", timedelta(hours=5, minutes=30)

WORDMARK = [
    "▓█████▄  ▄▄▄      ▒███████▒ ▄▄▄       ██▓",
    "▒██▀ ██▌▒████▄    ▒ ▒ ▒ ▄▀░▒████▄    ▓██▒",
    "░██   █▌▒██  ▀█▄  ░ ▒ ▄▀▒░ ▒██  ▀█▄  ▒██▒",
    "░▓█▄   ▌░██▄▄▄▄██   ▄▀▒   ░░██▄▄▄▄██ ░██░",
    "░▒████▓  ▓█   ▓██▒▒███████▒ ▓█   ▓██▒░██░",
    " ▒▒▓  ▒  ▒▒   ▓▒█░░▒▒ ▓░▒░▒ ▒▒   ▓▒█░░▓",
    " ░ ▒  ▒   ▒   ▒▒ ░░░▒ ▒ ░ ▒  ▒   ▒▒ ░ ▒ ░",
    " ░ ░  ░   ░   ▒   ░ ░ ░ ░ ░  ░   ▒    ▒ ░",
    "   ░          ░  ░  ░ ░          ░  ░ ░",
    " ░                ░",
]

# A chorten — the whitewashed stupas that line every road in Ladakh.
CHORTEN = [
    "         ●",
    "        ▐█▌",
    "        ▐█▌",
    "       ▐███▌",
    "       ▐███▌",
    "      ▀▀▀▀▀▀▀",
    "     ▐▀▀▀▀▀▀▀▌",
    "    ▄█████████▄",
    "   ▐███████████▌",
    "    ▀▀▀▀▀▀▀▀▀▀▀",
    "  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
    "  ███████████████",
    "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
]

PALETTES = {
    "dark": dict(
        bg="#0c0c0d", panel="#111113", line="#2a2a2e", fg="#ddd8cc", mute="#8d8a82",
        dim="#57554f", faint="#222225", accent="#e2583c", gold="#d8a548",
        far="#5a5860", snow="#bdb8ac", heat1="#4a2219", heat2="#83321f", heat3="#b8452b", near="#18181b", ridge="#26262a",
        stupa="#ddd8cc", stupa2="#8d8a82",
        flags=["#3f74c2", "#e8e3d6", "#d2432c", "#3d9159", "#e3b032"],
    ),
    "light": dict(
        bg="#f6f3ec", panel="#efebe2", line="#d5cfc2", fg="#1d1c1a", mute="#6c685f",
        dim="#a29d91", faint="#e4dfd4", accent="#c43f1f", gold="#a87612",
        far="#b9b3a6", snow="#6f6a60", heat1="#efcfc2", heat2="#e2a089", heat3="#d46a4b", near="#e6e1d6", ridge="#d6d0c3",
        stupa="#8a857a", stupa2="#b3ad9f",
        flags=["#2f62ad", "#b9b2a3", "#c43f1f", "#2f7d4a", "#c99412"],
    ),
}

# ──────────────────────────────────────────────────────────── geometry ──
FS = 12            # font size (px)
CW = FS * 0.6      # JetBrains Mono advance
LH = 16            # line height ≈ ascent+descent, so block glyphs tile seamlessly
ASC = 12.3         # baseline offset inside a line
W = 880


# ──────────────────────────────────────────────────────────── svg kit ──
_font_cache: dict = {}


def font_face(weight: int, chars: set[str]) -> str:
    if not chars:
        return ""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    name = "JetBrainsMono-Bold.woff2" if weight == 700 else "JetBrainsMono-Regular.woff2"
    key = (name, "".join(sorted(chars)))
    if key not in _font_cache:
        font = TTFont(FONTS / name)
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = []
        opts.name_IDs = []
        opts.notdef_outline = True
        s = subset.Subsetter(opts)
        s.populate(text="".join(chars) + " ")
        s.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        _font_cache[key] = base64.b64encode(buf.getvalue()).decode()
    return (f"@font-face{{font-family:'JBM';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{_font_cache[key]}) format('woff2')}}")


class SVG:
    def __init__(self, w: float, h: float, P: dict, title: str):
        self.w, self.h, self.P, self.title = w, h, P, title
        self.body: list[str] = []
        self.defs: list[str] = []
        self.css: list[str] = []
        self.regular: set[str] = set()
        self.bold: set[str] = set()

    def text(self, x, y, s, fill=None, cls="", bold=False, extra=""):
        if not s:
            return
        (self.bold if bold else self.regular).update(s)
        attrs = f' x="{x:.2f}" y="{y:.2f}"'
        if fill:
            attrs += f' fill="{fill}"'
        if cls or bold:
            attrs += f' class="{(cls + (" b" if bold else "")).strip()}"'
        self.body.append(f"<text{attrs}{extra}>{escape(s)}</text>")

    def add(self, s: str):
        self.body.append(s)

    def render(self) -> str:
        P = self.P
        faces = font_face(400, self.regular) + font_face(700, self.bold)
        base = (
            "text{font-family:'JBM',ui-monospace,SFMono-Regular,Menlo,monospace;"
            f"font-size:{FS}px;white-space:pre;font-variant-ligatures:none}}"
            ".b{font-weight:700}"
            "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.title)}">'
            f"<title>{escape(self.title)}</title>"
            f"<style>{faces}{base}{''.join(self.css)}</style>"
            f"<defs>{''.join(self.defs)}</defs>"
            f'<rect width="100%" height="100%" rx="12" fill="{P["bg"]}"/>'
            + "".join(self.body)
            + "</svg>"
        )


def gx(col: float, x0: float = 0) -> float:
    return x0 + col * CW


def gy(row: float, y0: float = 0) -> float:
    return y0 + row * LH + ASC


def typed(svg: SVG, x: float, y: float, segments, delay: float, speed: float = 0.045,
          cursor=True, cursor_color=None, key="t"):
    """Type `segments` [(text, color, bold)] out left-to-right with a stepping caret."""
    n = sum(len(t) for t, *_ in segments)
    width = n * CW
    dur = max(n * speed, 0.2)
    cx = x
    for t, color, *b in segments:
        svg.text(cx, y, t, fill=color, bold=bool(b and b[0]))
        cx += len(t) * CW
    P = svg.P
    # cover sits just after the text at rest; animation slides it back over the text
    svg.css.append(
        f"@keyframes {key}-type{{from{{transform:translateX(-{width + CW:.1f}px)}}to{{transform:translateX(0)}}}}"
        f".{key}-c{{animation:{key}-type {dur:.2f}s steps({n}) {delay:.2f}s both}}"
    )
    svg.add(f'<rect class="{key}-c" x="{x + width + CW:.2f}" y="{y - ASC - 1:.2f}" '
            f'width="{width + CW + 2:.2f}" height="{LH + 2}" fill="{P["bg"]}"/>')
    if cursor:
        svg.css.append(
            f"@keyframes {key}-cur{{from{{transform:translateX(-{width:.1f}px)}}to{{transform:translateX(0)}}}}"
            "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
            f".{key}-k{{animation:{key}-cur {dur:.2f}s steps({n}) {delay:.2f}s both,blink 1.05s steps(1) {delay + dur:.2f}s infinite}}"
        )
        svg.text(x + width + 1, y, "█", fill=cursor_color or P["accent"], cls=f"{key}-k")
    return delay + dur


def box(svg: SVG, x0, y0, col, row, wcols, hrows, title, P, right="", title_color=None,
        live=False):
    """btop-style rounded box drawn in box-drawing glyphs, title set into the top rule."""
    x, y = gx(col, x0), gy(row, y0)
    svg.text(x, y, "╭─", fill=P["line"])
    svg.text(gx(col + 3, x0), y, title, fill=title_color or P["accent"], bold=True)
    used = 3 + len(title) + 1 + (3 if live else 0)
    tail_len = wcols - used - 1 - (len(right) + 2 if right else 0)
    svg.text(gx(col + used, x0), y, "─" * tail_len, fill=P["line"])
    if right:
        svg.text(gx(col + wcols - len(right) - 2, x0), y, right, fill=P["mute"])
    svg.text(gx(col + wcols - 1, x0), y, "╮", fill=P["line"])
    for r in range(1, hrows - 1):
        svg.text(x, gy(row + r, y0), "│", fill=P["line"])
        svg.text(gx(col + wcols - 1, x0), gy(row + r, y0), "│", fill=P["line"])
    svg.text(x, gy(row + hrows - 1, y0), "╰" + "─" * (wcols - 2) + "╯", fill=P["line"])
    if live:
        svg.css.append("@keyframes live{0%,100%{opacity:1}50%{opacity:.2}}.live{animation:live 1.6s ease-in-out infinite}")
        svg.text(gx(col + 4 + len(title), x0), y, "●", fill=P["accent"], cls="live")


# ──────────────────────────────────────────────────────────────── data ──
GQL = """
query($login:String!){
  user(login:$login){
    createdAt
    followers{ totalCount }
    repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false, first:100,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{ name stargazerCount
        languages(first:8, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } }
    }
    contributionsCollection{
      contributionCalendar{ totalContributions
        weeks{ contributionDays{ date contributionCount } } }
    }
  }
}"""


def fetch_live() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set — run with --demo for sample data")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": GQL, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        sys.exit(f"GitHub API error: {payload['errors']}")
    u = payload["data"]["user"]
    langs: dict[str, int] = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [(d["date"], d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"]]
    return dict(
        created=u["createdAt"][:10],
        followers=u["followers"]["totalCount"],
        repos=u["repositories"]["totalCount"],
        stars=sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        langs=langs,
        days=days,
        total=cal["totalContributions"],
    )


def demo_data() -> dict:
    rnd = random.Random(42)
    end = date.today()
    start = end - timedelta(days=end.weekday() + 1 + 52 * 7)
    days = []
    d = start
    while d <= end:
        burst = 1 + 2.2 * math.sin(d.toordinal() / 23) ** 2
        n = 0 if rnd.random() < 0.38 else int(rnd.expovariate(1 / (2.4 * burst)))
        days.append((d.isoformat(), n))
        d += timedelta(days=1)
    return dict(created="2023-03-14", followers=27, repos=14, stars=86,
                langs={"CSS": 412_000, "Shell": 188_000, "Lua": 96_000, "HTML": 61_000,
                       "JavaScript": 33_000, "PHP": 12_000},
                days=days, total=sum(n for _, n in days))


def derive(D: dict) -> dict:
    days = D["days"]
    today = days[-1][0]
    streak = 0
    for i, (_, n) in enumerate(reversed(days)):
        if n:
            streak += 1
        elif i:          # a quiet *today* doesn't break the streak yet
            break
    best = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        best = max(best, run)
    peak = max(days, key=lambda t: t[1])
    created = date.fromisoformat(D["created"])
    now = date.fromisoformat(today)
    months = (now.year - created.year) * 12 + now.month - created.month
    year_total = sum(n for d, n in days if d.startswith(today[:4]))
    D.update(streak=streak, best=best, peak=peak, uptime=f"{months // 12}y {months % 12}m",
             year_total=year_total, year=today[:4])
    return D


# ──────────────────────────────────────────────────────────────── hero ──
def hero(P: dict, D: dict) -> str:
    cols, rows = 120, 23
    x0 = (W - cols * CW) / 2
    y0 = 10
    H = y0 * 2 + rows * LH
    s = SVG(W, H, P, "DAZAI — web designer, linux ricer, omarchy themes")
    rnd = random.Random(7)

    # ── terrain: classic /\ line-art ranges. (column, top row) per peak.
    FAR = [(7, 6), (17, 9), (29, 12), (43, 16), (60, 15), (77, 14), (93, 10), (102, 5), (113, 8)]
    NEAR = [(4, 15), (22, 13), (37, 18), (52, 15), (69, 19), (85, 17), (104, 12), (118, 15)]

    def ridge(peaks):
        top, ch, owner = [rows] * cols, [" "] * cols, [None] * cols
        for p, (pc, pt) in enumerate(peaks):
            for c in range(cols):
                r, g = (pt + (pc - 1 - c), "/") if c <= pc - 1 else (pt + (c - pc), "\\")
                if r < top[c]:
                    top[c], ch[c], owner[c] = r, g, p
        return top, ch, owner

    ftop, fch, fown = ridge(FAR)
    ntop, nch, nown = ridge(NEAR)
    sky_top = [min(ftop[c], ntop[c]) for c in range(cols)]

    word_w = max(len(l) for l in WORDMARK)
    wc, wr = (cols - word_w) // 2, 2
    tag_r = wr + len(WORDMARK) + 1
    tag_c = (cols - len(TAGLINE)) // 2

    # ── stars
    s.css.append(
        "@keyframes tw{0%,100%{opacity:.15}50%{opacity:1}}"
        ".tw{animation:tw var(--d) ease-in-out var(--o) infinite both}"
    )
    placed = 0
    while placed < 46:
        c, r = rnd.randrange(cols), rnd.randrange(0, rows - 6)
        if wc - 2 <= c <= wc + word_w + 2 and wr - 1 <= r <= tag_r:
            continue
        if 100 <= c <= 111 and r <= 5:   # moon
            continue
        if r >= sky_top[c] - 1:
            continue
        g = rnd.choice("··········.*+")
        col = P["fg"] if g in "*+" else P["mute"]
        s.text(gx(c, x0), gy(r, y0), g, fill=col, cls="tw",
               extra=f' style="--d:{rnd.uniform(2.4, 6):.2f}s;--o:-{rnd.uniform(0, 6):.2f}s"')
        placed += 1

    # ── moon: a thin crescent with a dotted halo
    mx, my = gx(105, x0), gy(2.2, y0)
    s.defs.append(f'<mask id="cres"><rect width="{W}" height="{H}" fill="#fff"/>'
                  f'<circle cx="{mx + 7}" cy="{my - 5}" r="15" fill="#000"/></mask>')
    s.add(f'<circle cx="{mx}" cy="{my}" r="27" fill="none" stroke="{P["dim"]}" stroke-width=".8" '
          f'stroke-dasharray="1 5" opacity=".7"/>')
    s.add(f'<circle cx="{mx}" cy="{my}" r="16" fill="{P["snow"]}" mask="url(#cres)"/>')

    # ── shooting star
    s.css.append(
        "@keyframes shoot{0%,86%{opacity:0;transform:translate(0,0)}"
        "88%{opacity:1}100%{opacity:0;transform:translate(-260px,90px)}}"
        ".shoot{animation:shoot 11s linear 3s infinite;opacity:0}"
    )
    s.add(f'<g class="shoot">')
    s.text(gx(92, x0), gy(1, y0), "*──·  ·", fill=P["fg"])
    s.add("</g>")

    # ── wordmark with a slow light sweep and an occasional glitch slice
    s.defs.append(
        f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="60">'
        f'<stop offset="0" stop-color="{P["fg"]}"/><stop offset=".44" stop-color="{P["fg"]}"/>'
        f'<stop offset=".5" stop-color="{P["accent"]}"/><stop offset=".56" stop-color="{P["fg"]}"/>'
        f'<stop offset="1" stop-color="{P["fg"]}"/>'
        f'<animateTransform attributeName="gradientTransform" type="translate" '
        f'values="-{W};{W}" dur="7s" repeatCount="indefinite"/></linearGradient>'
    )
    for i, l in enumerate(WORDMARK):
        s.text(gx(wc, x0), gy(wr + i, y0), l, fill="url(#shine)")
    s.css.append(
        "@keyframes glitch{0%,93%,100%{opacity:0;transform:translateX(0)}"
        "94%{opacity:.9;transform:translateX(7px)}95%{opacity:.7;transform:translateX(-5px)}"
        "96%{opacity:0}97%{opacity:.8;transform:translateX(3px)}98%{opacity:0}}"
        ".gl{animation:glitch 8s steps(1) 2s infinite;opacity:0}"
    )
    s.defs.append(f'<clipPath id="slice"><rect x="0" y="{gy(wr + 1, y0) - 6}" width="{W}" height="9"/>'
                  f'<rect x="0" y="{gy(wr + 4, y0) - 3}" width="{W}" height="5"/></clipPath>')
    s.add('<g class="gl" clip-path="url(#slice)">')
    for i, l in enumerate(WORDMARK):
        s.text(gx(wc, x0), gy(wr + i, y0), l, fill=P["accent"])
    s.add("</g>")

    # ── tagline, typed
    segs = []
    for j, part in enumerate(TAGLINE.split("·")):
        if j:
            segs.append(("·", P["accent"]))
        segs.append((part, P["mute"]))
    typed(s, gx(tag_c, x0), gy(tag_r, y0), segs, delay=0.6, speed=0.035, key="tag")

    # ── far range, mist, near ridge (drawn back to front)
    def grid():
        return [[" "] * cols for _ in range(rows)]

    far_l, snow_l, far_s = grid(), grid(), grid()
    for c in range(cols):
        t = ftop[c]
        if t >= ntop[c]:
            continue
        peak_top = FAR[fown[c]][1]
        snowy = peak_top <= 10 and t - peak_top <= 2
        (snow_l if snowy else far_l)[t][c] = fch[c]
        for k in range(t + 1, ntop[c]):
            depth = k - t
            if peak_top <= 10 and k - peak_top <= 3 and rnd.random() < .7 - depth * .18:
                snow_l[k][c] = rnd.choice(".:'")
            elif rnd.random() < .05 + depth * .012:
                far_s[k][c] = rnd.choice("..:")
    for layer, fill in ((far_s, P["dim"]), (far_l, P["far"]), (snow_l, P["snow"])):
        for r, row in enumerate(layer):
            line = "".join(row).rstrip()
            if line.strip():
                s.text(x0, gy(r, y0), line, fill=fill)

    # mist drifts between the two ranges
    s.css.append(
        "@keyframes drift{from{transform:translateX(-340px)}to{transform:translateX(900px)}}"
        ".mist{animation:drift var(--d) linear var(--o) infinite}"
    )
    for txt, r, d, o in [("~ ~~~ ~~ ~  ~~~~ ~", rows - 5, 70, 0), (" ~~ ~ ~~~~~ ~ ~~", rows - 3, 95, 40),
                         ("~~~ ~ ~~ ~", rows - 7, 120, 75)]:
        s.add(f'<g class="mist" style="--d:{d}s;--o:-{o}s">')
        s.text(0, gy(r, y0), txt, fill=P["dim"])
        s.add("</g>")

    # near ridge sits on an opaque silhouette so mist passes behind it
    pts = [(x0, H)]
    for c, t in enumerate(ntop):
        yy = y0 + t * LH + LH * .5
        pts += [(gx(c, x0), yy), (gx(c + 1, x0), yy)]
    pts.append((gx(cols, x0), H))
    s.add(f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="{P["bg"]}"/>')
    near_l, near_s = grid(), grid()
    for c in range(cols):
        t = ntop[c]
        if t >= rows:
            continue
        near_l[t][c] = nch[c]
        for k in range(t + 1, rows):
            if rnd.random() < .03 + (k - t) * .025:
                near_s[k][c] = rnd.choice(".,:;")
    for layer, fill in ((near_s, P["far"]), (near_l, P["mute"])):
        for r, row in enumerate(layer):
            line = "".join(row).rstrip()
            if line.strip():
                s.text(x0, gy(r, y0), line, fill=fill)

    # ── prayer flags strung between the two near peaks, fluttering
    xa, ya = gx(22, x0), y0 + 13 * LH + 3
    xb, yb = gx(52, x0), y0 + 15 * LH + 3
    sag = 16
    s.add(f'<path d="M{xa:.1f},{ya:.1f} Q{(xa + xb) / 2:.1f},{(ya + yb) / 2 + sag * 2:.1f} '
          f'{xb:.1f},{yb:.1f}" fill="none" stroke="{P["dim"]}" stroke-width=".8"/>')
    s.css.append(
        "@keyframes flap{0%,100%{transform:skewX(0) scaleY(1)}30%{transform:skewX(-14deg) scaleY(.92)}"
        "65%{transform:skewX(9deg) scaleY(1.04)}}"
        ".flag{transform-box:fill-box;transform-origin:50% 0;animation:flap var(--d) ease-in-out var(--o) infinite}"
    )
    n = 15
    for i in range(1, n):
        t = i / n
        x = (1 - t) ** 2 * xa + 2 * (1 - t) * t * (xa + xb) / 2 + t ** 2 * xb
        y = (1 - t) ** 2 * ya + 2 * (1 - t) * t * ((ya + yb) / 2 + sag * 2) + t ** 2 * yb
        c = P["flags"][i % 5]
        s.add(f'<rect class="flag" x="{x - 3.5:.1f}" y="{y:.1f}" width="7" height="9" fill="{c}" '
              f'style="--d:{rnd.uniform(1.6, 2.8):.2f}s;--o:-{rnd.uniform(0, 2):.2f}s"/>')

    return s.render()


# ─────────────────────────────────────────────────────────────── fetch ──
def fetch(P: dict, D: dict) -> str:
    x0, y0 = 26, 22
    rows = 19
    H = y0 + rows * LH + 14
    s = SVG(W, H, P, "fastfetch — system, stack and live GitHub stats")

    # hyprland-style animated gradient border
    s.defs.append(
        f'<linearGradient id="hb" gradientUnits="objectBoundingBox" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{P["accent"]}"/><stop offset=".5" stop-color="{P["line"]}"/>'
        f'<stop offset="1" stop-color="{P["gold"]}"/>'
        f'<animateTransform attributeName="gradientTransform" type="rotate" '
        f'values="0 .5 .5;360 .5 .5" dur="14s" repeatCount="indefinite"/></linearGradient>'
    )
    s.add(f'<rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="9" fill="{P["panel"]}" '
          f'stroke="url(#hb)" stroke-width="1.5"/>')

    prompt = [(PROMPT_USER, P["accent"], True), ("@", P["dim"]), (PROMPT_HOST, P["gold"], True),
              (" ~ ", P["dim"]), ("❯ ", P["accent"]), ("fastfetch", P["fg"])]
    # the typed() cover uses bg; inside the window it must match the panel
    s_bg = dict(P, bg=P["panel"])
    s.P = s_bg
    t_end = typed(s, gx(0, x0), gy(0, y0), prompt, delay=.4, cursor=False, key="p")
    s.P = P

    s.css.append(
        "@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}"
        ".in{animation:in .35s ease-out var(--o) both}"
    )
    reveal = t_end + .25

    def line_in(i):
        return f' style="--o:{reveal + i * .045:.2f}s"'

    # chorten logo — gold spire, whitewashed body
    s.defs.append(
        f'<linearGradient id="ch" gradientUnits="userSpaceOnUse" x1="0" y1="{gy(2, y0) - 12}" x2="0" y2="{gy(15, y0)}">'
        f'<stop offset="0" stop-color="{P["gold"]}"/><stop offset=".36" stop-color="{P["gold"]}"/>'
        f'<stop offset=".40" stop-color="{P["stupa"]}"/><stop offset="1" stop-color="{P["stupa2"]}"/></linearGradient>'
    )
    for i, l in enumerate(CHORTEN):
        s.add(f'<g class="in"{line_in(i)}>')
        s.text(gx(0, x0), gy(2 + i, y0), l, fill="url(#ch)")
        s.add("</g>")
    s.css.append("@keyframes glow{0%,100%{opacity:.55}50%{opacity:1}}.sun{animation:glow 3s ease-in-out infinite}")
    s.text(gx(9, x0), gy(2, y0), "●", fill=P["accent"], cls="sun")

    # palette row under the logo
    s.add(f'<g class="in"{line_in(15)}>')
    for i, c in enumerate(P["flags"] + [P["accent"], P["gold"], P["mute"]]):
        s.text(gx(i * 2 + 1, x0), gy(16, y0), "●", fill=c)
    s.add("</g>")

    def section(col, row, w, title, items, live=False, idx=0):
        rows_needed = len(items) + 2
        s.add(f'<g class="in"{line_in(idx)}>')
        box(s, x0, y0, col, row, w, rows_needed, title, P, live=live)
        s.add("</g>")
        for i, (k, v) in enumerate(items):
            s.add(f'<g class="in"{line_in(idx + i + 1)}>')
            s.text(gx(col + 2, x0), gy(row + 1 + i, y0), "◆", fill=P["accent"] if live else P["dim"])
            s.text(gx(col + 4, x0), gy(row + 1 + i, y0), k, fill=P["gold"])
            s.text(gx(col + 13, x0), gy(row + 1 + i, y0), v, fill=P["fg"])
            s.add("</g>")
        return row + rows_needed

    synced = (datetime.now(timezone.utc) + TZ_OFFSET).strftime("%d %b · %H:%M").lower()
    live_items = [
        ("repos", f"{D['repos']} public · {D['stars']} stars"),
        ("commits", f"{D['year_total']:,} in {D['year']}"),
        ("streak", f"{D['streak']}d now · {D['best']}d best"),
        ("uptime", f"{D['uptime']} on github"),
        ("synced", f"{synced} {TZ_LABEL}"),
    ]
    A, B, BW = 22, 69, 46
    r = section(A, 2, BW, "system", FETCH_SYSTEM, idx=0)
    section(A, r, BW, "web", FETCH_WEB, idx=8)
    r = section(B, 2, BW, "identity", FETCH_IDENTITY, idx=2)
    section(B, r, BW, "github", live_items, live=True, idx=8)

    # trailing prompt with blinking caret
    end = reveal + 18 * .045 + .4
    s.add(f'<g class="in" style="--o:{end:.2f}s">')
    x = gx(0, x0)
    for t, c, *b in [(PROMPT_USER, P["accent"], True), ("@", P["dim"]), (PROMPT_HOST, P["gold"], True),
                     (" ~ ", P["dim"]), ("❯ ", P["accent"])]:
        s.text(x, gy(rows - 1, y0), t, fill=c, bold=bool(b))
        x += len(t) * CW
    s.css.append("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.k{animation:blink 1.05s steps(1) infinite}")
    s.text(x, gy(rows - 1, y0), "█", fill=P["accent"], cls="k")
    s.add("</g>")
    return s.render()


# ─────────────────────────────────────────────────────────────── pulse ──
def pulse(P: dict, D: dict) -> str:
    x0, y0 = 22, 14
    rows = 26
    H = y0 * 2 + rows * LH
    s = SVG(W, H, P, f"activity — {D['total']:,} contributions in the last year")
    days = D["days"]

    # pad to whole weeks starting on Sunday
    first = date.fromisoformat(days[0][0])
    lead = (first.weekday() + 1) % 7
    cells = [None] * lead + days
    weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)][-53:]
    nonzero = sorted(n for _, n in days if n)
    q = [nonzero[int(len(nonzero) * f)] if nonzero else 1 for f in (.25, .5, .75)]

    def level(n):
        if not n:
            return 0
        return 1 if n <= q[0] else 2 if n <= q[1] else 3 if n <= q[2] else 4

    BW = 116
    box(s, x0, y0, 0, 0, BW, 12, "contributions", P, right=f"{D['total']:,} in the last year")
    gc = 7                       # first grid column
    s.defs.append(f'<clipPath id="sweep"><rect class="sw" x="{gx(gc, x0)}" y="0" '
                  f'width="{len(weeks) * 2 * CW}" height="{H}"/></clipPath>')
    s.css.append(
        "@keyframes sweep{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        f".sw{{transform-box:fill-box;transform-origin:0 0;animation:sweep 2.2s steps({len(weeks)}) .3s both}}"
    )
    # month labels
    last_m = None
    for w, wk in enumerate(weeks):
        d0 = next((d for d in wk if d), None)
        if d0:
            m = d0[0][5:7]
            if m != last_m and w < len(weeks) - 2:
                if last_m is not None:
                    label = date.fromisoformat(d0[0]).strftime("%b").lower()
                    s.text(gx(gc + w * 2, x0), gy(1.3, y0), label, fill=P["dim"])
                last_m = m
    for i, lab in ((1, "mon"), (3, "wed"), (5, "fri")):
        s.text(gx(2, x0), gy(2.5 + i, y0), lab, fill=P["dim"])

    glyph = ["·", "■", "■", "■", "■"]
    fills = [P["dim"], P["heat1"], P["heat2"], P["heat3"], P["accent"]]
    s.add('<g clip-path="url(#sweep)">')
    for dow in range(7):
        # one text run per level per weekday keeps the file small
        for lv in range(5):
            line = []
            for wk in weeks:
                d = wk[dow] if dow < len(wk) else None
                line.append((glyph[lv] if d and level(d[1]) == lv else " ") + " ")
            txt = "".join(line).rstrip()
            if txt.strip():
                s.text(gx(gc, x0), gy(2.5 + dow, y0), txt, fill=fills[lv])
    s.add("</g>")

    # scanner sweeping the year, and today's cell breathing
    s.css.append(
        f"@keyframes scan{{0%{{transform:translateX(0);opacity:0}}6%{{opacity:1}}94%{{opacity:1}}"
        f"100%{{transform:translateX({(len(weeks) - 1) * 2 * CW:.1f}px);opacity:0}}}}"
        ".scan{animation:scan 9s linear 3s infinite;opacity:0}"
        "@keyframes breathe{0%,100%{opacity:1}50%{opacity:.25}}.today{animation:breathe 1.4s ease-in-out infinite}"
    )
    s.add(f'<rect class="scan" x="{gx(gc, x0) - 2:.1f}" y="{gy(2.5, y0) - ASC:.1f}" width="{CW + 4:.1f}" '
          f'height="{7 * LH}" fill="{P["accent"]}" fill-opacity=".14" rx="2"/>')
    tw = len(weeks) - 1
    tdow = len(weeks[-1]) - 1
    s.text(gx(gc + tw * 2, x0), gy(2.5 + tdow, y0), "■", fill=P["gold"], cls="today")

    # legend + stats
    ly = gy(10, y0)
    s.text(gx(2, x0), ly, "less", fill=P["dim"])
    s.text(gx(7, x0), ly, "· ", fill=P["dim"])
    for i, k in enumerate(("heat1", "heat2", "heat3", "accent")):
        s.text(gx(9 + i * 2, x0), ly, "■", fill=P[k])
    s.text(gx(17, x0), ly, "more", fill=P["dim"])
    pk = date.fromisoformat(D["peak"][0]).strftime("%d %b").lower()
    stats = [("streak ", f"{D['streak']}d"), ("   best ", f"{D['best']}d"),
             ("   peak ", f"{D['peak'][1]} on {pk}")]
    total_len = sum(len(a) + len(b) for a, b in stats)
    c = BW - 3 - total_len
    for a, b in stats:
        s.text(gx(c, x0), ly, a, fill=P["mute"]); c += len(a)
        s.text(gx(c, x0), ly, b, fill=P["fg"], bold=True); c += len(b)

    # ── cava: weekly totals as a live visualiser
    nb, top, hb = 28, 13, 8
    wk_tot = [sum(d[1] for d in wk if d) for wk in weeks][-nb:]
    mx = max(wk_tot) or 1
    box(s, x0, y0, 0, top, 64, 13, "cava", P, right=f"weekly · last {nb} wks")
    base_y = gy(top + 1 + hb, y0) - ASC   # bottom edge of the bar zone
    zone_top = gy(top + 2, y0) - ASC
    s.defs.append(
        f'<linearGradient id="cv" gradientUnits="userSpaceOnUse" x1="0" y1="{base_y + LH}" x2="0" y2="{zone_top}">'
        f'<stop offset="0" stop-color="{P["dim"]}"/><stop offset=".45" stop-color="{P["gold"]}"/>'
        f'<stop offset="1" stop-color="{P["accent"]}"/></linearGradient>'
    )
    s.css.append(
        "@keyframes eq{0%,100%{transform:scaleY(var(--a))}25%{transform:scaleY(var(--b))}"
        "50%{transform:scaleY(var(--c))}75%{transform:scaleY(var(--b2))}}"
        ".eq{transform-box:fill-box;transform-origin:50% 100%;animation:eq var(--d) ease-in-out var(--o) infinite}"
    )
    rnd = random.Random(3)
    col_text = "\n"
    for i, v in enumerate(wk_tot):
        h = max(1, round(math.sqrt(v / mx) * hb))
        c = 3 + i * 2
        x = gx(c, x0)
        bar_top = base_y + LH - h * LH
        s.defs.append(f'<clipPath id="b{i}"><rect class="eq" x="{x - 1:.1f}" y="{bar_top:.1f}" '
                      f'width="{CW + 2:.1f}" height="{h * LH:.1f}" style="--a:1;--b:{rnd.uniform(.35, .8):.2f};'
                      f'--c:{rnd.uniform(.6, 1):.2f};--b2:{rnd.uniform(.25, .7):.2f};'
                      f'--d:{rnd.uniform(1.1, 2.2):.2f}s;--o:-{rnd.uniform(0, 2):.2f}s"/></clipPath>')
        s.add(f'<g clip-path="url(#b{i})">')
        for k in range(h):
            s.text(x, gy(top + 1 + hb - k, y0), "▆", fill="url(#cv)")
        s.add("</g>")
    s.text(gx(2, x0), gy(top + 11, y0), "─" * 59, fill=P["faint"])

    # ── languages
    langs = sorted(D["langs"].items(), key=lambda t: -t[1])[:6]
    tot = sum(v for _, v in D["langs"].items()) or 1
    LX = 66
    box(s, x0, y0, LX, top, 50, 13, "languages", P, right="by bytes")
    barw = 22
    s.css.append(
        "@keyframes fill{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        ".fill{transform-box:fill-box;transform-origin:0 50%;animation:fill 1.4s cubic-bezier(.2,.7,.2,1) var(--o) both}"
    )
    for i, (name, v) in enumerate(langs):
        y = gy(top + 2 + i, y0)
        frac = v / tot
        filled = max(1, round(frac * barw))
        s.text(gx(LX + 3, x0), y, name.lower()[:11], fill=P["fg"])
        s.text(gx(LX + 15, x0), y, "░" * barw, fill=P["faint"])
        s.add(f'<g class="fill" style="--o:{.5 + i * .12:.2f}s">')
        s.text(gx(LX + 15, x0), y, "█" * filled, fill=P["accent"] if i == 0 else (P["gold"] if i == 1 else P["mute"]))
        s.add("</g>")
        s.text(gx(LX + 38, x0), y, f"{frac * 100:5.1f}%", fill=P["mute"])
    y = gy(top + 10, y0)
    stats = [(f"{D['repos']}", " repos   "), (f"{D['stars']}", " stars   "), (f"{D['followers']}", " followers")]
    c = LX + 3
    for a, b in stats:
        s.text(gx(c, x0), y, a, fill=P["fg"], bold=True); c += len(a)
        s.text(gx(c, x0), y, b, fill=P["mute"]); c += len(b)
    return s.render()


# ──────────────────────────────────────────────────────── section heads ──
def head(P: dict, path: str, cmd: str, right: str, key: str) -> str:
    H = 46
    s = SVG(W, H, P, f"{path} — {cmd}")
    y = 22
    segs = [(PROMPT_USER, P["accent"], True), ("@", P["dim"]), (PROMPT_HOST, P["gold"], True),
            (f" {path} ", P["mute"]), ("❯ ", P["accent"]), (cmd, P["fg"])]
    end = typed(s, 14, y, segs, delay=.3, speed=.04, key=key)
    s.text(W - 14 - len(right) * CW, y, right, fill=P["dim"])
    s.css.append(
        "@keyframes rule{from{stroke-dashoffset:860}to{stroke-dashoffset:0}}"
        f".rule{{stroke-dasharray:860;animation:rule 1.6s ease-out {end:.2f}s both}}"
    )
    s.add(f'<line class="rule" x1="14" y1="35" x2="{W - 14}" y2="35" stroke="{P["line"]}" stroke-width="1"/>')
    return s.render()


# ─────────────────────────────────────────────────────────────── swatch ──
def theme_palette(name: str) -> list[str]:
    """Pull six representative colours from a theme's preview.png."""
    from PIL import Image

    url = f"https://raw.githubusercontent.com/{USER}/{name}/main/preview.png"
    with urllib.request.urlopen(url, timeout=30) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    im.thumbnail((320, 320))
    q = im.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(n for n, _ in counts)

    def sat(rgb):
        mx, mn = max(rgb), min(rgb)
        return 0 if mx == 0 else (mx - mn) / mx

    cands = [(n / total, tuple(pal[i * 3: i * 3 + 3])) for n, i in counts]
    # three dominant tones (the theme's surfaces) + three accents (its character)
    by_area = [c for _, c in cands]
    by_accent = [c for share, c in sorted(cands, key=lambda t: -(sat(t[1]) ** 1.5 * t[0] ** .35 * (max(t[1]) / 255)))]
    picked: list[tuple[int, int, int]] = []

    def take(pool, k):
        got = 0
        for rgb in pool:
            if got == k or len(picked) == 6:
                break
            if all(sum((a - b) ** 2 for a, b in zip(rgb, p)) > 900 for p in picked):
                picked.append(rgb); got += 1

    take(by_area, 3)
    take(by_accent, 3)
    take(by_area, 6)
    picked.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    return ["#%02x%02x%02x" % c for c in picked]


def swatch(P: dict, name: str, colors: list[str]) -> str:
    Wd, H = 420, 38
    s = SVG(Wd, H, P, f"{name} palette: {' '.join(colors)}")
    s.text(12, 18, name, fill=P["fg"], bold=True)
    s.text(12, 31, "omarchy theme", fill=P["dim"])
    s.css.append(
        "@keyframes pop{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        ".chip{transform-box:fill-box;transform-origin:50% 100%;animation:pop .5s cubic-bezier(.3,1.4,.5,1) var(--o) both}"
    )
    cw = 34
    x = Wd - 12 - len(colors) * (cw + 3) + 3
    for i, c in enumerate(colors):
        s.add(f'<rect class="chip" x="{x:.1f}" y="8" width="{cw}" height="14" rx="2" fill="{c}" '
              f'stroke="{P["line"]}" stroke-width=".6" style="--o:{.2 + i * .07:.2f}s"/>')
        s.add(f'<text x="{x + cw / 2:.1f}" y="32" fill="{P["dim"]}" text-anchor="middle" '
              f'style="font-size:7.5px">{c[1:]}</text>')
        s.regular.update(c[1:])
        x += cw + 3
    return s.render()


# ─────────────────────────────────────────────────────────────── footer ──
def footer(P: dict, D: dict) -> str:
    H = 88
    s = SVG(W, H, P, "drop a star if a theme made your terminal feel like home")
    cols = int((W - 28) / CW)
    # a full-width string of prayer flags to close the page
    xa, xb, ya, sag = 14, W - 14, 12, 22
    s.add(f'<path d="M{xa},{ya} Q{W / 2},{ya + sag * 2} {xb},{ya}" fill="none" stroke="{P["dim"]}" stroke-width=".8"/>')
    s.css.append(
        "@keyframes flap{0%,100%{transform:skewX(0) scaleY(1)}30%{transform:skewX(-14deg) scaleY(.92)}"
        "65%{transform:skewX(9deg) scaleY(1.04)}}"
        ".flag{transform-box:fill-box;transform-origin:50% 0;animation:flap var(--d) ease-in-out var(--o) infinite}"
    )
    rr = random.Random(5)
    n = 40
    for i in range(1, n):
        t = i / n
        x = (1 - t) ** 2 * xa + 2 * (1 - t) * t * W / 2 + t ** 2 * xb
        y = (1 - t) ** 2 * ya + 2 * (1 - t) * t * (ya + sag * 2) + t ** 2 * ya
        s.add(f'<rect class="flag" x="{x - 4:.1f}" y="{y:.1f}" width="8" height="10" fill="{P["flags"][i % 5]}" '
              f'opacity=".85" style="--d:{rr.uniform(1.6, 2.8):.2f}s;--o:-{rr.uniform(0, 2):.2f}s"/>')
    segs = [("❯ ", P["accent"]), ("drop a ", P["mute"]), ("*", P["gold"], True),
            (" if a theme made your terminal feel like home", P["mute"])]
    typed(s, 14, 70, segs, delay=.4, speed=.03, key="ft")
    synced = (datetime.now(timezone.utc) + TZ_OFFSET).strftime("%d %b %Y · %H:%M").lower()
    r = f"synced {synced} {TZ_LABEL}"
    s.text(W - 14 - len(r) * CW, 70, r, fill=P["dim"])
    return s.render()


# ───────────────────────────────────────────────────────────────── main ──
def main():
    demo = "--demo" in sys.argv
    D = derive(demo_data() if demo else fetch_live())
    ASSETS.mkdir(exist_ok=True)

    palettes = {}
    for t in THEMES:
        try:
            palettes[t] = theme_palette(t)
        except Exception as e:  # keep the last good swatch if a preview is unreachable
            print(f"swatch {t}: {e}", file=sys.stderr)

    out = {}
    for mode, P in PALETTES.items():
        out[f"hero-{mode}"] = hero(P, D)
        out[f"fetch-{mode}"] = fetch(P, D)
        out[f"pulse-{mode}"] = pulse(P, D)
        out[f"head-themes-{mode}"] = head(P, "~/themes", "ls --by palette", f"{len(THEMES):02d} omarchy themes", "h1")
        out[f"head-web-{mode}"] = head(P, "~/clients", "cat ladakh.index", f"{SITES:02d} sites · ladakh", "h2")
        out[f"footer-{mode}"] = footer(P, D)
        for t, cols in palettes.items():
            out[f"swatch-{t}-{mode}"] = swatch(P, t, cols)

    for name, svg in out.items():
        (ASSETS / f"{name}.svg").write_text(svg, encoding="utf-8")
    print(f"wrote {len(out)} svgs → {ASSETS}")


if __name__ == "__main__":
    main()
