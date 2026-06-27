# JWT 101: Key to Stateless Authentication

> A self-contained, signed token lets every service verify identity without asking anyone else.

**Type:** Learn
**Prerequisites:** HTTP Basics, Session-Based Authentication, Public-Key Cryptography Fundamentals
**Time:** ~30 minutes

---

## The Problem

Traditional session-based authentication stores state on the server. When a user logs in, the server creates a session record in memory or a database and hands the browser a session ID cookie. Every subsequent request ships that cookie back, and the server looks up the session to confirm the user is who they say they are.

This works fine for a single monolith. It breaks apart the moment you distribute your system. Imagine a user's login request hits Server A, which creates a session in its local memory. The next request is load-balanced to Server B — which has no idea that session exists. You can fix this with sticky sessions (tying a user to one instance) or a shared session store (Redis), but both add operational complexity and a new single point of failure.

Microservices make it worse. An API gateway, an order service, and a notification service are all independent processes. They don't share memory. Every service would need to call a central auth service for every incoming request, introducing latency, tight coupling, and a choke point that, if it goes down, takes your entire authentication system with it. What you need instead is a credential that carries enough information to be verified anywhere, by anyone who knows the right secret — without a phone call home.

---

## The Concept

A JSON Web Token (JWT, pronounced "jot") is a compact, URL-safe string that encodes a claim set and a cryptographic proof of its integrity. Any service that holds the verification key can confirm the token is untampered and trust its contents — no database lookup required.

### Structure

A JWT is three Base64URL-encoded segments joined by dots:

```
HEADER.PAYLOAD.SIGNATURE
```

**Example (decoded):**

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJzdWIiOiJ1c2VyXzEyMyIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTcxOTQwMDAwMCwiZXhwIjoxNzE5NDAzNjAwfQ
.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

**Segment 1 — Header**

Declares the token type and the signing algorithm:

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

**Segment 2 — Payload (Claims)**

The payload is a JSON object of *claims* — statements about the subject and metadata about the token itself:

| Claim | Name | Description |
|-------|------|-------------|
| `iss` | Issuer | Who issued the token (`"auth.example.com"`) |
| `sub` | Subject | Whom the token refers to (typically a user ID) |
| `aud` | Audience | Intended recipients — services must reject tokens not addressed to them |
| `exp` | Expiration | Unix timestamp after which the token is invalid |
| `iat` | Issued At | When the token was created |
| `nbf` | Not Before | Token is invalid before this time |
| `jti` | JWT ID | Unique identifier to prevent replay attacks |

Beyond these *registered* claims you can add any *private* claims your application needs — `role`, `org_id`, `plan`, etc. Keep the payload small: it is encoded, not encrypted.

**Segment 3 — Signature**

The signature ties the other two segments together and proves they have not been tampered with:

```
HMAC-SHA256(
  base64url(header) + "." + base64url(payload),
  secret
)
```

If anyone modifies even a single character in the header or payload, the signature check fails.

### How Verification Works

```
Client                          Service
  |                               |
  |  POST /login (credentials)    |
  |------------------------------>|
  |                               |  Validate credentials
  |  { token: "eyJ..." }          |  Sign token with secret
  |<------------------------------|
  |                               |
  |  GET /orders                  |
  |  Authorization: Bearer eyJ..  |
  |------------------------------>|
  |                               |  1. Split token into parts
  |                               |  2. Re-compute signature
  |                               |  3. Compare with provided sig
  |                               |  4. Check exp, aud, iss
  |  200 OK { orders: [...] }     |
  |<------------------------------|
```

The service never calls a database. It only needs the secret (or public key).

### Signing Strategies

| Strategy | Algorithm examples | Key type | Who can verify |
|----------|--------------------|----------|----------------|
| **Symmetric (HMAC)** | HS256, HS384, HS512 | Single shared secret | Anyone holding the same secret |
| **Asymmetric (RSA)** | RS256, RS384, RS512 | Private key signs, public key verifies | Anyone with the public key |
| **Asymmetric (ECDSA)** | ES256, ES384, ES512 | Private key signs, public key verifies | Anyone with the public key (smaller key than RSA) |

**When to choose which:**

- **HMAC** — simple setups where the issuer and verifiers are fully trusted services you control and can share a secret securely. Fastest option.
- **RSA / ECDSA** — multi-tenant or third-party integrations. The auth server keeps the private key and publishes the public keys via a JWKS endpoint. Downstream services can rotate without a secret rotation ceremony.

