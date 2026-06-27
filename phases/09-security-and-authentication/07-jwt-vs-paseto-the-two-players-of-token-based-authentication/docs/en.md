# JWT vs PASETO: The Two Players of Token-Based Authentication

> JWT gives you flexibility and footguns; PASETO gives you guardrails and sanity.

**Type:** Learn
**Prerequisites:** Stateless vs Stateful Authentication, Public-Key Cryptography Basics, HTTP Headers and Cookies
**Time:** ~25 minutes

---

## The Problem

Your API needs to verify that a request comes from a user who previously authenticated. You issue a token at login, the client sends it on every request, and your server validates it — no database round-trip needed. Sounds clean. But the token format you choose carries real security consequences.

JWT is the de-facto standard. It is flexible by design: you pick the algorithm, you pick the claims, you decide how the library should behave. That flexibility is the source of its most famous vulnerabilities. The `alg: none` attack, the algorithm confusion attack, and HS256-with-a-public-key are not theoretical; they have caused real breaches. The spec allows these things, and many libraries either encouraged or silently accepted them.

PASETO (Platform-Agnostic Security Tokens) was designed as a direct response to JWT's design mistakes. It removes the algorithm negotiation entirely: the version number in the token dictates the cryptography, full stop. The question for you as a system designer is not "which is newer" but "which set of trade-offs fits my threat model, team expertise, and ecosystem."

---

## The Concept

### JWT — Structure and How It Works

A JWT is three base64url-encoded segments joined by dots:

```
HEADER.PAYLOAD.SIGNATURE
```

**Header** — a JSON object declaring the token type and signing algorithm:
```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

**Payload** — a JSON object containing claims (registered, public, or private):
```json
{
  "sub": "user_42",
  "iss": "auth.example.com",
  "aud": "api.example.com",
  "exp": 1750000000,
  "iat": 1749996400,
  "roles": ["admin"]
}
```

**Signature** — computed over `base64url(header) + "." + base64url(payload)` using the algorithm declared in the header.

```
RS256 signature = RSA-PKCS1v15-Sign(
    SHA-256( base64url(header) + "." + base64url(payload) ),
    private_key
)
```

The payload is **not encrypted** in a standard JWT (JWS). It is merely base64url-encoded — anyone can decode it. If you need confidentiality, you use JWE (JSON Web Encryption), a separate, significantly more complex spec.

**JWT Algorithm Zoo**

| Algorithm | Type | Key material | Notes |
|-----------|------|-------------|-------|
| `HS256` | HMAC-SHA-256 | Shared secret | Fast; both sides must share the secret |
| `RS256` | RSA-PKCS1v15 | RSA key pair | Common in OAuth/OIDC; slow key generation |
| `ES256` | ECDSA P-256 | EC key pair | Smaller keys than RSA for equivalent security |
| `EdDSA` | Ed25519 | EC key pair | Modern, fast, less footgun-prone than ECDSA |
| `none` | None | — | **No signature** — allowed by spec, catastrophic in practice |
| `PS256` | RSA-PSS | RSA key pair | More secure padding than PKCS1v15 |

The core problem: the algorithm is embedded in the token itself, and the server must trust it — creating an attack surface.

---

### The JWT Attack Surface

**1. The `alg: none` Attack**
An attacker strips the signature and sets `"alg": "none"`. If the library checks `alg` from the token before validating, it may accept the unsigned token as valid. RFC 7518 explicitly permits `none` as a valid algorithm value.

**2. Algorithm Confusion (RS256 → HS256)**
If a server accepts both RS256 and HS256, an attacker can:
1. Obtain the server's RSA *public* key (often published at a JWKS endpoint).
2. Forge a token with `"alg": "HS256"` and sign it using the public key as the HMAC secret.
3. The server, seeing `alg: HS256`, uses the public key as the HMAC secret to verify — and it matches.

**3. Key Confusion via JWKS Kid Injection**
Crafting a `kid` header that causes the library to load an attacker-controlled key from a URL.

```
Token flow with algorithm confusion:

