#!/usr/bin/env python3
"""The Daily Fable — asks a rotating Claude model for a micro-fable and renders
it into an animated SVG scroll for the profile README.

Each day a different model takes the quill and *announces itself* — Opus for
depth, Sonnet for balance, Haiku for efficiency. The choice is seeded by the
date, so it's reproducible but feels random; on weekends the announcement
arrives as a riddle whose answer is the model.

History note: this page was originally written by `claude-fable-5`, Anthropic's
Mythos-class model. On 12 June 2026 the US government issued an export-control
directive suspending access to Fable 5 and Mythos 5 for all foreign nationals,
so the page now rotates among generally-available Claude models.
See: https://www.anthropic.com/news/fable-mythos-access

Usage:
  ANTHROPIC_API_KEY=sk-... python scripts/generate_fable.py
  python scripts/generate_fable.py --offline            # test, no API call
  python scripts/generate_fable.py --offline --model haiku   # force a model
  python scripts/generate_fable.py --offline --riddle        # force riddle style

Stdlib only — no dependencies.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import textwrap
import urllib.request
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_URL = "https://api.anthropic.com/v1/messages"

# The rotating cast. `id` is the exact API model string; `declare` is the plain
# themed-day announcement; `riddle` is the weekend variant whose answer is the
# model itself.
MODELS = [
    {
        "key": "opus",
        "id": "claude-opus-4-8",
        "name": "Opus 4.8",
        "trait": "depth",
        "declare": "A day for depth — Opus holds the pen.",
        "riddle": "I am the deepest of the three, slow to speak but long to see — who writes today?",
    },
    {
        "key": "sonnet",
        "id": "claude-sonnet-4-6",
        "name": "Sonnet 4.6",
        "trait": "balance",
        "declare": "Balance suits today — Sonnet writes.",
        "riddle": "Neither fastest nor most grand, the middle measure steadies the hand — who writes today?",
    },
    {
        "key": "haiku",
        "id": "claude-haiku-4-5-20251001",
        "name": "Haiku 4.5",
        "trait": "efficiency",
        "declare": "Today is a day for efficiency — and so, Haiku it is.",
        "riddle": "I am the swiftest of the three, costing least to set a thought free — who writes today?",
    },
]

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


def pick_model(today: dt.date) -> dict:
    """Deterministic-per-day but pseudo-random choice of model."""
    seed = int(hashlib.sha256(today.isoformat().encode()).hexdigest(), 16)
    return MODELS[seed % len(MODELS)]


def announcement(model: dict, today: dt.date, force_riddle: bool = False) -> str:
    """Themed-day line on weekdays; riddle on weekends (or when forced)."""
    if force_riddle or today.weekday() >= 5:  # Sat/Sun
        return model["riddle"]  # the reveal follows as "told by <model>"
    return model["declare"]


def call_claude(theme_desc: str, model_id: str) -> dict:
    key = os.environ["ANTHROPIC_API_KEY"]
    body = json.dumps({
        "model": model_id,
        "max_tokens": 8000,
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
    # Some models wrap JSON in reasoning/prose — extract the object robustly.
    text = "".join(b.get("text", "") for b in data["content"]).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(
            f"No JSON object found in model response. "
            f"model={model_id!r}, stop_reason={data.get('stop_reason')!r}, "
            f"block types={[b.get('type') for b in data['content']]}, "
            f"text={text[:300]!r}")
    fable = json.loads(match.group(0))
    assert {"title", "fable", "moral"} <= set(fable)
    return fable


def render_svg(fable: dict, theme_name: str, model: dict, today: dt.date) -> str:
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

    meta = (f"a {theme_name} fable · told fresh on {today:%d %b %Y} · "
            f"today's voice: {model['name']} ({model['trait']})")

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
  <text class="meta" x="70" y="{height - 28}">{escape(meta)}</text>
</svg>
"""


def update_readme(fable: dict, model: dict, today: dt.date, ann: str):
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    content = readme.read_text(encoding="utf-8")
    block = (f"<!--FABLE:START-->\n"
             f"> **{fable['title']}** — *{fable['moral']}* ({today:%d %b %Y})\n"
             f">\n"
             f"> <sub>🎙️ {ann} — *told by {model['name']}*</sub>\n"
             f"<!--FABLE:END-->")
    new = re.sub(r"<!--FABLE:START-->.*?<!--FABLE:END-->", block, content, flags=re.S)
    readme.write_text(new, encoding="utf-8")


def archive(fable: dict, theme_name: str, model: dict, today: dt.date, ann: str):
    d = ROOT / "fables"
    d.mkdir(exist_ok=True)
    (d / f"{today:%Y-%m-%d}.md").write_text(
        f"# {fable['title']}\n\n"
        f"*{theme_name}* · {today:%d %B %Y} · told by {model['name']} (`{model['id']}`)\n\n"
        f"> {ann}\n\n"
        f"{fable['fable']}\n\n**Moral:** {fable['moral']}\n",
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use built-in sample fable")
    ap.add_argument("--model", choices=[m["key"] for m in MODELS],
                    help="force a specific model (default: date-seeded pick)")
    ap.add_argument("--riddle", action="store_true", help="force the riddle-style announcement")
    args = ap.parse_args()

    today = dt.date.today()
    theme_name, theme_desc = pick_theme(today)

    if args.model:
        model = next(m for m in MODELS if m["key"] == args.model)
    else:
        model = pick_model(today)

    ann = announcement(model, today, force_riddle=args.riddle)
    fable = SAMPLE if args.offline else call_claude(theme_desc, model["id"])

    svg = render_svg(fable, theme_name, model, today)
    out = ROOT / "assets" / "fable.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    update_readme(fable, model, today, ann)
    archive(fable, theme_name, model, today, ann)
    print(f"✦ {fable['title']} ({theme_name}) — {model['name']} → {out}")
    print(f"  announcement: {ann}")


if __name__ == "__main__":
    main()
