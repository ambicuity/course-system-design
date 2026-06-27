# Cookies Vs Sessions Vs JWT Vs PASETO

> HTTP has no memory — every request starts from zero, and it is your auth layer's job to fix that.

**Type:** Learn
**Prerequisites:** HTTP fundamentals, REST API design, Basic cryptography concepts
**Time:** ~35 minutes

---

## The Problem

HTTP is a stateless protocol. Once the server sends a response, it forgets the client ever existed. That is fine for fetching a public web page, but it creates an immediate problem for anything that requires identity: a user logs in on request #1, and by request #2 the server has no idea who they are.

The naive fix — sending credentials on every request — is both insecure and impractical. Instead, systems issue some kind of token or identifier after a successful login and the client presents that proof on subsequent requests. The mechanism you choose determines where state lives, how revocation works, how you scale, and how badly you are hurt when something goes wrong.

Consider an e-commerce checkout. A user adds items to a cart (request A), updates their address (request B), and submits payment (request C). All three requests must be tied to the same authenticated identity. If your session mechanism is broken or improperly configured, request C could be processed for the wrong user, or an attacker who steals a token could complete the purchase using someone else's payment method. Getting this right is foundational, not optional.

---

## The Concept

### Cookies — The Transport Layer

A **cookie** is a small key-value pair the browser stores and automatically re-sends in the `Cookie` header on every matching request. The server sets cookies via the `Set-Cookie` response header.

Cookies are not an auth mechanism on their own — they are a *delivery vehicle*. What matters is what you put inside them and the flags you attach.

Key cookie attributes:

| Attribute | Effect |
|---|---|
| `HttpOnly` | Cookie is invisible to JavaScript — blocks XSS-based theft |
| `Secure` | Cookie is only sent over HTTPS |
| `SameSite=Strict` | Cookie is not sent on cross-site requests — blocks CSRF |
| `SameSite=Lax` | Sent on top-level navigation GET, blocked on cross-site POST |
| `Expires` / `Max-Age` | Session cookie (no expiry) vs persistent cookie |
| `Path` / `Domain` | Scope restrictions for which URLs receive the cookie |

**Always** combine `HttpOnly`, `Secure`, and `SameSite=Strict` (or `Lax`) on any auth cookie. Missing even one of these opens a class of attack.

---

### Sessions — Server-Side State

A **session** pairs a random, opaque identifier (the session ID) stored in a cookie with actual user data stored on the server. The server is the source of truth.

```
Login flow (server-side session):

Client                        Server                    Session Store
  |                              |                           |
  |-- POST /login (user+pass) -->|                           |
  |                              |-- store session data ---->|
  |<-- Set-Cookie: sid=abc123 ---|                           |
  |                              |                           |
  |-- GET /dashboard (sid=abc123)|                           |
  |                              |-- lookup sid=abc123 ----->|
  |                              |<-- {userId, roles, ...} --|
  |<-- 200 OK (dashboard) -------|                           |
```

The session store can be an in-memory dict (fine for a single server), Redis (standard for distributed systems), or a database. When the user logs out or the session expires, the server deletes the record and the cookie becomes worthless.

**Properties of session auth:**

- **Revocation is instant** — delete the session record and the user is logged out everywhere.
- **Server memory grows with users** — each active user costs storage in your session store.
- **Sticky sessions or shared store required** — in a horizontally scaled fleet, every server must reach the same session store, or requests must always route to the same server.

---

### JWT — Stateless Self-Contained Tokens

A **JSON Web Token** (JWT, pronounced "jot") encodes claims directly inside a signed token. The server issues a token at login and never stores it. On each request, the server only needs to *verify the signature* — no database round-trip.

