'use strict';
// The console's login: a form and a session cookie, in place of Caddy's
// `basic_auth` (the browser's own pop-up, which password managers rarely
// save). Caddy keeps the route; it asks this service `forward_auth` whether the
// visitor has a valid session, and shows the form when not (hosts/zylos/README.md
// "The login"). Stdlib only; listens on a unix socket (mode 0600) in the console
// dir, so no other user and no visitor can reach it except through Caddy.
//
//   GET  /_auth    forward_auth's question. A valid session answers 200 with
//                  the user in the user header (Caddy copies it onto the request);
//                  else 302 to the form for a page request, 401 for anything else.
//   GET  /login    the form: a plain username + password form, so a browser or a
//                  password manager offers to save it (autocomplete hints).
//   POST /login    checks the password (scrypt), sets the cookie, goes back to `next`
//                  (a path under the base only).
//   POST /logout   clears the cookie. GET /logout shows the button.
//   GET/POST /setup?token=…  a person sets their own password on a page: the link comes from
//                  `lib.js passwd NAME --link` (an agent can run it, there is no password in it),
//                  lives 30 minutes and works once. The agent never types or sees the password.
//
// The cookie holds user, expiry, a fingerprint of the user's stored hash and an HMAC
// with <console dir>/session.key. Removing a user or changing a password changes the
// fingerprint, so every session of that user ends at once; the logins file is read on
// each question. Honest limits: the key sits in the data dir, which the agent on a
// single-user host can read (the same as the console's secret); the login throttle is
// in memory and starts over with the service. A logout clears the browser's cookie only: a copied
// cookie works until it expires or the person's password changes. A wrong-password flood can lock
// a known user out for up to 15 minutes (the price of a throttle with no second factor).

const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const SESSION_DAYS = 14;
const USER_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;       // the console's own rule for a user name
const MIN_PASSWORD = 10;
const SCRYPT = { log2n: 15, r: 8, p: 1, maxmem: 128 * 1024 * 1024 };
const FREE_FAILS = 5;                                  // wrong passwords before the wait starts
const BODY_MAX = 4096;

// --- passwords: `user scrypt$15$8$1$<salt>$<key>` per line, base64url ----------------
function hashPassword(pw) {
  const salt = crypto.randomBytes(16);
  const key = crypto.scryptSync(pw, salt, 32, { N: 1 << SCRYPT.log2n, r: SCRYPT.r, p: SCRYPT.p, maxmem: SCRYPT.maxmem });
  return `scrypt$${SCRYPT.log2n}$${SCRYPT.r}$${SCRYPT.p}$${salt.toString('base64url')}$${key.toString('base64url')}`;
}

function parseHash(stored) {
  const m = /^scrypt\$(\d{1,2})\$(\d{1,2})\$(\d{1,2})\$([A-Za-z0-9_-]+)\$([A-Za-z0-9_-]+)$/.exec(stored || '');
  if (!m) return null;
  const [log2n, r, p] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (log2n < 10 || log2n > 20 || r < 1 || r > 16 || p < 1 || p > 4 || 128 * (2 ** log2n) * r > SCRYPT.maxmem) return null;   // refuses what scrypt would throw on
  return { log2n, r, p, salt: Buffer.from(m[4], 'base64url'), key: Buffer.from(m[5], 'base64url') };
}

function verifyPassword(pw, stored) {
  const h = parseHash(stored);
  if (!h || !h.key.length) return false;
  const got = crypto.scryptSync(pw, h.salt, h.key.length,
    { N: 1 << h.log2n, r: h.r, p: h.p, maxmem: SCRYPT.maxmem });
  return crypto.timingSafeEqual(got, h.key);
}

// The login path uses this one: scrypt runs on the thread pool, so a login attempt does not
// stop the loop that also answers every console request's /_auth.
async function verifyPasswordAsync(pw, stored) {
  const h = parseHash(stored);
  if (!h || !h.key.length) return false;
  const got = await new Promise((resolve, reject) => crypto.scrypt(pw, h.salt, h.key.length,
    { N: 1 << h.log2n, r: h.r, p: h.p, maxmem: SCRYPT.maxmem }, (e, k) => (e ? reject(e) : resolve(k))));
  return crypto.timingSafeEqual(got, h.key);
}