Attacker                         Server
   |                                |
   | -- Fetch public key (JWKS) --> |
   | <-- RSA public key  ---------- |
   |                                |
   | Craft JWT:                     |
   |   header: { alg: "HS256" }     |
   |   sign with public_key         |
   |   as HMAC secret               |
   |                                |
   | -- Send forged JWT ----------> |
   |                       verifies with public_key
   |                       as HMAC secret: SUCCESS
```

---

### PASETO — Structure and Design Philosophy

PASETO's token format:

```
version.purpose.payload[.footer]
```

- **version** — `v1`, `v2`, `v3`, or `v4`. Each version pins specific algorithms.
- **purpose** — either `local` (encrypted) or `public` (signed).
- **payload** — base64url-encoded bytes (plaintext claims in `public`; ciphertext in `local`).
- **footer** — optional, unencrypted metadata (key ID, issuer) — always authenticated.

**PASETO Versions and Algorithms**

| Version | Purpose | Algorithm | Status |
|---------|---------|-----------|--------|
| v1.local | Symmetric encryption | AES-256-CTR + HMAC-SHA-384 | Deprecated (legacy) |
| v1.public | Asymmetric signing | RSA-PSS-2048-SHA-384 | Deprecated (legacy) |
| v2.local | Symmetric encryption | XChaCha20-Poly1305 | Stable |
| v2.public | Asymmetric signing | Ed25519 | Stable |
| v3.local | Symmetric encryption | AES-256-CTR-HMAC-SHA-384 (NIST) | Stable (FIPS-compatible) |
| v3.public | Asymmetric signing | ECDSA P-384 | Stable (FIPS-compatible) |
| v4.local | Symmetric encryption | XChaCha20-Poly1305 | Recommended |
| v4.public | Asymmetric signing | Ed25519 | Recommended |

**Key insight:** The version embeds the algorithm. There is no `alg` field to tamper with. An attacker cannot convince a v4.public verifier to use a different algorithm.

**local vs public purpose**

```
PASETO local (v4.local):
  - Symmetric key shared between issuer and verifier
  - Payload is ENCRYPTED — third parties cannot read claims
  - Use when: issuer = verifier (same service or tightly coupled services)

PASETO public (v4.public):
  - Asymmetric: issuer holds private key; verifiers hold public key
  - Payload is SIGNED but NOT encrypted — claims are readable
  - Use when: multiple verifiers (microservices, third-party APIs)
```

---

### Head-to-Head Comparison

| Dimension | JWT | PASETO |
|-----------|-----|--------|
| Algorithm selection | Declared in token header (attacker-visible) | Fixed by version number |
| Algorithm confusion attack | Possible if library misconfigured | Not possible by design |
| `alg: none` attack | Possible in vulnerable libraries | Not possible — no `none` option |
| Payload confidentiality | JWS = no; JWE = yes (complex) | `local` = yes; `public` = no |
| Spec complexity | RFC 7519 + RFC 7515 + RFC 7518 + RFC 7516 | Single PASETO spec |
| Ecosystem maturity | Massive — every language, every framework | Growing — production-ready in major languages |
| OIDC/OAuth2 compatibility | Native — JWTs are the standard | Not standard; requires adaptation |
| Interoperability | Universal | Limited to PASETO-aware systems |
| Key management | JWKS standard, discovery built-in | Manual; no standard discovery endpoint |
| FIPS compliance | RSA, ECDSA (some variants) | v3 uses NIST algorithms |

---

## Build It / In Depth

### Step 1 — JWT Issue and Verify (Python, PyJWT)

```python
import jwt
from datetime import datetime, timedelta, timezone

SECRET = "super-secret-signing-key"  # For HS256
ALGORITHM = "HS256"

def issue_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iss": "auth.example.com",
        "aud": "api.example.com",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    # CRITICAL: always pass algorithms= explicitly
    # Never let the library read alg from the token
    return jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],          # whitelist, not from token header
        audience="api.example.com",
        options={"require": ["exp", "iss", "sub"]},
    )

token = issue_token("user_42")
claims = verify_token(token)
print(claims["sub"])  # user_42
```

Notice `algorithms=["HS256"]` is passed explicitly. The library should never accept whatever `alg` the token claims.

### Step 2 — JWT with RS256 (Asymmetric)

```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import jwt

