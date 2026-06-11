#!/usr/bin/env python3
"""The Daily Fable — asks claude-fable-5 for a micro-fable and renders it
into an animated SVG scroll for the profile README.

Usage:
  ANTHROPIC_API_KEY=sk-... python scripts/generate_fable.py
  python scripts/generate_fable.py --offline   # test without an API call

Stdlib only — no dependencies.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import textwrap
import urllib.request
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = "claude-fable-5"
API_URL = "https://api.anthropic.com/v1/messages"

THEMES = [
    ("AI & technology", "models, agents, automation, and the humans who work with them"),
    ("leadership & management", "directors, teams, decisions, and the cost of avoiding them"),
    ("cinema & storytelling", "filmmakers, audiences, scripts, and the truths films tell"),
    ("the Panchatantra tradition", "talking animals in the classic Indian fable style, with a modern echo"),
]

PROMPT = """Write an original micro-fable (70-90 words) about {theme_desc}.
Style: Aesop meets the Panchatantra — concrete characters, one small reversal, no preaching until the moral.
Return ONLY valid JSON, no markdown fences:
{{"title": "...", "fable": "...", "moral": "one sentence, max 16 words"}}"""

SAMPLE = {
    "title": "The Compiler and the Poet",
    "fable": (
        "A compiler boasted that it rejected every flawed line ever shown to it. "
        "A poet sat nearby, crossing out her own verses. \"You and I do the same work,\" "
        "she said. The compiler scoffed: \"I enforce rules. You merely feel.\" That night "
        "the poet wrote a program, and the compiler, finding no errors, passed it in "
        "silence — and no one remembered the compiler, but everyone quoted the poem it had approved."
    ),
    "moral": "Judgment is forgotten; what it permits to exist is remembered.",
}


def pick_theme(today: dt.date):
    return THEMES[today.toordinal() % len(THEMES)]


def call_claude(theme_desc: str) -> dict:
    key = os.environ["ANTHROPIC_API_KEY"]
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 600,
        "messages": [{"role": "user", "content": PROMPT.format(theme_desc=theme_desc)}],
    }).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    text = "".join(b.get("text", "") for b in data["content"]).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    fable = json.loads(text)
    assert {"title", "fable", "moral"} <= set(fable)
    return fable


def render_svg(fable: dict, theme_name: str, today: dt.date) -> str:
    body_lines = textwrap.wrap(fable["fable"], width=74)
    moral_lines = textwrap.wrap("Moral: " + fable["moral"], width=66)

    y = 96
    tspans = []
    for line in body_lines:
        tspans.append(
            f'<text class="body ln" x="70" y="{y}">{escape(line)}</text>')
        y += 27
    y += 14
    for line in moral_lines:
        tspans.append(
            f'<text class="moral ln" x="70" y="{y}">{escape(line)}</text>')
        y += 26
    height = y + 64

    # staggered fade-in per line
    styled = []
    for i, t in enumerate(tspans):
        styled.append(t.replace('class="', f'style="animation-delay:{0.8 + i * 0.18:.2f}s" class="'))
    text_block = "\n  ".join(styled)

    return f"""<svg viewBox="0 0 840 {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(fable['title'])}">
  <defs>
    <linearGradient id="parchment" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1d1f33"/>
      <stop offset="100%" stop-color="#15172a"/>
    </linearGradient>
    <style>
      .head {{ font: 700 26px Georgia, serif; fill: #ffd166; }}
      .meta {{ font: 13px 'Courier New', monospace; fill: #8b93b8; }}
      .body {{ font: 17px Georgia, serif; fill: #dde2f1; }}
      .moral {{ font: italic 17px Georgia, serif; fill: #f4a261; }}
      .ln {{ opacity: 0; animation: rise 0.9s ease forwards; }}
      @keyframes rise {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
      .rule {{ stroke: #ffd166; stroke-width: 1; opacity: 0.5; stroke-dasharray: 700; stroke-dashoffset: 700; animation: draw 2.5s ease 0.4s forwards; }}
      @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    </style>
  </defs>
  <rect width="840" height="{height}" rx="14" fill="url(#parchment)" stroke="#2e3354" stroke-width="1.5"/>
  <text class="head" x="70" y="52">✦ {escape(fable['title'])}</text>
  <line class="rule" x1="70" y1="66" x2="770" y2="66"/>
  {text_block}
  <text class="meta" x="70" y="{height - 28}">a {escape(theme_name)} fable · told fresh on {today:%d %b %Y} by {MODEL}</text>
</svg>
"""


def update_readme(fable: dict, today: dt.date):
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    content = readme.read_text(encoding="utf-8")
    block = (f"<!--FABLE:START-->\n"
             f"> **{fable['title']}** — *{fable['moral']}* ({today:%d %b %Y})\n"
             f"<!--FABLE:END-->")
    new = re.sub(r"<!--FABLE:START-->.*?<!--FABLE:END-->", block, content, flags=re.S)
    readme.write_text(new, encoding="utf-8")


def archive(fable: dict, theme_name: str, today: dt.date):
    d = ROOT / "fables"
    d.mkdir(exist_ok=True)
    (d / f"{today:%Y-%m-%d}.md").write_text(
        f"# {fable['title']}\n\n*{theme_name}* · {today:%d %B %Y} · told by {MODEL}\n\n"
        f"{fable['fable']}\n\n**Moral:** {fable['moral']}\n",
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use built-in sample fable")
    args = ap.parse_args()

    today = dt.date.today()
    theme_name, theme_desc = pick_theme(today)
    fable = SAMPLE if args.offline else call_claude(theme_desc)

    svg = render_svg(fable, theme_name, today)
    out = ROOT / "assets" / "fable.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    update_readme(fable, today)
    archive(fable, theme_name, today)
    print(f"✦ {fable['title']} ({theme_name}) → {out}")


if __name__ == "__main__":
    main()