// Only so an unknown user costs the same time as a known one.
const DUMMY = hashPassword(crypto.randomBytes(8).toString('hex'));

// Map user -> stored hash. A line that is not `name hash` (a Caddy bcrypt line from
// before the form login, a comment) is kept as given so `stale` can name it.
function readUsers(file) {
  const users = new Map();
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { return users; }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const [name, hash] = line.split(/\s+/);
    if (name && USER_RE.test(name) && hash) users.set(name, hash);
  }
  return users;
}

// The names whose line cannot log in: made for Caddy's basic_auth (bcrypt), so the
// person has to set a password again with `node zylos/lib.js passwd NAME`.
function staleUsers(file) {
  return [...readUsers(file)].filter(([, h]) => !parseHash(h)).map(([n]) => n);
}

// Add or replace one person (or remove with pw === null), atomically, mode 0600.
function setPassword(file, name, pw) {
  if (!USER_RE.test(name)) throw new Error(`${JSON.stringify(name)} is not a user name (letters, digits, . _ : -)`);
  if (pw !== null && String(pw).length < MIN_PASSWORD) throw new Error(`the password needs at least ${MIN_PASSWORD} characters`);
  const kept = [];
  let found = false;
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { /* a first user */ }
  for (const raw of text.split('\n')) {
    const first = raw.trim().split(/\s+/)[0];
    if (first === name) { found = true; continue; }
    if (raw.trim()) kept.push(raw.trim());
  }
  if (pw === null && !found) throw new Error(`${name} is not in the logins file`);
  if (pw !== null) kept.push(`${name} ${hashPassword(String(pw))}`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, kept.length ? `${kept.join('\n')}\n` : '', { mode: 0o600 });
  fs.renameSync(tmp, file);
  fs.chmodSync(file, 0o600);
  return found ? 'replaced' : 'added';
}

// --- the session cookie ---------------------------------------------------------------
const fingerprint = (stored) => crypto.createHash('sha256').update(stored).digest('hex').slice(0, 12);
const mac = (key, body) => crypto.createHmac('sha256', key).update(body).digest('base64url');

function makeToken(key, user, stored, now = Date.now()) {
  const body = `${Buffer.from(user).toString('base64url')}.${Math.floor(now / 1000) + SESSION_DAYS * 86400}.${fingerprint(stored)}`;
  return `${body}.${mac(key, body)}`;
}

// The user of a token that is signed, unexpired, and still matches the stored hash.
function checkToken(key, users, token, now = Date.now()) {
  const parts = String(token || '').split('.');
  if (parts.length !== 4) return null;
  const body = parts.slice(0, 3).join('.');
  const want = Buffer.from(mac(key, body));
  const have = Buffer.from(parts[3]);
  if (want.length !== have.length || !crypto.timingSafeEqual(want, have)) return null;
  const user = Buffer.from(parts[0], 'base64url').toString();
  const stored = users.get(user);
  if (!stored || !parseHash(stored) || fingerprint(stored) !== parts[2]) return null;
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

// --- the setup link: a token that is shown once and kept only as a hash --------------------------------
const SETUP_MINUTES = 30;
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

function readSetup(file, now) {
  try {
    const rows = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(rows) ? rows.filter((r) => r && typeof r.h === 'string' && r.exp > now) : [];
  } catch { return []; }
}

// The CLI and the service both rewrite the file: one at a time (a lock directory, atomic to make; a lock
// older than 10 s is a dead process's and is taken over).
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

function writeSetup(file, rows) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, JSON.stringify(rows), { mode: 0o600 });
  fs.renameSync(tmp, file);
  fs.chmodSync(file, 0o600);
}