private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()

token = jwt.encode({"sub": "user_42"}, private_key, algorithm="RS256")

# Verifiers only need the public key
claims = jwt.decode(token, public_key, algorithms=["RS256"])
```

### Step 3 — PASETO v4 Public (Python, pyseto)

```python
import pyseto
from pyseto import Key

# Generate Ed25519 key pair
private_key = Key.new(version=4, purpose="public", key=None)  # generate
public_key = private_key.public_key

# Issue
token = pyseto.encode(
    private_key,
    payload={"sub": "user_42", "exp": "2026-01-01T00:00:00Z"},
    footer={"kid": "key-2024-v4"},
)
print(token)
# v4.public.<base64url-payload>.<base64url-footer>

# Verify
decoded = pyseto.decode(public_key, token)
print(decoded.payload)   # {"sub": "user_42", "exp": "..."}
print(decoded.footer)    # {"kid": "key-2024-v4"}
```

No algorithm parameter. The `v4` prefix locks it to Ed25519 — the library rejects any token that starts with a different version prefix.

### Step 4 — PASETO v4 Local (Symmetric, Encrypted Payload)

```python
import pyseto
from pyseto import Key
import secrets

# 32 random bytes for XChaCha20-Poly1305
raw_key = secrets.token_bytes(32)
local_key = Key.new(version=4, purpose="local", key=raw_key)

# Payload is encrypted — third parties cannot read claims
token = pyseto.encode(
    local_key,
    payload={"sub": "user_42", "role": "admin"},
    footer={"service": "billing"},
)

decoded = pyseto.decode(local_key, token)
print(decoded.payload)   # decrypted claims
```

### Decision Flow

```
Need token-based auth?
        |
        v
  Does ecosystem mandate JWT?
  (OAuth2 provider, OIDC, existing infra)
        |
       YES --> Use JWT with RS256 or ES256
               Pin algorithms= in library config
               Validate iss/aud/exp always
        |
       NO
        |
        v
  Can you control both issuer and verifier?
        |
       YES --> PASETO v4.local (encrypted)
        |
       NO (multiple verifiers / third parties)
        |
        v
  Use PASETO v4.public (signed, Ed25519)
