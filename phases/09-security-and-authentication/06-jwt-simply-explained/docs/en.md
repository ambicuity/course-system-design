# JWT Simply Explained

> A JWT is a tamper-proof envelope you hand to the client — the server trusts it without ever looking anything up.

**Type:** Learn
**Prerequisites:** HTTP Basics, Symmetric vs Asymmetric Cryptography, Session-Based Authentication
**Time:** ~25 minutes

---

## The Problem

Traditional session-based authentication stores a session record on the server. Every time the client makes a request, the server looks up that record in a database or an in-memory store (e.g., Redis) to confirm the user is authenticated. This works fine when you have one server — but it breaks down as soon as you scale horizontally. If a user authenticates on Server A and their next request lands on Server B, Server B has no record of that session. You either need sticky sessions, a shared session store, or a way to avoid server-side state altogether.

Consider a company running separate microservices: an API gateway, an orders service, a payment service, and a notifications service. If each service has to call a central auth service on every request just to verify the caller's identity, you've introduced latency, a single point of failure, and tight coupling. The auth service becomes a bottleneck.

JWT (JSON Web Token) solves this by moving the authentication state to the client. Instead of handing the user an opaque session ID that points to server-side data, you hand them a self-contained, cryptographically signed token. Any service that holds the right key can verify the token independently — no network call required.

---

## The Concept

### Structure: Three Dots, Three Parts

A JWT is three Base64URL-encoded strings joined by dots:

```
xxxxx.yyyyy.zzzzz
  │       │       │
Header  Payload  Signature
```

Each part is independently decodable. Only the **Signature** provides security.

**1. Header**

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

`alg` declares the signing algorithm. Common values:

| Algorithm | Type        | Notes                                       |
|-----------|-------------|---------------------------------------------|
| HS256     | Symmetric   | HMAC + SHA-256. One shared secret key.      |
| RS256     | Asymmetric  | RSA + SHA-256. Private key signs, public key verifies. |
| ES256     | Asymmetric  | ECDSA + SHA-256. Smaller keys than RSA.     |
| PS256     | Asymmetric  | RSA-PSS. Probabilistic, stronger than RS256.|

**2. Payload**

The payload holds **claims** — statements about the entity (usually the user) plus metadata. Three claim categories:

- **Registered claims** — defined by the JWT spec (RFC 7519). Not mandatory but strongly recommended:
  - `iss` (issuer): who issued the token
  - `sub` (subject): whom the token is about, typically a user ID
  - `aud` (audience): intended recipient(s)
  - `exp` (expiration): Unix timestamp after which the token is invalid
  - `iat` (issued at): when the token was created
  - `nbf` (not before): token is invalid before this time
  - `jti` (JWT ID): unique identifier, useful for revocation

- **Public claims** — application-defined, registered with IANA to avoid collisions (e.g., `email`, `name`).

- **Private claims** — custom claims agreed on between producer and consumer (e.g., `role`, `org_id`, `plan`).

Example payload:

```json
{
  "sub": "usr_8f2k1p",
  "email": "alice@example.com",
  "role": "admin",
  "iat": 1719360000,
  "exp": 1719363600
}
```

**3. Signature**

The signature is the security anchor. For HS256:

```
signature = HMAC-SHA256(
  base64url(header) + "." + base64url(payload),
  secret_key
)
```

For RS256:

```
signature = RSA_SIGN(
  base64url(header) + "." + base64url(payload),
  private_key
)
```

If anyone modifies the header or payload after the token is issued, the signature will no longer match — verification fails.

### How Verification Works

```
Client                        Server / Service
  │                               │
  │──── POST /login ─────────────►│
  │◄─── JWT (signed) ─────────────│
  │                               │
  │──── GET /orders               │
  │     Authorization: Bearer <JWT>──►│
  │                               │ 1. Split on "."
  │                               │ 2. base64url-decode header → get alg
  │                               │ 3. Recompute signature over header.payload
  │                               │ 4. Compare to token's signature
  │                               │ 5. Check exp, iss, aud
  │◄─── 200 OK ───────────────────│
```

The server never queries a database to validate identity. The cryptographic check **is** the authentication.

### Symmetric vs Asymmetric Signing

| Property              | Symmetric (HS256)                      | Asymmetric (RS256/ES256)                        |
|-----------------------|----------------------------------------|-------------------------------------------------|
| Key material          | Single shared secret                   | Private key (sign) + public key (verify)        |
| Who can verify        | Anyone who knows the secret            | Anyone with the public key (can be published)   |
| Key distribution risk | High — every verifier needs the secret | Low — public key is safe to share broadly       |
| Best for              | Single service, internal tokens        | Microservices, third-party consumers, OIDC      |
| Performance           | Faster (HMAC is cheap)                 | Slightly slower (asymmetric math)               |

