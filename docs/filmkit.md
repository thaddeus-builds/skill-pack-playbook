# filmkit

A film spec in, a finished film out. filmkit is the engine under a maker pack: the pack decides **what the film says** (the story, the facts, who may appear, which platform) and writes
that down as one JSON document, the *film spec*; filmkit decides **how it is made** (camera moves, cuts, a grade, animated type, sound, a loudness target) and checks it before it renders.
The spec is the only thing the two share, so either side can change without the other noticing.

```
maker pack (story, facts, people, channel)  ->  film spec  ->  filmkit (validate, check, still, render, inspect)  ->  film.mp4
```

What filmkit is **not**: it makes no picture from nothing (the footage and photos are the caller's), makes no voice (a voice line is a file the caller brings, made by whichever provider the
pack chose), judges no claim (a number on screen is the pack's to source), and decides no platform's rules (it ships profiles for where type may sit, nothing else). Nothing third-party is
inside a film it makes: the music and effects are synthesised here, the fonts are the caller's.

Needs: Python 3.10+, numpy, Pillow, scipy, and `ffmpeg` + `ffprobe` on the PATH. `python3 -m filmkit demo --out DIR` makes synthetic clips and a spec that uses everything; start there.

## The verbs

Every verb prints one JSON document; a problem exits 1 with the list.

| verb | does |
|---|---|
| `validate SPEC` | everything wrong with the spec, each as `where: what`, files included; `ok: true` when it can be rendered |
| `check SPEC` | the layout and timing checks below, on the spec alone, in about a second |
| `still SPEC --at T --out PNG [--scale S]` | one frame of the finished film (footage with the grade, graphics, scrim): the way to look before rendering. Counts source frames like a render, so it is the frame a render would show |
| `render SPEC --out MP4 [--preview F] [--workdir DIR]` | the film; `--preview 0.25` renders at a quarter of the size, fast and at low quality, for looking at timing |
| `inspect FILE` | duration, size, resolution, average bitrate, integrated loudness (LUFS) and true peak of a finished file |
| `looks`, `elements` | the grade looks and the graphics elements there are |
| `demo --out DIR` | synthetic assets and `film.json` |

Python: `from filmkit import load, problems, render, still, inspect` (`load(path)` returns `(spec, base_dir)`; every relative path in a spec is read from `base_dir`).

## The film spec, `filmkit.film/1`

Times are seconds, coordinates and sizes are pixels of the spec's own canvas (the design size; a preview renders smaller and everything scales), the order of `overlays` is their stacking
order. The schema is additive: a new key may appear in `/1`, a changed meaning is `/2`, and a spec that names a schema filmkit does not know is refused.

```json
{"schema": "filmkit.film/1", "id": "sample-a", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 44.0, "bpm": 90,
 "assets": {"clip1": {"type": "video", "path": "raw/clip1.mp4"}, "logo": {"type": "image", "path": "logo.png"}},
 "fonts": {"black": "fonts/Black.otf", "bold": "...", "med": "...", "reg": "..."},
 "shots": [{"id": "s1", "asset": "clip1", "start": 0, "end": 4, "in": 8.0, "speed": 1.0, "fit": "fill",
            "camera": {"zoom": [1.3, 1.0], "center": [[0.4, 0.66], [0.5, 0.5]]}, "dim": [0, 0], "blur": 0,
            "transition": {"type": "dissolve", "dur": 0.4}}],
 "grade": {"look": "teal_warm_soft", "over": {"grain": 4}},
 "overlays": [{"element": "title", "t0": 0.4, "t1": 4.6, "lines": ["A TITLE", "THAT RISES."], "x": 64, "y": 330, "size": 124}],
 "scrim": {"top": 0.30, "bottom": 0.60, "top_alpha": 100, "bottom_alpha": 165},
 "fade_out": {"t": 43.2, "dur": 0.8},
 "audio": {"voice": [{"t": 0.55, "file": "vo_0.wav", "gain": 1.0}],
           "music": {"bpm": 90, "pluck_from": 9.3, "impacts": [0.0, 9.333], "risers": [[7.0, 9.333]], "whooshes": [3.62], "pings": [24.6]},
           "duck_db": -7, "lufs": -16, "fade_out": 1.4},
 "encode": {"bitrate": "10M", "minrate": "8500k", "maxrate": "12M", "bufsize": "24M"},
 "safe": {"profile": "tiktok"}}
```

**Shots.** A shot owns `[start, end]`; shots must touch (no gap, no overlap) and the last one ends at `duration`. A video shot reads from `in` seconds into its file at `speed`; an image is
a still. `fit: "fill"` crops the picture to the canvas (the camera chooses where); `fit: "card"` sets a landscape photo on a darkened, blurred copy of itself with a shadow (`card:
{width, y}`), which is how a group photo sits in a portrait film. The **camera** is a zoom and a centre that ease from the first value to the second over the shot (`center` is the
crop's centre as a fraction of the picture). `dim` and `blur` darken or soften a shot under type. A **transition** is *into* the shot it sits on (so not on the first), centred on the cut,
`cut`, `dissolve`, `flash`, `push`, `dip` or `wipe`, no longer than half either shot. A phone clip stored sideways plays upright.

**Grade.** A look is a handful of numbers made into a 3D LUT (`looks` lists them; `over` changes any number), plus a vignette and fine grain, and is applied to the *footage* only: the
type and the logo on top stay the pure colour they were drawn in. `natural` leaves colour alone; `teal_warm_soft` is the first sample's look (the haze off the blacks, shadows leaning teal,
highlights warm, a little more colour).

**Overlays** are elements (below), each `{element, t0, t1, ...}`. Times inside an element are seconds after its `t0`, so moving an element in time moves all of it. The **scrim** is a soft
dark gradient at the top and the bottom under the type; `"scrim": false` for none.

**Audio.** `voice` lines are files placed at a time (mono or stereo; the first channel is used). The music is synthesised from `bpm`: a bed (a slow chord loop, plucks from `pluck_from`),
`impacts` on cuts, `risers` building into a big cut (`[from, to]`), `whooshes` on moves, `pings` on items appearing; `music: {"bed": false}` keeps only the effects. The bed ducks `duck_db`
under speech. The whole is brought to `lufs`, **measured on the stereo file that is delivered** (one mono signal on two channels reads 3 LU louder than on one), with a limiter set so that the delivered file's true peak is about -1 dBTP
even after the AAC encode; the report says what it landed on (`mix_lufs`). A film with no sound at all stays silent.

**Encode.** `bitrate`/`minrate`/`maxrate`/`bufsize` for a client that fixes a floor, or `{"crf": 18}`; H.264, yuv420p, AAC 192k, 44.1 kHz.

## Elements

`filmkit elements` lists them; the parameters are in the element's own class in `filmkit/elements.py`.

| element | what | main params |
|---|---|---|
| `title` | lines of type that rise and fade in one after another, optionally out again | `lines`, `x`, `y`, `size`, `font` (black/bold/med/reg), `fill`, `anchor` (l/m/r), `tracking`, `stagger`, `out` |
| `text` | one tracked line that fades in (a tagline, a label) | `text`, `x`, `y`, `size`, `tracking`, `anchor`, `alpha` |
| `chip` | a rounded label with a pulsing dot | `text`, `x`, `y`, `dot`, `accent` |
| `brackets` | four corner brackets growing out from the centre of a box | `box` `[x0, y0, x1, y1]`, `out`, `arm`, `width`, `color` |
| `scan` | a sweeping line with a trail and a measuring rule on the edge of a box | `box`, `period`, `color` |
| `counter` | a number counting up to `target`, then a suffix that pops | `target`, `suffix`, `size`, `suffix_size`, `hold`, `x`, `y` |
| `steps` | a vertical rail with numbered items appearing in turn, the whole leaving at `out` | `items` `[[number, title]...]`, `x`, `top`, `step`, `gap`, `first`, `out` |
| `rule` | a line that grows from its centre (or `grow: "left"`) | `x0`, `x1`, `y`, `thickness`, `dur`, `color` |
| `logo` | the brand mark faded in and out | `asset`, `x`, `y`, `width`, `opacity`, `fade_in`, `fade_out`, `rise`, `align` |

A new element is one class with `check(params)`, `draw(layer, t, params, ctx, element)` and `boxes(t, params, ctx, element)`, registered with `@element("name")`; `boxes` is what lets the
layout check see its type.

## The checks (`check`, run before a render)

- **Layout.** Each element reports where its type sits at each moment; `check` samples the film and names a line that leaves the **safe area** (`safe.profile`: `tiktok` 60/250 to 900/1250,
  `reels`, `shorts` 60/250 to 900/1350, `full` the frame less a margin; or `safe.box`) and any two lines that sit on each other at the same moment. The `tiktok` numbers are the stricter
  reading of guides that disagree: confirm them against TikTok's own template before a client's film goes out under them.
- **Timing.** A voice line that overlaps another or runs past the end of the film; a cut more than 80 ms off a beat of `bpm`.
- **Fonts.** A role with no file falls back to Noto Sans CJK from the usual places, then to the face Pillow carries; the report names the roles that fell back, so a film is never made in
  the wrong face without saying so.

## Craft rules the engine encodes (from the first sample)

These are what separates "a template" from "a cut":

1. **Cut on the beat.** Choose a BPM, put every cut on a beat of it (90 BPM: a beat is 0.667 s, a bar 2.667 s), put an `impact` on the cut and let type enter on a beat. The ear feels the
   grid before the eye does; `check` flags a cut that drifts.
2. **No picture ever sits still.** Every shot has a zoom or a drift (1.0 to 1.1 or 1.2 over its length) with easing; the camera is where a phone clip gets its "produced" look.
3. **Type is a layer, not a part of the picture.** Grade the footage, leave the type pure white; put a scrim under it; keep it inside the safe area; reveal it line by line, never all at once.
4. **Transitions mean something.** `flash` on a hit, `push` into a new topic, `dissolve` for the same thought continuing, `dip` to end. One of each is a vocabulary; five `dissolve`s is a slideshow.
5. **The voice is the loudest thing, the bed ducks under it**, the riser tells the ear a big cut is coming, the ping marks each item that appears.
6. **A proof is a number with a source.** A counter on screen is the pack's claim: the pack keeps the source quote beside it (the maker pack's rule, not filmkit's).
7. **End on the ask**: logo, one line of what the company does, one line of what the viewer should do, all inside the safe area.

## Limits

- Tested on vertical 1080x1920; other canvases are valid specs but their safe-area profiles are the caller's to give (`safe.box`).
- The grade is a look, not a colourist: it will not rescue badly exposed footage.
- The synthesised music is a bed and effects for a promotional film, not a composition; a pack that wants a licensed track mixes it in with `voice` entries (a file at a time) and sets `music.bed` to false.
- Rendering is single-process Python: a 44-second 1080x1920 film is minutes on a laptop, longer on a small server; `--preview` is for looking, a render is for sending.