```

---

## Use It

**JWT in the wild**

- **Auth0, Okta, Cognito** — all issue JWTs as ID tokens and access tokens per the OIDC spec. The standard mandates JWT; PASETO is not an option here.
- **Kubernetes** — service account tokens are JWTs signed by the cluster CA.
- **Firebase** — authentication tokens are JWTs signed with RS256.
- **Spring Security, ASP.NET Core** — both have first-class JWT middleware.

**PASETO in the wild**

- **Paserk** (PASETO Extended Requirements for Keys) — a companion spec for key wrapping, key IDs, and password-protected keys. Addresses the JWKS gap.
- **FootprintJS / Footprint** — uses PASETO for session tokens specifically to avoid JWT's algorithm footguns.
- **ORY Kratos** — the open-source identity server supports PASETO tokens as of recent versions.
- Any greenfield service that controls its own auth stack and wants strong defaults out of the box.

**When to choose what**

| Scenario | Recommendation |
|----------|---------------|
| Integrating with an OAuth2/OIDC provider | JWT — you have no choice |
| Internal microservices, same org controls issuer & verifier | PASETO v4.public or v4.local |
| Sensitive claims (role, balance) must be opaque to clients | PASETO v4.local or JWE |
| FIPS-140-2 compliance required | PASETO v3 (NIST algorithms) |
| Broad language/framework support needed | JWT (larger ecosystem) |
| New service, greenfield, no compliance constraints | PASETO v4 |

---

## Common Pitfalls

- **Not pinning the algorithm in JWT libraries.** Many older libraries (node-jsonwebtoken before v9, python-jose in certain configurations) read `alg` from the token header unless you explicitly whitelist. Always pass `algorithms=["RS256"]` or equivalent. Never pass `algorithms=None`.

- **Using HS256 with a short or guessable secret.** HS256 is only as strong as your secret. Secrets shorter than 256 bits are offline-brutable. If you use HS256, generate a 256-bit random secret with a CSPRNG (`secrets.token_bytes(32)`) and never reuse it across environments.

- **Putting sensitive data in the JWT payload.** Standard JWT payloads (JWS) are base64url-encoded, not encrypted. Roles and user IDs are fine; social security numbers, passwords, or PII are not. Use JWE or PASETO v4.local if the payload must be confidential.

- **Ignoring token expiration and revocation.** Stateless tokens cannot be revoked without a blocklist. Set `exp` aggressively (15–60 minutes for access tokens) and build a short-lived token + refresh-token rotation pattern. Never issue tokens with no expiry.

- **Trusting the `kid` header blindly.** JWT allows a `kid` (key ID) header to hint which key to use for verification. Vulnerable implementations fetch the key from a URL specified in `kid` — a server-side request forgery and key injection vector. Always resolve `kid` against a static local registry or a trusted JWKS endpoint, never from an arbitrary URL.

- **Assuming PASETO eliminates all token security concerns.** PASETO removes cryptographic footguns, but you still need proper expiration, claim validation (`iss`, `aud`, `sub`), key rotation strategy, and transport security (TLS). The format does not substitute for a security architecture.

---

## Exercises

1. **Easy** — Decode the payload of a JWT without verifying the signature (using base64url decoding in any language). Observe what claims are visible. Now repeat with a PASETO v4.local token and explain why the payload is unreadable.

2. **Medium** — Simulate the algorithm confusion attack in a sandboxed environment: issue a JWT signed with RS256, extract the public key, and attempt to forge a token using that public key as an HS256 secret. Test whether your chosen JWT library rejects it when you pin `algorithms=["RS256"]` vs when you omit the pin.

3. **Hard** — Design a token issuance system for a microservices architecture with three services: an auth service, a payment service, and a notification service. The payment service must not be able to read tokens issued for the notification service, and vice versa. Choose between JWT and PASETO, justify your algorithm and purpose choice, define the claim schema, and sketch the key distribution strategy.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| JWT | An encrypted, secure token | A base64url-encoded JSON structure. The default (JWS) is **signed but not encrypted**. Anyone can decode the payload. |
| JWS | A type of JWT | JSON Web Signature — the signed-but-not-encrypted variant of JWT. What most people mean when they say "JWT". |
| JWE | Advanced JWT | JSON Web Encryption — a separate spec that encrypts the payload. Much more complex than JWS. |
| `alg: none` | A configuration option | A deliberate loophole in the JWT spec allowing tokens with **no signature at all**, exploitable in vulnerable libraries. |
| PASETO `local` | The local version | A token with a **symmetrically encrypted** payload. Only parties holding the shared key can read or verify it. |
| PASETO `public` | A public token anyone can read | A token with an **asymmetrically signed** payload. Anyone with the public key can verify it, but the payload is still readable (not confidential). |
| Algorithm confusion | Choosing the wrong algorithm | A specific attack where the server is tricked into using a different algorithm (e.g., RS256 public key as HS256 secret) to verify a forged token. |

---

## Further Reading

- **PASETO Specification (Official)** — https://paseto.io/rfc/ — The canonical spec covering all versions, purposes, and test vectors.
- **RFC 7519 — JSON Web Token (JWT)** — https://datatracker.ietf.org/doc/html/rfc7519 — The full JWT spec; read §4 (Claims) and §7 (Validation) carefully.
- **"Critical Vulnerabilities in JSON Web Token Libraries" — Auth0 (2015)** — https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/ — The original post documenting the `alg: none` and algorithm confusion attacks. Foundational reading.
- **PASERK — PASETO Extended Requirements for Keys** — https://github.com/paseto-standard/paserk — The companion key-wrapping and key-ID spec that addresses PASETO's lack of a JWKS equivalent.
- **"JWT Security Best Practices" — IETF BCP** — https://datatracker.ietf.org/doc/html/rfc8725 — RFC 8725: JSON Web Token Best Current Practices. Covers every known JWT attack class and the mitigations.
