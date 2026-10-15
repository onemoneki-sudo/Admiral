"""The film's sound: sound effects only, no music, synthesized here and timed to film.js, so the film owes no one
for them.

    python3 docs/film/score.py out.wav        # 92 s, 48 kHz stereo (needs numpy and scipy)

A cue for each thing that happens on screen (a window opening, a notification, a mark, a click, a station lighting
up), sonar on the fleet's radar, and two hits under the statement.
"""

import sys
import wave

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
DUR = 92.0
P = 1.2  # film.js opens on its poster for this long; every cue is that much later
IN, D = 41.6, 6.4  # film.js's decisions scene comes in here and lasts this long; every cue from here on is that much later
N = int(SR * (DUR + P + D))
rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def note_names(*names):
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    out = []
    for n in names:
        step, acc, octv = n[0], n[1:-1], int(n[-1])
        out.append(12 * (octv + 1) + base[step] + {"": 0, "b": -1, "#": 1}[acc])
    return out


def lowpass(x, cutoff, order=2):
    return sosfilt(butter(order, cutoff, "low", fs=SR, output="sos"), x)


def highpass(x, cutoff, order=2):
    return sosfilt(butter(order, cutoff, "high", fs=SR, output="sos"), x)


def env(n, attack, release, curve=2.0):
    """A swell: attack and release in samples, sustain between."""
    e = np.ones(n)
    a, r = min(attack, n // 2), min(release, n // 2)
    if a:
        e[:a] = np.linspace(0, 1, a) ** curve
    if r:
        e[-r:] = np.linspace(1, 0, r) ** curve
    return e


class Track:
    def __init__(self):
        self.l = np.zeros(N + SR * 4)
        self.r = np.zeros(N + SR * 4)

    def add(self, at, sig, gain=1.0, pan=0.0, shift=True):
        """Mix a mono signal in at `at` seconds of the story, panned -1 (left) to 1 (right). A cue from IN on moves
        past the decisions scene, unless shift is False (the scene's own cues)."""
        i = int((at + P + (D if shift and at >= IN else 0)) * SR)
        if i < 0:
            sig, i = sig[-i:], 0
        sig = sig[:len(self.l) - i]
        lg, rg = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        self.l[i:i + len(sig)] += sig * gain * lg * 1.41
        self.r[i:i + len(sig)] += sig * gain * rg * 1.41


def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR


# ---------- instruments ----------
def pluck(f, seconds=0.9, decay=5.0, tone=1.0):
    t = t_axis(seconds)
    x = (np.sin(2 * np.pi * f * t) + 0.4 * tone * np.sin(4 * np.pi * f * t) + 0.12 * tone * np.sin(6 * np.pi * f * t))
    return x * np.exp(-decay * t) * env(len(t), int(0.004 * SR), int(0.05 * SR), 1)


def ping(f=1760, seconds=2.6):
    """Sonar: a pure tone that rings, with a faint lower partial."""
    t = t_axis(seconds)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 0.5 * t)
    return x * np.exp(-2.2 * t) * env(len(t), int(0.006 * SR), int(0.2 * SR), 1)


def thump(seconds=0.6, f0=110, f1=42, gain=1.0):
    t = t_axis(seconds)
    f = f1 + (f0 - f1) * np.exp(-18 * t)
    return gain * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-6 * t)


def impact(seconds=3.5):
    """A deep hit with a bright air on top, for the big statements."""
    t = t_axis(seconds)
    low = np.sin(2 * np.pi * np.cumsum(38 + 70 * np.exp(-10 * t)) / SR) * np.exp(-1.6 * t)
    air = highpass(rng.standard_normal(len(t)), 3000) * np.exp(-3.5 * t) * 0.08
    return low + air


def whoosh(seconds=0.9, lo=300, hi=4000, peak=0.6):
    """Noise swept through a band, swelling to `peak` of its length."""
    t = t_axis(seconds)
    noise = rng.standard_normal(len(t))
    out = np.zeros_like(noise)
    steps = 24
    edges = np.linspace(0, len(t), steps + 1).astype(int)
    for k in range(steps):  # a band that moves: filter in short blocks
        c = lo * (hi / lo) ** (k / (steps - 1))
        sos = butter(2, [c * 0.7, min(c * 1.4, SR / 2 - 100)], "band", fs=SR, output="sos")
        out[edges[k]:edges[k + 1]] = sosfilt(sos, noise)[edges[k]:edges[k + 1]]
    shape = np.where(t < seconds * peak, (t / (seconds * peak)) ** 2, np.exp(-6 * (t - seconds * peak) / seconds))
    return out * shape * 0.5