// A new token for `user` (who need not exist yet: the page creates the line). Earlier unused
// tokens of the same user are dropped, so the newest link is the only one.
function makeSetupToken(file, user, now = Date.now()) {
  if (!USER_RE.test(user)) throw new Error(`${JSON.stringify(user)} is not a user name (letters, digits, . _ : -)`);
  const token = crypto.randomBytes(32).toString('base64url');
  locked(file, () => {
    const rows = readSetup(file, now).filter((r) => r.user !== user);
    rows.push({ h: sha(token), user, exp: now + SETUP_MINUTES * 60_000 });
    writeSetup(file, rows);
  });
  return { token, minutes: SETUP_MINUTES };
}

// The user a token is for (not consumed), or null.
function peekSetupToken(file, token, now = Date.now()) {
  const h = sha(String(token || ''));
  const r = readSetup(file, now).find((x) => x.h === h);
  return r ? r.user : null;
}

// Use it up: the user, or null when unknown, expired or already used.
function takeSetupToken(file, token, now = Date.now()) {
  const h = sha(String(token || ''));
  return locked(file, () => {
    const rows = readSetup(file, now);
    const r = rows.find((x) => x.h === h);
    if (!r) return null;
    writeSetup(file, rows.filter((x) => x.h !== h));
    return r.user;
  });
}

