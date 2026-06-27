# Tokens vs API Keys

> API keys identify the application; tokens identify the user — confusing them is the root of most auth bugs.

**Type:** Learn
**Prerequisites:** HTTP Basics, Authentication vs Authorization, OAuth 2.0 Overview
**Time:** ~25 minutes

---

## The Problem

You are building a ride-sharing platform. Your mobile app needs to call the backend on behalf of a logged-in rider. A third-party mapping company also needs to call your routes API to embed your data in their product. And your internal microservices need to call each other. Three different callers — same word "authentication" — but wildly different requirements.

If you reach for API keys everywhere, you end up handing long-lived secrets to mobile clients where they can be extracted from the APK. Every logged-out session still has a valid key. You cannot tell whether it was Alice or Bob who performed a sensitive action.

If you reach for JWT everywhere, your third-party mapping partner needs to create a "user account" to get a token, and their key expires every 15 minutes, breaking their nightly batch jobs.

The root issue: **identity type matters**. Some callers are applications (machines, services, partners); others are human users with sessions. The credential format — API key vs token — exists to serve these two different trust models precisely.

---

## The Concept

### What an API Key Actually Is

An API key is an opaque, high-entropy random string that acts as a long-lived password for a service account or an application. It carries no claims of its own. When the API Gateway sees the key, it must **look it up in a data store** to discover who owns it, what scopes it has, and whether it is still valid.

```
Client                         API Gateway         Key Store (DB/Redis)
  |  GET /v1/routes             |                        |
  |  x-api-key: ak_live_...    |                        |
  |--------------------------->|                        |
  |                            |-- lookup(ak_live_..)-->|
  |                            |<-- {owner, scopes, ok}--|
  |                            |                        |
  |                            |-- forward request ---> [Service]
```

Key properties:
- **Opaque** — the string itself reveals nothing about the owner.
- **Stateful validation** — every request hits the key store.
- **Long-lived** — typically rotate on a schedule (months/years), not per session.
- **Application identity** — identifies an application or a partner, not a human user.
- **No embedded expiry** — revocation is immediate (delete the row), but expiry requires explicit logic.

### What a Token (JWT) Actually Is

A JSON Web Token is a **self-contained, signed data structure** that carries claims inside it. The server does not need to look anything up — it just verifies the cryptographic signature and reads the payload.

```
Header (Base64Url)          Payload (Base64Url)          Signature
{                           {                            HMAC-SHA256(
  "alg": "HS256",             "sub": "user_42",            base64url(header) +
  "typ": "JWT"                "roles": ["rider"],           "." +
}                             "iat": 1719360000,            base64url(payload),
                              "exp": 1719363600             secret
                            }                            )
```

The three parts are joined with dots: `<header>.<payload>.<signature>`.

Validation flow — entirely in-process, no round-trips:

```
Client                         API Gateway
  |  GET /v1/trips              |
  |  Authorization: Bearer <JWT>|
  |--------------------------->|
  |                            | 1. Decode header, find alg
  |                            | 2. Verify signature with public key / secret
  |                            | 3. Check exp, nbf, iss, aud claims
  |                            | 4. Extract sub + roles → forward to service
  |                            |
  |                            |-- forward (with user context in headers) --> [Service]
```

Key properties:
- **Self-contained** — the payload carries everything needed for authorization decisions.
- **Stateless validation** — no DB call; scales horizontally without a shared session store.
- **Short-lived** — `exp` is typically 15 minutes to 1 hour.
- **User identity** — `sub` is a user ID; claims encode roles, permissions, tenancy.
- **Hard to revoke** — because validation is local, a stolen token is valid until it expires.

### The Core Trade-off Table

| Dimension            | API Key                              | JWT (Access Token)                    |
|----------------------|--------------------------------------|---------------------------------------|
| **Identifies**       | Application / service account        | Authenticated user (or service)       |
| **Validation**       | Server-side DB/cache lookup          | Local signature verification          |
| **Statefulness**     | Stateful (key store required)        | Stateless (claims are self-contained) |
| **Lifetime**         | Long-lived (months–years)            | Short-lived (minutes–hours)           |
| **Revocation**       | Immediate (delete from store)        | Difficult before expiry               |
| **Carries claims**   | No — server must look them up        | Yes — roles, scopes, tenancy embedded |
| **Secret exposure**  | Must be kept server-side / env vars  | Safe to send to clients (signed, not encrypted) |
| **Rotation burden**  | Manual; breaks integrations          | Auto via refresh token rotation       |
| **Best fit**         | M2M, 3rd-party integrations, CLIs    | User sessions, single-page apps, mobile |

