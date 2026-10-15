"""Real output for the film: the demo fleet's board, and the status line Claude Code would draw for it (claude-hud's
lines, when it is installed, then Admiral's), turned from terminal colors into HTML. Nothing here is drawn by hand.

    python3 docs/film/build_assets.py      # writes docs/film/assets.js
"""

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SGR = re.compile(r"\x1b\[([0-9;]*)m")
OSC = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\")  # hyperlinks: dropped, the text stays

BASIC = {30: "#3b4252", 31: "#f2777a", 32: "#7cc47f", 33: "#e5c07b", 34: "#6fa8dc", 35: "#c792ea", 36: "#66c2cd",
         37: "#d8dee9", 90: "#6b7686", 91: "#ff8b8b", 92: "#98dc9b", 93: "#f0d38a", 94: "#82b8f0", 95: "#d7a6f2",
         96: "#8ad7e0", 97: "#eef1f5"}


def xterm(n):
    if n < 16:
        return BASIC.get(30 + n if n < 8 else 82 + n, "#d8dee9")
    if n < 232:
        n -= 16
        return "#%02x%02x%02x" % tuple(0 if v == 0 else 55 + v * 40 for v in (n // 36, n // 6 % 6, n % 6))
    g = 8 + (n - 232) * 10
    return "#%02x%02x%02x" % (g, g, g)


def ansi_html(text):
    """Terminal output to HTML spans: colors, bold and dim kept, as a terminal shows them."""
    text = OSC.sub("", text)
    out, style, pos = [], {}, 0
    for m in SGR.finditer(text):
        chunk = text[pos:m.start()]
        if chunk:
            out.append(span(chunk, style))
        codes = [int(c) for c in m.group(1).split(";") if c] or [0]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                style = {}
            elif c == 1:
                style["bold"] = True
            elif c == 2:
                style["dim"] = True
            elif c == 22:
                style.pop("bold", None), style.pop("dim", None)
            elif c in BASIC:
                style["color"] = BASIC[c]
            elif c == 39:
                style.pop("color", None)
            elif c == 38 and codes[i + 1:i + 2] == [5]:
                style["color"], i = xterm(codes[i + 2]), i + 2
            elif c == 38 and codes[i + 1:i + 2] == [2]:
                style["color"], i = "#%02x%02x%02x" % tuple(codes[i + 2:i + 5]), i + 4
            i += 1
        pos = m.end()
    if text[pos:]:
        out.append(span(text[pos:], style))
    return "".join(out)


def cells(text):
    """Wide (CJK) characters kept exactly two terminal cells wide, so a status line stays aligned in any font."""
    return "".join(f'<span class="w2">{ch}</span>' if unicodedata.east_asian_width(ch) in "WF" else ch
                   for ch in html.escape(text))


def span(chunk, style):
    css = []
    if "color" in style:
        css.append(f"color:{style['color']}")
    if style.get("bold"):
        css.append("font-weight:700")
    if style.get("dim"):
        css.append("opacity:.55")
    return f'<span style="{";".join(css)}">{cells(chunk)}</span>' if css else cells(chunk)


def main():
    work = tempfile.mkdtemp(prefix="admiral-film-")
    project = os.path.join(work, "acme-shop")  # the made-up project the demo session works in
    os.makedirs(project)
    subprocess.run(["git", "init", "-q", "-b", "main", project], check=True)
    subprocess.run(["git", "-C", project, "-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-q",
                    "--allow-empty", "-m", "init"], check=True)
    transcript = os.path.join(work, "transcript.jsonl")
    open(transcript, "w").close()
    base = ""
    try:
        with open(os.path.expanduser("~/.config/admiral/config.toml"), "rb") as fh:
            base = tomllib.load(fh).get("statusline", {}).get("base", "")
    except OSError:
        pass
    cfg = os.path.join(work, "config.toml")
    with open(cfg, "w") as fh:
        fh.write(f'state_dir = {json.dumps(os.path.join(work, "state"))}\n[statusline]\nbase = {json.dumps(base)}\n')
    env = dict(os.environ, ADMIRAL_CONFIG=cfg, PYTHONPATH=ROOT)
    assets = {}
    for lang, commander_name, worker_name in (("en", "Commander-Search", "Search-Synonyms"), ("zh", "总指挥-搜索", "搜索-同义词")):
        subprocess.run([sys.executable, "-m", "admiral", "demo", "--once", "--lang", lang], check=True, env=env, capture_output=True)
        demo_cfg = os.path.join(work, "state", "demo", "config.toml")
        with open(os.path.join(work, "state", "demo", "state", "board.json"), encoding="utf-8") as fh:
            board = json.load(fh)

        def statusline(session_id, cols):
            stdin = {"session_id": session_id, "transcript_path": transcript, "cwd": project,
                     "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
                     "workspace": {"current_dir": project, "project_dir": project}, "version": "2.1.299",
                     "context_window": {"current_usage": {"input_tokens": 61000, "output_tokens": 2000,
                                                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                                        "context_window_size": 200000},
                     "rate_limits": {"five_hour": {"used_percentage": 23, "resets_at": int(time.time()) + 2 * 3600 + 840}}}
            r = subprocess.run([sys.executable, "-m", "admiral", "statusline"], input=json.dumps(stdin), capture_output=True,
                               text=True, cwd=project, env=dict(env, ADMIRAL_CONFIG=demo_cfg, COLUMNS=str(cols + 4)))
            return [ansi_html(line) for line in r.stdout.rstrip("\n").split("\n")]

        commander = next(g["leadRow"]["sessionId"] for g in board["groups"] if g["leadRow"] and g["leadRow"]["name"] == commander_name)
        worker = next(x["sessionId"] for g in board["groups"] for x in g["members"] if x["name"] == worker_name)
        sys.path.insert(0, ROOT)
        from admiral.demo import ZH_NAMES
        assets[lang] = {"board": board, "hudLines": 3 if base else 0, "names": ZH_NAMES if lang == "zh" else {},
                        "statusCommander": statusline(commander, 150), "statusDocked": statusline(commander, 104),
                        "statusWorker": statusline(worker, 150)}
    with open(os.path.join(HERE, "assets.js"), "w", encoding="utf-8") as fh:
        fh.write("// Generated by build_assets.py from Admiral's real output on the demo fleet. Do not edit.\n")
        text = json.dumps(assets, ensure_ascii=False)
        for root in sorted({work, os.path.realpath(work)}, key=len, reverse=True):  # no path of this machine in the repository
            text = text.replace(root, "~/acme-shop")
        fh.write("window.ASSETS = " + text + ";\n")
    print("wrote assets.js: " + ", ".join(f"{k} {v['board']['count']} sessions" for k, v in assets.items()))


if __name__ == "__main__":
    main()