In a microservices architecture, prefer asymmetric signing. The auth service keeps the private key. Every downstream service fetches the public key from a JWKS (JSON Web Key Set) endpoint and verifies independently.

---

## Build It / In Depth

### Step 1 — Create and Sign a JWT (Python)

```python
import jwt  # PyJWT library: pip install PyJWT
import datetime

SECRET_KEY = "super-secret-dev-only"

payload = {
    "sub": "usr_8f2k1p",
    "email": "alice@example.com",
    "role": "admin",
    "iat": datetime.datetime.utcnow(),
    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
}

token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
print(token)
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfOGYyazFwIiwiZW1haWwiOiJhbGljZUBleGFtcGxlLmNvbSIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTcxOTM2MDAwMCwiZXhwIjoxNzE5MzYzNjAwfQ.<signature>
```

### Step 2 — Decode Without Verification (Inspect Only)

```python
import base64, json

parts = token.split(".")

def decode_part(part):
    # Base64URL padding
    padding = 4 - len(part) % 4
    padded = part + "=" * padding
    return json.loads(base64.urlsafe_b64decode(padded))

print(decode_part(parts[0]))  # Header
print(decode_part(parts[1]))  # Payload
# The signature (parts[2]) is binary — you cannot decode it to JSON
```

This step demonstrates that the header and payload are **not encrypted** — they are only encoded. Anyone can read them. Do not put secrets in JWT claims.

### Step 3 — Verify a JWT

```python
try:
    decoded = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub"]},
    )
    print(decoded["role"])  # "admin"
except jwt.ExpiredSignatureError:
    print("Token has expired — force re-login")
except jwt.InvalidSignatureError:
    print("Signature mismatch — token was tampered with")
except jwt.DecodeError:
    print("Malformed token")
```

### Step 4 — RS256 Signing (Microservices Pattern)

```bash
# Generate key pair (auth service keeps private.pem, distributes public.pem)
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

```python
# Auth service — signs the token
with open("private.pem", "rb") as f:
    private_key = f.read()

token = jwt.encode(payload, private_key, algorithm="RS256")

# Any downstream service — verifies without the private key
with open("public.pem", "rb") as f:
    public_key = f.read()

decoded = jwt.decode(token, public_key, algorithms=["RS256"])
```

### Step 5 — JWKS Endpoint (Production Pattern)

In production, services don't distribute public keys as files. They publish a **JWKS** (JSON Web Key Set) endpoint:

```
GET https://auth.example.com/.well-known/jwks.json