### Stateless vs Stateful Trade-offs

| Property | JWT (stateless) | Session (stateful) |
|----------|-----------------|--------------------|
| Server memory | None | Per-session entry |
| Revocation | Hard (token lives until `exp`) | Instant (delete session) |
| Horizontal scale | Trivial | Requires shared store |
| Payload inspection | Readable by anyone | Opaque to client |
| Logout | Requires block-list or short `exp` | Delete session record |

The inability to revoke a token mid-flight is the most important trade-off. Design your system around it, not against it.

---

## Build It / In Depth

### Issuing a JWT (Python, PyJWT)

```python
import jwt
import datetime

SECRET = "your-256-bit-secret"  # store in env, never in code

def create_token(user_id: str, role: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + datetime.timedelta(hours=1),  # short-lived
        "iss": "auth.example.com",
        "aud": "api.example.com",
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

token = create_token("user_123", "admin")
print(token)
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyIs...
```

### Verifying a JWT

```python
def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],       # NEVER pass algorithms=None
            audience="api.example.com", # enforce audience
            issuer="auth.example.com",  # enforce issuer
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError as e:
        raise Exception(f"Invalid token: {e}")

claims = verify_token(token)
print(claims["sub"])   # "user_123"
print(claims["role"])  # "admin"
```

### Using Asymmetric Keys (RS256)

```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Load keys (generated once: openssl genrsa -out private.pem 2048)
with open("private.pem", "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

with open("public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read(), backend=default_backend())

# Issue — auth server only
token = jwt.encode({"sub": "user_123", "exp": ...}, private_key, algorithm="RS256")

# Verify — any downstream service with public key only
payload = jwt.decode(token, public_key, algorithms=["RS256"], audience="api.example.com")
```

### Serving Public Keys via JWKS

The standard way to distribute public keys is a JSON Web Key Set endpoint:

