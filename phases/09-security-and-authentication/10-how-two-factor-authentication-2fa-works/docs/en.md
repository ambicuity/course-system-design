# How Two-factor Authentication (2FA) Works?

> Passwords prove what you know; 2FA adds proof of what you have or who you are — stealing one factor is no longer enough.

**Type:** Learn
**Prerequisites:** Password Hashing, Session vs Token Authentication
**Time:** ~18 minutes

## The Problem

A password database breach is not a hypothetical. LinkedIn (2012), RockYou2021, and dozens of other incidents exposed hundreds of millions of credentials. When a user reuses the same password across sites — and most do — a single breach cascades into account takeovers on every service that user touches. An attacker who buys a credential dump on the dark web can replay the username/password pair against your service in seconds, and your login endpoint cannot tell the difference between the real user and the attacker.

The root issue is that a password is a single shared secret. Once it leaves the user's head (written on a sticky note, phished, keylogged, or simply guessed), the attacker possesses it just as completely as the legitimate user does. There is no physical presence requirement, no device requirement, no biological requirement — just a string.

Two-factor authentication breaks this model. Even with a valid password, an attacker must simultaneously control a second independent channel — typically a device the real user holds. Account takeovers drop dramatically: Google reported in 2019 that device-based 2FA blocks 99% of bulk phishing attacks.

## The Concept

### The Three Authentication Factors

Authentication factors are independent sources of evidence about identity. They fall into three categories:

| Factor | Name | Examples |
|--------|------|---------|
| Something you **know** | Knowledge factor | Password, PIN, security questions |
| Something you **have** | Possession factor | Phone (TOTP app), hardware key (YubiKey), SMS to SIM |
| Something you **are** | Inherence factor | Fingerprint, Face ID, retina scan |

**2FA** requires exactly two different factors — not two passwords, which are both "something you know." **MFA** is the broader term for requiring two or more factors; 2FA is the most common MFA configuration.

### How the Flow Works

```
 ┌─────────────┐                        ┌──────────────────────┐
 │   Browser   │                        │  Auth Server         │
 └──────┬──────┘                        └──────────┬───────────┘
        │  1. POST /login {user, password}          │
        │ ─────────────────────────────────────────>│
        │                                           │  2. Verify password hash
        │  3. 200 OK  {state: "needs_2fa",          │
        │              session_token: <tmp>}        │
        │ <─────────────────────────────────────────│
        │                                           │
        │  4. POST /verify-2fa {otp: "847291"}      │
        │ ─────────────────────────────────────────>│
        │                                           │  5. Validate OTP
        │  6. 200 OK  {access_token: <jwt>}         │
        │ <─────────────────────────────────────────│
```

The server issues a short-lived **partial session** after step 1 — the user is authenticated on the first factor but not yet authorised. This token is scoped only to the `/verify-2fa` endpoint. Full access is granted only after the second factor is confirmed.

### TOTP: The Dominant Standard (RFC 6238)

Time-based One-Time Passwords are the engine behind Google Authenticator, Authy, and Microsoft Authenticator. The algorithm is elegant:

**Enrollment (once):**
- Server generates a random 160-bit shared secret `K`.
- Secret is transmitted to the user's device via a QR code (a `otpauth://` URI).
- Both sides now share `K` — no further communication needed.

**Code generation (every 30 s):**
```
T     = floor( (unix_timestamp - T₀) / 30 )   # 30-second time step
HMAC  = HMAC-SHA1(K, T)                        # 20-byte digest
offset = HMAC[19] & 0x0f                       # low nibble of last byte
code  = (HMAC[offset..offset+3] & 0x7fffffff) % 10⁶
```

The result is the 6-digit code shown in the app. The server performs the same computation. If the codes match (allowing ±1 window for clock skew), authentication succeeds. Because the code changes every 30 seconds and depends on the secret `K`, an intercepted code is useless 30 seconds later.

### SMS OTP — Convenient but Weaker

The server generates a random 6–8 digit code, stores it with a 5–10 minute TTL, then sends it via SMS. The user types it in. There is no shared cryptographic secret established in advance; the OTP is created fresh per authentication.

**Why it is weaker than TOTP:**
- SIM-swap attacks allow attackers to redirect SMS to a new device via social engineering of the carrier.
- SS7 protocol vulnerabilities can allow interception of SMS in transit.
- The code travels over a third-party carrier network outside your control.

NIST SP 800-63B deprecates SMS OTP as a sole 2FA mechanism for high-assurance use cases.

## Build It / In Depth

### Implementing TOTP Verification (Python)

```python
import hmac, hashlib, struct, time, base64

def hotp(secret_b32: str, counter: int) -> str:
    """HOTP (RFC 4226) — building block for TOTP."""
    key = base64.b32decode(secret_b32.upper())
    msg = struct.pack(">Q", counter)          # counter as 8-byte big-endian
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)

def totp(secret_b32: str, window: int = 1) -> list[str]:
    """TOTP (RFC 6238) — returns valid codes for current window."""
    T = int(time.time()) // 30
    return [hotp(secret_b32, T + i) for i in range(-window, window + 1)]

def verify_totp(secret_b32: str, user_code: str) -> bool:
    """Accept codes for current ±1 time steps to handle clock skew."""
    return user_code in totp(secret_b32, window=1)
```

### Enrollment Flow (Pseudocode)

```python
import secrets, pyotp, qrcode

def enroll_2fa(user_id: str) -> dict:
    secret = pyotp.random_base32()          # 160-bit random secret
    db.store(user_id, totp_secret=secret, totp_verified=False)

    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user_email,
        issuer_name="MyApp"
    )
    qr = qrcode.make(uri)                  # render QR for user to scan
    return {"qr": qr, "manual_code": secret}

def confirm_enrollment(user_id: str, code: str) -> bool:
    secret = db.get_totp_secret(user_id)
    if verify_totp(secret, code):
        db.update(user_id, totp_verified=True)
        recovery_codes = generate_recovery_codes(user_id)
        return True, recovery_codes        # show recovery codes ONCE
    return False, []
```