---

## In Depth

### The Full Token Flow (OAuth 2.0 / OIDC Pattern)

```
Browser / Mobile App          Identity Provider (IdP)      API Gateway       Backend Service
       |                               |                        |                    |
       |--- POST /auth/login --------->|                        |                    |
       |    {email, password}          |                        |                    |
       |<-- 200 {access_token (JWT),   |                        |                    |
       |         refresh_token} -------|                        |                    |
       |                               |                        |                    |
       |--- GET /api/trips             |                        |                    |
       |    Authorization: Bearer <JWT>|--------------------->>|                    |
       |                               |    verify sig + exp    |                    |
       |                               |    (no DB call)        |--- forward ------->|
       |                               |                        |   x-user-id: 42    |
       |                               |                        |   x-roles: rider   |
       |<----- 200 {trips: [...]} -----|------------------------|<------------------|
```

When the access token expires, the client silently exchanges the refresh token for a new pair:

```
App                              Token Endpoint
 |--- POST /auth/refresh -------->|
 |    {refresh_token: <opaque>}   |
 |<-- 200 {new_access_token,      |
 |         new_refresh_token} ----|   ← refresh token rotation
```

Refresh token rotation invalidates the old refresh token on each use. If a refresh token is stolen and replayed, the server sees two uses of the same token and can revoke the family.

### The Full API Key Flow

```python
# Step 1: Developer registers and generates a key (server-side)
import secrets, hashlib

def generate_api_key():
    raw = secrets.token_urlsafe(32)          # e.g. "ak_live_Xk9..."
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    db.execute(
        "INSERT INTO api_keys (hash, owner_id, scopes, created_at) VALUES (?,?,?,?)",
        (key_hash, owner_id, ["routes:read"], now())
    )
    return raw   # returned ONCE; never stored in plaintext
```

```python
# Step 2: Validation middleware (FastAPI example)
async def validate_api_key(request: Request):
    raw_key = request.headers.get("x-api-key")
    if not raw_key:
        raise HTTPException(status_code=401)

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    record = await redis.get(f"apikey:{key_hash}")          # cache-first
    if not record:
        record = await db.fetchone(
            "SELECT owner_id, scopes FROM api_keys WHERE hash=? AND revoked=0",
            (key_hash,)
        )
        if record:
            await redis.setex(f"apikey:{key_hash}", 300, json.dumps(record))

    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")

    request.state.owner_id = record["owner_id"]
    request.state.scopes   = record["scopes"]
```

> **Tip:** Never store API keys in plaintext. Store a SHA-256 hash. Return the raw key exactly once at creation — just like a password reset token.

### Choosing a Format: Decision Tree

```
Is the caller a human user with a session?
  YES → Issue a short-lived JWT access token + refresh token.
        Use OIDC/OAuth 2.0. Identity Provider manages the flow.

  NO → Is this a 3rd-party developer / partner integration?
         YES → Issue an API key. Long-lived, scoped, revocable.
               Store only the hash server-side.

         NO → Is this an internal service-to-service call?
                YES → mTLS + service account JWT (workload identity)
                      or a scoped API key per environment.
                NO → Re-examine whether you need auth at all.
```

---

## Use It

### Where Real Systems Use Each

| System / Service   | Credential Used                          | Why                                        |
|--------------------|------------------------------------------|--------------------------------------------|
| **Stripe**         | API keys (`sk_live_...`, `pk_live_...`)  | M2M; long-lived; scoped by secret/publishable |
| **GitHub**         | Personal Access Tokens (PATs) + OAuth apps | PATs are API keys scoped to repos/orgs   |
| **AWS**            | Access Key ID + Secret (API keys) for CLI; STS temporary tokens for assumed roles | Long-term for automation, short-term for humans |
| **Auth0 / Okta**   | JWT access tokens (RS256 signed)         | Stateless user sessions, RBAC in claims   |
| **Google APIs**    | API key for public data; OAuth token for user data | Separation of public vs. user-scoped access |
| **Kubernetes**     | Service Account JWTs (OIDC)              | Workload identity; short-lived, bound to pod |

