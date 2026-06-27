# Session, Cookie, JWT, Token, SSO, and OAuth 2.0 Explained in One Diagram

> HTTP is stateless — every authentication mechanism is just a different way of lying to it convincingly.

**Type:** Learn
**Prerequisites:** HTTP Fundamentals, Client-Server Architecture, Basic Cryptography Concepts
**Time:** ~25 minutes

---

## The Problem

HTTP was designed stateless. Every request is independent — the server has no built-in memory of who sent the last one. But every real application needs to know *who you are* after you log in. If you add an item to a cart, the server needs to connect that action to your account on the next request, and the request after that.

The naive solution — send your username and password on every single request — is obviously wrong. What we need is a way to prove "I already authenticated" without re-sending credentials every time. And that single problem has spawned at least six distinct mechanisms in wide production use, each optimizing for different trade-offs: server memory, cross-domain support, delegation, federation, and mobile UX.

The confusion compounds because these mechanisms are often layered on top of each other. OAuth 2.0 can *issue* JWTs. SSO can *use* OAuth 2.0. A JWT can be stored *in* a cookie. Understanding each primitive separately — and then how they compose — is the prerequisite for every meaningful conversation about auth architecture.

---

## The Concept

### Mental Model: Six Primitives, Two Categories

```
┌─────────────────────────────────────────────────────────────────┐
│  WHO ARE YOU?  (AuthN — Authentication)                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────────┐ │
│  │ Session  │  │  Cookie  │  │   Token   │  │     JWT       │ │
│  └──────────┘  └──────────┘  └───────────┘  └───────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  CAN YOU DO THIS?  (AuthZ — Authorization)                      │
│  ┌───────────┐  ┌─────────────────────────┐                    │
│  │    SSO    │  │       OAuth 2.0          │                    │
│  └───────────┘  └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1. Session + Cookie (Server-Side State)

The server creates a session record in memory (or a database) when you log in and hands you back a random `session_id`. The browser stores this in a cookie and sends it on every subsequent request.

```
Browser                      Server
  │── POST /login ─────────────▶│
  │   {user, password}          │  verify creds
  │                             │  create session: {id: "abc123", user: "alice"}
  │◀── Set-Cookie: sid=abc123 ──│  store in Redis
  │                             │
  │── GET /dashboard ──────────▶│
  │   Cookie: sid=abc123        │  look up session["abc123"] → alice
  │◀── 200 OK ─────────────────│
```

**Trade-offs:**
| Aspect | Detail |
|---|---|
| Server memory | Every active user consumes server-side storage |
| Revocation | Instant — delete the session record |
| Horizontal scaling | Requires shared session store (Redis, Memcached) |
| Cross-domain | Cookies are origin-bound; doesn't work across domains out of the box |
| CSRF exposure | High — cookie sent automatically on every request |

---

### 2. Token-Based Authentication (Stateless)

Instead of storing state on the server, encode identity *into* the token. The server issues a signed blob; the client stores it and sends it in the `Authorization` header.

```
Browser                      Server
  │── POST /login ─────────────▶│
  │                             │  verify creds
  │                             │  create token: sign({user:"alice"}, secret)
  │◀── {token: "eyJ..."} ───────│  (nothing stored server-side)
  │                             │
  │── GET /dashboard ──────────▶│
  │   Authorization: Bearer eyJ │  verify signature → alice
  │◀── 200 OK ─────────────────│
```

No session store needed. Each server in a cluster can validate independently by re-computing the signature.

---

### 3. JWT — JSON Web Token

JWT is the *standard format* for tokens (RFC 7519). A JWT is three Base64URL-encoded JSON objects joined by dots:

```
header.payload.signature

eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9    ← header: {"alg":"HS256","typ":"JWT"}
.
eyJzdWIiOiJhbGljZSIsImV4cCI6MTcwMDAwMH0  ← payload: {"sub":"alice","exp":1700000}
.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c  ← HMAC-SHA256 signature
```

**Standard claims in the payload:**

| Claim | Meaning |
|---|---|
| `sub` | Subject (user ID) |
| `iss` | Issuer (who created the token) |
| `aud` | Audience (intended recipient) |
| `exp` | Expiry (Unix timestamp) |
| `iat` | Issued-at time |
| `jti` | JWT ID (unique identifier, used for revocation) |

**Signing algorithms:**
- `HS256` — symmetric HMAC. Same secret signs and verifies. Use only when issuer = verifier.
- `RS256` — asymmetric RSA. Private key signs; public key verifies. Use when multiple services need to verify without holding the secret.

---

### 4. SSO — Single Sign-On

SSO delegates authentication to a central Identity Provider (IdP). Once you authenticate there, all connected Service Providers (SPs) trust the IdP's assertion without you re-entering credentials.

```
User         App A (SP)        IdP (e.g. Okta)      App B (SP)
  │──────────────▶│                   │                  │
  │  Not logged in│                   │                  │
  │◀──────────────│                   │                  │
  │  Redirect to IdP                  │                  │
  │───────────────────────────────────▶                  │
  │  Login once                       │                  │
  │◀──────────────────────────────────│                  │
  │  SAML assertion / OIDC token      │                  │
  │──────────────▶│                   │                  │
  │  Token verified; logged into A    │                  │
  │                                   │                  │
  │──────────────────────────────────────────────────────▶
  │  Same session → already logged in; redirect back     │
  │◀─────────────────────────────────────────────────────│
```

Protocols used for SSO: **SAML 2.0** (XML-based, enterprise), **OpenID Connect / OIDC** (JSON/JWT-based, modern web and mobile).

---

### 5. OAuth 2.0 — Delegated Authorization

OAuth 2.0 is an *authorization* framework, not an authentication protocol. It lets a user grant a third-party application limited access to their resources on another service — without handing over passwords.

**Four roles:**
- **Resource Owner** — the user
- **Client** — the third-party app requesting access
- **Authorization Server** — issues tokens (e.g. Google, GitHub)
- **Resource Server** — holds the protected data (e.g. Gmail API)

**Authorization Code Flow** (most common, most secure):

```
User (Browser)      Client App         Auth Server        Resource Server
      │────── Click "Login with Google" ──▶│                    │
      │◀─────── Redirect to Google ─────────│                    │
      │──────────────────────────────────────▶                   │
      │  login + consent                    │                    │
      │◀──────────────────────────────────── code=xyz            │
      │──────── code=xyz ────────────────────▶                   │
      │                    POST /token       │                    │
      │                    code + secret ────▶                   │
      │                    ◀──────── access_token + refresh_token│
      │                                     │                    │
      │                    GET /userinfo ────────────────────────▶
      │                    Authorization: Bearer <token>         │
      │                    ◀──────────────────────── user data   │
```

**Four grant types and when to use them:**

| Grant Type | Use Case |
|---|---|
| Authorization Code (+PKCE) | Web apps, mobile apps — user is present |
| Client Credentials | Machine-to-machine, no user involved |
| Device Code | Smart TVs, CLIs where browser redirect is awkward |
| Implicit | Deprecated; was used for SPAs, replaced by Auth Code + PKCE |

---

## Build It / In Depth

### Scenario: A User Logs Into a Multi-Service Platform

#### Step 1 — Session-based login (traditional)

```python
# Flask example — session stored server-side in Redis
from flask import Flask, session, request, jsonify
import redis, uuid

app = Flask(__name__)
r = redis.Redis()

@app.post("/login")
def login():
    user = authenticate(request.json["username"], request.json["password"])
    if not user:
        return jsonify({"error": "invalid credentials"}), 401
    sid = str(uuid.uuid4())
    r.setex(f"session:{sid}", 3600, user["id"])  # expires in 1 hour
    resp = jsonify({"ok": True})
    resp.set_cookie("sid", sid, httponly=True, secure=True, samesite="Lax")
    return resp