**Structure:** `header.payload.signature` — three Base64url-encoded segments separated by dots.

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9   ← header
.eyJ1c2VySWQiOiI0MiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTcxNzAwMDAwMH0
.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c   ← signature
```

Decoded header: `{"alg": "HS256", "typ": "JWT"}`
Decoded payload: `{"userId": "42", "role": "admin", "exp": 1717000000}`

**Standard claims:**

| Claim | Meaning |
|---|---|
| `iss` | Issuer — who created the token |
| `sub` | Subject — who the token is about |
| `aud` | Audience — who should accept it |
| `exp` | Expiry timestamp (Unix epoch) — MUST be checked |
| `iat` | Issued-at timestamp |
| `jti` | JWT ID — unique identifier for the token |

**Algorithms matter:**

- `HS256` — HMAC-SHA256. Symmetric: the same secret signs *and* verifies. If you share your API with a third party, they can also forge tokens.
- `RS256` — RSA-SHA256. Asymmetric: private key signs, public key verifies. Safe to publish the verification key.
- `ES256` — ECDSA-SHA256. Same asymmetric model as RS256 but with shorter keys.

**The critical flaw — `alg: none`:** Early JWT libraries accepted a token with no signature if the header declared `alg: none`. An attacker could remove the signature, set `alg: none`, change the payload to `role: admin`, and the server would accept it. Never use a library that permits this and always explicitly whitelist your expected algorithm.

**Revocation problem:** Because the server is stateless, it cannot "cancel" a token before its `exp`. If a JWT is stolen, it is valid until it expires. The only practical mitigation is short expiry windows (5–15 minutes) combined with a refresh token flow, or maintaining a small deny-list (at which point you lose some of the stateless benefit).

```
JWT verification flow (no session store needed):

Client                        Server
  |                              |
  |-- GET /api (Bearer jwt) ---->|
  |                              |-- decode header
  |                              |-- verify signature (local key)
  |                              |-- check exp, iss, aud
  |<-- 200 OK -------------------|
```

---

### PASETO — A Safer Token Standard

**PASETO** (Platform-Agnostic Security Tokens) was designed specifically to eliminate the footguns in JWT. Where JWT lets you pick from a menu of algorithms (some of which are dangerous), PASETO gives you a small set of versioned, opinionated specs.

**Versions:**

| Version | Symmetric (local) | Asymmetric (public) |
|---|---|---|
| v1 (legacy) | AES-256-CTR + HMAC-SHA384 | RSA-PSS with SHA384 |
| v2 (deprecated) | XSalsa20Poly1305 | Ed25519 |
| v3 | AES-256-CTR + HMAC-SHA384 | ECDSA over P-384 |
| v4 (current) | XChaCha20-Poly1305 | Ed25519 |

**Two token purposes:**

- **local** — symmetric encryption. The payload is encrypted and authenticated. Only parties with the shared key can read or verify it. Use for tokens that stay within your own infrastructure.
- **public** — asymmetric signing. The payload is readable (like JWT) but signed with a private key; anyone with the public key can verify. Use when you need to share tokens with third parties.

PASETO tokens are not JWTs. The format is `v4.local.<base64url>` or `v4.public.<base64url>`. Because the version is baked into the token prefix, there is no `alg` field an attacker can manipulate.

**Why PASETO over JWT?**

1. No algorithm confusion attacks — the algorithm is fixed by the version.
2. No `alg: none` possible.
3. Modern symmetric tokens use authenticated encryption (AEAD), so local tokens hide the payload from anyone without the key.
4. Footgun surface is dramatically smaller.

---

### Side-by-Side Comparison

| Property | Cookie+Session | JWT | PASETO |
|---|---|---|---|
| State location | Server-side store | Client-side token | Client-side token |
| Revocation | Instant (delete record) | Hard (wait for expiry) | Hard (same as JWT) |
| Scalability | Requires shared store | Fully stateless | Fully stateless |
| Payload visibility | Hidden (server-side) | Visible (Base64) | local: encrypted; public: visible |
| Algorithm agility | N/A | Dangerous — too many options | Safe — version-pinned |
| Token size | Tiny (ID only) | Medium (base64 JSON) | Similar to JWT |
| Browser support | Native | Manual (localStorage or cookie) | Manual |
| Revocation complexity | O(1) delete | Need deny-list | Need deny-list |

---

## Build It / In Depth

### Step 1 — Session-Based Auth (Python + Redis)

```python
import secrets
import redis
import json
from datetime import timedelta

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

