# Explaining JSON Web Token (JWT) with simple terms

> A JWT is a signed envelope: anyone can read it, but only the issuer can forge it.

**Type:** Learn
**Prerequisites:** HTTP basics, Hashing and digital signatures, Session-based authentication
**Time:** ~20 minutes

## The Problem

Your mobile app calls an API server. The server needs to know who is making each request — but HTTP is stateless. Every call arrives with no memory of who logged in five seconds ago.

The classic fix is server-side sessions: the server stores session state in memory or a database and hands the client a random session ID cookie. This works fine for a single server. Once you scale to dozens of servers or microservices, every service must either share that session store or call back to the auth service on every request. That shared store becomes a latency bottleneck and a single point of failure.

What if instead the server could hand the client a small, tamper-proof document that says "this is Alice, she is an admin, valid until 5 PM"? The client attaches it to every request and *any* service can verify it locally — no database round-trip, no shared state. That document is a JSON Web Token.

## The Concept

A JWT is a compact, URL-safe string made of three Base64URL-encoded segments joined by dots:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9   ← Header
.
eyJzdWIiOiJ1c2VyXzEyMyIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTcxNTAwMDAwMH0
.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c              ← Signature
```

### Part 1 — Header

The header is a JSON object that declares the token type and the signing algorithm:

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

Common `alg` values:

| Algorithm | Type       | Use case                                  |
|-----------|------------|-------------------------------------------|
| HS256     | Symmetric  | Single-service; one shared secret         |
| RS256     | Asymmetric | Auth server signs; many services verify   |
| ES256     | Asymmetric | Smaller signature, same trust model as RS |
| EdDSA     | Asymmetric | Modern choice, very fast verification     |

### Part 2 — Payload (Claims)

The payload is a JSON object containing *claims* — statements about the subject:

```json
{
  "iss": "auth.example.com",
  "sub": "user_123",
  "aud": "api.example.com",
  "exp": 1715000000,
  "iat": 1714996400,
  "role": "admin"
}
```

**Registered claims** (standardized by RFC 7519):

| Claim | Meaning              | Notes                                    |
|-------|----------------------|------------------------------------------|
| `iss` | Issuer               | Who created the token                    |
| `sub` | Subject              | Who the token is about (user ID)         |
| `aud` | Audience             | Who should accept the token              |
| `exp` | Expiration (Unix ts) | Reject if `now > exp`                    |
| `iat` | Issued-at            | When it was minted                       |
| `nbf` | Not-before           | Reject if `now < nbf`                    |
| `jti` | JWT ID               | Unique ID; used for revocation allowlist |

Custom claims like `role`, `email`, or `org_id` go in the same object.

**Important:** the payload is Base64URL-encoded, not encrypted. Anyone who holds the token can decode and read every claim. Never put passwords, PII, or secrets in the payload unless you additionally encrypt it (JWE — JSON Web Encryption, a separate spec).

### Part 3 — Signature

The signature is what makes the token tamper-proof. For HS256:

```
signature = HMAC-SHA256(
  base64url(header) + "." + base64url(payload),
  secret_key
)
```

For RS256 the auth server uses its *private key* to sign; downstream services verify with the *public key* fetched from a well-known JWKS endpoint. No shared secret is distributed to every service.

### The Verification Flow

```
Client                    Server / Service
  |                            |
  |-- POST /login -----------> |
  |<-- 200 OK, JWT ----------- |
  |                            |
  |-- GET /api/orders          |
  |   Authorization: Bearer <JWT>
  |                            |
  |                    [1] Split token on "."
  |                    [2] Verify signature
  |                    [3] Check exp, aud, iss
  |                    [4] Extract sub, role
  |<-- 200 OK, orders data --- |
```

Verification is pure CPU — no DB query required. This is the core scalability win.

## Build It / In Depth

### Minting a JWT in Python

```python
import jwt  # PyJWT library
import time

SECRET = "super-secret-key"  # For HS256; keep this out of source control

def issue_token(user_id: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "iss": "auth.example.com",
        "sub": user_id,
        "aud": "api.example.com",
        "role": role,
        "iat": now,
        "exp": now + 3600,  # 1 hour
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],
        audience="api.example.com",
    )
    # Raises jwt.ExpiredSignatureError, jwt.InvalidAudienceError, etc.


# --- Demo ---
token = issue_token("user_123", "admin")
print(token)

claims = verify_token(token)
print(claims["sub"], claims["role"])  # user_123  admin
```

### Decoding a token by hand (no library needed for reading)

```bash
# Split the token and base64-decode each segment
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.XXXXX"

echo $TOKEN | cut -d. -f1 | base64 --decode   # header JSON
echo $TOKEN | cut -d. -f2 | base64 --decode   # payload JSON
```

### RS256 — Auth server signs, every service verifies

```
Auth Server                       API Service A          API Service B
     |                                  |                      |
     | holds private_key.pem            | fetches public key   | fetches public key
     |                                  |   from JWKS endpoint |   from JWKS endpoint
     |                                  |                      |
     |--- issues JWT signed with -----> |                      |
     |    private key                   | verify(token,        | verify(token,
     |                                  |   public_key)        |   public_key)
