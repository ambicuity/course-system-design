# 5 REST API Authentication Methods

> Choosing the wrong auth method doesn't break your API — it just breaks it later, at 3 AM, in production.

**Type:** Learn
**Prerequisites:** HTTP fundamentals, stateless vs. stateful design, HTTPS/TLS basics
**Time:** ~25 minutes

---

## The Problem

You've built an API endpoint — `GET /api/orders` — that returns every order in your database. Publicly exposing it means anyone with a browser can harvest your data. You need a way for the server to answer: *who is calling me, and are they allowed to?*

The naive solution — a shared password in the URL — breaks immediately under load: passwords leak through logs, browsers cache URLs, and there's no way to revoke access per-client. Each of the five methods that emerged as industry standards solves a distinct version of this problem: internal scripts need simplicity, web apps need sessions, mobile SPAs need stateless tokens, third-party integrations need delegated permission grants, and machine-to-machine traffic needs opaque keys.

Pick the wrong method and you'll either ship something too weak to protect real data, or something so complex your own team can't operate it. The goal here is a crisp mental model of when each method applies, what its security boundary is, and what breaks at scale.

---

## The Concept

Authentication answers "who are you?" by verifying a credential. For REST APIs the credential travels with every request — REST is stateless, so the server must be able to authenticate the caller from the request alone (or from a session ID that points to server-side state).

### The Five Methods at a Glance

| Method | Credential type | State | Best for |
|---|---|---|---|
| Basic Auth | username + password | Stateless | Quick prototypes, internal tools |
| Session Auth | Session cookie → server-side record | Stateful | Traditional web apps, server-rendered HTML |
| Token Auth (JWT) | Signed token (opaque or self-describing) | Stateless | SPAs, mobile apps, microservices |
| OAuth 2.0 | Access token via authorization grant | Token is stateless; grant flow is stateful | Third-party integrations, delegated access |
| API Key | Pre-shared secret key | Stateless | Machine-to-machine, service-to-service |

### How Each Method Works

**1. Basic Authentication**

The client encodes `username:password` in Base64 and sends it in the `Authorization` header on every single request:

```
Authorization: Basic dXNlcjpwYXNzd29yZA==
```

The server decodes the header, looks up the user, and compares hashes. Base64 is **not encryption** — it's encoding. Without HTTPS, credentials are plaintext on the wire. Even with HTTPS, the credential is sent with every request, widening the exposure window. There is also no built-in revocation mechanism shorter than changing the password.

**2. Session Authentication**

```
Client          Server
  |-- POST /login (user+pass) -->|
  |                              | Creates session in DB/Redis
  |<-- 200 OK, Set-Cookie: sid=abc |
  |                              |
  |-- GET /orders (Cookie: sid=abc) -->|
  |                              | Looks up sid → user
  |<-- 200 OK [orders] ----------|
```

The server holds the session record. The cookie is just a pointer. This means every server in a cluster must share the session store (Redis, Memcached, or a database), or you must use sticky sessions. Revocation is instant — delete the session row. CSRF attacks are a real threat because cookies are sent automatically by browsers.

**3. Token Authentication (JWT)**

After login the server issues a signed token containing claims. The most common format is JSON Web Token (JWT):

```
Header.Payload.Signature
eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIiwiZXhwIjoxNzA1MDAwMDAwfQ.abc...
```

The payload is Base64-decoded by anyone — it is not secret. The **signature** (HMAC-SHA256 or RS256) proves the server issued it. Because the token is self-describing, the server does not need a database lookup — just verify the signature and check `exp`. This makes JWTs horizontally scalable. The downside: revocation requires either short expiry + refresh tokens, or a token deny-list (which reintroduces state).

**4. OAuth 2.0**

OAuth solves a different problem: *delegated authorization*. A user grants your app permission to act on their behalf at another service (e.g., reading their Google Calendar), without giving your app their Google password.

```
User      Your App      Auth Server (Google)    Resource Server
  |-------> |                                    |
  |         |-- Authorization Request ---------->|
  |<---------|-- Redirect to consent screen -----|
  |          |                                   |
  |----------|-- User grants permission -------->|
  |          |<-- Authorization Code ------------|
  |          |-- Exchange code for token ------->|
  |          |<-- Access Token + Refresh Token --|
  |          |                                   |
  |          |-- GET /calendar (Bearer token) -->|
  |          |<-- Calendar data -----------------|
```

The access token is then used exactly like a Bearer token on the resource server. OAuth is not authentication by itself — OpenID Connect (OIDC) adds an `id_token` on top of OAuth to confirm user identity.

**5. API Key Authentication**

A static, opaque string issued once per client. Common in two delivery styles:

- **Header:** `X-API-Key: sk_live_abc123` (preferred)
- **Query string:** `?api_key=sk_live_abc123` (logs exposure risk)

The server maintains a lookup table: key → permissions + rate-limit bucket. Simple, but the key must be treated like a password. No expiry by default — rotation is manual.

---

## Build It / In Depth

### Comparing the Full Request Lifecycle

Below is a concrete decision walkthrough for a fintech API that needs to support three clients: a browser-based dashboard, a mobile app, and a partner's backend service.

**Scenario: GET /api/v1/transactions**

```
Client A: Browser dashboard (needs CSRF protection, server-rendered)
  → Session Auth: cookie + SameSite=Strict + CSRF token on mutations

Client B: React SPA / iOS app (no server-side session store, must scale)
  → JWT: short-lived access token (15 min) + refresh token (7 days, HttpOnly cookie)

Client C: Partner backend calling nightly (service-to-machine, no user involved)
  → API Key: key in X-API-Key header, IP allowlist, per-key rate limit
```

