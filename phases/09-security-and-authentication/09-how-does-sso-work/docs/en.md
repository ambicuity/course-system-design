# How Does SSO Work?

> One login, every door — the Identity Provider becomes the single source of trust.

**Type:** Learn
**Prerequisites:** HTTP & cookies, session vs. token authentication, public-key cryptography basics
**Time:** ~25 minutes

---

## The Problem

Every web application needs to know who the user is. The naive approach is to build authentication into each service individually: Slack manages its own passwords, Jira manages its own, your internal HR portal manages its own. A company with 30 internal tools now has 30 password databases, 30 session stores, 30 "forgot password" flows, and 30 places where a stale employee account can be missed when someone leaves.

From the user's perspective it is even worse. They authenticate to Gmail, get work done, switch to Confluence, log in again, open the CRM, log in again. Every new browser tab is a tax on attention. Enterprise users routinely have dozens of tabs open across a dozen SaaS products; re-authenticating on every page load is not just irritating — it is a real productivity loss that compounds across an entire organization.

The security picture is worse still. Spreading credentials across many services multiplies the attack surface. A breach at any one of them exposes passwords that employees have reused elsewhere. IT cannot enforce consistent policies (MFA, session length, conditional access) when each app enforces its own. Single Sign-On solves all of this by designating one authoritative source of identity — an **Identity Provider** — and letting every other application defer to it.

---

## The Concept

### Roles

| Role | Abbreviation | Responsibility |
|---|---|---|
| **Identity Provider** | IdP | Owns credentials, authenticates the user, issues tokens |
| **Service Provider** | SP | The app the user wants to use; trusts the IdP |
| **User Agent** | — | The browser (or native app) that shuttles messages between IdP and SP |

The IdP and SP never talk directly in a browser-based flow. All communication goes through the user's browser via **redirects** and **form POSTs** (or URL fragments). This is deliberate: it lets the IdP and SP live on completely different origins with no direct network path between them.

### The Two Major Protocols

**SAML 2.0** (Security Assertion Markup Language) is XML-based and popular in enterprise environments (Okta, Azure AD, Google Workspace with corporate customers). Assertions are signed XML documents.

**OIDC** (OpenID Connect) sits on top of OAuth 2.0 and uses JSON Web Tokens (JWTs). It is the modern default for consumer apps, mobile, and SaaS products. Most new integrations use OIDC.

Both protocols share the same conceptual shape: the IdP issues a cryptographically signed **assertion / token** that the SP can verify without calling back to the IdP on every request.

### The IdP Session vs. the SP Session

This is the key mental model. There are **two separate sessions**:

```
Browser <--cookie A--> IdP (e.g., accounts.google.com)
Browser <--cookie B--> SP  (e.g., app.slack.com)
```

When you first log in, both sessions are created. When you visit a second SP, the SP has no session for you yet — but the browser still holds the IdP session cookie. The IdP recognizes that you are already authenticated, issues a token for the new SP without prompting for credentials again, and the new SP creates its own session. The user experiences zero friction.

### Token Anatomy (OIDC / JWT)

An OIDC **ID token** is a JWT with three Base64url-encoded sections:

```
header.payload.signature

Header:  { "alg": "RS256", "kid": "abc123" }
Payload: {
  "iss": "https://idp.example.com",
  "sub": "user_123",
  "aud": "app.slack.com",
  "exp": 1719878400,
  "email": "alice@example.com",
  "name": "Alice"
}
Signature: RSA-SHA256(header + "." + payload, IdP_private_key)
```

The SP validates the signature using the IdP's **public key** (fetched from a well-known JWKS endpoint). No shared secret, no round-trip to the IdP per request. The token is short-lived (typically 1 hour); longer-lived sessions are maintained via the SP's own cookie, not by extending the token.

---

## Build It / In Depth

### Full OIDC SSO Flow (Step by Step)

```
User          Browser           SP (Slack)          IdP (Google)
 |               |                  |                     |
 |--visit slack--|                  |                     |
 |               |--GET /dashboard->|                     |
 |               |                  |--no session found   |
 |               |<-302 redirect to IdP with:------------|
 |               |   ?response_type=code                  |
 |               |   &client_id=slack_client_id           |
 |               |   &redirect_uri=https://slack.com/cb   |
 |               |   &scope=openid email profile          |
 |               |   &state=random_csrf_token             |
 |               |   &nonce=random_replay_token           |
 |               |                  |                     |
 |               |--GET /authorize?...------------------->|
 |               |                  |     check IdP session
 |               |                  |     (already logged in?)
 |               |                  |                     |
 |  [If no IdP session: show login form, user authenticates]
 |               |                  |                     |
 |               |<-302 redirect to redirect_uri?code=AUTH_CODE&state=...
 |               |                  |                     |
 |               |--GET /cb?code=AUTH_CODE-------------->|
 |               |                  |                     |
 |               |                  |--POST /token------->|
 |               |                  |  code=AUTH_CODE     |
 |               |                  |  client_secret=...  |
 |               |                  |                     |
 |               |                  |<--{id_token, access_token, refresh_token}
 |               |                  |                     |
 |               |                  | validate id_token   |
 |               |                  | (check sig, iss, aud, exp, nonce)
 |               |                  | create SP session   |
 |               |<--Set-Cookie: session=SP_SESSION_ID---|
 |               |<--HTTP 200 /dashboard----------------|
```

The **authorization code** is short-lived (seconds) and single-use. The actual tokens are exchanged server-to-server between the SP backend and IdP `/token` endpoint, keeping them out of the browser's URL bar and history.

### What Happens for a Second App (e.g., Jira)