```

The JWKS endpoint (`/.well-known/jwks.json`) publishes the public key set. Services cache this and rotate keys without restarting.

### Short-lived + Refresh token pattern

```
Access token:   exp = 15 minutes  (stateless, verified locally)
Refresh token:  exp = 30 days     (opaque, stored in DB, used once)

Client          Auth Server           Resource Server
  |                  |                       |
  |-- POST /refresh  |                       |
  |   {refreshToken} |                       |
  |<-- new accessJWT |                       |
  |                  |                       |
  |-- GET /data, Authorization: Bearer <JWT>  |
  |<-- 200 OK --------------------------------|
```

Keeping access tokens short-lived limits the blast radius if one is stolen — it expires in minutes rather than days.

## Use It

| Scenario                            | Recommended approach                                     |
|-------------------------------------|----------------------------------------------------------|
| Single-server web app               | Server-side sessions + secure cookie (simpler, revocable)|
| Microservices / API gateway         | JWT (RS256); gateway verifies, propagates claims         |
| Mobile / SPA calling REST APIs      | JWT access token + refresh token                         |
| Third-party API access (OAuth 2.0)  | JWT as Bearer token in Authorization header              |
| Machine-to-machine (M2M)            | JWT with `client_credentials` grant                      |

**Ecosystem implementations:**

- **Auth0 / Okta / Cognito** — fully managed JWT issuance + JWKS rotation
- **Keycloak** — self-hosted, supports RS256/ES256, full OIDC
- **Passport.js** — middleware layer in Node.js; `passport-jwt` strategy
- **Spring Security** — `spring-security-oauth2-resource-server` validates JWT out of the box
- **nginx / Kong** — gateway-level JWT verification plugin before requests reach upstream

## Common Pitfalls

- **Storing JWTs in `localStorage`**: Exposes the token to XSS attacks. Store access tokens in memory and refresh tokens in `HttpOnly; Secure; SameSite=Strict` cookies instead.

- **Long-lived access tokens**: A 24-hour or 7-day access token is almost as dangerous as a password. Set `exp` to 15 minutes and use refresh tokens for longevity.

- **Ignoring the `alg` claim on the server**: The infamous "algorithm confusion" attack sets `alg: none` in the header to bypass signature verification. Always explicitly allow-list algorithms on the server side — never trust the header's `alg` blindly.

- **Putting sensitive data in the payload**: Base64 is not encryption. Emails, phone numbers, internal IDs, or permission details are visible to anyone who holds the token. Minimize payload claims; use opaque IDs and look up details server-side when needed.

- **No revocation strategy**: JWTs are valid until `exp`, full stop. If a user logs out or a token is stolen, there is no built-in way to invalidate it. Solutions: keep access tokens very short-lived, maintain a `jti` blocklist (a small Redis set of revoked IDs), or switch to opaque tokens for sessions that need instant revocation.

## Exercises

1. **Easy** — Paste any JWT from jwt.io into the debugger. Identify the algorithm in the header, the subject and expiry in the payload, and explain why the signature section says "invalid" when you change any character in the payload.

2. **Medium** — Implement a simple Express.js middleware that validates a JWT on every protected route. It should return `401` for missing tokens, `401` for expired tokens, and `403` if the `role` claim is not `admin` on admin-only routes. Test it with a valid token, an expired token, and a tampered payload.

3. **Hard** — Design a revocation system for short-lived JWTs (15-minute expiry) that supports "log out all devices". Specify what you store in Redis, how the `jti` claim is used, how you avoid the Redis lookup becoming a hot bottleneck under high load, and how you handle Redis downtime without locking out all users.

## Key Terms

| Term           | What people think                          | What it actually means                                                                      |
|----------------|--------------------------------------------|---------------------------------------------------------------------------------------------|
| JWT            | An encrypted user session                  | A signed (not encrypted) JSON object; anyone with the token can read its claims             |
| Claim          | A field in the JSON body                   | A key-value statement about the subject; some are standardized (exp, sub), others custom    |
| Signature      | Proof the server "trusts" the token        | A cryptographic MAC or digital signature that proves the payload hasn't been altered        |
| HS256          | "Secure enough for production"             | Symmetric — auth server and every verifying service share the same secret; rotate carefully |
| RS256          | "Slower, more complex"                     | Asymmetric — private key stays on auth server; public key can be shared freely with anyone  |
| Base64URL      | Encryption                                 | Encoding only — it compresses binary to printable ASCII; fully reversible with no key       |
| Refresh token  | Another JWT                                | Usually an opaque random string stored in a DB; used only to mint new access tokens         |

## Further Reading

- [RFC 7519 — JSON Web Token](https://datatracker.ietf.org/doc/html/rfc7519) — the authoritative specification for claims, structure, and validation rules
- [jwt.io](https://jwt.io) — interactive debugger and library directory for every major language
- [OWASP JWT Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — attack vectors and mitigations (alg:none, key confusion, claim injection)
- [Auth0 — Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation) — reference implementation of the refresh + access token pattern with rotation and reuse detection
- [PyJWT Documentation](https://pyjwt.readthedocs.io/en/stable/) — well-documented Python library covering all algorithms, claim validation, and JWKS fetching