// --- the page ---------------------------------------------------------------------------
const WORDS = {
  en: { title: 'Sign in', user: 'Username', pass: 'Password', go: 'Sign in', bad: 'Wrong username or password.',
        wait: 'Too many tries. Wait a little and try again.', out: 'Sign out', gone: 'You are signed out.', again: 'Sign in again',
        refused: 'The request did not come from this page.',
        setup: 'Set your password', new: 'New password (at least 10 characters)', again2: 'Type it again', save: 'Save and sign in',
        short: 'The password needs at least 10 characters.', differ: 'The two passwords differ.',
        dead: 'This link has been used or has expired. Ask for a new one.', for: 'Account' },
  zh: { title: '登录', user: '用户名', pass: '密码', go: '登录', bad: '用户名或密码不对。',
        wait: '试得太多了，请稍等再试。', out: '退出登录', gone: '你已退出登录。', again: '重新登录',
        refused: '这个请求不是从本页发出的。',
        setup: '设置密码', new: '新密码（至少 10 个字符）', again2: '再输入一次', save: '保存并登录',
        short: '密码至少 10 个字符。', differ: '两次输入不一样。',
        dead: '这个链接已经用过或已过期。请重新要一个。', for: '账号' },
};
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function page(lang, title, inner) {
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title>
<style>body{font:16px system-ui,sans-serif;background:#f6f6f4;color:#1c1c1a;display:grid;place-items:center;min-height:100vh;margin:0}
main{background:#fff;border:1px solid #ddd;border-radius:10px;padding:28px;width:min(92vw,340px)}
h1{font-size:20px;margin:0 0 18px}label{display:block;font-size:14px;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;padding:9px;font-size:16px;border:1px solid #bbb;border-radius:6px}
button{margin-top:18px;width:100%;padding:10px;font-size:16px;border:0;border-radius:6px;background:#1c1c1a;color:#fff;cursor:pointer}
.err{color:#a11;margin:0 0 6px}@media(prefers-color-scheme:dark){body{background:#161614;color:#eee}main{background:#1f1f1c;border-color:#333}
input{background:#161614;color:#eee;border-color:#555}button{background:#eee;color:#161614}.err{color:#f88}}</style></head>
<body><main>${inner}</main></body></html>`;
}

function formPage(lang, title, base, next, message) {
  const w = WORDS[lang];
  return page(lang, `${title} · ${w.title}`, `<h1>${esc(title)}</h1>${message ? `<p class="err" role="alert">${esc(message)}</p>` : ''}
<form method="post" action="${esc(base)}/login">
<input type="hidden" name="next" value="${esc(next)}">
<label for="username">${w.user}</label><input id="username" name="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus>
<label for="password">${w.pass}</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">${w.go}</button></form>`);
}

// --- the service ------------------------------------------------------------------------
// opts: usersFile, keyFile, setupFile, base ('/seo', '' for a site root), title, userHeader, now()
function createHandler(opts) {
  const base = (opts.base || '').replace(/\/+$/, '');
  const title = opts.title || 'Console';
  const header = String(opts.userHeader || 'X-Remote-User').toLowerCase();
  const now = opts.now || Date.now;
  const key = loadKey(opts.keyFile);
  const fails = new Map();                              // 'ip:..' / 'user:..' -> {n, until}
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
  // a `next` is followed only when it stays under the base: never another site
  const safeNext = (n) => {
    const s = String(n || '');
    if (!s.startsWith(`${base}/`) || s.startsWith('//') || /[\x00-\x20\x7f\\]/.test(s) || s.startsWith(`${base}/login`) || s.startsWith(`${base}/logout`)) return `${base}/`;
    return s;
  };
  let inflight = 0;                                      // logins being checked: scrypt is the costly part
  const sweep = () => {
    if (fails.size < 5000) return;
    for (const [k, e] of fails) if (e.until <= now() && e.n < FREE_FAILS) fails.delete(k);
    if (fails.size >= 5000) fails.clear();               // under a flood, forgetting beats growing
  };
  const blocked = (names) => names.some((k) => (fails.get(k)?.until || 0) > now());
  const fail = (names) => names.forEach((k) => {
    const e = fails.get(k) || { n: 0, until: 0 };
    e.n += 1;
    sweep();
    if (e.n >= FREE_FAILS) e.until = now() + Math.min(900, 30 * 2 ** (e.n - FREE_FAILS)) * 1000;
    fails.set(k, e);
  });

  const send = (res, code, body, extra = {}) => {
    res.writeHead(code, {
      'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
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

  // The form, or a 413 and a closed connection once the body passes BODY_MAX.
  function readForm(req, res, cb) {
    let n = 0;
    let over = false;
    const chunks = [];
    req.on('data', (c) => {
      n += c.length;
      if (n <= BODY_MAX) { chunks.push(c); return; }
      if (!over) { over = true; res.writeHead(413, { Connection: 'close' }); res.end(); }
    });
    req.on('end', () => { if (!over) cb(new URLSearchParams(Buffer.concat(chunks).toString())); });
  }

  const serve = (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const lang = langOf(req);
    const w = WORDS[lang];
    if (url.pathname === '/_auth' && (req.method === 'GET' || req.method === 'HEAD')) {
      const user = checkToken(key, readUsers(opts.usersFile), cookieOf(req), now());
      if (user) { res.writeHead(200, { [header]: user, 'Cache-Control': 'no-store' }); return res.end(); }
      const m = String(req.headers['x-forwarded-method'] || 'GET').toUpperCase();
      if (m !== 'GET' && m !== 'HEAD') { res.writeHead(401, { 'Cache-Control': 'no-store' }); return res.end(); }
      // Behind handle_path Caddy may send the path with the prefix stripped: put it back
      const fwd = String(req.headers['x-forwarded-uri'] || '');
      const next = fwd.startsWith('/') && !fwd.startsWith('//') && !(base && (fwd === base || fwd.startsWith(`${base}/`))) ? `${base}${fwd}` : fwd;
      res.writeHead(302, { Location: `${base}/login${next ? `?next=${encodeURIComponent(next)}` : ''}`, 'Cache-Control': 'no-store' });
      return res.end();
    }
    if (url.pathname === '/login' && req.method === 'GET') {
      return send(res, 200, formPage(lang, title, base, safeNext(url.searchParams.get('next')), ''));
    }
    if (url.pathname === '/login' && req.method === 'POST') {
      if (!sameOrigin(req)) return send(res, 403, page(lang, title, `<p class="err">${w.refused}</p>`));
      return readForm(req, res, async (f) => {
        try {
          const name = String(f.get('username') || '').trim().slice(0, 64);
          const next = safeNext(f.get('next'));
          const names = [`ip:${ipOf(req)}`, `user:${name.toLowerCase()}`];
          if (blocked(names) || inflight >= 4) return send(res, 429, formPage(lang, title, base, next, w.wait));
          const users = readUsers(opts.usersFile);
          const stored = users.get(name);
          const real = Boolean(stored && parseHash(stored));
          inflight += 1;
          let ok;
          try { ok = (await verifyPasswordAsync(String(f.get('password') || '').slice(0, 1024), real ? stored : DUMMY)) && real; } finally { inflight -= 1; }
          if (!ok) { fail(names); return send(res, 401, formPage(lang, title, base, next, w.bad)); }
          fails.delete(names[1]);
          return go(res, next, { 'Set-Cookie': setCookie(req, makeToken(key, name, stored, now()), SESSION_DAYS * 86400) });
        } catch (e) {
          console.error(`login: ${e.stack || e}`);
          if (!res.headersSent) res.writeHead(500, { 'Cache-Control': 'no-store' });
          return res.end();
        }
      });
    }
    if (url.pathname === '/setup' && (req.method === 'GET' || req.method === 'POST')) {
      const setupPage = (token, user, message, code = 200) => send(res, code, page(lang, title, `<h1>${w.setup}</h1>${message ? `<p class="err" role="alert">${esc(message)}</p>` : ''}
<p>${w.for}: <b>${esc(user)}</b></p>
<form method="post" action="${esc(base)}/setup"><input type="hidden" name="token" value="${esc(token)}">
<input type="text" name="username" value="${esc(user)}" autocomplete="username" hidden readonly>
<label for="password">${w.new}</label><input id="password" name="password" type="password" autocomplete="new-password" required minlength="10" autofocus>
<label for="password2">${w.again2}</label><input id="password2" name="password2" type="password" autocomplete="new-password" required minlength="10">
<button type="submit">${w.save}</button></form>`));
      const dead = (code = 410) => send(res, code, page(lang, title, `<p class="err">${w.dead}</p>`));
      if (!opts.setupFile) return dead(404);
      const ipKey = `setup:${ipOf(req)}`;
      if (blocked([ipKey])) return send(res, 429, page(lang, title, `<p class="err">${w.wait}</p>`));
      if (req.method === 'GET') {
        const t = url.searchParams.get('token') || '';
        const user = peekSetupToken(opts.setupFile, t, now());
        if (!user) { if (t.length >= 40) fail([ipKey]); return dead(); }     // a guess looks like a token; a preview bot's stale link is no attack
        return setupPage(t, user, '');
      }
      if (!sameOrigin(req)) return send(res, 403, page(lang, title, `<p class="err">${w.refused}</p>`));
      return readForm(req, res, (f) => {
        try {
          const t = String(f.get('token') || '');
          const user = peekSetupToken(opts.setupFile, t, now());
          if (!user) { fail([ipKey]); return dead(); }
          const pw = String(f.get('password') || '');
          if (pw.length > 1024 || pw.length < 10) return setupPage(t, user, w.short, 400);
          if (pw !== String(f.get('password2') || '')) return setupPage(t, user, w.differ, 400);
          setPassword(opts.usersFile, user, pw);                // the link is used up only once the password is written
          takeSetupToken(opts.setupFile, t, now());
          const stored = readUsers(opts.usersFile).get(user);
          return go(res, `${base}/`, { 'Set-Cookie': setCookie(req, makeToken(key, user, stored, now()), SESSION_DAYS * 86400) });
        } catch (e) {
          console.error(`login: ${e.stack || e}`);
          if (!res.headersSent) res.writeHead(500, { 'Cache-Control': 'no-store' });
          return res.end();
        }
      });
    }
    if (url.pathname === '/logout') {
      if (req.method === 'POST') {
        if (!sameOrigin(req)) return send(res, 403, page(lang, title, `<p class="err">${w.refused}</p>`));
        req.resume();
        return send(res, 200, page(lang, title, `<p>${w.gone}</p><p><a href="${esc(base)}/login">${w.again}</a></p>`),
          { 'Set-Cookie': setCookie(req, '', 0) });
      }
      return send(res, 200, page(lang, title, `<form method="post" action="${esc(base)}/logout"><button type="submit">${w.out}</button></form>`));
    }
    return send(res, 404, page(lang, title, '<p>404</p>'));
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

module.exports = { makeSetupToken, peekSetupToken, takeSetupToken, SETUP_MINUTES, hashPassword, verifyPassword, verifyPasswordAsync, readUsers, staleUsers, setPassword, makeToken, checkToken, loadKey,
                   createHandler, listen, MIN_PASSWORD, SESSION_DAYS, USER_RE };
