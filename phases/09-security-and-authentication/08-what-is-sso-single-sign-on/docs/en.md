# What is SSO (Single Sign-On)?

> One login, everywhere — because users shouldn't re-authenticate at every door.

**Type:** Learn
**Prerequisites:** Session vs Token Authentication, OAuth 2.0 Basics, HTTP Cookies and Headers
**Time:** ~20 minutes

## The Problem

Imagine you work at a company that uses Salesforce for CRM, Jira for tickets, GitHub for code, and Slack for chat. Without SSO, every employee has four separate accounts with four separate passwords. When a new hire joins, IT provisions four accounts. When someone leaves, IT must revoke four accounts — and if they miss one, that person still has access. This is not a hypothetical: credential sprawl is one of the top causes of both security breaches and help-desk overhead.

The same problem hits consumer products. Google operates dozens of services: Gmail, YouTube, Google Docs, Google Maps, Google Drive. If you had to log in separately to each one, the experience would be unbearable. Users would reuse weak passwords across services, making every service as insecure as the weakest one.

Without SSO, authentication is duplicated across every service. Each service must store credentials, implement password reset flows, handle session management, and deal with MFA. With SSO, you centralize that complexity in a single **Identity Provider (IdP)** and let every other service delegate to it. Security improves, UX improves, and your audit log is in one place.

## The Concept

SSO separates the concept of **authentication** (who are you?) from the individual services that need to authorize access. Two roles are always present:

- **Identity Provider (IdP):** The central authority that authenticates the user and issues tokens. Examples: Okta, Google, Azure AD, Keycloak.
- **Service Provider (SP):** An application that trusts the IdP and grants access based on the token it receives. Examples: Salesforce, Slack, GitHub (with SAML configured).

### Sessions: Global vs Local

SSO maintains two separate sessions:

| Session | Owner | Scope | Stored in |
|---|---|---|---|
| **Global session** | IdP | All services | Cookie on IdP domain (e.g., `accounts.google.com`) |
| **Local session** | Each SP | That SP only | Cookie on the SP's domain |

When you log in once, the IdP sets a global session cookie. Every subsequent SP can detect this session and issue its own local session without prompting for credentials again.

### The SSO Flow (OIDC / Token-Based)

```
User                Gmail (SP)            SSO Auth Server (IdP)
 |                      |                          |
 |-- GET /inbox ------->|                          |
 |                      |-- No local session       |
 |<-- 302 redirect -----|  (redirect to IdP) ----->|
 |                                                 |
 |-- GET /login (IdP) ---------------------------->|
 |                                                 |-- No global session
 |<-- Login form ----------------------------------|
 |                                                 |
 |-- POST credentials ---------------------------->|
 |                                                 |-- Validates credentials
 |                                                 |-- Creates global session
 |                                                 |-- Creates signed token (JWT / SAML assertion)
 |<-- 302 redirect + token ----------------------->|
 |                                                 |
 |-- GET /inbox?token=... ->|                      |
 |                          |-- Validate token ---->|
 |                          |<-- "valid" + claims --|
 |                          |-- Create local session|
 |<-- 200 /inbox ----------|                       |
 |                                                 |
 |-- GET youtube.com ------>| (YouTube SP)         |
 |                          |-- No local session    |
 |<-- 302 redirect ---------|  (redirect to IdP) -->|
 |                                                 |-- Global session EXISTS
 |                                                 |-- Issues new token (no login needed)
 |<-- 302 redirect + token ----------------------->|
 |                                                 |
 |-- GET /?token=... ------>| (YouTube)            |
 |                          |-- Validate token ---->|
 |                          |<-- "valid" + claims --|
 |<-- 200 YouTube ---------|                       |
```

### Key Protocols

SSO is not a single protocol — it is a concept implemented by several protocols:

| Protocol | Format | Best for | Notes |
|---|---|---|---|
| **SAML 2.0** | XML assertions | Enterprise B2B, HR/ERP systems | Verbose but widely supported; uses POST binding |
| **OpenID Connect (OIDC)** | JSON (JWT) | Consumer apps, modern APIs | Built on OAuth 2.0; returns `id_token` + `access_token` |
| **CAS (Central Auth Service)** | HTTP redirects + XML | University systems | Older, simpler; rarely used in new builds |
| **Kerberos** | Tickets | Internal corporate networks, Active Directory | Works at network level; no browser redirects |

**OIDC is the right choice for almost every new system.** SAML is required when integrating with legacy enterprise software that only speaks SAML.

### Token Validation: Two Strategies

When a Service Provider receives a token, it can validate it two ways:

