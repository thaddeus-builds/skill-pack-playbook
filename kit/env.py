"""The single .env lookup chain: process env -> optional HOME file ->
`<DATA_DIR>/.env`.

  * Process env always wins; among files, later sources override earlier.
  * `<P>_AUTH_ENV_PATHS` (comma-separated paths) replaces the file chain;
    `none`, or set but empty, turns it off: process env only. That is the
    cloud / multi-client setting: a HOME-level file otherwise fills every
    var a process leaves unset, including another client's data dir and
    keys.
  * The cwd is never part of the chain: agent shells change directory, so
    a `./.env` would be whatever directory happened to be current
    (including a harness checkout); that is how live credentials once
    leaked into a test. `<DATA_DIR>/.env` joins the chain only when the
    data dir is already set in the process env, and any relative entry
    (a relative data dir, override path or home file) is dropped, since
    it would resolve against the cwd.
  * Files are parsed, never sourced: values may hold `|` and `$` (refresh
    tokens do). KEY=VALUE per line; `#` comments and blank lines skipped;
    a leading `export ` is dropped (a shell-style file means the same
    thing); a value in matching single or double quotes is unquoted; a
    missing or unreadable file is skipped silently.
  * Some names are never taken from a file (`never_from_file()`), only
    from the process env: a gate secret (`is_gate_secret()`: any
    `*CONFIRM_CODE_SECRET`, kit.human's relayed-code key, and the owner
    console's `CONSOLE_SECRET`), since an agent can write or read a .env
    and with the secret could make its own approval codes; kit.human's
    test seam `KIT_TTY` and the `PYTEST_CURRENT_TEST` marker (a file
    standing in for the terminal would pass a piped agent off as a person
    retyping); `KIT_HARNESS_ROOT` (which harness, and so which gate, the
    kit binds); `DYLD_*`, `LD_*` and `PYTHON*` (what code a child loads);
    and the harness's own `[env].never_from_file` names. Such a line is
    skipped by every read below, never loaded; `refused()` names it (file
    and name, never the value) for doctor. Seen in the video-ads harness,
    whose agent could otherwise have confirmed through its own .env.
  * `load_into_environ()` copies the chain into os.environ once, at the
    entry point, without overriding anything, and remembers where each
    copied value came from, so doctor and every forwarded script agree on
    one value and doctor can name its source.

`chain()` is the configured singleton (`<P>_AUTH_ENV_PATHS`,
`<P>_DATA_DIR`, `[harness].home_env_file`, `[env].default_prefixes`,
`[env].never_from_file`).

Test: kit/tests/test_env.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from kit import config as _config
from kit.contract import HarnessError
from kit.human import TTY_ENV
from kit.messages import msg

ENV_ONLY = "none"      # <P>_AUTH_ENV_PATHS value that disables the file chain
PROCESS = "process env"
CONSOLE_SECRET = "CONSOLE_SECRET"          # the owner console's own secret
NEVER_FROM_FILE = (TTY_ENV, "PYTEST_CURRENT_TEST", _config.ROOT_ENV)
NEVER_FROM_FILE_PREFIXES = ("DYLD_", "LD_", "PYTHON")


def is_gate_secret(name: str) -> bool:
    """A variable that signs or checks a person's approval: any harness's
    `<P>_CONFIRM_CODE_SECRET` (kit.human) or the console's CONSOLE_SECRET."""
    return name == CONSOLE_SECRET or name.endswith("CONFIRM_CODE_SECRET")


def never_from_file(name: str, extra: tuple[str, ...] = ()) -> bool:
    """A variable no env file may set: a gate secret, the gate's test seam
    or a test marker, the bound harness, a loader or interpreter variable,
    or one of `extra` (the harness's `[env].never_from_file`)."""
    return (is_gate_secret(name) or name in NEVER_FROM_FILE or name in extra
            or name.startswith(NEVER_FROM_FILE_PREFIXES))


class EnvError(HarnessError):
    """A required variable is set nowhere in the chain."""


