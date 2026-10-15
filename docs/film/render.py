"""Render the film: every frame of index.html in a headless browser, piped to ffmpeg.

    python3 docs/film/render.py                      # docs/media/admiral.mp4 (1920x1080, 30 fps, with sound and a cover)
    python3 docs/film/render.py --lang zh            # docs/media/admiral.zh.mp4, the Chinese version
    python3 docs/film/render.py --stills 3 12.5 30   # PNG frames at those seconds, to check the picture
    python3 docs/film/render.py --gif 41 51 out.gif  # a GIF of seconds 41 to 51 (needs gifski)
    python3 docs/film/render.py --resound            # the same picture, the sound and cover made again (after score.py changes)

Needs Playwright with Chromium (pip install playwright; playwright install chromium) and ffmpeg. Run
build_assets.py first: the film draws Admiral's real output on the demo fleet.
"""

import argparse
import os
import shutil
import subprocess
import tempfile

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(os.path.dirname(HERE), "media")
FPS = 30
COVER = 0  # the cover picture is this frame: the poster the film opens on
LUFS = -19  # the sound's loudness (effects only, so quieter than music would be); peaks are held under -2.5 dBFS, so the AAC encode stays under 0 dBTP


def page_of(p, lang):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page.goto("file://" + os.path.join(HERE, "index.html") + f"?lang={lang}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    return browser, page


def frame(page, t):
    page.evaluate(f"render({t})")
    return page.locator("#stage").screenshot(type="png")


def stills(times, out, lang="en"):
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        browser, page = page_of(p, lang)
        for t in times:
            path = os.path.join(out, f"frame-{t:06.2f}{'' if lang == 'en' else '.' + lang}.png")
            with open(path, "wb") as fh:
                fh.write(frame(page, t))
            print(path)
        browser.close()


def video(start, end, out, fps=FPS, lang="en"):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png",
                           "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser, page = page_of(p, lang)
        end = end if end is not None else page.evaluate("DURATION")
        n = int((end - start) * fps)
        for i in range(n):
            ff.stdin.write(frame(page, start + i / fps))
            if i % (fps * 5) == 0:
                print(f"  {start + i / fps:5.1f}s / {end}s", flush=True)
        browser.close()
    ff.stdin.close()
    ff.wait()
    print(out)


def finish(silent, out):
    """The film with its sound (score.py, brought to LUFS by one gain and a limiter, so its dynamics stay) and its frame at
    COVER as the cover picture, also kept next to it as <out>.cover.png."""
    tmp = tempfile.mkdtemp()
    try:
        wav, cover = os.path.join(tmp, "score.wav"), os.path.join(tmp, "cover.jpg")
        subprocess.run(["python3" if not os.environ.get("FILM_PYTHON") else os.environ["FILM_PYTHON"],
                        os.path.join(HERE, "score.py"), wav], check=True, capture_output=True)
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", wav, "-af", "ebur128", "-f", "null", "-"],
                               capture_output=True, text=True).stderr
        measured = float(probe.split("Integrated loudness:")[1].split("I:")[1].split("LUFS")[0])
        png = os.path.splitext(out)[0] + ".cover.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(COVER), "-i", silent, "-frames:v", "1", png], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", png, "-q:v", "2", cover], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", silent, "-i", wav, "-i", cover,
                        "-map", "0:v", "-map", "1:a", "-map", "2:v", "-c:v:0", "copy", "-c:v:1", "mjpeg",
                        "-disposition:v:1", "attached_pic", "-af", f"volume={LUFS - measured:.2f}dB,alimiter=limit=0.75:attack=2:release=80:level=false",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out], check=True)
        print(out)
    finally:
        shutil.rmtree(tmp)


def gif(start, end, out, width=1200, fps=20, lang="en"):
    tmp = tempfile.mkdtemp()
    try:
        mp4 = os.path.join(tmp, "clip.mp4")
        video(start, end, mp4, fps=fps, lang=lang)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mp4, os.path.join(tmp, "f%04d.png")], check=True)
        frames = sorted(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".png"))
        subprocess.run(["gifski", "--quiet", "--fps", str(fps), "--width", str(width), "--quality", "90", "-o", out, *frames],
                       check=True)
        print(out)
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", nargs="+", type=float)
    ap.add_argument("--gif", nargs=3, metavar=("START", "END", "OUT"))
    ap.add_argument("--lang", choices=["en", "zh"], default="en")
    ap.add_argument("--out")
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--resound", action="store_true")
    a = ap.parse_args()
    a.out = a.out or os.path.join(MEDIA, "admiral.mp4" if a.lang == "en" else f"admiral.{a.lang}.mp4")
    if a.stills:
        stills(a.stills, os.path.join(tempfile.gettempdir(), "admiral-film-stills"), a.lang)
    elif a.gif:
        gif(float(a.gif[0]), float(a.gif[1]), a.gif[2], lang=a.lang)
    elif a.resound:
        silent = a.out + ".silent.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", a.out, "-map", "0:v:0", "-c", "copy", silent], check=True)
        finish(silent, a.out)
        os.remove(silent)
    else:
        silent = a.out + ".silent.mp4"
        video(a.start, a.end, silent, lang=a.lang)
        finish(silent, a.out)
        os.remove(silent)