```
GET https://auth.example.com/.well-known/jwks.json

{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "2024-key-1",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

Downstream services fetch this endpoint, cache the keys, and use the `kid` header in each JWT to pick the right key. When you rotate keys, publish the new key alongside the old one. Old tokens (still valid by `exp`) continue to verify against the old key.

### Token Refresh Pattern

Short-lived access tokens (15 min) pair with long-lived refresh tokens (7 days):

```
┌──────────┐      login        ┌──────────┐
│  Client  │ ───────────────▶  │   Auth   │
│          │ ◀─── access (15m) │  Server  │
│          │ ◀─── refresh (7d) └──────────┘
│          │
│          │  access expired
│          │ ─── POST /token/refresh (refresh token) ──▶ Auth
│          │ ◀─── new access token ──────────────────── Auth
└──────────┘
```

Refresh tokens ARE stored server-side (in a database or Redis) so they can be revoked on logout or compromise. Access tokens remain stateless.

---

## Use It

### Frameworks and Libraries

| Ecosystem | Library | Notes |
|-----------|---------|-------|
| Python | `PyJWT` | Simple; `python-jose` for JWKS support |
| Node.js | `jsonwebtoken` | De-facto standard; `jose` for Web Crypto API |
| Go | `golang-jwt/jwt` | Widely used; integrates cleanly with middleware |
| Java | `jjwt` (JJWT), Spring Security | Spring Security handles validation middleware |
| .NET | `System.IdentityModel.Tokens.Jwt` | Built into ASP.NET Core Identity |

### In Real Systems

- **API Gateways (Kong, AWS API Gateway):** Validate JWTs at the edge before requests reach upstream services. Each microservice trusts the gateway's decision.
- **OAuth 2.0 / OpenID Connect:** OIDC ID tokens ARE JWTs. Access tokens in OAuth 2.0 are often JWTs (though the spec doesn't require it). Identity providers like Auth0, Keycloak, Okta, and AWS Cognito all issue JWTs.
- **Service-to-Service (M2M):** Services authenticate each other using JWTs issued via the OAuth 2.0 Client Credentials flow — no human user involved.
- **WebSockets / SSE:** Because WebSockets can't easily carry Authorization headers after the handshake, the token is passed as a query parameter during the initial HTTP upgrade request, then discarded once the connection is open.

### Choosing Token Lifetime

| Access Token Lifetime | Trade-off |
|-----------------------|-----------|
| < 5 min | Very secure; high refresh traffic |
| 15 min | Standard — good balance |
| 1 hour | Common in less-sensitive APIs |
| > 1 day | Only for offline/batch access; add extra revocation controls |

---

## Common Pitfalls

- **Accepting `"alg": "none"`** — Some early libraries honored the `none` algorithm, allowing an attacker to strip the signature entirely and forge arbitrary tokens. Always pass an explicit allowlist of algorithms to your verify call: `algorithms=["HS256"]`, never `algorithms=None` or derived from the token header.

- **Storing sensitive data in the payload** — Base64URL is encoding, not encryption. Anyone can decode the payload with `base64 -d` in a terminal. Never put passwords, credit card numbers, or PII in claims. If you need confidential claims, use JWE (JSON Web Encryption) instead.

- **Ignoring the `exp` claim** — Failing to check expiry means a stolen token grants permanent access. Always validate `exp`, `iss`, and `aud` explicitly. Many libraries skip these by default unless you pass options.

- **Weak or reused secrets** — A 256-bit HMAC secret should be generated cryptographically: `openssl rand -hex 32`. Never use a short string, a password, or the same secret across environments. A brute-forceable secret breaks all tokens ever signed with it.

- **No revocation strategy** — JWTs can't be unilaterally revoked. When a user logs out or changes their password, tokens issued before that event remain valid until `exp`. Mitigate with: short-lived access tokens (15 min), a server-side blocklist (Redis `SET jti <exp-ttl> NX`), or by rotating the signing secret (nukes all tokens, including legitimate ones).

---

## Exercises

1. **Easy — Decode without verification.** Take any JWT from jwt.io and manually Base64URL-decode the header and payload segments using a command-line tool or a small script. Confirm you can read the claims without knowing the secret. This reinforces the point that JWTs are not encrypted.

2. **Medium — Refresh token flow.** Implement a minimal auth service (Flask or Express) that issues a 1-minute access token and a 7-day refresh token on login. Store refresh tokens in an in-memory dict. On `POST /refresh`, validate the refresh token, delete the old one, and issue a new pair. On `POST /logout`, delete the refresh token. Test that an access token continues to work after the 1-minute window expires if you keep refreshing.

3. **Hard — Key rotation with JWKS.** Set up an auth server that serves RSA public keys at `/.well-known/jwks.json` and includes a `kid` header in issued JWTs. Build a downstream service that fetches, caches, and verifies tokens using the correct key by `kid`. Then simulate a key rotation: generate a new RSA key pair, publish both old and new keys at the JWKS endpoint, and verify that tokens signed with the old key still validate while new tokens use the new key.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **JWT** | An encrypted credential | A *signed* (not encrypted) JSON object. Anyone can read the payload. |
| **Claim** | Any field you add to the token | A statement about the subject. Registered claims (`exp`, `sub`, etc.) have defined semantics; private claims are yours to define. |
| **Signature** | A password attached to the token | An HMAC or asymmetric cryptographic proof that the header and payload have not been altered since issuance. |
| **Stateless auth** | No server involvement at all | No *session state* on the server — but the signing key, JWKS, and refresh token store still live server-side. |
| **JWKS** | A key management tool | A JSON endpoint (`jwks.json`) that publishes a service's current public key(s) so any consumer can verify its JWTs without prior coordination. |
| **`alg: none`** | A legitimate "no signature" mode | A historical vulnerability. Never accept it in production. |
| **Refresh token** | Just another JWT | Often an opaque random string stored server-side, explicitly designed to be revocable — unlike an access token. |

---

## Further Reading

- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) — The authoritative specification. Sections 4 (Claims) and 7 (Validation) are most relevant.
- [RFC 7517 — JSON Web Key (JWK)](https://datatracker.ietf.org/doc/html/rfc7517) — Defines the JWKS format used for public key distribution.
- [jwt.io](https://jwt.io) — Interactive debugger to inspect any JWT; also the canonical list of per-language libraries.
- [OWASP JWT Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — Practical attack vectors and mitigations (language-agnostic despite the URL).
- [Auth0 "Critical Vulnerabilities in JSON Web Token Libraries"](https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/) — The original 2015 post exposing the `alg:none` and RS/HS confusion attacks; still essential reading.