### Recovery Codes

Recovery codes are single-use backup codes (typically 8–16 alphanumeric characters, 8–10 codes per account) stored as bcrypt hashes in the database. When a user loses their authenticator device, they can consume one recovery code to bypass 2FA and regain access. Each code must be deleted (or marked used) immediately after consumption.

```sql
CREATE TABLE recovery_codes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    code_hash   TEXT NOT NULL,        -- bcrypt hash of the plaintext code
    used_at     TIMESTAMPTZ,          -- NULL until consumed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Use It

| Method | Mechanism | Security Level | UX Friction | When to Use |
|--------|-----------|---------------|-------------|-------------|
| TOTP app (Authenticator) | Shared secret + time | High | Low–Medium | Most consumer and enterprise apps |
| Hardware key (FIDO2/WebAuthn) | Public-key cryptography, phishing-resistant | Very High | Low (tap a key) | High-value accounts, privileged access |
| SMS OTP | Server-generated code via carrier | Medium | Low | Legacy systems, broad user base without smartphones |
| Push notification (Duo, Okta) | Out-of-band approval | High | Very Low | Enterprise SSO, VPN login |
| Email OTP | Server-generated code via email | Medium–Low | Low | Low-risk flows, fallback |
| Biometrics (Face/Touch ID) | On-device biometric unlock | High (local) | Very Low | Mobile apps with secure enclave |

**FIDO2/WebAuthn** deserves special mention: the authenticator (hardware key or platform authenticator) signs a challenge with a private key that never leaves the device. The server stores only a public key. This architecture is phishing-proof — the signed challenge is scoped to the exact origin, so a fake phishing site receives a signature that is useless against the real site.

Use it via the Web Authentication API in the browser or platform SDKs on iOS/Android. Services like Cloudflare, GitHub, and Apple now offer passkeys, which extend WebAuthn to replace the password entirely.

## Common Pitfalls

- **Skipping 2FA for API keys and service accounts.** Developer portals and internal dashboards are prime targets. Enforce 2FA org-wide in your identity provider rather than trusting individual users to opt in.

- **Allowing SMS as the only 2FA option for privileged accounts.** SIM-swap attacks are documented and have been used against crypto executives and public figures. Require TOTP or hardware keys for admin and finance roles.

- **Not issuing recovery codes at enrollment.** Users who lose their phone and have no recovery path will be permanently locked out. Generate recovery codes at enrollment, display them once, and store bcrypt hashes — not plaintext.

- **Accepting the same OTP twice.** TOTP codes are valid for a 30-second window. If an attacker intercepts a code mid-flight, they can replay it within that window. Track consumed codes in a short-lived cache (Redis with 90-second TTL) and reject re-use.

- **Ignoring the partial session token scope.** After step 1, the server issues a temporary token to track the in-progress 2FA challenge. If this token is too broad in scope, an attacker who steals it at step 1 can skip 2FA and call other endpoints. Scope the partial session strictly to the `/verify-2fa` route.

## Exercises

1. **Easy:** Draw the TOTP enrollment and login flows for a user who sets up Google Authenticator. Identify every piece of data stored on (a) the server and (b) the user's device after enrollment.

2. **Medium:** A user reports their TOTP code is always rejected. Diagnose possible root causes and propose a solution for each (hint: think about clock skew, wrong secret, wrong time step, code reuse rejection, and app time zone issues).

3. **Hard:** Design a 2FA system that supports TOTP, hardware keys (WebAuthn), and SMS fallback, with the constraint that SMS can only be used if no other factor has been enrolled. Outline the database schema, the enrollment state machine, and the policy enforcement logic at the verify endpoint.

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| 2FA | "Two passwords" | Two *different factor types* — e.g., password + TOTP; two passwords is just stronger single-factor |
| TOTP | "One-time password sent by the server" | A code generated *locally* on the user's device using a shared secret and the current timestamp |
| HOTP | "Just TOTP but older" | HMAC-based OTP (RFC 4226) uses an *incrementing counter* instead of time — the base algorithm TOTP builds on |
| Recovery codes | "A backup password" | Single-use bypass codes stored as hashes, consumed exactly once to recover account access |
| FIDO2 / WebAuthn | "Another name for TOTP" | A phishing-resistant public-key standard where the private key never leaves the user's device |
| Partial session | "A half-authenticated JWT" | A short-lived, narrowly scoped token issued after factor 1 that authorises only the factor-2 verification call |
| SIM swap | "A technical attack on the network" | Social engineering of a mobile carrier to transfer a victim's phone number to an attacker-controlled SIM |

## Further Reading

- [RFC 6238 — TOTP: Time-Based One-Time Password Algorithm](https://datatracker.ietf.org/doc/html/rfc6238) — the canonical specification; short and readable.
- [NIST SP 800-63B — Digital Identity Guidelines: Authentication](https://pages.nist.gov/800-63-3/sp800-63b.html) — definitive US government guidance on authenticator assurance levels and acceptable 2FA methods.
- [WebAuthn Guide by Duo](https://webauthn.guide) — practical introduction to FIDO2/WebAuthn with interactive demos.
- [Google Security Blog: 2FA Efficacy Study (2019)](https://security.googleblog.com/2019/05/new-research-how-effective-is-basic.html) — data on how different 2FA methods block automated and targeted attacks.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — implementation-level checklist covering 2FA, rate limiting, lockout policies, and session management.