1. **Back-channel (introspection):** The SP calls the IdP's `/introspect` endpoint with the token. The IdP confirms validity and returns claims. Slower (network call) but always authoritative — revocation is instant.
2. **Local verification (JWT signature):** The SP holds the IdP's public key and verifies the JWT signature locally. Faster (no network call) but revocation is delayed until the token expires.

Most production systems use local verification for `access_token` checks and back-channel for security-sensitive decisions (e.g., account takeover scenarios).

## Build It / In Depth

### OIDC SSO Flow — Step by Step with Real Parameters

**Step 1: SP redirects user to IdP (Authorization Request)**

```
GET https://accounts.google.com/o/oauth2/v2/auth
  ?response_type=code
  &client_id=YOUR_CLIENT_ID
  &redirect_uri=https://myapp.com/callback
  &scope=openid%20email%20profile
  &state=abc123_csrf_token
  &nonce=xyz789
```

- `state` prevents CSRF: the SP stores this value, then verifies it matches on callback.
- `nonce` prevents replay attacks on the `id_token`.
- `scope=openid` is what makes this OIDC (not plain OAuth 2.0).

**Step 2: User authenticates at IdP**

If no global session exists, the user sees the login form. If a global session cookie is present, this step is silent — the IdP immediately redirects back.

**Step 3: IdP redirects back with Authorization Code**

```
GET https://myapp.com/callback
  ?code=4/P7q7W91a-oMsCeLvIaQm6bTrgtp7
  &state=abc123_csrf_token
```

The `code` is short-lived (typically 60 seconds) and single-use.

**Step 4: SP exchanges code for tokens (back-channel)**

```bash
curl -X POST https://oauth2.googleapis.com/token \
  -d "code=4/P7q7W91a-oMsCeLvIaQm6bTrgtp7" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "redirect_uri=https://myapp.com/callback" \
  -d "grant_type=authorization_code"
```

Response:
```json
{
  "access_token": "ya29.A0ARrdaM...",
  "expires_in": 3599,
  "id_token": "eyJhbGciOiJSUzI1NiJ9...",
  "token_type": "Bearer",
  "refresh_token": "1//04..."
}
```

**Step 5: SP decodes and validates `id_token`**

```python
import jwt
from jwt import PyJWKClient

# Fetch Google's public keys
jwks_client = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
signing_key = jwks_client.get_signing_key_from_jwt(id_token)

# Verify signature, expiry, audience, issuer, and nonce
claims = jwt.decode(
    id_token,
    signing_key.key,
    algorithms=["RS256"],
    audience="YOUR_CLIENT_ID",
    issuer="https://accounts.google.com",
    options={"verify_exp": True},
)
# claims: {"sub": "1098765432", "email": "user@example.com", "name": "Jane Doe", ...}
```

**Step 6: SP creates its own local session**

```python
# Store user identity in your session (e.g., Redis-backed session store)
session["user_id"] = claims["sub"]
session["email"] = claims["email"]
session["authenticated_at"] = time.time()
```

The SP now has a local session. Next visit to the same SP uses this local session — no IdP roundtrip needed.

### SAML 2.0 Flow (For Enterprise Comparison)

SAML uses XML-signed assertions instead of JWTs. The flow is similar but uses HTTP POST binding to deliver the assertion:

```
SP --redirect--> IdP login
IdP --POST assertion (base64 XML)--> SP's Assertion Consumer Service (ACS) URL
SP validates XML signature against IdP's X.509 certificate
SP creates local session
```

SAML assertions carry attributes (email, groups, roles) in XML elements. The SP maps these to its internal user model.

## Use It

### Identity Providers by Segment

| Provider | Best for | Protocol Support | Notes |
|---|---|---|---|
| **Okta** | Enterprise workforce, B2B | SAML, OIDC, SCIM | Market leader; deep app catalog; expensive at scale |
| **Auth0** (Okta subsidiary) | Developer-first, B2C | OIDC, SAML, Social | Excellent SDK support; generous free tier |
| **Google Workspace** | Google-native orgs | OIDC, SAML | Free with Workspace; limited customization |
| **Azure Active Directory** | Microsoft-centric enterprise | OIDC, SAML, Kerberos | Deep Windows/Office integration |
| **Keycloak** | Self-hosted, open-source | OIDC, SAML, CAS | Full control; needs ops effort |
| **AWS IAM Identity Center** | AWS-native organizations | SAML, OIDC | Manages access to AWS accounts and apps |
| **Ping Identity** | Large regulated enterprise | SAML, OIDC, FIDO | Common in banking, healthcare |

### When to Use Which Protocol