def create_session(user_id: str, roles: list[str]) -> str:
    session_id = secrets.token_hex(32)          # cryptographically random
    payload = json.dumps({"userId": user_id, "roles": roles})
    r.setex(f"session:{session_id}", timedelta(hours=8), payload)
    return session_id

def validate_session(session_id: str) -> dict | None:
    raw = r.get(f"session:{session_id}")
    if not raw:
        return None                             # expired or revoked
    return json.loads(raw)

def revoke_session(session_id: str) -> None:
    r.delete(f"session:{session_id}")           # instant revocation
```

The session ID goes into a cookie: `Set-Cookie: sid=<session_id>; HttpOnly; Secure; SameSite=Strict`.

---

### Step 2 — JWT Issuance and Verification (Python + PyJWT)

```python
import jwt
import time

SECRET = "your-256-bit-secret"        # or load RSA key pair for RS256

def issue_token(user_id: str, roles: list[str]) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "roles": roles,
        "iat": now,
        "exp": now + 900,              # 15-minute access token
        "iss": "api.example.com",
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

def verify_token(token: str) -> dict:
    # CRITICAL: whitelist the algorithm — never pass algorithms=None
    return jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],          # explicit allowlist
        options={"require": ["exp", "iss", "sub"]},
        issuer="api.example.com",
    )
```

---

### Step 3 — PASETO v4 Local Token (Python + python-paseto)

```python
from pyseto import Key, Paseto

key = Key.new(version=4, purpose="local", key=secrets.token_bytes(32))
paseto = Paseto.new(exp=900)           # 15-minute expiry

# Issue
token = paseto.encode(key, payload={"userId": "42", "role": "admin"})
# Returns: "v4.local.<encrypted-base64url>"

# Verify and decrypt
claims = paseto.decode(key, token)
print(claims.payload)                  # {"userId": "42", "role": "admin"}
```

The `v4.local` prefix is fixed — there is no way to swap in a weaker algorithm at the token level.

---

### Step 4 — Refresh Token Pattern (JWT or PASETO)

Short-lived access tokens plus a longer-lived refresh token solve the revocation problem without giving up most of the stateless benefit.

```
  Client                 Auth Server              Resource Server
    |                        |                          |
    |-- POST /login -------->|                          |
    |<-- access_token (15m) -|                          |
    |   refresh_token (7d)   |                          |
    |                        |                          |
    |-- GET /api (access) -->|-- verify (stateless) --->|
    |<-- 200 OK -------------|<-- 200 OK ---------------|
    |                        |                          |
    |-- (access expired) ----|                          |
    |-- POST /refresh ------>|                          |
    |   (refresh_token)      |-- check deny-list ------>|
    |<-- new access_token ---|                          |