@app.get("/me")
def me():
    sid = request.cookies.get("sid")
    user_id = r.get(f"session:{sid}")
    if not user_id:
        return jsonify({"error": "unauthenticated"}), 401
    return jsonify({"user_id": user_id.decode()})
```

#### Step 2 — JWT-based login (stateless)

```python
import jwt, datetime

SECRET = "your-256-bit-secret"

def issue_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("token expired")
    except jwt.InvalidTokenError:
        raise ValueError("invalid token")
```

#### Step 3 — OAuth 2.0 Authorization Code Flow (Google)

```bash
# Step 1: Redirect user to Google
GET https://accounts.google.com/o/oauth2/v2/auth
  ?client_id=YOUR_CLIENT_ID
  &redirect_uri=https://yourapp.com/callback
  &response_type=code
  &scope=openid%20email%20profile
  &state=random_csrf_token
  &code_challenge=BASE64URL(SHA256(code_verifier))   # PKCE
  &code_challenge_method=S256

# Step 2: Exchange code for tokens (server-side)
POST https://oauth2.googleapis.com/token
  Content-Type: application/x-www-form-urlencoded

  code=4/P7q7W91...
  &client_id=YOUR_CLIENT_ID
  &client_secret=YOUR_CLIENT_SECRET
  &redirect_uri=https://yourapp.com/callback
  &grant_type=authorization_code
  &code_verifier=ORIGINAL_VERIFIER   # PKCE

# Response:
{
  "access_token": "ya29.A0...",
  "expires_in": 3599,
  "id_token": "eyJhbGciOiJSUzI1NiJ9...",   ← OIDC JWT with user identity
  "refresh_token": "1//0g...",
  "token_type": "Bearer"
}
```

#### JWT Anatomy (decoded)

```json
// Header
{ "alg": "RS256", "typ": "JWT", "kid": "abc123" }

// Payload (OIDC id_token from Google)
{
  "iss": "https://accounts.google.com",
  "sub": "110248495921238986820",
  "aud": "YOUR_CLIENT_ID",
  "exp": 1700000000,
  "iat": 1699996400,
  "email": "alice@example.com",
  "email_verified": true,
  "name": "Alice Smith"
}