```
Browser           SP (Jira)          IdP (Google)
   |                  |                     |
   |--GET /jira/-->   |                     |
   |                  | no SP session       |
   |<-302 to IdP------|                     |
   |                  |                     |
   |--GET /authorize?...------------------->|
   |                  |   IdP session cookie present — user recognized
   |                  |   no login prompt issued
   |<-302 to Jira cb with new AUTH_CODE-----|
   |                  |                     |
   | [rest of token exchange identical]     |
```

The user never saw a login screen for Jira. This is the SSO effect.

### SAML Variant (Simplified)

In SAML, the SP sends a signed `<AuthnRequest>` XML document to the IdP. The IdP responds with a `<Response>` containing signed `<Assertion>` elements. The browser carries the response as a Base64-encoded form POST. The mechanics differ but the trust model is identical: SP trusts the IdP's signature, not a shared secret.

---

## Use It

| Product | Protocol | Typical Use Case |
|---|---|---|
| **Okta** | SAML, OIDC | Enterprise workforce SSO, MFA, lifecycle management |
| **Azure Active Directory / Entra ID** | SAML, OIDC, WS-Fed | Microsoft-centric enterprises, Office 365 |
| **Google Workspace (Cloud Identity)** | SAML, OIDC | Google-native orgs; acts as IdP for third-party SaaS |
| **Auth0** | OIDC, SAML | Developer-friendly; B2C and B2B SaaS |
| **AWS Cognito** | OIDC | AWS workloads; federate to existing IdP or manage users natively |
| **Keycloak** | OIDC, SAML | Open-source self-hosted IdP; common in on-prem/hybrid setups |
| **Ping Identity** | SAML, OIDC | Regulated industries (finance, healthcare) with strict compliance needs |

**Decision guide:**
- Starting a new SaaS product targeting developers or consumers → **Auth0** or **Cognito**
- Existing enterprise workforce, Microsoft-heavy → **Azure AD / Entra ID**
- Need open-source self-hosted control → **Keycloak**
- Large enterprise with heterogeneous app portfolio → **Okta** or **Ping**

---

## Common Pitfalls

- **Skipping nonce and state validation.** The `state` parameter prevents CSRF on the redirect callback; the `nonce` prevents replay attacks on the ID token. Omitting either opens the door to session fixation. Always generate them server-side, store them in the session, and verify them on callback.

- **Trusting the ID token for API authorization.** The ID token tells you *who* the user is. The *access token* is what the SP should present to resource servers. Passing an ID token to downstream APIs leaks user PII in every API call and breaks when the token expires.

- **Assuming logout terminates all sessions.** SLO (Single Log-Out) is notoriously fragile. Logging out of the IdP does not automatically invalidate existing SP session cookies unless each SP implements the SLO endpoint and the IdP notifies them. Design for this: give SP sessions short TTLs and require re-authentication for sensitive actions.

- **Not verifying `aud` (audience) in the JWT.** A token issued for `app-a.example.com` could be forwarded to `app-b.example.com` and accepted if `aud` is not checked. Always assert that the audience matches your own client ID.

- **Storing tokens in `localStorage`.** XSS can exfiltrate tokens from `localStorage`. Store them in `HttpOnly`, `Secure`, `SameSite=Lax` cookies managed by the backend. The browser never needs to read them directly.

---

## Exercises

1. **Easy — trace the flow.** Draw the sequence diagram for an OIDC SSO login to a new service (without an existing IdP session). Label: the authorization request, the authorization code, the token exchange, and the two cookies that end up in the browser.

2. **Medium — compare SAML vs. OIDC.** A company has 200 legacy enterprise apps that support SAML, and a new React SPA they are building. Explain which protocol you would use for each and why. What would a migration path look like if they wanted to consolidate to OIDC over time?

3. **Hard — design SLO.** Your company requires that terminating an employee's account propagates a logout to all 40 integrated SaaS apps within 60 seconds. Design a system for this. Consider: IdP-initiated SLO, backchannel logout (OIDC spec), session token revocation lists, webhook fan-out, and what happens if an SP is unreachable.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **SSO** | A single password used everywhere | A trust delegation scheme where one IdP authenticates the user and issues tokens that SPs accept without storing credentials themselves |
| **IdP (Identity Provider)** | "The login server" | The authoritative system that owns user identities, manages credentials, enforces MFA, and issues signed assertions about authenticated users |
| **SP (Service Provider)** | "The app" | An application that has outsourced authentication to an IdP; it receives and validates tokens but never sees raw passwords |
| **SAML Assertion** | An XML config file | A signed XML document issued by an IdP that attests to a user's identity and attributes; the SP trusts it because of the IdP's digital signature |
| **ID Token** | Same as an access token | A JWT that conveys *who* authenticated; intended for the client, not for calling APIs. Separate from the access token used for resource authorization |
| **Authorization Code** | The login result | A short-lived, single-use opaque code exchanged server-to-server for real tokens; keeps tokens out of the browser URL bar |
| **SLO (Single Log-Out)** | "Log out of everything automatically" | An optional, often incomplete protocol extension for propagating logout events to all SPs; real-world implementations vary widely in reliability |

---

## Further Reading

- [OpenID Connect Core 1.0 Specification](https://openid.net/specs/openid-connect-core-1_0.html) — the authoritative spec; sections 3.1 (Authorization Code Flow) and 2 (ID Token) are most relevant.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — practical security guidance covering session management, token storage, and logout.
- [Auth0 — "What is SSO?"](https://auth0.com/blog/what-is-and-how-does-single-sign-on-work/) — vendor-neutral conceptual walkthrough with diagrams.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — foundational reading since OIDC extends OAuth 2.0; Section 4.1 covers Authorization Code Grant.
- [SAMLtest.id](https://samltest.id/) — live SAML testing endpoint useful for validating SP integrations and understanding SAML assertion structure hands-on.
