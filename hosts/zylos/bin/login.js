'use strict';
// The console's sign-in: a one-time link and a session cookie, no password (0.8.0, the owner's R41).
// The agent runs `node zylos/lib.js link NAME` and sends the printed address; the person opens it,
// presses the one button, and that browser stays signed in for 90 days. Caddy keeps the route; it
// asks this service (`forward_auth`) whether the visitor has a valid session (hosts/zylos/README.md
// "The login"). Stdlib only; listens on a unix socket (mode 0600) in the console dir, so no other
// user and no visitor can reach it except through Caddy.
//
//   GET  /_auth       forward_auth's question. A valid session answers 200 with the user in the user
//                     header (Caddy copies it onto the request); else 302 to /login for a page
//                     request, 401 for anything else.
//   GET  /in/<token>  the link: a page with the name and one button. Nothing is spent on a GET: a chat
//                     app's link preview fetches the address before the person does. A token that is
//                     cut short or garbled (wrong length, letters, check) says so, in other words than
//                     a used or expired one.
//   POST /in/<token>  the button: spends the token, adds the person's line when there is none, sets
//                     the cookie, goes to the console.
//   GET  /login       says to ask the agent for a sign-in link (there is no form).
//   POST /logout      clears the cookie. GET /logout shows the button.
//   /setup            a 0.6/0.7 password link someone still holds: says to ask for a new one.
//
// The users file has one `name <stamp>` line per person. The cookie holds user, expiry, a fingerprint
// of the stamp and an HMAC with <console dir>/session.key; the file is read on each question, so
// `lib.js signout NAME` (a new stamp) or `lib.js remove NAME` ends every session of that person at
// once. A 0.7.x line (`scrypt$…`, or a bcrypt line from before) is a stamp as good as any: its
// cookies keep working until they expire. Honest limits: a link is a bearer secret for 30 minutes,
// and the agent that prints it can use it; the key sits in the data dir, which the agent on a
// single-user host can read; the throttle is in memory and starts over with the service; a logout
// clears this browser's cookie only, so a copied cookie works until it expires or `signout`.

const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const SESSION_DAYS = 90;
const LINK_MINUTES = 30;
const USER_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;       // the console's own rule for a user name
// The link's token: 26 random letters from an alphabet a chat app leaves alone and a person cannot
// misread (no l, o, 0, 1; 5 bits each, 130 bits), then 2 check letters from sha256 of those 26, so a
// token cut short or changed in forwarding is told apart from one that was used or expired.
const ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789';
const RANDOM_LEN = 26;
const TOKEN_LEN = RANDOM_LEN + 2;
const FREE_FAILS = 5;                                  // wrong tokens from one address before the wait starts
const BODY_MAX = 4096;

const sha = (s) => crypto.createHash('sha256').update(s).digest();

// --- the link's token --------------------------------------------------------------------
const checkOf = (body) => { const d = sha(body); return ALPHABET[d[0] & 31] + ALPHABET[d[1] & 31]; };

function newLinkToken() {
  const body = [...crypto.randomBytes(RANDOM_LEN)].map((b) => ALPHABET[b & 31]).join('');   // 256 = 8 * 32: uniform
  return body + checkOf(body);
}

// Whether a token is whole: the length, the alphabet and the check. Not whether it is known.
function linkShape(token) {
  const t = String(token || '');
  if (t.length !== TOKEN_LEN || [...t].some((c) => !ALPHABET.includes(c))) return false;
  return checkOf(t.slice(0, RANDOM_LEN)) === t.slice(RANDOM_LEN);
}

// --- the users file: `name <stamp>` per line ------------------------------------------------
const newStampValue = () => `link$${crypto.randomBytes(18).toString('base64url')}`;

// Map user -> stamp. Any second field is a stamp: a `link$…` one, a 0.7.x `scrypt$…` hash, a bcrypt
// line from before the form login. Comments and blank lines are skipped.
function readUsers(file) {
  const users = new Map();
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { return users; }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const [name, stamp] = line.split(/\s+/);
    if (name && USER_RE.test(name) && stamp) users.set(name, stamp);
  }
  return users;
}

// The CLI and the service both rewrite the files: one at a time (a lock directory, atomic to make; a
// lock older than 10 s is a dead process's and is taken over).
function locked(file, fn) {
  const lock = `${file}.lock`;
  const wait = new Int32Array(new SharedArrayBuffer(4));
  for (let i = 0; ; i++) {
    try { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.mkdirSync(lock); break; } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      try { if (Date.now() - fs.statSync(lock).mtimeMs > 10_000) fs.rmdirSync(lock); } catch { /* gone */ }
      if (i > 200) throw new Error(`${lock} is held`);
      Atomics.wait(wait, 0, 0, 10);
    }
  }
  try { return fn(); } finally { try { fs.rmdirSync(lock); } catch { /* gone */ } }
}