// Signature — RS256, verified with Google's public JWKS endpoint
// https://www.googleapis.com/oauth2/v3/certs
```

---

## Use It

| Mechanism | When to reach for it | Real examples |
|---|---|---|
| Session + Cookie | Traditional server-rendered apps, strong revocation needs | Django, Rails, PHP apps |
| JWT (stateless) | Microservices, API gateways, mobile backends | AWS API Gateway authorizers, Kong |
| SSO / SAML | Enterprise workforce apps, corporate identity federation | Okta, PingFederate, Azure AD |
| SSO / OIDC | Consumer-facing apps, modern enterprise | Auth0, Cognito, Google Workspace |
| OAuth 2.0 (Auth Code) | Third-party integrations: "Login with X", data access delegation | GitHub Apps, Stripe Connect, Google APIs |
| OAuth 2.0 (Client Credentials) | Service-to-service API calls | Twilio, Stripe API keys (conceptually) |
| Refresh Tokens | Long-lived sessions without long-lived access tokens | Any mobile app, Google OAuth, Azure AD |

**Stack-specific notes:**
- **Next.js / Vercel**: Use `next-auth` (now Auth.js) — it wraps OAuth 2.0 + OIDC + session management behind a single API.
- **AWS**: Use Cognito User Pools for OIDC/OAuth, Cognito Identity Pools for AWS resource access.
- **Kubernetes**: Service accounts use short-lived JWTs (`serviceaccount` tokens, RS256 signed by kube-apiserver).
- **Redis**: The canonical choice for distributed session storage. Use `SET session:{id} {data} EX 3600`.

---

## Common Pitfalls

- **Storing JWTs in `localStorage`**: Accessible to JavaScript on the page, making them vulnerable to XSS. Prefer `httpOnly` cookies for JWTs in browser contexts — they're immune to JS reads. Use CSRF tokens or `SameSite=Strict` to mitigate the CSRF exposure that comes with cookies.

- **Not validating JWT claims**: Verifying the signature is not enough. You must also check `exp` (not expired), `iss` (expected issuer), and `aud` (your service is the intended audience). Libraries that only verify the signature silently accept tokens issued for a completely different service.

- **Using `alg: none`**: A historically exploited attack where a crafted JWT with `"alg": "none"` could bypass signature verification in naive libraries. Always pin the expected algorithm explicitly when calling `jwt.decode(token, key, algorithms=["RS256"])` — never accept the algorithm from the token header.

- **Treating OAuth 2.0 access tokens as identity**: An access token proves the *client was authorized*, not *who the user is*. For identity, use the **OIDC id_token** or call the `/userinfo` endpoint. Mixing the two causes broken auth in multi-tenant systems.

- **No token rotation on refresh**: Issuing the same refresh token forever creates an indefinitely valid credential if it leaks. Implement **refresh token rotation**: issue a new refresh token each time one is used and invalidate the old one. Many IdPs (Auth0, Cognito) do this automatically.

---

## Exercises

1. **Easy** — Draw the request/response sequence for a session-based login on paper. Label: the cookie name, where the session lives on the server, and what happens when you call `/logout`. Then repeat for a JWT-based flow and identify which steps disappear.

2. **Medium** — Implement a Node.js Express endpoint that accepts a Google OIDC `id_token` as a `Bearer` token, fetches Google's JWKS public keys from `https://www.googleapis.com/oauth2/v3/certs`, and verifies the signature, `iss`, `aud`, and `exp` claims before returning the user's email. Use the `jose` library.

3. **Hard** — Design a multi-service platform (e.g. an e-commerce site with a separate payments microservice) that uses JWT-based auth for inter-service calls. How do you handle token revocation when a user is banned mid-session? Compare three approaches: a blacklist in Redis, short token TTLs with refresh, and phantom/jti tracking. Evaluate each on latency, storage cost, and correctness.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Session** | A general word for "being logged in" | A server-side record keyed by a random ID sent to the browser in a cookie |
| **Cookie** | Where auth lives | An HTTP header (`Set-Cookie` / `Cookie`) for transmitting small key-value pairs; can carry a session ID *or* a JWT or anything else |
| **JWT** | A login token | A signed, self-contained JSON payload — the signature makes it verifiable without a server-side lookup |
| **OAuth 2.0** | A login system | An *authorization* delegation framework — it lets apps act on your behalf; identity is a separate concern (OIDC adds it on top) |
| **SSO** | Logging in once for everything | A pattern where a central Identity Provider authenticates the user and issues assertions to multiple Service Providers; can be implemented via SAML or OIDC |
| **Access Token** | Proof of who you are | A short-lived credential proving a client was *authorized* to act on a user's behalf — not necessarily carrying identity |
| **Refresh Token** | A way to stay logged in | A long-lived credential used only to obtain new access tokens without re-authenticating; must be stored securely and rotated |

---

## Further Reading

- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) — the canonical spec; read sections 4 (claims) and 7 (validation) carefully.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — authoritative source; Sections 4.1 (Authorization Code) and 4.4 (Client Credentials) are the two you'll use 90% of the time.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — how OIDC layers identity on top of OAuth 2.0; pay attention to the `id_token` validation rules in Section 3.1.3.7.
- [jwt.io](https://jwt.io) — paste any JWT to decode and inspect the header and payload; also lists and compares library support by language.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://datatracker.ietf.org/doc/html/rfc9700) — updated threat model and mitigations; mandates PKCE for all authorization code flows, deprecates implicit grant.