def blip(f1=1320, f2=1760):
    """A notification: two short tones."""
    a = pluck(f1, 0.18, 22, 0.3)
    b = pluck(f2, 0.5, 9, 0.3)
    out = np.zeros(int(0.65 * SR))
    out[:len(a)] += a
    out[int(0.09 * SR):int(0.09 * SR) + len(b)] += b
    return out


def tick(f=2400):
    t = t_axis(0.08)
    return (np.sin(2 * np.pi * f * t) * np.exp(-60 * t)) + highpass(rng.standard_normal(len(t)), 2000) * np.exp(-90 * t) * 0.3


def click():
    t = t_axis(0.05)
    return highpass(rng.standard_normal(len(t)), 1500) * np.exp(-140 * t) + np.sin(2 * np.pi * 900 * t) * np.exp(-90 * t) * .6


def reverb(x, seconds=2.8, seed=3):
    r = np.random.default_rng(seed)
    t = t_axis(seconds)
    ir = r.standard_normal(len(t)) * np.exp(-3.2 * t / seconds * 3)
    ir = lowpass(ir, 5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    return fftconvolve(x, ir)[:len(x)]


# ---------- the cues ----------
def compose():
    sfx = Track()
    # 1. too many windows (0..7): a hiss that rises under them
    sw = highpass(rng.standard_normal(int(6.6 * SR)), 1200) * np.linspace(0, 1, int(6.6 * SR)) ** 3 * 0.05
    sfx.add(0.0, lowpass(sw, 6000))
    for i in range(22):  # each window opening
        sfx.add(.15 + i * .16, tick(2600 + (i % 5) * 180), .12, pan=((i * 37) % 11) / 5.5 - 1)
    for at in (2.4, 3.0, 3.5, 3.9, 4.3, 4.6):  # notifications
        sfx.add(at, blip(), .16, pan=((at * 7) % 2) - 1)
    for at, g in ((1.1, .5), (2.2, .5), (5.0, .8)):  # the three lines
        sfx.add(at, thump(), g)
    sfx.add(5.6, whoosh(1.4, 200, 6000, .85), .5)
    # 2. the fleet (7..14): a hit for the title, sonar on the sweep
    sfx.add(7.0, impact(3.0), .45)
    for at in (7.6, 10.1, 12.6):
        sfx.add(at, ping(), .14, pan=-.3)
        sfx.add(at + .38, ping(), .05, pan=.4)  # its echo
    # 3..5. the interface (14..51.6)
    sfx.add(15.6, whoosh(.8, 400, 3000, .5), .18)  # the status line draws
    for at in (17.6, 18.6, 19.6, 20.6, 21.6, 23.9, 25.3):  # each mark
        sfx.add(at, pluck(hz(note_names("A5")[0]), .5, 9, .2), .10, pan=.2)
    sfx.add(27.0, whoosh(1.4, 250, 2500, .7), .3, pan=.5)  # the sidebar slides in
    sfx.add(28.8, whoosh(1.2, 150, 1500, .8), .22)  # zoom
    for k, at in enumerate((30.4, 30.9, 31.4)):  # the three ways a session waits
        sfx.add(at, pluck(hz(note_names("E5", "G5", "A5")[k]), .5, 8, .3), .10, pan=-.4)
    sfx.add(34.6, whoosh(1.2, 150, 1500, .8), .2)
    sfx.add(41.6, whoosh(1.4, 1500, 200, .3), .25)  # step back
    sfx.add(44.8, click(), .55, pan=.3)  # the click
    sfx.add(45.0, whoosh(.9, 300, 5000, .6), .35, pan=-.3)  # the window comes forward
    sfx.add(45.35, pluck(hz(note_names("A5")[0]), 1.6, 3, .6), .16, pan=-.3)
    sfx.add(45.4, pluck(hz(note_names("E6")[0]), 1.6, 3, .4), .09, pan=-.3)
    # 6. milestones (51.6..59.4): one note per station as it lights up
    for k, m in enumerate(note_names("D4", "F4", "A4", "C5", "D5")):
        at = 52.4 + k * 1.05
        sfx.add(at, pluck(hz(m), 1.4, 3.5, .7), .16, pan=-.6 + k * .3)
        sfx.add(at, thump(.4, 100, 50), .12)
    # 7. a PR finds its owner (59.4..66.8)
    for k in range(4):  # the push output, line by line
        sfx.add(60.2 + k * .35, tick(1800 + k * 200), .08)
    sfx.add(61.9, whoosh(1.1, 400, 4000, .7), .3)
    sfx.add(63.0, pluck(hz(note_names("G5")[0]), 1.4, 3.5, .6), .15)
    sfx.add(63.0, thump(.4, 110, 55), .2)
    # 8. what you can close (66.8..73.4)
    for k in range(3):
        sfx.add(67.4 + k * .35, thump(.35, 120, 60), .18)
        sfx.add(67.4 + k * .35, pluck(hz(note_names("D5", "F5", "A5")[k]), .6, 7, .3), .08)
    # 9. the playbook (73.4..80), then a riser towards the statement
    for k in range(6):
        sfx.add(74.0 + k * .15, tick(2200 + k * 150), .07)
    sfx.add(77.2, whoosh(.9, 600, 3000, .6), .22)
    sfx.add(78.0, whoosh(2.0, 150, 8000, .98), .45)  # riser into the silence
    # 10. the statement (80..84): silence, then two hits
    sfx.add(80.2, impact(3.8), .9)
    sfx.add(81.2, impact(3.2), .75)
    sfx.add(81.2, pluck(hz(note_names("A5")[0]), 2.4, 1.8, .5), .14)
    # 11. the end (84..92)
    sfx.add(84.4, ping(1174.7, 3.5), .12, pan=-.2)
    sfx.add(84.8, ping(1174.7, 3.5), .05, pan=.3)
    for k, at in enumerate((86.6, 86.8, 87.0)):  # the install lines
        sfx.add(at, tick(1900 + k * 150), .07)
    # the decisions scene (IN .. IN + D): calls go to the commander; four are logged, two come to the person together
    def dec(u, sig, gain, pan=0.0):
        sfx.add(IN + u, sig, gain, pan, shift=False)
    dec(0.0, whoosh(.9, 1500, 300, .4), .22)
    for k in range(6):
        dec(.4 + k * .08, tick(2200 + k * 120), .06, pan=-.6)
    dec(.6, thump(.4, 110, 55), .14)
    route = [0, 4, 1, 2, 5, 3]  # the order film.js sends them; 0-3 are logged, 4-5 are the person's
    for n, i in enumerate(route):
        go, back = 1.1 + n * .32, 1.9 + n * .32
        dec(go, blip(1180, 1480), .07, pan=-.4)
        dec(go + .55, click(), .12, pan=-.1)
        if i < 4:
            dec(back + .5, pluck(hz(note_names("E6", "G6", "A6", "C7")[i]), .7, 7, .3), .1, pan=.5)
        else:
            dec(back + .5, blip(1568, 1976), .1, pan=.5)
    dec(4.4, ping(1318.5, 2.4), .1, pan=.4)
    dec(D - .5, whoosh(.8, 300, 1500, .6), .18)
    return sfx


def main(out):
    sfx = compose()
    L, R = sfx.l[:N], sfx.r[:N]
    wetL, wetR = reverb(L, seed=3), reverb(R, seed=4)  # one room for everything, a touch decorrelated
    L, R = L * .78 + wetL * .42, R * .78 + wetR * .42
    L, R = highpass(L, 38), highpass(R, 38)
    L, R = L - .45 * lowpass(L, 220), R - .45 * lowpass(R, 220)  # a low shelf down: no boom, no mud
    L, R = L + .25 * highpass(L, 2500), R + .25 * highpass(R, 2500)  # a little air
    fade = np.ones(N)
    fade[-int(2.0 * SR):] = np.linspace(1, 0, int(2.0 * SR)) ** 1.5
    fade[:int(.05 * SR)] = np.linspace(0, 1, int(.05 * SR))
    L, R = L * fade, R * fade
    peak = max(np.max(np.abs(L)), np.max(np.abs(R)))
    L, R = np.tanh(L / peak * 1.35) / np.tanh(1.35), np.tanh(R / peak * 1.35) / np.tanh(1.35)  # gentle limiting
    L, R = L * 0.89, R * 0.89  # about -1 dBFS
    data = (np.stack([L, R], axis=1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "score.wav")