def parse(path: str | os.PathLike) -> dict[str, str]:
    """KEY=VALUE pairs of one env file ({} when missing or unreadable)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    vals: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k.startswith("export "):
            k = k[len("export "):].strip()
        if len(v) >= 2 and v[0] in "'\"" and v[-1] == v[0]:
            v = v[1:-1]
        if k:
            vals[k] = v
    return vals


class EnvChain:
    def __init__(self, *, paths_var: str, data_dir_var: str,
                 home_file: str | None,
                 default_prefixes: dict[str, str] | None = None,
                 never: tuple[str, ...] | list[str] = ()):
        self.paths_var = paths_var
        self.data_dir_var = data_dir_var
        self.home_file = home_file or None
        self.default_prefixes = dict(default_prefixes or {})
        self.never = tuple(never)            # the harness's own never-from-file names
        self.read: list[str] = []            # the chain load_into_environ read
        self.loaded: dict[str, str] = {}     # name -> file it was copied from

    def default_paths(self) -> list[str]:
        """The chain's files in priority order (later wins). `~` expands;
        a relative entry is dropped: it would be read against the cwd."""
        override = os.environ.get(self.paths_var)
        if override is not None:
            if override.strip().lower() in ("", ENV_ONLY):
                return []
            out = [p.strip() for p in override.split(",") if p.strip()]
        else:
            out = [self.home_file] if self.home_file else []
            data_dir = os.environ.get(self.data_dir_var, "").strip()
            if data_dir:
                out.append(os.path.join(os.path.expanduser(data_dir), ".env"))
        return [p for p in (os.path.expanduser(x) for x in out)
                if os.path.isabs(p)]

    def load_with_sources(self, paths: list[str] | None = None
                          ) -> dict[str, tuple[str, str]]:
        """{KEY: (value, file it came from)} over the chain (later wins)."""
        merged: dict[str, tuple[str, str]] = {}
        for p in self.default_paths() if paths is None else paths:
            merged.update({k: (v, p) for k, v in parse(p).items()
                           if not never_from_file(k, self.never)})
        return merged

    def refused(self, paths: list[str] | None = None
                ) -> list[tuple[str, str]]:
        """(file, name) of every line a chain file sets that is never
        loaded (never_from_file); names only, never a value."""
        return [(p, k) for p in (self.default_paths() if paths is None
                                 else paths)
                for k in parse(p) if never_from_file(k, self.never)]

    def load(self, paths: list[str] | None = None) -> dict[str, str]:
        """The merged files only (process env NOT included)."""
        return {k: v for k, (v, _) in self.load_with_sources(paths).items()}

    def resolve(self, name: str, *, paths: list[str] | None = None
                ) -> tuple[str | None, str | None]:
        """(value, source): source is "process env", the file, or None."""
        if name in os.environ:
            return os.environ[name], PROCESS
        return self.load_with_sources(paths).get(name, (None, None))

    def get(self, name: str, default: str | None = None, *,
            paths: list[str] | None = None) -> str | None:
        value, _ = self.resolve(name, paths=paths)
        return default if value is None else value

    def require(self, name: str, *, paths: list[str] | None = None) -> str:
        """The value, or EnvError naming the files actually searched."""
        val = self.get(name, paths=paths)
        if val:
            return val
        searched = ", ".join(self.default_paths() if paths is None
                             else paths) or "(no env files: process env only)"
        raise EnvError(
            msg("env_required",
                f"{name} is required — set it in the process environment or "
                f"in one of the env files searched: {searched}",
                name=name, searched=searched),
            [f"{_config.config().cli} doctor"])

    def credential_prefix(self, var: str, *,
                          paths: list[str] | None = None) -> str:
        """The credential-name prefix `var` selects: its value when set, else
        its fixed default (default_prefixes); a var with no default is
        required."""
        val = self.get(var, paths=paths)
        if val:
            return val
        if var in self.default_prefixes:
            return self.default_prefixes[var]
        return self.require(var, paths=paths)

    def load_into_environ(self) -> dict[str, str]:
        """Copy every chain value the process env lacks into os.environ
        (process env wins); returns {name: file} for what was copied."""
        self.read = self.default_paths()
        added = {k: vs for k, vs in self.load_with_sources(self.read).items()
                 if k not in os.environ}
        os.environ.update({k: v for k, (v, _) in added.items()})
        self.loaded = {k: src for k, (_, src) in added.items()}
        return dict(self.loaded)

    def source(self, name: str) -> tuple[str | None, str | None]:
        """(value, source) as doctor shows it: the file load_into_environ
        took it from, else resolve()."""
        if name in self.loaded and name in os.environ:
            return os.environ[name], self.loaded[name]
        return self.resolve(name)


_chain: EnvChain | None = None


def chain() -> EnvChain:
    """The EnvChain the bound harness declares (cached until config.use)."""
    global _chain
    if _chain is None:
        cfg = _config.config()
        table = cfg.raw.get("env", {})
        never = table.get("never_from_file", [])
        if not (isinstance(never, list)
                and all(isinstance(n, str) and n for n in never)):
            raise _config.ConfigError(
                f"{cfg.root / _config.FILE}: [env].never_from_file must be a "
                f"list of variable names, got {never!r}")
        _chain = EnvChain(paths_var=cfg.env("AUTH_ENV_PATHS"),
                          data_dir_var=cfg.env("DATA_DIR"),
                          home_file=cfg.home_env_file or None,
                          default_prefixes=table.get("default_prefixes", {}),
                          never=never)
    return _chain


@_config.on_reset
def _clear() -> None:
    global _chain
    _chain = None