function writeAtomic(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, text, { mode: 0o600 });
  fs.renameSync(tmp, file);
  fs.chmodSync(file, 0o600);
}

const checkName = (name) => {
  if (!USER_RE.test(String(name))) throw new Error(`${JSON.stringify(name)} is not a user name (letters, digits, . _ : -)`);
};

// One person's line, rewritten under the lock: `change(stamp or null)` returns the new stamp, null to
// take the line out, or undefined to leave the file as it is. Other lines are kept as they are.
function changeUser(file, name, change) {
  checkName(name);
  return locked(file, () => {
    let text = '';
    try { text = fs.readFileSync(file, 'utf8'); } catch { /* a first user */ }
    const kept = [];
    let had = null;
    for (const raw of text.split('\n')) {
      const line = raw.trim();
      if (!line) continue;
      const [first, stamp] = line.split(/\s+/);
      if (first === name && !line.startsWith('#')) { had = stamp || ''; continue; }
      kept.push(line);
    }
    const next = change(had);
    if (next === undefined) return had;
    if (next !== null) kept.push(`${name} ${next}`);
    writeAtomic(file, kept.length ? `${kept.join('\n')}\n` : '');
    return next;
  });
}

// The person's stamp, adding their line when there is none (a first sign-in). An existing line is
// left alone, so a sign-in on a second device does not sign the first one out.
const ensureUser = (file, name) => changeUser(file, name, (had) => (had ? undefined : newStampValue()));

// A new stamp: every session of that person ends at once. Throws when there is no such person.
function signOutUser(file, name) {
  return changeUser(file, name, (had) => {
    if (had === null) throw new Error(`${name} is not in the logins file`);
    return newStampValue();
  });
}

function removeUser(file, name) {
  changeUser(file, name, (had) => {
    if (had === null) throw new Error(`${name} is not in the logins file`);
    return null;
  });
}

// --- the session cookie ---------------------------------------------------------------
const fingerprint = (stamp) => crypto.createHash('sha256').update(stamp).digest('hex').slice(0, 12);
const mac = (key, body) => crypto.createHmac('sha256', key).update(body).digest('base64url');

function makeToken(key, user, stamp, now = Date.now()) {
  const body = `${Buffer.from(user).toString('base64url')}.${Math.floor(now / 1000) + SESSION_DAYS * 86400}.${fingerprint(stamp)}`;
  return `${body}.${mac(key, body)}`;
}

// The user of a cookie that is signed, unexpired, and still matches the person's stamp.
function checkToken(key, users, token, now = Date.now()) {
  const parts = String(token || '').split('.');
  if (parts.length !== 4) return null;
  const body = parts.slice(0, 3).join('.');
  const want = Buffer.from(mac(key, body));
  const have = Buffer.from(parts[3]);
  if (want.length !== have.length || !crypto.timingSafeEqual(want, have)) return null;
  const user = Buffer.from(parts[0], 'base64url').toString();
  const stamp = users.get(user);
  if (!stamp || fingerprint(stamp) !== parts[2]) return null;
  if (!(Number(parts[1]) * 1000 > now)) return null;
  return user;
}

function loadKey(file) {
  try {
    const k = fs.readFileSync(file, 'utf8').trim();
    if (k.length >= 32) { fs.chmodSync(file, 0o600); return k; }
  } catch { /* made below */ }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const k = crypto.randomBytes(32).toString('hex');
  fs.writeFileSync(file, `${k}\n`, { mode: 0o600 });
  fs.chmodSync(file, 0o600);
  return k;
}

// --- the links file: [{h, user, exp}], a token kept only as its hash --------------------------
const hashOf = (token) => sha(String(token || '')).toString('hex');

function readLinks(file, now) {
  try {
    const rows = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(rows) ? rows.filter((r) => r && typeof r.h === 'string' && r.exp > now) : [];
  } catch { return []; }
}

// A new link for `user`, who need not exist yet (the first sign-in adds the line). An older unused
// link for the same name is dropped, so the newest is the only one.
function makeLink(file, user, now = Date.now()) {
  checkName(user);
  const token = newLinkToken();
  locked(file, () => {
    const rows = readLinks(file, now).filter((r) => r.user !== user);
    rows.push({ h: hashOf(token), user, exp: now + LINK_MINUTES * 60_000 });
    writeAtomic(file, JSON.stringify(rows));
  });
  return { token, minutes: LINK_MINUTES };
}