```

Store refresh tokens server-side (a small table of `jti` → status). When a user logs out, add the refresh token's `jti` to the deny-list. Access tokens remain stateless — the deny-list only needs to cover the refresh token lifetime.

---

## Use It

**Cookie + Session** is the default choice for traditional web applications with server-rendered HTML. Rails, Django, Express session middleware, and PHP all default to this model. It is simple, revocation works perfectly, and the browser handles the cookie automatically. Use it when your backend is a monolith or a small cluster sharing a Redis session store.

**JWT** is the dominant choice for API-first systems, mobile apps, and SPAs communicating with multiple microservices. Microservices can verify tokens locally without calling a central auth server. Use `RS256` or `ES256` (asymmetric) when different services need to verify tokens but should not be able to issue them. Use short expiry + refresh tokens to reduce the blast radius of token theft. Libraries exist in every language.

**PASETO** is the right default for new greenfield token systems where you control both the issuer and verifiers. Choose `v4.local` for tokens that never leave your infrastructure (most service-to-service auth). Choose `v4.public` as a drop-in JWT replacement when you need third parties to verify tokens without sharing a secret. Adoption is growing but the ecosystem is smaller than JWT; check that your language has a mature library before committing.

**OAuth 2.0 / OIDC** builds on top of all three — the access token format (opaque, JWT, or PASETO) is a separate decision from the OAuth flow you use. OIDC mandates JWTs for ID tokens.

| Scenario | Recommended approach |
|---|---|
| Server-rendered web app, single region | Cookie + Session (Redis) |
| SPA + REST API, single backend | JWT (short-lived) in `Authorization: Bearer` |
| Microservices, service-to-service | JWT RS256 or PASETO v4.public |
| High-security internal tokens | PASETO v4.local |
| Third-party integrations (OAuth) | JWT (per OIDC spec) |
| Need instant revocation on logout | Cookie + Session OR JWT + deny-list |

---

## Common Pitfalls

- **Storing JWTs in `localStorage`** — localStorage is accessible to any JavaScript on the page. An XSS vulnerability anywhere on your domain lets an attacker steal the token and use it from their own machine. Prefer `HttpOnly` cookies (with `SameSite=Strict`) to deliver JWTs or session IDs; the browser sends the cookie automatically and JavaScript cannot read it.

- **Not validating `exp`, `iss`, and `aud` on JWTs** — many older libraries default to ignoring claims unless you explicitly opt in. A token accepted after expiry or from a different issuer breaks the entire security model. Always explicitly configure required claims and trusted issuers.

- **Algorithm confusion with JWT `alg: HS256` vs `RS256`** — if your library reads the algorithm from the token header and you switch between symmetric and asymmetric keys, an attacker can craft a token signed with the public key (which is public knowledge), set `alg: HS256`, and your server will verify it against the public key used as an HMAC secret. Whitelist the single algorithm you expect; never let the token tell the server which algorithm to use.

- **Sessions without a shared store in a load-balanced cluster** — if server A issues a session and server B handles the next request, server B has no record of it. The user gets logged out randomly. Always use a centralized session store (Redis is standard) rather than in-process memory when running more than one server.

- **Trusting the `sub` claim without verifying the signature** — Base64 is not encryption. Anyone can decode a JWT payload without a key. Never treat the payload as secure until the signature is verified. Similarly, never skip expiry checks because "we rotate keys so old tokens are useless."

---

## Exercises

1. **(Easy)** Take an existing JWT (you can generate one at jwt.io) and decode the header and payload without using any library. Identify the algorithm, subject, and expiry. Explain why this is safe to do but does not mean the token is authentic.

2. **(Medium)** Implement a minimal session auth system for a REST API using any language. Add a `/logout` endpoint that correctly invalidates the session. Then refactor the storage layer so you can swap Redis for an in-memory dict without changing the endpoint code.

3. **(Hard)** Design the auth architecture for a system with three components: a user-facing SPA, a Node.js BFF (Backend for Frontend), and five internal microservices. Decide which token format each boundary uses, where tokens are stored on the client, how logout propagates across all services, and how you handle a compromised access token before its expiry. Write a one-page design doc with your trade-offs.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Cookie | A small piece of auth data | A general-purpose HTTP key-value transport; auth data is what you put *in* it |
| Session | Synonymous with "being logged in" | A server-side record keyed by a random ID sent to the client via cookie |
| JWT | A secure encrypted token | A Base64url-encoded, *signed* (not encrypted) JSON structure; the payload is fully readable |
| Stateless auth | No server storage needed at all | No per-request session lookup; the server still needs keys and may need a deny-list |
| PASETO | "JWT but safer, same idea" | A separate token standard with fixed algorithms per version, eliminating algorithm agility attacks |
| Refresh token | Just a longer-lived JWT | A credential used to obtain new access tokens; should be stored server-side and revocable |
| `alg: none` | An edge case that no one ships | A real historical attack vector where JWT libraries accepted unsigned tokens |

---

## Further Reading

- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) — the authoritative spec covering all standard claims and the signing/encryption model.
- [PASETO Specification (GitHub)](https://github.com/paseto-standard/paseto-spec) — full spec for all PASETO versions with rationale for each cryptographic choice.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — practical guidance on cookie flags, session fixation, and secure logout.
- [Auth0 — JWT Handbook](https://auth0.com/resources/ebooks/jwt-handbook) — free deep-dive covering JWT structure, use cases, and common vulnerabilities with code examples.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://datatracker.ietf.org/doc/html/rfc9700) — if you are building on top of OAuth 2.0, this is the security guidance that supersedes the original RFC 6749 recommendations.