### JWT in Practice (Python / FastAPI)

```python
import jwt
from datetime import datetime, timedelta, timezone

SECRET = "super-secret-key"  # In prod: load from env, use RS256 with private key

def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired — client must refresh")
    except jwt.InvalidTokenError:
        raise ValueError("Token invalid")
```

### OAuth 2.0 Client Credentials (Machine-to-Machine)

When your backend calls another backend (no user involved), use the **Client Credentials** grant — the simplest OAuth flow:

```bash
# Step 1: Get a token
curl -X POST https://auth.example.com/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=my-service" \
  -d "client_secret=abc123" \
  -d "scope=read:orders"

# Response:
# { "access_token": "eyJ...", "expires_in": 3600 }

# Step 2: Call the API
curl https://api.example.com/orders \
  -H "Authorization: Bearer eyJ..."
```

### API Key Rotation (Zero Downtime)

```
1. Issue new key K2 alongside existing K1
2. Distribute K2 to the client out-of-band
3. Client migrates traffic to K2 (both keys valid during overlap)
4. Revoke K1 after confirmed migration
5. Monitor for K1 usage — alert if seen (indicates stale config)
```

---

## Use It

### How Major Platforms Apply These Methods

| Platform / Use Case | Method Used | Why |
|---|---|---|
| GitHub REST API | API Key (PAT) + OAuth apps | Automation scripts + third-party integrations |
| Google APIs | OAuth 2.0 (OIDC for identity) | Delegated access to user data |
| Stripe | API Key (secret + publishable) | Server-to-server payments, simple secret rotation |
| AWS API Gateway | API Key + IAM SigV4 or Cognito JWT | Multi-tier: key for rate limiting, JWT for identity |
| Internal microservices (k8s) | JWT (service mesh) or mTLS | Short-lived tokens from a Vault/SPIFFE issuer |
| Legacy enterprise intranet | Session Auth | Browser-based, server-rendered, no CORS complexity |
| Webhook receivers | HMAC signature on payload | Verify the sender, not a bearer token |

### Decision Guide

```
Is a human user logging in via a browser?
  YES → Does your app need server-side rendering?
         YES → Session Auth
         NO  → JWT (SPA/mobile)
  NO  → Is a third party accessing user data on the user's behalf?
         YES → OAuth 2.0
         NO  → Is it machine-to-machine with a fixed set of callers?
                YES → API Key
                NO  → Client Credentials (OAuth M2M)
```

---

## Common Pitfalls

- **Sending API keys in query strings.** Query strings are stored in server logs, browser history, and intermediary caches. Always use headers. If you must use query strings (some webhook callbacks), scrub them from logs immediately.

- **JWTs without expiry.** A JWT without an `exp` claim is valid forever. If the signing key leaks, every token ever issued is compromised. Set short expiry (≤15 min for access tokens) and implement refresh token rotation.

- **Storing JWTs in localStorage.** localStorage is accessible to any JavaScript on the page, making it an XSS target. Store access tokens in memory; store refresh tokens in HttpOnly, Secure, SameSite=Strict cookies.

- **Confusing OAuth with authentication.** OAuth 2.0 grants *authorization* (access to resources), not identity proof. Use OpenID Connect (`scope=openid`) to get an `id_token` if you need to know *who* the user is. Building "Login with Google" on raw OAuth without OIDC is a known vulnerability class.

- **Session fixation with Basic Auth on internal tools.** Basic Auth with no rate limiting or account lockout is brute-forceable. Even on internal networks, combine Basic Auth with IP allowlisting and set a `realm` that does not leak your internal naming conventions.

---

## Exercises

1. **Easy:** For each of the five methods, write down the HTTP header or cookie name used to carry the credential in a real request. Verify your answers by capturing traffic from a real API (e.g., GitHub, Stripe sandbox) with a tool like `curl -v` or browser DevTools.

2. **Medium:** Design the auth strategy for a multi-tenant SaaS API that must support (a) human users via a React SPA, (b) partner companies calling from their backends, and (c) webhooks your system sends to partners. Specify the method for each caller type, the token lifetimes, and how revocation works in each case.

3. **Hard:** Implement JWT access + refresh token rotation in a language of your choice. Requirements: access token expires in 15 minutes; refresh token expires in 7 days and is rotated on every use (old refresh token invalidated when a new one is issued); detect and block refresh token reuse (replay attack). Describe how your deny-list scales under high read throughput.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Base64 | Encryption | Encoding — completely reversible without a key; adds zero security |
| JWT | An authentication protocol | A token format (RFC 7519) — a signed JSON payload; the *protocol* is Bearer token auth |
| OAuth 2.0 | A login system | An authorization framework for delegated access; login (identity) requires OIDC on top |
| Stateless auth | No database needed | The server needs no session store, but may still need a token deny-list for revocation |
| Bearer token | Same as API key | A short-lived credential (often a JWT) — "whoever bears this token gets access" |
| Refresh token | A second password | A long-lived credential used only to obtain new access tokens; must be rotated and revoked |
| PKCE | Optional OAuth hardening | Proof Key for Code Exchange — required for public clients (SPAs, mobile) to prevent auth code interception |

---

## Further Reading

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://datatracker.ietf.org/doc/html/rfc7617)
- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://datatracker.ietf.org/doc/html/rfc9700)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Auth0 — The Definitive Guide to OAuth 2.0](https://auth0.com/docs/authenticate/protocols/oauth)