- **Building a new SaaS product?** → OIDC with Auth0 or Keycloak. JWTs are easy to work with, libraries are excellent, and the flow is simpler.
- **Integrating with an enterprise HR system (Workday, SAP)?** → SAML 2.0. These systems predate OIDC and only speak SAML.
- **Internal tool on a corporate Windows network?** → Kerberos via Active Directory. Transparent browser SSO with no redirects.
- **Need provisioning/deprovisioning in addition to SSO?** → Add **SCIM 2.0** on top of any SSO protocol for automatic user lifecycle management.

## Common Pitfalls

- **Not validating `state` on callback.** The `state` parameter is your CSRF defense. If you skip verifying it matches what you stored, an attacker can trick a user's browser into completing an auth flow initiated by the attacker. Always check `state`.

- **Trusting `id_token` without verifying the signature.** Decoding a JWT is not the same as verifying it. Always validate the RS256/ES256 signature against the IdP's published public keys. Skipping this allows token forgery.

- **Hardcoding the IdP's public key.** IdPs rotate their signing keys periodically. Use the IdP's JWKS endpoint (`/.well-known/jwks.json`) and cache keys with a short TTL. Hardcoded keys will silently break on rotation.

- **Not handling Single Logout (SLO).** SSO makes login seamless, but logout is harder. If a user logs out of one SP and you don't propagate the logout to the IdP and other SPs, those sessions remain active. Implement back-channel or front-channel SLO for security-sensitive applications (banking, healthcare).

- **Confusing OIDC with OAuth 2.0.** OAuth 2.0 is an *authorization* protocol — it grants access to resources. OIDC is an *authentication* layer built on top of OAuth 2.0. Using a plain OAuth 2.0 `access_token` to prove identity is an anti-pattern; use the `id_token` for that.

## Exercises

1. **Easy — Trace the flow.** Draw the full SSO redirect flow for a user who (a) logs into App A for the first time, then (b) navigates to App B without re-entering credentials. Label each HTTP request as either SP→IdP, IdP→SP, or browser redirect. Identify exactly where the global session and local sessions are created.

2. **Medium — Compare protocols.** You need to integrate your SaaS product with a Fortune 500 customer whose IT team only supports SAML 2.0. List five concrete differences between setting up SAML vs. OIDC from your SP's perspective: what configuration values you exchange, how tokens look, and where signature verification happens.

3. **Hard — Design SLO.** Your company's SSO setup has one IdP and five SPs. A user logs in to all five, then their laptop is stolen. Design a Single Logout system that, upon receiving a logout request at any SP, terminates all five local sessions and the global IdP session within 30 seconds. Specify the API calls, session store operations, and any trade-offs in your design.

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **SSO** | "Logging in once and never seeing a login screen again" | An authentication scheme where a central IdP authenticates the user and issues tokens that SPs accept, so the user only enters credentials once per global session |
| **IdP (Identity Provider)** | "The company that makes the login button" | The authoritative service that verifies user identity and issues signed assertions or tokens; examples: Okta, Azure AD, Google |
| **SP (Service Provider)** | "The app you're logging into" | An application that delegates authentication to an IdP and trusts the tokens it issues, rather than managing credentials itself |
| **SAML assertion** | "Same as a JWT" | An XML document, signed with an X.509 key, that the IdP POSTs to the SP's ACS URL; heavier and more verbose than a JWT but required by many enterprise systems |
| **OIDC / OpenID Connect** | "OAuth 2.0 with login" | A thin identity layer on top of OAuth 2.0 that adds a standard `id_token` (JWT) and a `/userinfo` endpoint for retrieving user claims |
| **Global session** | "The session on the app you're using" | The session the IdP maintains for the authenticated user, scoped to the IdP's domain; this is what enables transparent re-authentication across SPs |
| **SCIM** | "Part of SSO" | A separate protocol (System for Cross-domain Identity Management) for *provisioning* users — creating, updating, deactivating accounts automatically; complements SSO but is not part of it |

## Further Reading

- [OpenID Connect Core 1.0 Specification](https://openid.net/specs/openid-connect-core-1_0.html) — The authoritative spec; the "Authentication" and "ID Token Validation" sections are essential reading.
- [SAML 2.0 Technical Overview (OASIS)](https://www.oasis-open.org/committees/download.php/27819/sstc-saml-tech-overview-2.0-cd-02.pdf) — The canonical SAML reference; read the Web SSO profiles section.
- [Auth0 Docs — OIDC Handbook](https://auth0.com/docs/authenticate/protocols/openid-connect-protocol) — Practical walkthrough of OIDC flows with diagrams; beginner-friendly without sacrificing accuracy.
- [Okta Developer Blog — SAML vs OIDC](https://developer.okta.com/blog/2019/02/26/saml-vs-oidc) — Side-by-side protocol comparison with deployment guidance.
- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) — Defines the JWT format used in OIDC `id_token`; sections 4 (claims) and 7 (validation) are the most relevant.