{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-2024-06",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

Each JWT includes a `kid` (key ID) header claim so verifiers know which key in the JWKS to use. This supports **key rotation** without downtime — publish a new key, old tokens signed with the previous key still verify until they expire.

### Full Auth Flow Diagram

```
User                Auth Service            Orders Service
 │                       │                       │
 │── POST /auth/login ──►│                       │
 │   { email, password } │                       │
 │                       │ validate credentials  │
 │◄── JWT (RS256) ───────│                       │
 │                       │                       │
 │── GET /orders ────────────────────────────────►│
 │   Authorization: Bearer <JWT>                  │
 │                                               │ fetch JWKS (cached)
 │                                               │ verify sig + exp + aud
 │◄── 200 { orders: [...] } ─────────────────────│
```

---

## Use It

### Where You'll See JWT in Practice

| Technology / Standard | JWT Role                                                                      |
|-----------------------|-------------------------------------------------------------------------------|
| **OAuth 2.0**         | Access tokens are often JWTs (but the spec doesn't require it)                |
| **OpenID Connect**    | ID tokens are always JWTs — carry user identity claims                        |
| **Auth0 / Okta / Cognito** | Issue RS256 JWTs; expose JWKS endpoints automatically                  |
| **AWS API Gateway**   | Native JWT authorizer validates tokens without Lambda                         |
| **Kubernetes**        | Service account tokens are JWTs used to authenticate pods to the API server   |
| **Firebase**          | Firebase Auth issues JWTs signed with Google's RSA keys                       |
| **GraphQL APIs**      | JWT in Authorization header; resolvers extract claims to control field access  |

### JWT vs Session Tokens

| Dimension              | Server-Side Session             | JWT                                        |
|------------------------|---------------------------------|--------------------------------------------|
| State location         | Server (DB / Redis)             | Client (cookie or localStorage)            |
| Revocation             | Instant — delete the record     | Hard — must wait for expiry or use a blocklist |
| Horizontal scaling     | Requires shared session store   | Stateless — any node can verify            |
| Network calls per req  | 1 (session lookup)              | 0 (crypto verification only)               |
| Payload size           | Tiny (session ID ~32 bytes)     | Larger (~300–800 bytes per token)          |
| Secret data in token   | Safe (ID only, data server-side)| Unsafe — payload is only encoded, not encrypted |

Choose JWTs when you need stateless verification at scale or across service boundaries. Choose server-side sessions when you need instant revocation or cannot tolerate the payload size overhead.

---

## Common Pitfalls

- **Storing JWTs in `localStorage`.** JavaScript on the page can read `localStorage`, making tokens vulnerable to XSS. Prefer `HttpOnly` cookies — they are inaccessible to JavaScript and are sent automatically with requests.

- **Setting expiry too long.** A token with a 30-day `exp` that gets stolen gives an attacker a 30-day window. Use short-lived access tokens (15 minutes) paired with a longer-lived refresh token stored in an `HttpOnly` cookie.

- **Trusting the `alg` claim in the header.** Some early libraries let attackers set `"alg": "none"` to bypass signature verification entirely. Always specify allowed algorithms server-side; never accept `none`.

- **Putting sensitive data in the payload.** The payload is Base64URL-encoded, not encrypted. Anyone who intercepts a JWT can decode and read every claim. Use JWE (JSON Web Encryption) if you need to protect payload contents, or store sensitive data server-side and only reference it by ID in the token.

- **No revocation strategy.** JWTs are valid until they expire. If a user logs out or changes their password, old tokens remain valid. Maintain a short-lived blocklist (Redis `SET` with TTL equal to token lifetime) for security-critical events like password changes or account suspension, or keep access token lifetimes very short (≤15 minutes).

---

## Exercises

1. **Easy** — Paste any JWT from jwt.io into the decoder on that same site. Identify the algorithm, subject (`sub`), expiration (`exp`), and at least one custom claim. Convert the `exp` timestamp to a human-readable date and determine whether the token is still valid.

2. **Medium** — Implement a simple Express.js middleware that validates a JWT on every protected route. It should return `401 Unauthorized` if the token is missing, expired, or has an invalid signature. Return `403 Forbidden` if the token is valid but the `role` claim does not match the required role for that route.

3. **Hard** — Design a revocation system for short-lived access tokens (15-minute TTL) and long-lived refresh tokens (7-day TTL). The system must support: (a) logout invalidating both tokens immediately, (b) password change invalidating all existing tokens for that user, (c) admin-initiated account suspension. Describe your storage schema, the flow for token refresh, and how you handle clock skew across nodes.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **JWT** | A secure, encrypted user token | A Base64URL-encoded, signed (but not encrypted) data structure — the payload is readable by anyone |
| **Claim** | A field inside the JSON payload | A key-value assertion about the subject; registered claims (`sub`, `exp`) have standardized semantics |
| **Signature** | Encrypts the token content | Cryptographically binds the header and payload to a key; prevents tampering but does not hide the content |
| **HS256** | A hashing algorithm | HMAC-SHA256 — symmetric signing that requires both parties to share the same secret |
| **RS256** | Just a stronger hash | RSA signature with SHA-256 — asymmetric, so the private key signs and the public key verifies |
| **JWKS** | A config file for keys | A JSON endpoint that publishes the public key(s) used to verify tokens — enables key rotation |
| **Refresh Token** | A longer-lived JWT | An opaque or JWT credential used only to obtain new access tokens; should be stored server-side with revocation support |

---

## Further Reading

- [RFC 7519 — JSON Web Token specification](https://datatracker.ietf.org/doc/html/rfc7519) — the authoritative standard; sections 4 and 7 are most practical.
- [jwt.io](https://jwt.io) — interactive debugger for decoding and verifying tokens; also maintains a library compatibility matrix.
- [RFC 7517 — JSON Web Key (JWK)](https://datatracker.ietf.org/doc/html/rfc7517) — defines the JWKS format used in production key distribution.
- [OWASP JWT Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — common vulnerabilities and mitigations, including the `alg:none` attack in detail.
- [Auth0 — The Anatomy of a JSON Web Token](https://auth0.com/blog/json-web-token-signing-algorithms-overview/) — accessible deep dive into signing algorithm trade-offs with real-world context.
