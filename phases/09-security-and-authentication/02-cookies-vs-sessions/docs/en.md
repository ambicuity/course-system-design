# Cookies vs Sessions

> HTTP is stateless by design — cookies and sessions are the two strategies for bolting state back on, and choosing the wrong one at the wrong layer will bite you in production.

**Type:** Learn
**Prerequisites:** HTTP fundamentals, Stateless vs Stateful systems, Authentication basics
**Time:** ~25 minutes

---

## The Problem

HTTP was designed as a stateless protocol: every request is independent, and the server has no memory of previous requests from the same client. This is great for caching and horizontal scaling, but it creates an immediate problem for any app that needs to know *who* is making a request.

Consider an e-commerce checkout flow. A user logs in, adds items to a cart, enters shipping details, and completes payment — across five or more separate HTTP requests. Without some mechanism to carry identity and state between those requests, every page would demand a fresh login and every cart would be empty. The server needs a way to answer "is this the same person I authenticated three requests ago?"

Two patterns dominate: **cookies** (where the browser holds the state) and **server-side sessions** (where the server holds the state and the browser carries only an opaque reference ID). Both use the `Set-Cookie` header to store something on the client, which is why people conflate them — but the *where* and *what* of what's stored have profoundly different security, scalability, and operational consequences.

---

## The Concept

### How Cookies Work

A cookie is a small piece of data the server instructs the browser to store and automatically resend on every subsequent request to the same origin. The server sets it with a `Set-Cookie` response header; the browser stores it and includes it in a `Cookie` request header on matching future requests.

```
Browser                          Server
  |                                |
  |  POST /login  (credentials)    |
  |------------------------------> |
  |                                |  verify credentials
  |  200 OK                        |
  |  Set-Cookie: user_id=42;       |
  |    HttpOnly; Secure; SameSite=Strict
  |<------------------------------ |
  |                                |
  |  GET /dashboard                |
  |  Cookie: user_id=42            |
  |------------------------------> |
  |                                |  read user_id=42 from cookie
  |  200 OK  (personalized page)   |
  |<------------------------------ |
```

The **data lives in the browser**. No server-side storage is required. The server trusts what the cookie says (after signature verification if signed).

**Key cookie attributes:**

| Attribute | What it does |
|-----------|-------------|
| `HttpOnly` | Cookie inaccessible to JavaScript — blocks XSS theft |
| `Secure` | Only transmitted over HTTPS |
| `SameSite=Strict` | Never sent on cross-site requests — blocks CSRF |
| `SameSite=Lax` | Sent on top-level navigations, blocked on sub-resources |
| `Max-Age` / `Expires` | Lifetime; absence = session cookie (deleted when browser closes) |
| `Domain` | Which domains receive the cookie |
| `Path` | URL prefix scope |

### How Server-Side Sessions Work

A session stores state **on the server** (memory, Redis, a database). The browser receives only an opaque, random session ID (a UUID or similar token) in a cookie. On each request, the server uses that ID to look up the full session record.

```
Browser                          Server                     Session Store
  |                                |                              |
  |  POST /login  (credentials)    |                              |
  |------------------------------> |                              |
  |                                |  generate session_id=abc123  |
  |                                |  store {user_id:42, role:"admin"} -> |
  |  200 OK                        |                              |
  |  Set-Cookie: session_id=abc123; HttpOnly; Secure
  |<------------------------------ |                              |
  |                                |                              |
  |  GET /dashboard                |                              |
  |  Cookie: session_id=abc123     |                              |
  |------------------------------> |                              |
  |                                |  GET session_id=abc123 ----> |
  |                                |  <-- {user_id:42, role:"admin"}
  |                                |  render page for user 42     |
  |  200 OK                        |                              |
  |<------------------------------ |                              |
```

The **data lives on the server**. The browser only knows an ID. Invalidating a session is instant — delete the record.

### Side-by-Side Comparison

