# Who should use filmkit

filmkit turns one JSON film spec (footage, pictures, text, sound) into a finished film with ffmpeg. It is for a skill pack that has to **compose** a video from parts it already has. It is
not a model, it makes no shots and no voice, and it decides nothing about what a film says.

| Skill pack | Use it? | Why |
|---|---|---|
| `proofcut` | Yes, today | It builds films from a client's own footage, stills and voice lines, and vendors filmkit for the render. |
| `adcut` | Not now | It has its own ffmpeg-based render code and its own tests for it. Moving it is the adcut pack's decision, to be made when there is a reason; nothing here asks for it. |
| `product-image-to-video` | Not now | It produces keyframes only. If it later has to cut keyframes and clips into a finished film (type, a grade, sound, a loudness target), start from filmkit rather than another renderer. |
| Any other pack | Only if it composes video | A pack that reports, plans or writes copy has no use for it. |

## What using it costs

- numpy, Pillow, scipy and `ffmpeg`/`ffprobe` on the machine. That is why filmkit is not in `kit/`: every pack vendors `kit/`, and a pack that makes no films must not carry these.
- It is not stdlib-only, so a pack that holds to the kit's stdlib rule runs it as a program (`python3 -m filmkit`, under `uv` with the dependencies pinned), as proofcut does, and does not
  import it.
- No fonts. A spec names four files (or Noto Sans CJK on the machine is used). Whether a face may go in a client's film is the client's to check; no font file belongs in this repository.

## How a pack takes it

Copy `engines/filmkit/filmkit/` and `engines/filmkit/docs/filmkit.md` into the pack as a plain copy with a manifest and the commit it came from, and never edit the copy: a fix is a
change here, with a version bump in `VERSION`, `pyproject.toml` and `filmkit/__init__.py`, and a line in `CHANGELOG.md`. proofcut's `tools/vendor_filmkit.py` and
`tests/test_filmkit_vendored.py` do exactly this and are the pattern to copy.

## What it will not do

It does not write the story, source a number on screen, clear a person's face or voice, or know a platform's rules beyond the safe-area profile it checks. Those are the calling pack's
(see `docs/filmkit.md`, "Limits").
