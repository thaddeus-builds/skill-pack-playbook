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
//
// The cookie holds user, expiry, a fingerprint of the user's stored hash and an HMAC
// with <console dir>/session.key. Removing a user or changing a password changes the
// fingerprint, so every session of that user ends at once; the logins file is read on
// each question. Honest limits: the key sits in the data dir, which the agent on a
// single-user host can read (the same as the console's secret); the login throttle is
// in memory and starts over with the service.

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
  if (log2n < 10 || log2n > 20 || r > 16 || p > 4) return null;
  return { log2n, r, p, salt: Buffer.from(m[4], 'base64url'), key: Buffer.from(m[5], 'base64url') };
}

function verifyPassword(pw, stored) {
  const h = parseHash(stored);
  if (!h || !h.key.length) return false;
  const got = crypto.scryptSync(pw, h.salt, h.key.length,
    { N: 1 << h.log2n, r: h.r, p: h.p, maxmem: SCRYPT.maxmem });
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
    if (k.length >= 32) return k;
  } catch { /* made below */ }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const k = crypto.randomBytes(32).toString('hex');
  fs.writeFileSync(file, `${k}\n`, { mode: 0o600 });
  fs.chmodSync(file, 0o600);
  return k;
}

// --- the page ---------------------------------------------------------------------------
const WORDS = {
  en: { title: 'Sign in', user: 'Username', pass: 'Password', go: 'Sign in', bad: 'Wrong username or password.',
        wait: 'Too many tries. Wait a little and try again.', out: 'Sign out', gone: 'You are signed out.', again: 'Sign in again',
        refused: 'The request did not come from this page.' },
  zh: { title: '登录', user: '用户名', pass: '密码', go: '登录', bad: '用户名或密码不对。',
        wait: '试得太多了，请稍等再试。', out: '退出登录', gone: '你已退出登录。', again: '重新登录',
        refused: '这个请求不是从本页发出的。' },
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
// opts: usersFile, keyFile, base ('/seo', '' for a site root), title, userHeader, now()
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
    if (!s.startsWith(`${base}/`) || s.startsWith('//') || /[\\\r\n]/.test(s) || s.startsWith(`${base}/login`) || s.startsWith(`${base}/logout`)) return `${base}/`;
    return s;
  };
  const blocked = (names) => names.some((k) => (fails.get(k)?.until || 0) > now());
  const fail = (names) => names.forEach((k) => {
    const e = fails.get(k) || { n: 0, until: 0 };
    e.n += 1;
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

  // the Origin of a POST must be the host the visitor used (a login CSRF is still a CSRF)
  const sameOrigin = (req) => {
    const o = req.headers.origin;
    if (!o) return true;
    try { return new URL(o).host === (req.headers['x-forwarded-host'] || req.headers.host); } catch { return false; }
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
      const next = String(req.headers['x-forwarded-uri'] || '');
      res.writeHead(302, { Location: `${base}/login${next ? `?next=${encodeURIComponent(next)}` : ''}`, 'Cache-Control': 'no-store' });
      return res.end();
    }
    if (url.pathname === '/login' && req.method === 'GET') {
      return send(res, 200, formPage(lang, title, base, safeNext(url.searchParams.get('next')), ''));
    }
    if (url.pathname === '/login' && req.method === 'POST') {
      if (!sameOrigin(req)) return send(res, 403, page(lang, title, `<p class="err">${w.refused}</p>`));
      return readForm(req, res, (f) => {
        const name = String(f.get('username') || '').trim();
        const next = safeNext(f.get('next'));
        const names = [`ip:${ipOf(req)}`, `user:${name.toLowerCase()}`];
        if (blocked(names)) return send(res, 429, formPage(lang, title, base, next, w.wait));
        const users = readUsers(opts.usersFile);
        const stored = users.get(name);
        const ok = verifyPassword(String(f.get('password') || ''), stored && parseHash(stored) ? stored : DUMMY) && Boolean(stored && parseHash(stored));
        if (!ok) { fail(names); return send(res, 401, formPage(lang, title, base, next, w.bad)); }
        fails.delete(names[1]);
        return go(res, next, { 'Set-Cookie': setCookie(req, makeToken(key, name, stored, now()), SESSION_DAYS * 86400) });
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

// Listen on a unix socket made private before the first connection.
function listen(opts) {
  const server = http.createServer(createHandler(opts));
  try { fs.rmSync(opts.sock, { force: true }); } catch { /* a stale socket we cannot remove fails below */ }
  const old = process.umask(0o177);
  server.listen(opts.sock, () => { process.umask(old); try { fs.chmodSync(opts.sock, 0o600); } catch { /* listen already made it 0600 */ } });
  server.on('error', () => process.umask(old));
  return server;
}

module.exports = { hashPassword, verifyPassword, readUsers, staleUsers, setPassword, makeToken, checkToken, loadKey,
                   createHandler, listen, MIN_PASSWORD, SESSION_DAYS, USER_RE };