| Dimension | Cookie (client-side state) | Server-Side Session |
|-----------|---------------------------|---------------------|
| State lives in | Browser (client) | Server store (memory/Redis/DB) |
| What browser holds | The actual data (or signed token) | Opaque session ID only |
| Server storage needed | No | Yes |
| Horizontal scaling | Easy — any server can verify | Requires shared store or sticky sessions |
| Logout / invalidation | Must wait for cookie to expire (or use a blocklist) | Delete session record — immediate |
| Data exposure risk | Data in cookie visible if not encrypted | Data never leaves server |
| Cookie size limit | ~4 KB | ID is tiny (few dozen bytes) |
| Network overhead | Cookie data sent on every request | Only ID sent; data fetched server-side |
| Revocation complexity | Hard without extra infrastructure | Trivially easy |

### The "Cookie" vs "Session" Naming Trap

The word *session* has two meanings in practice:

1. **Session cookie** — a cookie with no `Max-Age`/`Expires` attribute. The browser deletes it when it closes. This says nothing about whether state is client-side or server-side.
2. **Server-side session** — the pattern described above where the server holds the state.

A server-side session *uses* a session cookie to store the ID. They are different concepts despite sharing the word.

### Under the Hood: What Makes a Cookie "Secure"

Without signing or encryption, a plain-value cookie like `user_id=42` is trivially forgeable — any user can set that cookie to `user_id=1` and impersonate an admin. Real systems do one of two things:

**Option A — HMAC signature (common for simple cookies):**
```
value = base64(user_id=42)
signature = HMAC-SHA256(secret_key, value)
cookie = value.signature
```
The server recomputes the signature and rejects any cookie where they don't match. The data is readable but tamper-evident.

**Option B — Encryption (JWT or encrypted session token):**
The payload is encrypted so it is neither readable nor forgeable without the key. JWTs (JSON Web Tokens) serialize this as `header.payload.signature` and are a common form of client-side stateful cookie.

**Option C — Opaque session ID (server-side session):**
The ID itself carries no information. Even if stolen, it reveals nothing about the user's data — only about their active session.

---

## Build It / In Depth

### Step 1: Bare Cookie Auth (Python / Flask)

```python
from flask import Flask, request, make_response, redirect
import hashlib, hmac, base64, os

app = Flask(__name__)
SECRET = os.environ["COOKIE_SECRET"]  # e.g. a 32-byte random value

def sign(value: str) -> str:
    sig = hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).digest()
    return value + "." + base64.urlsafe_b64encode(sig).decode()

def verify(signed: str) -> str | None:
    if "." not in signed:
        return None
    value, sig_b64 = signed.rsplit(".", 1)
    expected = sign(value)
    if hmac.compare_digest(expected, signed):
        return value
    return None

@app.post("/login")
def login():
    username = request.form["username"]
    # ... verify credentials against DB ...
    resp = make_response(redirect("/dashboard"))
    resp.set_cookie(
        "user",
        sign(f"id=42&name={username}"),
        httponly=True,
        secure=True,
        samesite="Strict",
        max_age=3600,
    )
    return resp

@app.get("/dashboard")
def dashboard():
    raw = request.cookies.get("user")
    payload = verify(raw) if raw else None
    if not payload:
        return redirect("/login")
    return f"Hello, {payload}"
```

This is stateless cookie auth. No database call needed for the session itself.

### Step 2: Server-Side Session with Redis

