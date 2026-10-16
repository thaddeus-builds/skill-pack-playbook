#!/usr/bin/env python3
"""kit.env: the one .env lookup chain.

  * process env wins over every file;
  * <P>_AUTH_ENV_PATHS=none (or set but empty) disables the files; a comma
    list replaces the chain;
  * the cwd is never part of the chain (a ./.env in the cwd is ignored);
  * later files win; missing files are skipped; values are parsed, never
    sourced (quotes stripped, `|` and `$` kept, `export ` dropped);
  * sources are named; require() raises a coded EnvError; credential
    prefixes default; load_into_environ() never overrides and remembers
    where each value came from; chain() follows the bound skill pack;
  * a gate secret, the gate's test seam, a test marker, the binding, a
    loader variable or a skill pack's own listed name in a file is never
    loaded, and refused() names it (an ordinary key still loads).
"""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import config, env  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402


def write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def main() -> int:
    _shop.use()
    data = _shop.data_dir()           # SHOP_DATA_DIR set, AUTH_ENV_PATHS=none
    del os.environ["SHOP_AUTH_ENV_PATHS"]
    tmp = Path(tmp_dir("env-"))
    home = write(tmp / "home.env", "X_HOME=home\nX_BOTH=home\n")
    write(data / ".env", "X_DATA=data\nX_BOTH=data\n")
    ch = env.EnvChain(paths_var="SHOP_AUTH_ENV_PATHS",
                      data_dir_var="SHOP_DATA_DIR", home_file=str(home))

    print("[1] the chain's shape")
    check("home file, then <DATA_DIR>/.env",
          ch.default_paths() == [str(home), str(data / ".env")],
          ch.default_paths())
    check("later file wins on a collision", ch.get("X_BOTH") == "data")
    saved = os.environ.pop("SHOP_DATA_DIR")
    check("no data dir in the process env: home file only",
          ch.default_paths() == [str(home)])
    os.environ["SHOP_DATA_DIR"] = saved
    no_home = env.EnvChain(paths_var="SHOP_AUTH_ENV_PATHS",
                           data_dir_var="SHOP_DATA_DIR", home_file=None)
    check("no home file configured: <DATA_DIR>/.env only",
          no_home.default_paths() == [str(data / ".env")])

    print("\n[2] never the cwd")
    cwd_dir = Path(tmp_dir("cwd-"))
    write(cwd_dir / ".env", "X_CWD=leaked\nX_DATA=cwd\n")
    here = os.getcwd()
    os.chdir(cwd_dir)
    try:
        check("a ./.env in the cwd is not read",
              ch.get("X_CWD") is None and ch.get("X_DATA") == "data")
        check("cwd/.env is not in the chain",
              str(cwd_dir / ".env") not in ch.default_paths()
              and ".env" not in ch.default_paths())
        os.environ["SHOP_DATA_DIR"] = "."
        check("a relative data dir adds no cwd-relative .env",
              ch.default_paths() == [str(home)] and ch.get("X_CWD") is None)
        os.environ["SHOP_DATA_DIR"] = str(data)
        os.environ["SHOP_AUTH_ENV_PATHS"] = f".env,{home}"
        check("a relative override entry is dropped, absolute ones kept",
              ch.default_paths() == [str(home)] and ch.get("X_CWD") is None)
        del os.environ["SHOP_AUTH_ENV_PATHS"]
        rel_home = env.EnvChain(paths_var="SHOP_AUTH_ENV_PATHS",
                                data_dir_var="SHOP_DATA_DIR", home_file=".env")
        check("a relative home file is dropped too",
              rel_home.default_paths() == [str(data / ".env")])
    finally:
        os.chdir(here)
        os.environ["SHOP_DATA_DIR"] = str(data)
    saved_home = os.environ["HOME"]
    os.environ["HOME"] = str(tmp)
    os.environ["SHOP_AUTH_ENV_PATHS"] = "~/home.env"
    check("~ expands in an override entry", ch.default_paths() == [str(home)])
    del os.environ["SHOP_AUTH_ENV_PATHS"]
    os.environ["HOME"] = saved_home

    print("\n[3] process env wins")
    os.environ["X_BOTH"] = "process"
    check("process env beats every file", ch.get("X_BOTH") == "process"
          and ch.resolve("X_BOTH") == ("process", env.PROCESS))
    del os.environ["X_BOTH"]

    print("\n[4] <P>_AUTH_ENV_PATHS")
    custom = write(tmp / "custom.env", "X_CUSTOM=1\n")
    os.environ["SHOP_AUTH_ENV_PATHS"] = f"{custom}, {tmp / 'absent.env'}"
    check("a comma list replaces the chain",
          ch.default_paths() == [str(custom), str(tmp / "absent.env")]
          and ch.get("X_CUSTOM") == "1" and ch.get("X_HOME") is None)
    for val in ("none", "NONE", "", "  "):
        os.environ["SHOP_AUTH_ENV_PATHS"] = val
        check(f"SHOP_AUTH_ENV_PATHS={val!r}: process env only",
              ch.default_paths() == [] and ch.get("X_HOME") is None
              and ch.get("X_DATA") is None)
    del os.environ["SHOP_AUTH_ENV_PATHS"]

    print("\n[5] parsing, never sourcing")
    q = write(tmp / "q.env", "# a comment\n\nQ1='single quoted'\n"
              'Q2="double quoted"\nQ3=plain|with|pipes\nQ4=$HOME/x\n'
              "Q5=' mixed \" quotes '\nexport Q6=exported\nnot a pair\n"
              " Q7 = spaced \nQ8=a=b\n")
    got = ch.load([str(q)])
    check("quotes stripped", got["Q1"] == "single quoted"
          and got["Q2"] == "double quoted" and got["Q5"] == ' mixed " quotes ')
    check("| and $ kept verbatim", got["Q3"] == "plain|with|pipes"
          and got["Q4"] == "$HOME/x")
    check("`export ` dropped, keys/values trimmed, first = splits",
          got["Q6"] == "exported" and got["Q7"] == "spaced"
          and got["Q8"] == "a=b")
    check("comments, blanks and lines without = skipped",
          set(got) == {f"Q{i}" for i in range(1, 9)}, sorted(got))
    check("a missing file is skipped silently",
          ch.load([str(tmp / "absent.env")]) == {})

    print("\n[6] sources, require, prefixes")
    check("load_with_sources names each file",
          ch.load_with_sources()["X_HOME"] == ("home", str(home))
          and ch.load_with_sources()["X_BOTH"] == ("data", str(data / ".env")))
    check("resolve: file value -> its path; unset -> (None, None)",
          ch.resolve("X_HOME") == ("home", str(home))
          and ch.resolve("X_ABSENT_ANYWHERE") == (None, None))
    e = raises(lambda: ch.require("X_ABSENT_ANYWHERE"), env.EnvError)
    check("require: a coded EnvError (a SkillPackError) naming what was searched",
          isinstance(e, SkillPackError) and e.message.code == "env_required"
          and e.message.params["name"] == "X_ABSENT_ANYWHERE"
          and str(home) in e.message.params["searched"]
          and e.next == ["shop doctor"], e)
    pre = env.EnvChain(paths_var="SHOP_AUTH_ENV_PATHS",
                       data_dir_var="SHOP_DATA_DIR", home_file=None,
                       default_prefixes={"SHOP_API_PREFIX": "API"})
    os.environ["SHOP_AUTH_ENV_PATHS"] = "none"
    check("credential_prefix: the fixed default when unset",
          pre.credential_prefix("SHOP_API_PREFIX") == "API")
    os.environ["SHOP_API_PREFIX"] = "ACME_API"
    check("… an explicit value wins",
          pre.credential_prefix("SHOP_API_PREFIX") == "ACME_API")
    del os.environ["SHOP_API_PREFIX"]
    check("… a var with no default is required",
          raises(lambda: pre.credential_prefix("SHOP_OTHER_PREFIX"),
                 env.EnvError) is not None)
    del os.environ["SHOP_AUTH_ENV_PATHS"]

    print("\n[7] load_into_environ(): once, never overriding")
    os.environ["X_BOTH"] = "process"
    added = ch.load_into_environ()
    check("copies what the process env lacks, returns name -> file",
          added.get("X_HOME") == str(home) and os.environ["X_HOME"] == "home"
          and os.environ["X_DATA"] == "data")
    check("never overrides the process env",
          os.environ["X_BOTH"] == "process" and "X_BOTH" not in added)
    check("source(): the file a copied value came from, else process env",
          ch.source("X_HOME") == ("home", str(home))
          and ch.source("X_BOTH") == ("process", env.PROCESS))
    for k in ("X_BOTH", "X_HOME", "X_DATA"):
        os.environ.pop(k, None)

    print("\n[8] chain() follows the bound skill pack")
    c = env.chain()
    check("chain() uses SHOP_AUTH_ENV_PATHS / SHOP_DATA_DIR, no HOME file",
          c.paths_var == "SHOP_AUTH_ENV_PATHS"
          and c.data_dir_var == "SHOP_DATA_DIR" and c.home_file is None
          and c.default_paths() == [str(data / ".env")])
    check("chain() is cached", env.chain() is c)
    other = Path(tmp_dir("h-"))
    write(other / "skill-pack.toml", '[skill_pack]\nname = "o"\ncli = "o"\n'
          'env_prefix = "OTHER"\nhome_env_file = "~/.other.env"\n'
          '[env]\ndefault_prefixes = {OTHER_API_PREFIX = "API"}\n')
    config.use(other)
    c2 = env.chain()
    check("config.use() rebuilds it for the new skill pack",
          c2 is not c and c2.paths_var == "OTHER_AUTH_ENV_PATHS"
          and c2.home_file == "~/.other.env"
          and c2.default_prefixes == {"OTHER_API_PREFIX": "API"})
    _shop.use()

    print("\n[9] a gate secret, the seam, a binding: never from a file")
    planted = ("SHOP_CONFIRM_CODE_SECRET", "OTHER_CONFIRM_CODE_SECRET",
               "CONSOLE_SECRET", "KIT_TTY", "PYTEST_CURRENT_TEST",
               "KIT_SKILL_PACK_ROOT", "PYTHONPATH", "DYLD_INSERT_LIBRARIES",
               "LD_PRELOAD", "SHOP_TEST_SEAM", "KIT_TEST_RUN")
    forms = ("{n}=planted-{i}\n", "export {n}=planted-{i}\n",
             "  {n} = 'planted-{i}'\n", "export  {n}  =planted-{i}\n")
    write(data / ".env", "".join(forms[i % len(forms)].format(n=n, i=i)
                                 for i, n in enumerate(planted))
          + "X_OK=ordinary\n")
    seamed = env.EnvChain(paths_var="SHOP_AUTH_ENV_PATHS",
                          data_dir_var="SHOP_DATA_DIR", home_file=None,
                          never=("SHOP_TEST_SEAM",))
    keep = {n: os.environ.pop(n, None) for n in planted}
    try:
        added = seamed.load_into_environ()
        check("an ordinary key in the data-dir .env still loads",
              added == {"X_OK": str(data / ".env")}
              and os.environ.get("X_OK") == "ordinary", added)
        check("no planted name reaches os.environ",
              not any(os.environ.get(n) for n in planted),
              [n for n in planted if os.environ.get(n)])
        check("get/resolve/load see none of them either",
              all(seamed.resolve(n) == (None, None) for n in planted)
              and set(seamed.load()) == {"X_OK"})
        check("refused() names each (plain, `export `, spaced and quoted "
              "forms), with its file, never a value",
              seamed.refused() == [(str(data / ".env"), n) for n in planted]
              and "planted" not in repr(seamed.refused()))
        check("the skill pack's own name is refused only when it lists it",
              "SHOP_TEST_SEAM" in ch.load() and "SHOP_TEST_SEAM" not in
              seamed.load())
        os.environ["SHOP_CONFIRM_CODE_SECRET"] = "from-process"
        check("the process env still sets a gate secret",
              seamed.get("SHOP_CONFIRM_CODE_SECRET") == "from-process")
        check("is_gate_secret: the confirm-code keys and the console's",
              all(env.is_gate_secret(n) for n in planted[:3])
              and not any(env.is_gate_secret(n) for n in
                          ("SHOP_API_KEY", "SECRET_SAUCE", "KIT_TTY")))
    finally:
        os.environ.pop("X_OK", None)
        for n, v in keep.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
    write(other / "skill-pack.toml", '[skill_pack]\nname = "o"\ncli = "o"\n'
          'env_prefix = "OTHER"\n[env]\nnever_from_file = ["OTHER_SEAM"]\n')
    config.use(other)
    check("chain() takes [env].never_from_file",
          env.chain().never == ("OTHER_SEAM",))
    write(other / "skill-pack.toml", '[skill_pack]\nname = "o"\ncli = "o"\n'
          'env_prefix = "OTHER"\n[env]\nnever_from_file = "OTHER_SEAM"\n')
    config.use(other)
    check("… and refuses one that is not a list of names",
          raises(env.chain, config.ConfigError) is not None)
    _shop.use()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
