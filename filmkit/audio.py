"""Sound: a music bed and effects made by our own synthesis (no third-party sound, so a film on any platform carries no music licence question), a mix with the voice lines the caller
brings (files: the voice is made elsewhere, by a provider the pack chooses), the bed ducked under speech, a fade at the end and a loudness target. Everything is numpy and scipy."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from .util import FilmkitError, ffmpeg_path, run

SR = 44100
DEFAULT_PROGRESSION = [[57, [57, 60, 64, 69]], [53, [53, 57, 60, 65]], [48, [48, 52, 55, 64]], [55, [55, 59, 62, 67]]]      # Am F C G, the root first


def midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def lowpass(x, f, order=2):
    return sosfilt(butter(order, min(f, SR / 2 - 100), btype="low", fs=SR, output="sos"), x)


def highpass(x, f, order=2):
    return sosfilt(butter(order, min(f, SR / 2 - 100), btype="high", fs=SR, output="sos"), x)


def env(n: int, a=0.01, r=0.2) -> np.ndarray:
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def saws(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    return sum(2 * ((t * f * 2 ** (c / 1200)) % 1.0) - 1 for c in (-7, 0, 7)) / 3


def reverb(x: np.ndarray, secs=2.2, wet=0.28, seed=3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(secs * SR)
    ir = lowpass(rng.standard_normal(n) * np.exp(-np.linspace(0, 6.5, n)), 5000)
    w = fftconvolve(x, ir)[:len(x)]
    w *= np.max(np.abs(x)) / (np.max(np.abs(w)) + 1e-9)
    return x * (1 - wet) + w * wet


def place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(t * SR)
    n = min(len(sig), len(buf) - i)
    if n > 0 and i >= 0:
        buf[i:i + n] += sig[:n] * gain


def riser(rng, t0: float, t1: float, top: float = 9000) -> np.ndarray:
    m = int((t1 - t0) * SR)
    x = rng.standard_normal(m)
    out = np.zeros(m)
    for c in range(24):
        a, b = c * m // 24, (c + 1) * m // 24
        out[a:b] = highpass(x[a:b], 400 * (top / 400) ** (c / 24), 2)
    return out * np.linspace(0, 1, m) ** 2.2 * 0.20


def whoosh(rng, dur: float = 0.7) -> np.ndarray:
    m = int(dur * SR)
    x = rng.standard_normal(m)
    out = np.zeros(m)
    for c in range(14):
        a, b = c * m // 14, (c + 1) * m // 14
        f = 300 * (6000 / 300) ** (np.sin(np.pi * (c + 0.5) / 14))
        out[a:b] = highpass(lowpass(x[a:b], f * 3), f * 0.6)
    return out * np.sin(np.linspace(0, np.pi, m)) ** 2 * 0.26


def impact(rng, dur: float = 1.8) -> np.ndarray:
    m = int(dur * SR)
    tt = np.arange(m) / SR
    return np.sin(2 * np.pi * (46 + 38 * np.exp(-tt * 7)) * tt) * np.exp(-tt * 2.6) * 0.55 + lowpass(rng.standard_normal(m), 1800) * np.exp(-tt * 9) * 0.35


def ping(step: int) -> np.ndarray:
    tt = np.arange(int(0.9 * SR)) / SR
    f = midi(81 + [0, 4, 7, 12, 14, 16][step % 6])
    return np.sin(2 * np.pi * f * tt + np.sin(2 * np.pi * f * 3.0 * tt) * np.exp(-tt * 12) * 1.2) * np.exp(-tt * 5) * 0.12


def bed(dur: float, bpm: float = 90, progression=None, pluck_from: float = 0.0, pluck_gain: float = 0.13) -> np.ndarray:
    """An ambient bed: a pad on each bar's chord, a sub on the root, eighth-note FM plucks from `pluck_from` with an echo, a long reverb."""
    prog_ = progression or DEFAULT_PROGRESSION
    n = int(dur * SR)
    pad, sub, pluck = np.zeros(n), np.zeros(n), np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    for b in range(int(dur / bar) + 1):
        t0 = b * bar
        if t0 >= dur:
            break
        root, notes = prog_[b % len(prog_)]
        ln = int(min(bar + 1.2, dur - t0 + 1.2) * SR)
        seg = sum(saws(midi(nt), ln) for nt in notes)
        place(pad, lowpass(seg, 1400) * env(ln, 0.7, 1.0) * 0.16, t0)
        tt = np.arange(int((bar + 0.4) * SR)) / SR
        place(sub, np.sin(2 * np.pi * midi(root - 24) * tt) * env(len(tt), 0.05, 0.4) * 0.34, t0)
    rng = np.random.default_rng(11)
    t, k = 0.0, 0
    while t < dur - 0.4:
        b = int(t / bar)
        root, notes = prog_[b % len(prog_)]
        if t >= pluck_from - 1e-6:
            nt = notes[1:][(k * 3 + b) % (len(notes) - 1)] + 12 + (12 if (k % 8) in (5, 7) else 0)
            f = midi(nt)
            tt = np.arange(int(0.55 * SR)) / SR
            mod = np.sin(2 * np.pi * f * 2.0 * tt) * np.exp(-tt * 9) * 1.6
            place(pluck, np.sin(2 * np.pi * f * tt + mod) * np.exp(-tt * 6.5), t, pluck_gain * (0.8 + 0.2 * rng.random()))
        k += 1
        t += beat / 2
    d = int(beat * 0.75 * SR)
    echo = np.zeros_like(pluck)
    if d < n:
        echo[d:] += pluck[:-d] * 0.38
        echo[2 * d:] += pluck[:-2 * d] * 0.16
    return reverb(pad + pluck + echo, 2.2, 0.30) + sub