### Token Types in OAuth 2.0

OAuth distinguishes two token types with different validation mechanics:

| Type             | Format     | Validation         | Used For                        |
|------------------|------------|--------------------|---------------------------------|
| **Access Token** | JWT or opaque | Local (JWT) or introspection endpoint | Bearer credential on API calls |
| **Refresh Token**| Opaque     | Database lookup    | Obtaining new access tokens     |
| **ID Token**     | JWT (OIDC) | Local sig verify   | Proving user identity to client |

Opaque access tokens require a token introspection endpoint (`POST /oauth/introspect`), making them stateful like API keys. JWT access tokens are stateless but carry the revocation tradeoff.

---

## Common Pitfalls

- **Storing API keys in client-side code.** Mobile apps and frontend JS are decompilable. Public API keys (like Stripe's publishable key) are intentionally safe for clients. Secret keys never are. Use a backend proxy for any secret-key operation.

- **Issuing long-lived JWTs to avoid the refresh dance.** A 7-day JWT is functionally equivalent to an API key — you lose revocability entirely. Keep access tokens under 1 hour. Use the refresh token to silently renew.

- **Not hashing API keys at rest.** A database dump or a compromised replica reveals all keys in plaintext. Hash with SHA-256 (fast is fine here — keys are high entropy, rainbow tables don't apply).

- **Embedding sensitive claims in JWT without encryption.** JWT is Base64-encoded, not encrypted. Anyone who intercepts the token (or reads it from `localStorage`) can decode the payload. Do not put PII, financial data, or internal system details in the payload. Use JWE if you need confidentiality.

- **Ignoring the JWT `aud` (audience) claim.** A token issued for your mobile app is valid against your web API too if you skip audience validation. Always set `aud` to the specific service and verify it on receipt.

---

## Exercises

1. **Easy** — Given a JWT `eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzQyIiwiZXhwIjoxNzE5MzYzNjAwfQ.<sig>`, decode the payload (use jwt.io or base64 decode). What user ID does it identify, and when does it expire? What can you learn from this without the signing key?

2. **Medium** — Design an API key system for a SaaS that needs: per-workspace keys, per-key rate limits, scope restrictions (read-only vs read-write), and instant revocation. Sketch the database schema and the validation middleware. How do you handle cache invalidation on revocation?

3. **Hard** — Your team proposes replacing all user JWTs with opaque tokens validated through a central introspection service to solve the revocation problem. Analyze the trade-offs: latency impact, single point of failure, horizontal scaling, and cache strategy. When is this worth the cost, and when is short-TTL JWT + refresh rotation the better answer?

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **API Key** | Any authentication credential | An opaque, long-lived secret identifying an application, validated server-side via lookup |
| **JWT** | A secure, encrypted token | A Base64-encoded, *signed* (not encrypted by default) JSON structure carrying self-describing claims |
| **Stateless auth** | Auth that uses no server memory | Validation that requires no external lookup — the token carries everything needed to make the decision |
| **Refresh token** | A second API key | A one-time-use opaque credential that exchanges for a new access token; rotated on every use |
| **Token introspection** | Reading a JWT payload | A server-side endpoint (`/oauth/introspect`) that validates opaque tokens and returns their metadata |
| **Scope** | Role or permission | A string label that bounds what a credential is authorized to do (e.g., `routes:read`, `trips:write`) |
| **Claims** | JWT metadata fields | Key-value assertions embedded in a token payload (`sub`, `exp`, `roles`, `iss`, `aud`, etc.) |

---

## Further Reading

- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) — the canonical spec; read sections 4 (claims) and 7 (validation) carefully.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — defines access tokens, refresh tokens, and grant types.
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/) — covers broken authentication and improper asset management; directly applicable to both key types.
- [Auth0 Docs: Access Tokens vs ID Tokens](https://auth0.com/docs/secure/tokens/access-tokens) — practical breakdown with real configuration examples.
- [AWS STS Documentation: Temporary Security Credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html) — real-world example of short-lived tokens replacing long-lived keys for human and machine access.