```python
import redis, uuid, json
from flask import Flask, request, make_response, redirect

app = Flask(__name__)
r = redis.Redis(host="localhost", port=6379, db=0)
SESSION_TTL = 3600  # seconds

def create_session(data: dict) -> str:
    session_id = str(uuid.uuid4())
    r.setex(f"session:{session_id}", SESSION_TTL, json.dumps(data))
    return session_id

def get_session(session_id: str) -> dict | None:
    raw = r.get(f"session:{session_id}")
    return json.loads(raw) if raw else None

def delete_session(session_id: str):
    r.delete(f"session:{session_id}")

@app.post("/login")
def login():
    # ... verify credentials ...
    session_id = create_session({"user_id": 42, "role": "admin"})
    resp = make_response(redirect("/dashboard"))
    resp.set_cookie(
        "session_id",
        session_id,
        httponly=True,
        secure=True,
        samesite="Strict",
        max_age=SESSION_TTL,
    )
    return resp

@app.get("/dashboard")
def dashboard():
    session_id = request.cookies.get("session_id")
    session = get_session(session_id) if session_id else None
    if not session:
        return redirect("/login")
    return f"Hello user {session['user_id']} (role: {session['role']})"

@app.post("/logout")
def logout():
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)
    resp = make_response(redirect("/login"))
    resp.delete_cookie("session_id")
    return resp
```

Notice logout is now instant and reliable — deleting the Redis key means the session ID is immediately invalid, even if the cookie persists in the browser.

### Step 3: Inspecting Cookies in the Browser

```bash
# Check cookie headers on a response
curl -v -c cookies.txt https://example.com/login \
  -d "username=alice&password=secret" 2>&1 | grep -i 'set-cookie'

# Subsequent request with stored cookies
curl -v -b cookies.txt https://example.com/dashboard
```

### Decision Procedure

```
Need to support logout / revocation?
  YES -> Server-side session (delete session record)
  NO  -> Cookie can work if data is small enough

Is the payload > 2 KB?
  YES -> Server-side session (cookie size limit)
  NO  -> Either works

Multiple services need to read session state?
  YES -> Shared session store (Redis) or signed JWT passed between services
  NO  -> Either works

Stateless / edge-deployed architecture?
  YES -> Signed or encrypted cookie (JWTs) — no server store to share
  NO  -> Server-side session is simpler to reason about
```

---

## Use It

### Frameworks and Default Choices

| Framework / Tool | Default approach | Notes |
|-----------------|-----------------|-------|
| Flask (flask-session) | Server-side (filesystem/Redis) | `SESSION_TYPE = "redis"` |
| Django | Server-side (DB or cache) | `SESSION_ENGINE` configurable |
| Express (express-session) | Server-side (MemoryStore by default) | MemoryStore leaks — use connect-redis in prod |
| Rails | Cookie-based (encrypted) | `ActionDispatch::Session::CookieStore` by default |
| Next.js / Iron Session | Encrypted cookie | Stateless, edge-friendly |
| Laravel | Server-side (file/DB/Redis) | Configurable via `SESSION_DRIVER` |

### JWT as a Client-Side Session Cookie

JWTs are commonly stored in `HttpOnly` cookies (not `localStorage` — that is XSS-accessible). A JWT-in-cookie setup behaves like a signed encrypted cookie:

```
Set-Cookie: token=eyJhbGci...; HttpOnly; Secure; SameSite=Strict
```

Trade-offs vs opaque session ID:
- No server store needed — great for stateless microservices
- Revocation is hard: JWTs are valid until expiry; use short TTLs (15 min) + refresh token pattern
- Payload visible (base64 decoded) unless encrypted — use JWE for sensitive claims

### When to Use Each

**Use server-side sessions when:**
- You need reliable, instant logout (financial apps, admin panels)
- Session data is large or sensitive
- You are building a monolith or have a shared Redis cluster
- You need fine-grained session management (view all active sessions, kill one)

**Use client-side cookies (signed/encrypted) when:**
- You are deploying to edge functions or serverless with no shared store
- You need stateless horizontal scaling without a Redis dependency
- Token size is small and revocation requirements are soft (short TTL)
- You are building an API consumed by mobile apps alongside browsers

---

## Common Pitfalls

- **Storing sensitive data in unsigned cookies.** A plain `user_id=42` cookie is trivially forgeable. Always sign (HMAC) or encrypt cookie payloads. Never store roles, permissions, or PII in a cookie without cryptographic protection.

