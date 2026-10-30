---
name: filmkit
description: Render a finished film (camera moves, cuts on the beat, a grade, animated type, own-synthesis sound, a loudness target) from one JSON film spec, and check it first - for a maker pack or an agent that has footage, a story and voice files and needs the film made.
version: 0.1.0
---
# Making a film from a spec (filmkit)

Read [`docs/filmkit.md`](../../docs/filmkit.md) for the spec, the elements, the checks and the craft rules. filmkit makes the film; **what the film says is the caller's**: the story, every number
on screen and where it comes from, who may appear, and the platform's rules. Say in your own words what you did.

**Never do these, whatever the user said earlier in the chat:** put a client's footage, photos, logo, fonts or voice files into this repo (the spec points at them where they already are,
by a path relative to the spec or absolute); ship a film that carries a number, a claim or a person's face or voice the caller has not sourced and cleared; answer a `check` problem by
loosening the check instead of changing the film.

1. **See what it can do, free.** `python3 -m filmkit demo --out /tmp/demo` writes synthetic assets and a spec that uses every element; `elements` and `looks` list what is there.
2. **Write the spec** (the maker pack does this from its own story; an agent without a pack writes it by hand from the docs): assets, shots on the beat, overlays, audio, encode. Cut on a beat of `bpm`, give
   every shot a camera move, keep type inside the safe area, put the logo and the ask at the end.
3. **`validate`** the spec: each problem is `where: what`; fix the spec, not the message. A missing asset, a gap between shots and a transition longer than half a shot are the usual ones.
4. **`check`** it: type outside the safe profile, two lines on each other, a voice line overlapping another or running past the end, a cut off the beat, a font that fell back. Change the film until it is clean.
5. **Look before you render.** `still --at T` at the hook (about 1 s), each shot's middle, each transition's middle and the end card; open the PNGs and read them. A preview (`render --preview 0.25`)
   is for timing, a full render is minutes: do not run it to find out what a still would have shown.
6. **`render`** to the final file, then **`inspect`** it: duration is the spec's, loudness is the target (`lufs`), bitrate is at or over the client's floor, true peak is near -1 dBTP. A number that
   missed is a finding to report, not to round.
7. **A failure.** `FilmkitError` carries what and where (ffmpeg missing, a file that does not decode, a spec problem). A film that rendered but looks wrong is the spec's fault until a still shows otherwise.