// The user a link is for (not spent), or null.
function peekLink(file, token, now = Date.now()) {
  const h = hashOf(token);
  const r = readLinks(file, now).find((x) => x.h === h);
  return r ? r.user : null;
}

// Spend it: the user, or null when unknown, expired or already used.
function takeLink(file, token, now = Date.now()) {
  const h = hashOf(token);
  return locked(file, () => {
    const rows = readLinks(file, now);
    const r = rows.find((x) => x.h === h);
    if (!r) return null;
    writeAtomic(file, JSON.stringify(rows.filter((x) => x.h !== h)));
    return r.user;
  });
}

// Drop every unused link of a person (`signout`, `remove`: no way in is left open).
function dropLinks(file, user, now = Date.now()) {
  locked(file, () => {
    const rows = readLinks(file, now);
    const kept = rows.filter((r) => r.user !== user);
    if (kept.length !== rows.length) writeAtomic(file, JSON.stringify(kept));
  });
}

// --- the pages ----------------------------------------------------------------------------
const WORDS = {
  en: { title: 'Sign in', go: 'Sign in', as: 'Sign in as',
        ask: 'To sign in, ask the agent for a sign-in link. It works once, within 30 minutes; this browser then stays signed in for 90 days.',
        incomplete: 'This link is incomplete: it may have been cut off when it was forwarded. Ask the person who sent it to send a new one.',
        dead: 'This link has been used or has expired. Ask for a new one.',
        old: 'This link is from an older version of the sign-in. Ask for a new sign-in link.',
        wait: 'Too many tries. Wait a little and try again.', out: 'Sign out', gone: 'You are signed out.', again: 'How to sign in again',
        refused: 'The request did not come from this page.',
        noIn: 'signing in is not an ask', noOut: 'signing out is not an ask' },
  zh: { title: '登录', go: '登录', as: '登录为',
        ask: '要登录，请向助手要一个登录链接。链接只能用一次，30 分钟内有效；登录后这个浏览器 90 天内保持登录。',
        incomplete: '这个链接不完整，可能在转发时被截断了。请让发给你的人重新发一个。',
        dead: '这个链接已经用过或已过期，请重新要一个。',
        old: '这个链接来自旧版本的登录方式，请重新要一个登录链接。',
        wait: '试得太多了，请稍等再试。', out: '退出登录', gone: '你已退出登录。', again: '怎样重新登录',
        refused: '这个请求不是从本页发出的。',
        noIn: '登录不是一个需要回答的问题', noOut: '退出登录不是一个需要回答的问题' },
};
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function page(lang, title, inner) {
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${esc(title)}</title>
<style>body{font:16px system-ui,sans-serif;background:#f6f6f4;color:#1c1c1a;display:grid;place-items:center;min-height:100vh;margin:0}
main{background:#fff;border:1px solid #ddd;border-radius:10px;padding:28px;width:min(92vw,340px)}
h1{font-size:20px;margin:0 0 18px}p{line-height:1.5}
button{margin-top:18px;width:100%;padding:10px;font-size:16px;border:0;border-radius:6px;background:#1c1c1a;color:#fff;cursor:pointer}
.err{color:#a11;margin:0 0 6px}@media(prefers-color-scheme:dark){body{background:#161614;color:#eee}main{background:#1f1f1c;border-color:#333}
button{background:#eee;color:#161614}.err{color:#f88}}</style></head>
<body><main>${inner}</main></body></html>`;
}

// Every page the service draws, by name (the tests run kit.guards.asks over each). Each POST form
// says with `data-no` why it offers no "no": signing in and signing out are not asks.
function pages(lang, title, base) {
  const w = WORDS[lang];
  const note = (cls, text) => page(lang, `${title} · ${w.title}`, `<h1>${esc(title)}</h1><p${cls ? ` class="${cls}" role="alert"` : ''}>${esc(text)}</p>`);
  return {
    login: () => note('', w.ask),
    link: (token, user) => page(lang, `${title} · ${w.title}`, `<h1>${esc(title)}</h1>
<p>${w.as} <b>${esc(user)}</b></p>
<form method="post" action="${esc(base)}/in/${esc(token)}" data-no="${esc(w.noIn)}"><button type="submit" autofocus>${w.go}</button></form>`),
    incomplete: () => note('err', w.incomplete),
    dead: () => note('err', w.dead),
    old: () => note('err', w.old),
    wait: () => note('err', w.wait),
    refused: () => note('err', w.refused),
    logout: () => page(lang, `${title} · ${w.out}`,
      `<h1>${esc(title)}</h1><form method="post" action="${esc(base)}/logout" data-no="${esc(w.noOut)}"><button type="submit">${w.out}</button></form>`),
    gone: () => page(lang, `${title} · ${w.out}`, `<h1>${esc(title)}</h1><p>${w.gone}</p><p><a href="${esc(base)}/login">${w.again}</a></p>`),
    missing: () => page(lang, title, '<p>404</p>'),
  };
}

// --- the service ------------------------------------------------------------------------
// opts: usersFile, keyFile, linksFile, base ('/seo', '' for a site root), title, userHeader, allowHosts, now()
function createHandler(opts) {
  const base = (opts.base || '').replace(/\/+$/, '');
  const title = opts.title || 'Console';
  const header = String(opts.userHeader || 'X-Remote-User').toLowerCase();
  const now = opts.now || Date.now;
  const key = loadKey(opts.keyFile);
  const fails = new Map();                              // 'link:<ip>' -> {n, until}
  const cookieName = `session_${crypto.createHash('sha256').update(base || '/').digest('hex').slice(0, 6)}`;

  const langOf = (req) => (/^\s*zh/i.test(req.headers['accept-language'] || '') ? 'zh' : 'en');
  const cookieOf = (req) => {
    for (const p of String(req.headers.cookie || '').split(';')) {
      const i = p.indexOf('=');
      if (i > 0 && p.slice(0, i).trim() === cookieName) return p.slice(i + 1).trim();
    }
    return '';
  };
  const secure = (req) => String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim() === 'https';
  const ipOf = (req) => String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'local';
  const setCookie = (req, value, maxAge) => `${cookieName}=${value}; Path=${base || '/'}; Max-Age=${maxAge}; HttpOnly; SameSite=Lax${secure(req) ? '; Secure' : ''}`;
  const sweep = () => {
    if (fails.size < 5000) return;
    for (const [k, e] of fails) if (e.until <= now() && e.n < FREE_FAILS) fails.delete(k);
    if (fails.size >= 5000) fails.clear();               // under a flood, forgetting beats growing
  };
  const blocked = (k) => (fails.get(k)?.until || 0) > now();
  const fail = (k) => {
    const e = fails.get(k) || { n: 0, until: 0 };
    e.n += 1;
    sweep();
    if (e.n >= FREE_FAILS) e.until = now() + Math.min(900, 30 * 2 ** (e.n - FREE_FAILS)) * 1000;
    fails.set(k, e);
  };

  const send = (res, code, body, extra = {}) => {
    res.writeHead(code, {
      'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
      // not no-referrer: under it a browser sends `Origin: null` on the button's POST, which sameOrigin refuses
      'Referrer-Policy': 'same-origin', ...extra,
    });
    res.end(body);
  };
  const go = (res, to, extra = {}) => { res.writeHead(303, { Location: to, 'Cache-Control': 'no-store', ...extra }); res.end(); };

  // the Origin of a POST must be the host the visitor used (a login CSRF is still a CSRF): the host the
  // request names, or one of the console's own public names (`allowHosts`, the console's --allow-host
  // list). The second is needed behind a platform entry that rewrites Host to localhost, after which
  // Caddy sends X-Forwarded-Host: localhost too, so every POST on the public domain was refused (issue #488).
  const allowed = new Set((opts.allowHosts || []).map((x) => String(x).trim().toLowerCase()).filter(Boolean));
  const sameOrigin = (req) => {
    const o = req.headers.origin;
    if (!o) return true;
    let host;
    try { host = new URL(o).host.toLowerCase(); } catch { return false; }
    return host === String(req.headers['x-forwarded-host'] || req.headers.host || '').toLowerCase() || allowed.has(host);
  };

  // Read and drop the body, or a 413 and a closed connection once it passes BODY_MAX.
  function drain(req, res, cb) {
    let n = 0;
    let over = false;
    req.on('data', (c) => {
      n += c.length;
      if (n > BODY_MAX && !over) { over = true; res.writeHead(413, { Connection: 'close' }); res.end(); }
    });
    req.on('end', () => { if (!over) cb(); });
  }

  const serve = (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const lang = langOf(req);
    const P = pages(lang, title, base);
    const read = req.method === 'GET' || req.method === 'HEAD';
    if (url.pathname === '/_auth' && read) {
      const user = checkToken(key, readUsers(opts.usersFile), cookieOf(req), now());
      if (user) { res.writeHead(200, { [header]: user, 'Cache-Control': 'no-store' }); return res.end(); }
      const m = String(req.headers['x-forwarded-method'] || 'GET').toUpperCase();
      if (m !== 'GET' && m !== 'HEAD') { res.writeHead(401, { 'Cache-Control': 'no-store' }); return res.end(); }
      res.writeHead(302, { Location: `${base}/login`, 'Cache-Control': 'no-store' });
      return res.end();
    }
    const link = /^\/in\/([^/]*)\/?$/.exec(url.pathname);
    if (link && (read || req.method === 'POST')) {
      let token = '';
      try { token = decodeURIComponent(link[1]).trim().toLowerCase(); } catch { /* left empty: incomplete */ }
      if (!linkShape(token)) return send(res, 400, P.incomplete());      // cut short or changed: no guess, not counted
      const ipKey = `link:${ipOf(req)}`;
      if (blocked(ipKey)) return send(res, 429, P.wait());
      if (read) {
        const user = opts.linksFile ? peekLink(opts.linksFile, token, now()) : null;
        if (!user) { fail(ipKey); return send(res, 410, P.dead()); }
        return send(res, 200, P.link(token, user));                     // a GET never spends: a link preview fetches it too
      }
      if (!sameOrigin(req)) return send(res, 403, P.refused());
      return drain(req, res, () => {
        try {
          const user = opts.linksFile ? takeLink(opts.linksFile, token, now()) : null;
          if (!user) { fail(ipKey); return send(res, 410, P.dead()); }
          const stamp = ensureUser(opts.usersFile, user);
          return go(res, `${base}/`, { 'Set-Cookie': setCookie(req, makeToken(key, user, stamp, now()), SESSION_DAYS * 86400) });
        } catch (e) {
          console.error(`login: ${e.stack || e}`);
          if (!res.headersSent) res.writeHead(500, { 'Cache-Control': 'no-store' });
          return res.end();
        }
      });
    }
    if (url.pathname === '/login') {
      if (read) return send(res, 200, P.login());
      req.resume();
      return send(res, 410, P.login());                                  // a saved 0.7 password form: nothing is checked
    }
    if (url.pathname === '/setup') {
      req.resume();
      return send(res, 410, P.old());                                    // a 0.6/0.7 password link someone still holds
    }
    if (url.pathname === '/logout') {
      if (req.method === 'POST') {
        if (!sameOrigin(req)) return send(res, 403, P.refused());
        req.resume();
        return send(res, 200, P.gone(), { 'Set-Cookie': setCookie(req, '', 0) });
      }
      return send(res, 200, P.logout());
    }
    return send(res, 404, P.missing());
  };

  // A bug in one request must not take the console's process down with it.
  return (req, res) => {
    try { serve(req, res); } catch (e) {
      console.error(`login: ${e.stack || e}`);
      if (!res.headersSent) res.writeHead(500, { 'Cache-Control': 'no-store' });
      res.end();
    }
  };
}

// Listen on a unix socket inside a directory only this user can enter (checked: owned by us,
// not a symlink, mode 0700), then chmod the socket itself. The process umask is left alone: the
// console this process starts inherits it.
function privateDir(dir) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const st = fs.lstatSync(dir);
  if (!st.isDirectory() || st.isSymbolicLink() || (process.getuid && st.uid !== process.getuid())) throw new Error(`${dir} is not a directory of this user`);
  if (st.mode & 0o077) fs.chmodSync(dir, 0o700);
}

function listen(opts) {
  privateDir(path.dirname(opts.sock));
  const server = http.createServer(createHandler(opts));
  try { fs.rmSync(opts.sock, { force: true }); } catch { /* a stale socket we cannot remove fails below */ }
  server.listen(opts.sock, () => {
    fs.chmodSync(opts.sock, 0o600);
    const st = fs.lstatSync(opts.sock);
    if (process.getuid && st.uid !== process.getuid()) { server.close(); server.emit('error', new Error(`${opts.sock} is not ours`)); }
  });
  return server;
}

module.exports = { makeLink, peekLink, takeLink, dropLinks, linkShape, newLinkToken, readUsers, ensureUser, signOutUser, removeUser,
                   makeToken, checkToken, loadKey, pages, createHandler, listen,
                   ALPHABET, TOKEN_LEN, LINK_MINUTES, SESSION_DAYS, USER_RE };