- **Using MemoryStore in production for server-side sessions.** Express's default in-memory session store leaks memory, doesn't survive restarts, and is not shared across processes. Always configure Redis or another durable backend before going to production.

- **Missing `HttpOnly` and `Secure` flags.** Without `HttpOnly`, any XSS attack can read your session cookie via `document.cookie`. Without `Secure`, the cookie travels in plaintext on non-HTTPS connections. Both flags must always be set for authentication cookies.

- **Forgetting SameSite.** Without `SameSite=Strict` or `SameSite=Lax`, your session cookie is sent on cross-site requests, making it vulnerable to CSRF. Modern browsers default to `Lax` but you should set it explicitly.

- **Assuming deleting the cookie logs the user out.** With server-side sessions, logout must delete the server-side session record *and* clear the cookie. Cookie-only approaches cannot guarantee logout — if an attacker captured the cookie before logout, it remains valid until it expires. Address this with short TTLs or a token revocation blocklist.

- **Setting overly long cookie expiry.** A `Max-Age` of one year is a long window for a stolen session cookie to be abused. Match expiry to your actual security requirements: authentication cookies should typically expire in hours, not weeks, unless paired with refresh token rotation.

---

## Exercises

1. **Easy** — Set up a minimal Python Flask app with a login route. On successful login, set a signed cookie using HMAC-SHA256. On a protected `/profile` route, verify the signature and display the user's name. Use `curl` to confirm the cookie is present and that tampering the value causes a redirect to `/login`.

2. **Medium** — Extend the Flask app to use Redis-backed server-side sessions instead of signed cookies. Implement a `/logout` route that deletes the Redis session record. Then, using two separate browser tabs, verify that logging out in one tab invalidates the session in the other tab on next refresh.

3. **Hard** — Design a session management system for a banking application that: (a) uses server-side sessions stored in Redis with a 15-minute idle timeout, (b) shows the user a list of all their active sessions (device, IP, last seen), (c) allows killing any individual session, and (d) forcibly terminates all sessions on password change. Sketch the Redis key schema, the relevant API endpoints, and how the "last seen" TTL sliding window is implemented without a write on every request.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Cookie | A way to store login info in the browser | A key-value string the browser stores and automatically sends to the server; can hold any small data, not just auth |
| Session | A server-side concept only | An ambiguous word: can mean a server-side session record *or* a "session cookie" (one that expires when the browser closes) — context determines which |
| Session cookie | A secure, server-backed session | A cookie with no `Expires`/`Max-Age` attribute; the browser discards it on close regardless of server-side backing |
| `HttpOnly` | Encrypts the cookie | Prevents JavaScript from reading the cookie via `document.cookie`; the cookie is still transmitted in plaintext unless `Secure` is also set |
| CSRF | Stealing a cookie | Tricking a victim's browser into making an authenticated request to a site using their existing cookies, without needing to steal them |
| JWT | A session replacement | A signed (and optionally encrypted) JSON token; can be used as a stateless session but carries its own revocation challenges |
| Session store | The browser's cookie jar | The server-side storage (Redis, DB, memory) where session data is persisted; the browser only holds the ID |

---

## Further Reading

- [MDN Web Docs — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies) — definitive reference for all cookie attributes, SameSite behavior, and browser handling
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — production-grade guidance on session ID generation, secure transport, expiry, and invalidation
- [RFC 6265 — HTTP State Management Mechanism](https://datatracker.ietf.org/doc/html/rfc6265) — the actual cookie specification; essential when debugging edge-case browser behavior
- [Auth0 Blog — Cookies vs Tokens](https://auth0.com/blog/cookies-vs-tokens-definitive-guide/) — practical comparison focusing on JWT tokens in cookies vs localStorage, with security implications for SPAs
- [Redis Documentation — Keyspace Notifications](https://redis.io/docs/manual/keyspace-notifications/) — useful for implementing session expiry callbacks and "last active" tracking in Redis-backed session stores
