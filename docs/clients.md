# Client folders

Every client has one folder, under one root per machine. The layers and the meeting and source rules come from the client hub (docs/consoles.md, "Where a client's folder lives", issue #479; `scaffold/new_hub.py`). This page adds the root's setting, where each kind of material goes, the links a machine needs, and the check that holds all of it: `python3 scaffold/clients.py` (test: `scaffold/tests/test_clients.py`). *Seen once:* the owner's request of 2026-11-05 to keep every client's material in one place, and the first client folder, which a session laid out by hand with its own `relink.sh`.

## The root, per machine

Each machine names its clients root once. `CLIENTS_DIR` in the environment wins; else the one line in `~/.config/openmax/clients_dir`, which `clients.py where --set DIR` writes. A desktop app does not always read the shell profile, so the file is what makes the setting hold everywhere. With neither set, every tool stops and says so: it never guesses from the working directory or a default, so two machines never disagree without anyone knowing. A folder under the root whose name starts with `_` or `.` (`_backups`) is not a client.

## One client's folder

| Layer | What is in it | Who writes it |
| --- | --- | --- |
| `README.md` | the client's card: who, which packs, where things are, what not to touch | a person or the agent, in the owner's language |
| `intake/` | `brief.md`, `decisions.md` (a mirror: the record that counts is the pack's decision rows), `open-questions.md`, and `meetings/<YYYY-MM-DD>/` (a meeting's recording, transcript and notes together) | a person edits it to correct the agent; the agent drafts |
| `sources/` | everything else the client or a platform gave us, kept as received, and `INDEX.tsv`, one row an item (a row for a folder covers what is in it). New material lands in `inbox/<YYYY-MM-DD>-<from>/`; material that came in folders of its own (by kind, or a mirror of the client's cloud drive) stays in them | `clients.py source`, or a pack's own pull |
| `reports/` | what the packs made for people to read | the packs |
| `.machine/` | the hub or workspace (database, console, wrappers), each pack's data, `connections/` (keys and tokens, 0700), `downloads/`, and `links.tsv` | tools only; nobody opens it to recall the client |

`sources/` and `reports/` may be links into `.machine/` when a tool writes there.

A client with material and no pack yet starts with `clients.py new CLIENT --title T --term NAME [--term NAME …]`: the card, the intake files, `sources/` with its index, `reports/`, and `.machine/` (0700) holding `client_terms.txt` with the names given. A pack's workspace or the hub (`new_client.py`, `new_hub.py`) goes under `.machine/` later.

## Where each kind of material goes

| The material | Where | `--from` |
| --- | --- | --- |
| a meeting: recording, transcript, AI notes, the slides shown | `intake/meetings/<date>/`, then what it changed goes into `brief.md`, `decisions.md` and `open-questions.md` | (not in the index) |
| a chat log, a message export | `sources/` | `chat` |
| a link the client sent (a reference video, a competitor's page) | `sources/INDEX.tsv`, one `link` row, the URL as its path | `chat` or `client` |
| a video, a picture or a file the client sent | `sources/` | `client` |
| an export a person took from a platform | `sources/` | `platform` |
| a file an agent pulled through a platform API | `sources/` | `api-agent` |
| an answer to the agent's ask, a digest | `sources/` | `ask`, `digest` |

`clients.py source CLIENT FILE_OR_URL --from F --title T` copies the file into `inbox/<today>-<from>/` (the original is never moved or renamed), writes its row with the next id (`EV-001` up, never reused) and its sha256, and refuses the same bytes twice, naming the earlier id. A file or folder already under `sources/` with no row gets its row in place (never a copy or a move), with `duplicate_of` when the same bytes are listed already. Over 500 MB the sha256 is left empty.

## Links a machine needs

Tools, permission rules and scheduled jobs often hold paths outside the folder (`~/openmax/workspaces/<client>`, a bridge's config). Those paths become links into the folder, listed once in `.machine/links.tsv` (`path`, `target`, `note`; the target is a path inside the folder). `clients.py relink CLIENT` makes them on this machine: a link that leads to its target stays (however it is written), a wrong link is replaced, a real file or folder in the way is reported and never touched, and a link inside the client folder is written relative, so the folder still works after it moves. After copying a client to another machine, set the root and run `relink`. Copy a folder with keys in it only machine to machine or on an encrypted disk, never through a cloud drive or a chat.

## The check

`clients.py check [CLIENT…]` names each problem on one line and exits 1 on any:

- the card and the three intake files are missing;
- `INDEX.tsv` has another header, an id twice, or a source outside the list above;
- a row's file is missing, or a file under `sources/` has no row of its own or of a folder above it;
- a `.env` or a `connections` folder outside `.machine/`;
- `.machine/connections` readable by others;
- a `links.tsv` target outside the folder or missing;
- no `client_terms.txt` under `.machine/`.

Names, amounts and ids of a client stay in its folder, never in a code repository. Each client's `.machine/` holds a `client_terms.txt` (its names, one a line), and the playbook's pre-push hook runs the leak guard (`kit/tools/leak_guard.py`) over every list under this machine's root before the suites: a push that adds a listed name is refused. Install the hook once per clone (`git config core.hooksPath .githooks`). *Seen once:* a client's name written into this page and the tool's docstring on 2026-11-05, in a clone with no hook installed.