def read_audio(path: Path) -> np.ndarray:
    """A file as mono float samples at 44.1 kHz (its first channel; a voice file is mono, and our own mixes are two equal channels)."""
    out = run_bytes([ffmpeg_path(), "-v", "error", "-i", str(path), "-af", "pan=mono|c0=c0", "-f", "f32le", "-ar", str(SR), "-"])      # the first channel: a downmix would add gain
    return np.frombuffer(out, dtype="<f4").astype(np.float64)


def run_bytes(cmd):
    import subprocess
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise FilmkitError(f"{cmd[0]} failed: {r.stderr.decode(errors='replace')[-300:]}")
    return r.stdout


LIMIT = 0.80                                                                    # the sample-peak ceiling, -1.9 dBFS: AAC adds 0.4 to 1 dB, so the delivered true peak stays at or under -1 dBTP


def measure_lufs(src: list[str], chain: str = "") -> float | None:
    """Integrated loudness (LUFS) of an input run through `chain` (a filter chain ending in a comma, or empty); None when it cannot be measured (silence)."""
    r = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostats", *src, "-af", chain + "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    lufs = None
    for line in r.stderr.splitlines():
        t = line.strip()
        if t.startswith("I:"):
            lufs = float(t.split()[1])
    return lufs if lufs is not None and lufs > -70 else None


def normalise(pcm: Path, target: float, out_wav: Path) -> float | None:
    """Bring a mono 16-bit mix to `target` LUFS and out as a stereo wav. Loudness is measured on what is delivered, the stereo file: the same mono signal on two channels reads 3 LU louder than
    on one, which is how a one-pass loudnorm on the mono mix ended 3 LU high. So: measure, apply the gain, let the limiter hold the peaks, measure the result again, and close the gap in up to
    three rounds. Returns the loudness it ended at."""
    src = ["-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", str(pcm)]
    limit = f"alimiter=limit={LIMIT}:level=false"
    pan = "pan=stereo|c0=c0|c1=c0"
    now = measure_lufs(src, pan + ",")
    gain = (target - now) if now is not None else 0.0
    for _ in range(3):
        got = measure_lufs(src, f"volume={gain:.2f}dB,{limit},{pan},")
        if got is None or abs(got - target) < 0.15:
            break
        gain += target - got
    run([ffmpeg_path(), "-v", "error", "-y", *src, "-af", f"volume={gain:.2f}dB,{limit},{pan}", "-ar", str(SR), str(out_wav)])
    return measure_lufs(["-i", str(out_wav)])


def mix(spec_audio: dict, duration: float, base_dir: Path, out_wav: Path) -> dict:
    """Build the soundtrack of a film into `out_wav` (stereo, the loudness target applied) and say what went in."""
    n = int(duration * SR)
    music = spec_audio.get("music") or {}
    vo = np.zeros(n)
    voice_ends = []
    for ev in spec_audio.get("voice", []):
        p = Path(ev["file"])
        sig = read_audio(p if p.is_absolute() else base_dir / p)
        sig = reverb(np.concatenate([sig, np.zeros(SR)]), 0.9, 0.10) * env(len(sig) + SR, 0.02, 0.35)
        place(vo, sig, ev["t"], ev.get("gain", 1.0))
        voice_ends.append(round(ev["t"] + len(sig) / SR - 1.0, 2))
    rng = np.random.default_rng(5)
    bd = bed(duration, music.get("bpm", 90), music.get("progression"), music.get("pluck_from", 0.0)) if music.get("bed", True) and music else np.zeros(n)
    fx = np.zeros(n)
    for a, b in music.get("risers", []):
        place(fx, riser(rng, a, b), a)
    for t0 in music.get("impacts", []):
        place(fx, impact(rng), t0)
    for t0 in music.get("whooshes", []):
        place(fx, whoosh(rng), t0)
    for i, t0 in enumerate(music.get("pings", [])):
        place(fx, ping(i), t0)
    win = int(0.05 * SR)
    rms = np.sqrt(np.convolve(vo ** 2, np.ones(win) / win, mode="same"))
    act = np.clip(np.convolve((rms > 0.012).astype(float), np.ones(int(0.35 * SR)) / int(0.35 * SR), mode="same") * 1.6, 0, 1)
    duck = 10 ** (spec_audio.get("duck_db", -7) / 20)
    mx = bd * (1 - (1 - duck) * act) * 0.9 + fx * (0.85 + 0.15 * (1 - act)) + vo * 1.15
    k = min(n, int(spec_audio.get("fade_out", 1.4) * SR))                       # a fade longer than the film is the whole film
    fade = np.ones(n)
    fade[-k:] = np.linspace(1, 0, k)
    mx = mx * fade
    pk = float(np.max(np.abs(mx)))
    silent = pk < 1e-4                                                          # loudnorm would turn silence into noise: leave a silent film silent
    mx = mx / pk * 0.92 if not silent else np.zeros(n)
    pcm = Path(out_wav).with_suffix(".pcm")
    pcm.write_bytes((mx * 32767).astype("<i2").tobytes())
    target = spec_audio.get("lufs", -16)
    if silent:
        run([ffmpeg_path(), "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", str(pcm), "-af", "pan=stereo|c0=c0|c1=c0", "-ar", str(SR), str(out_wav)])
        got = None
    else:
        got = normalise(pcm, target, Path(out_wav))
    pcm.unlink(missing_ok=True)
    return {"voice_ends": voice_ends, "lufs_target": target, "mix_lufs": got}
