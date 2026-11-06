# filmkit

A film spec in, a finished film out. filmkit is the engine under a maker pack: the pack decides **what the film says** (the story, the facts, who may appear, which platform) and writes
that down as one JSON document, the *film spec*; filmkit decides **how it is made** (camera moves, cuts, a grade, animated type, sound, a loudness target) and checks it before it renders.
The spec is the only thing the two share, so either side can change without the other noticing.

```
maker pack (story, facts, people, channel)  ->  film spec  ->  filmkit (validate, check, still, render, inspect)  ->  film.mp4
```

What filmkit is **not**: it makes no picture from nothing (the footage and photos are the caller's), makes no matte (the cutout below needs one, made by whatever segmented the footage: see "The matte seam"), makes no voice (a voice line is a file the caller brings, made by whichever provider the
pack chose), judges no claim (a number on screen is the pack's to source), and decides no platform's rules (it ships profiles for where type may sit, nothing else). Nothing third-party is
inside a film it makes: the music and effects are synthesised here, the fonts are the caller's.

Needs: Python 3.10+, numpy, Pillow, scipy, and `ffmpeg` + `ffprobe` on the PATH. `python3 -m filmkit demo --out DIR` makes synthetic clips and a spec that uses everything; start there.

## The verbs

Every verb prints one JSON document and nothing else on stdout (progress goes to stderr). Exit 0 is success; 1 is a problem (`validate`: the list; `check`: `ok: false`; anything that failed: `{"error": ...}`, never a traceback); 2 is a command line that does not parse (also JSON); 130 is an interrupt or a SIGTERM, after the render's work folder and ffmpeg children are cleaned up.

| verb | does |
|---|---|
| `validate SPEC` | everything wrong with the spec, each as `where: what`: every number is checked for type and range (no NaN, no bool, no string where a number goes), every file for being what it is called (a video asset has a video stream, an image opens, a shot's `in` is inside its clip); `ok: true` when it can be rendered, and nothing `validate` passes crashes a later verb |
| `check SPEC` | the layout and timing checks below, on the spec alone, in about a second |
| `still SPEC --at T --out PNG [--scale S]` | one frame of the finished film (footage with the grade, graphics, scrim): the way to look before rendering. Counts source frames like a render and holds a clip's last frame when a shot outlasts it, so it is the frame a render would show; `--at` outside the film is an error |
| `render SPEC --out MP4 [--preview F] [--workdir DIR]` | the film; `--preview 0.25` renders at a quarter of the size, fast and at low quality, for looking at timing. It refuses an `--out` that is a file the film reads (a clip, a font, a voice line, the spec) or in a folder that is not there, makes the sound and draws every overlay once before the first frame (a mistake costs seconds), and reads every ffmpeg child's exit status |
| `inspect FILE` | duration, size, resolution, colour tags (`color_space`, `color_range`), average and per-stream bitrate (`video_kbps`, `audio_kbps`, from the packets), integrated loudness (LUFS) and true peak of a finished file |
| `looks`, `elements` | the grade looks and the graphics elements there are |
| `demo --out DIR` | synthetic assets and `film.json` |

Python: `from filmkit import load, problems, render, still, inspect` (`load(path)` returns `(spec, base_dir)` with `base_dir` absolute; every relative path in a spec is read from it; a file that is not a JSON object, or holds `NaN` or `Infinity`, is a `FilmkitError`). `problems` never raises: a shape it does not foresee is a line.

## The film spec, `filmkit.film/1`

Times are seconds, coordinates and sizes are pixels of the spec's own canvas (the design size; a preview renders smaller and everything scales), the order of `overlays` is their stacking
order. The schema is additive: a new key may appear in `/1`, a changed meaning is `/2`, and a spec that names a schema filmkit does not know is refused.

```json
{"schema": "filmkit.film/1", "id": "sample-a", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 44.0, "bpm": 90,
 "assets": {"clip1": {"type": "video", "path": "raw/clip1.mp4"}, "logo": {"type": "image", "path": "logo.png"}},
 "fonts": {"black": "fonts/Black.otf", "bold": "...", "med": "...", "reg": "...", "serif": "fonts/Serif-Bold.otf"},
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
`cut` (no `dur`), `dissolve`, `flash`, `push`, `dip`, `wipe` or `ghost` (a `dur` from 0.02 to 3 s, no longer than half either shot; a `ghost` is a quick whip, an echo smeared along x that is widest at the middle, and is refused over 0.5 s: 0.15 to 0.3 reads best). A phone clip stored sideways plays upright and one with a non-square pixel is stretched to the shape it is shown in. A shot that outlasts its clip holds the clip's last frame; a clip that is HDR (HLG or PQ) is not tone-mapped, and `render` says so under `notes`. `fit: "card"` ignores `dim`, `blur` and the camera's centre (the zoom applies). `fps` is a whole number (29.97 is 30 here).

**Story-film shot features** (all additive in `/1`; a synthetic example of each is `story.json` of `filmkit demo`):

- `fit: "panel"` with `panel: {bg, title, frame, y, height, caption, ...}`: a solid colour (`bg`, default blue; `bg2` makes it a vertical gradient down to that colour), a `title` (one to three lines) on the upper part, the picture in the middle inside a
  `frame` ({`width`, `color`}, default 10 px white) at `y` (its top) and `height`, pushing in slowly (the shot's `camera` zoom, 1.0 to 1.08 when it has none; the frame stays), and a `caption`
  under the frame. Also `margin` (room each side), `title_size`, `title_y`, `title_fill`, `title_font`, `caption_size`, `caption_font`. The title and the caption are type: they are drawn as
  `title` and `text` overlays that last as long as the shot (so they are in `check`'s layout and glyph checks), the title shrinks to stay above the frame, and `check` names type that
  lands on the frame. `fit: "card"` is a photo on a blurred copy of itself; a panel is a different look.
- `fit: "split"` with `split: {bottom: {asset, in, speed, camera}, at, seam}`: two clips stacked, the shot's own `asset`, `in`, `speed` and `camera` the top half, `bottom` the other (each
  decoded and cropped on its own, to the half it fills); `at` (0.2 to 0.8, default 0.5) is where the join is from the top; `seam: {color, width}` draws a line there.
- `cutout: {matte, outline, bg}` on a `fit: "fill"` shot: the presenter cutout. `matte` is an asset id (below); `bg: {zoom, blur, tint, tint_mix, posterize}` makes the backdrop from the same
  frame (the camera's view enlarged by `zoom`, default 1.8, blurred `blur` px, mixed `tint_mix` of the way to the colour `tint`, reduced to `posterize` levels a channel: flat, soft, tinted); the
  subject (where the matte is white) stays sharp on top; `outline: {color, width, dash: [on, off], speed, offset}` draws dashes along the matte's edge (px; `speed` is px a second along it, negative
  runs the other way, `offset` moves the line out from the edge) and `outline: false` leaves it out. The camera moves the picture and the matte together. About 0.3 s a 1080x1920 frame.

**The matte seam.** filmkit makes no matte: it does no segmentation, and a matte is an input, made by the maker pack (or whatever tool it uses). A matte is a grayscale video (asset
`type: "video"`), a numbered picture sequence (`type: "frames"`, `path` a pattern such as `matte/m_%04d.png`, numbered from 0 or 1, `fps` its rate, default 30) or one picture (`type: "image"`, held
for the whole shot), white where the subject is. It must be **as big as the shot's clip and have its frames**: it is read with the shot's own `in` and `speed`, so frame k of the clip is frame k of
the matte, and `validate` names a matte of another size or a shorter one. The edge is thresholded at half grey; pieces smaller than 0.2 percent of the picture are noise and get no outline.

**Grade.** A look is a handful of numbers made into a 3D LUT (`looks` lists them; `over` changes any number), plus a vignette and fine grain, and is applied to the *footage* only: the
type and the logo on top stay the pure colour they were drawn in. `natural` leaves colour alone; `teal_warm_soft` is the first sample's look (the haze off the blacks, shadows leaning teal,
highlights warm, a little more colour).

**Overlays** are elements (below), each `{element, t0, t1, ...}`. Times inside an element are seconds after its `t0`, so moving an element in time moves all of it. The **scrim** is a soft
dark gradient at the top and the bottom under the type; `"scrim": false` for none.

**Audio.** `voice` lines are files placed at a time (mono or stereo; a stereo file is the mean of its first two channels, so a voice on one channel is heard). Each line is brought to one level before its `gain` (RMS of the part that speaks), so a quiet file neither sits under the bed nor fails to duck it, and a silent file is an error. The music is synthesised from `bpm` (the film's own, unless `music.bpm` names another): a bed (a slow chord loop, plucks from `pluck_from`),
`impacts` on cuts, `risers` building into a big cut (`[from, to]`), `whooshes` on moves, `pings` on items appearing; `music: {"bed": false}` keeps only the effects. The bed ducks `duck_db`
under speech. The whole is brought to `lufs`, **measured on the stereo file that is delivered** (one mono signal on two channels reads 3 LU louder than on one), with a limiter set so that the delivered file's true peak is about -1 dBTP
even after the AAC encode; the report says what it landed on (`mix_lufs`) and whether that is within 1 LU of the target (`lufs_met`: a film under 0.4 s cannot be measured, and a target above what the limiter can reach lands lower). A film with no sound at all stays silent.

**Encode.** `bitrate`/`minrate`/`maxrate`/`bufsize` for a client that fixes a floor, or `{"crf": 18}`; H.264 as BT.709 limited-range yuv420p (converted with the 709 matrix and tagged `colorspace/primaries/trc bt709`, `range tv`: a player that takes untagged HD as 709 shows the colour that was graded), AAC 192k, 44.1 kHz. Bitrates are strings like `10M`, `8500k` or `9000000`. A floor is checked, not hoped for: x264 spends less than its target on an easy picture (a short, still, dark film), so `render` measures the video stream's own bitrate (its packets, not the container) and, when it is under `minrate`, encodes again with a higher target (twice at most, never above `maxrate`); the report says `video_kbps`, `floor_kbps` and `floor_met`.

## Elements

`filmkit elements` lists them; the parameters are in the element's own class in `filmkit/elements.py`.

| element | what | main params |
|---|---|---|
| `title` | lines of type that rise and fade in one after another, optionally out again | `lines`, `x`, `y`, `size`, `font` (black/bold/med/reg), `fill`, `anchor` (l/m/r), `tracking`, `stagger`, `out`, `max_width`, `max_height` (the size shrinks until the widest line fits the width and the lines fit the height, never below 60 percent; the layout check sees the size used); `typewriter` (characters a second: each line types in after the one before, the layout check uses the whole line), `tracking_in` (letter spacing eases from this wide value to `tracking` over `tracking_dur` while the line fades in; the size is fitted for the widest) |
| `text` | one tracked line that fades in (a tagline, a label) | `text`, `x`, `y`, `size`, `tracking`, `anchor`, `alpha`, `max_width` (shrinks to fit), `typewriter` (characters a second; the box the layout check sees is the whole text's), `stroke` (`{width, color, alpha}`: an outline round the letters, for words over a bright picture) |
| `chip` | a rounded label with a pulsing dot | `text`, `x`, `y`, `dot`, `accent`, `max_width` (the whole chip: the text shrinks to fit) |
| `brackets` | four corner brackets growing out from the centre of a box | `box` `[x0, y0, x1, y1]`, `out`, `arm`, `width`, `color` |
| `scan` | a sweeping line with a trail and a measuring rule on the edge of a box | `box`, `period`, `color` |
| `counter` | a number counting up to `target`, then a suffix that pops | `target`, `suffix`, `size`, `suffix_size`, `hold`, `x`, `y`, `max_width` (the number and its suffix scale down together to fit, never below half) |
| `steps` | a vertical rail with numbered items appearing in turn, the whole leaving at `out` | `items` `[[number, title]...]`, `x`, `top`, `step`, `gap`, `first`, `out`, `name_size` (default 66, 54 for a long title), `max_width` (each title shrinks to fit the room right of its number) |
| `rule` | a line that grows from its centre (or `grow: "left"`) | `x0`, `x1`, `y`, `thickness`, `dur`, `color` |
| `kinetic` | one big word in the `serif` face that sweeps in from an edge (`dir`: left, right, top, bottom; `sweep` 0.4 s, with an echo and a lean), rests big at `at` ({x, y}, the middle of the word) for `hold`, then in `settle` seconds shrinks and moves to `to` ({x, y, size}, `anchor` l/m/r) and stays as a line | `text`, `to`, `at`, `size` (the big size), `dir`, `fill` (cream), `shadow`, `sweep`, `hold`, `settle`, `tracking`, `max_width` (both sizes shrink to fit) |
| `year` | a big serif number or phrase that rises into place with a soft shadow, optionally held and faded out | `text`, `x`, `y`, `anchor`, `size`, `fill` (cream), `shadow`, `rise`, `dur`, `hold` (then fades over `out_dur`), `tracking`, `max_width` |
| `logo` | the brand mark faded in and out | `asset`, `x`, `y`, `width`, `max_height` (a square mark gets narrower so it is no taller), `opacity`, `fade_in`, `fade_out`, `rise`, `align`; the layout check sees its box |

A new element is one class with `check(params)`, `draw(layer, t, params, ctx, element)`, `boxes(t, params, ctx, element)` and, for type, `texts(params)` (the (font role, text) pairs it sets, for the glyph check), registered with `@element("name")`; `boxes` is what lets the
layout check see it. A box whose name starts with `~` is a decoration (rule, brackets, scan line): it has to be on the canvas and may sit on type.

## The checks (`check`, run before a render)

- **Layout.** Each element reports where its type and logo sit at each moment (a line that has faded out, a steps list that has left, is no longer there); `check` samples the film and names a line that leaves the **safe area** (`safe.profile`: `tiktok` 60/250 to 900/1250,
  `reels`, `shorts` 60/250 to 900/1350, `full` the frame less a margin, scaled with the canvas; or `safe.box`, in the canvas's own pixels, used as given; a profile that is not one of these is a `validate` problem) and any two lines that sit on each other at the same moment. A line's box is its width across and the face's own ink rows down (a descender, a CJK bottom, a counter's digits are inside it); a steps item's number and dot count too. The `tiktok` numbers are the stricter
  reading of guides that disagree: confirm them against TikTok's own template before a client's film goes out under them.
- **Timing.** A voice line that overlaps another or runs past the end of the film; a cut more than 80 ms off a beat of `bpm`.
- **Glyphs.** A character the face a line is set in has no glyph for (a pill emoji, a rare character, Chinese asked of a Latin face) would be drawn as an empty box: `check` names it under `glyphs`, and `ok` is false.
- **Fonts.** A role with no file falls back to Noto Sans CJK (Noto Serif CJK for `serif`) from the usual places, then to the face Pillow carries; the report names the roles that fell back, so a film is never made in
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

8. **One loud move at a time.** A `kinetic` word sweeps in on the beat and settles before the next line arrives; the `year` rises while the picture holds; a `ghost` marks a change of place, so use it
   once or twice, not on every cut.
9. **A cutout needs a clean matte.** The outline follows every flicker of the edge, so a matte that jitters makes the dashes crawl; smooth the matte upstream, not here.

## Limits

- Tested on vertical 1080x1920; other canvases are valid specs but their safe-area profiles are the caller's to give (`safe.box`).
- Type is set one character at a time (tracking), so there is no shaping: combining marks, ligatures, ZWJ emoji and complex scripts (Thai, Arabic, Devanagari) come out wrong; CJK and precomposed Latin are right. The CJK fallback faces are looked for as the split `.otf` files (macOS) and the `.ttc` collections of Debian/Ubuntu `fonts-noto-cjk` (Simplified Chinese is face 2); `fonts-noto-cjk-extra` is needed there for the Black and Medium weights.
- Footage is read with the file and pipe protocols only, and a container that names other files or addresses (`concat`, `hls`, `sdp`...) is refused.
- A `cutout` outlines the outer edge of up to three pieces of the matte (not holes in it); a matte is read at the clip's size, so a clip with a non-square pixel needs one made for its shown shape.
- `duration` is up to 600 s and at least two frames.
- The grade is a look, not a colourist: it will not rescue badly exposed footage.
- The synthesised music is a bed and effects for a promotional film, not a composition; a pack that wants a licensed track mixes it in with `voice` entries (a file at a time) and sets `music.bed` to false.
- Rendering is single-process Python: a 44-second 1080x1920 film is minutes on a laptop, longer on a small server; `--preview` is for looking, a render is for sending.
