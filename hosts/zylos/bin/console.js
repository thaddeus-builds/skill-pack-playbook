#!/usr/bin/env node
'use strict';
// The owner console as a pm2 service: SKILL.md lifecycle.service names this
// file and the root ecosystem.config.cjs runs it (zylos/README.md "The
// console service"). It runs the vendored playbook console,
// `uv run --no-project <skill dir>/<console.entry>`, in the foreground:
//
//   --dir <data dir>/console      the console's event log and secret
//   --host 127.0.0.1 --port P     P = console.port_key's value, else console.port
//   --user-header H               who clicked: the header the host's Caddy sets
//                                 after basic_auth (believed from loopback only)
//   --title T                     console.title_key's value, else the manifest name
//   --allow-host D …              console.allow_host_key's value (the public
//                                 domain Caddy passes through as Host)
//   --relay-cmd <cli>             this node on bin/cli.js, when console.args
//                                 carries --relay-verbs (serve.py wants both)
//   <console.args…>               the rest, as the manifest gives them
//
// Keys are read like the harness reads them (process env, then the .env
// chain). <PREFIX>_CONFIRM_CODE_SECRET, which the relay's harness runs need
// to issue and check a click's one-time code, is a fresh random value made at
// each start and exported to the console's process only: never written to a
// file (the harness never loads it from one: kit/env.py), never printed. Both
// calls of one click run under the same start. Exits 2 on a bad port or host,
// 127 without uv, else with the console's status. Stdlib only.

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const h = require('../lib.js');

const c = h.consoleCommand();
if (c.error) {
  console.error(`${h.NAME} console: ${c.error}`);
  process.exit(2);
}
const uv = h.findUv();
if (!uv) {
  console.error(`${h.NAME} console: uv not found; run node ${h.POST_INSTALL}`);
  process.exit(127);
}
fs.mkdirSync(h.CONSOLE_DIR, { recursive: true, mode: 0o700 });
const env = h.cliEnv();
env[h.CONFIRM_SECRET_VAR] = crypto.randomBytes(32).toString('hex');
// the relay's harness runs find uv the same way
env.PATH = [path.dirname(uv), env.PATH].filter(Boolean).join(path.delimiter);
const child = spawn(uv, ['run', '--no-project', c.entry, ...c.argv], { stdio: 'inherit', env });
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => child.kill(sig));
child.on('error', (e) => { console.error(`${h.NAME} console: ${e.message}`); process.exit(127); });
child.on('exit', (code, signal) => process.exit(code ?? 128 + (os.constants.signals[signal] || 0)));
