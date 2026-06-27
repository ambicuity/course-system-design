# Top 12 Tips for API Security

> An API that is easy to use and hard to misuse is the only API worth shipping.

**Type:** Learn
**Prerequisites:** Authentication vs. Authorization, Rate Limiting and Throttling, API Gateway Patterns
**Time:** ~30 minutes

---

## The Problem

APIs are the exposed nerve endings of your system. Every endpoint you publish is a contract with the outside world — and every contract is a potential attack surface. In 2023, Gartner projected that APIs would become the number-one attack vector for enterprise web applications, yet most teams treat security as a post-launch concern.

Consider a common scenario: a mobile banking app talks to a REST API backed by microservices. The team builds quickly — they wire up JWT tokens, ship HTTPS, and call it "secure." Six months later an attacker replays a stale token to drain accounts, a competitor scrapes pricing data by hammering an unrated endpoint, and an internal audit reveals that error responses are leaking database table names in stack traces. None of these required a sophisticated breach — they exploited basic omissions.

This lesson gives you a concrete checklist of the twelve controls that close the most common API vulnerabilities. Each tip is a building block. Miss even two or three and the gaps compound: a missing rate limit + verbose errors + no input validation is enough for a competent attacker to enumerate users, cause denial-of-service, and eventually craft a working SQL injection payload.

---

## The Concept

API security is a layered defense. No single control is sufficient on its own. The model below shows how the twelve tips map to four distinct protection layers:

```
 External Client
        |
        v
+---------------------------------------+
| TRANSPORT LAYER                       |  Tip 1: HTTPS / TLS
+---------------------------------------+
        |
        v
+---------------------------------------+
| IDENTITY & ACCESS LAYER               |  Tip 2: OAuth 2.0
|                                       |  Tip 3: WebAuthn (phishing-resistant MFA)
|                                       |  Tip 4: Leveled API Keys
|                                       |  Tip 5: Authorization (RBAC / ABAC)
+---------------------------------------+
        |
        v
+---------------------------------------+
| TRAFFIC & INPUT LAYER                 |  Tip 6: Rate Limiting
|                                       |  Tip 8: IP / Domain Whitelisting
|                                       |  Tip 12: Input Validation
+---------------------------------------+
        |
        v
+---------------------------------------+
| OPERATIONAL LAYER                     |  Tip 7: API Versioning
|                                       |  Tip 9: OWASP API Top 10
|                                       |  Tip 10: API Gateway
|                                       |  Tip 11: Error Handling
+---------------------------------------+
        |
        v
 Internal Services / Databases
```

### The Twelve Tips at a Glance

| # | Tip | What it protects against |
|---|-----|--------------------------|
| 1 | Use HTTPS | Eavesdropping, MITM, credential theft in transit |
| 2 | Use OAuth 2.0 | Credential sharing, over-privileged tokens |
| 3 | Use WebAuthn | Phishing, credential stuffing, password reuse |
| 4 | Leveled API Keys | Blast radius when a key is compromised |
| 5 | Authorization | Privilege escalation, BOLA/IDOR attacks |
| 6 | Rate Limiting | Brute force, DDoS, scraping, enumeration |
| 7 | API Versioning | Breaking-change accidents, forced migrations |
| 8 | Whitelisting | Unauthorized callers, SSRF |
| 9 | OWASP API Top 10 | Systematic vulnerability class coverage |
| 10 | API Gateway | Centralized policy enforcement |
| 11 | Error Handling | Information disclosure, stack-trace leakage |
| 12 | Input Validation | Injection attacks, schema abuse |

---

## Build It / In Depth

### Tip 1 — Use HTTPS (TLS 1.2+)

TLS encrypts the channel. Without it, every token, cookie, and request body is readable to anyone on the path.

```nginx
# Nginx — redirect HTTP to HTTPS and enforce modern TLS
server {
    listen 80;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
}
```

Enable HSTS so browsers remember to use HTTPS even before the first redirect resolves.

---

### Tip 2 — Use OAuth 2.0

OAuth 2.0 lets clients prove identity without sharing passwords. The core flow for server-side apps:

```
Client → Authorization Server: GET /authorize?response_type=code&client_id=...&scope=read
                 User logs in and consents
Authorization Server → Client: redirect?code=AUTH_CODE
Client → Authorization Server: POST /token {code, client_secret}
Authorization Server → Client: {access_token, refresh_token, expires_in}
Client → Resource Server: GET /api/data   Authorization: Bearer ACCESS_TOKEN
```

Always:
- Use `state` parameter to prevent CSRF on the redirect.
- Use PKCE (`code_challenge`) for public clients (mobile, SPA).
- Issue short-lived access tokens (15 min) and longer-lived refresh tokens (hours/days).
- Scope tokens narrowly: `read:orders` not `*`.

---

### Tip 3 — Use WebAuthn for Phishing-Resistant MFA

WebAuthn (FIDO2) replaces passwords with public-key cryptography bound to a specific origin. A private key never leaves the device; the server stores only the public key. Phishing fails because the authenticator checks the origin URL before signing.

```
Registration:
  Server → Client: challenge (random bytes)
  Client → Authenticator: create credential (user consent)
  Authenticator → Client: public key + attestation
  Client → Server: store public key

Authentication:
  Server → Client: challenge
  Client → Authenticator: sign challenge with private key
  Client → Server: assertion
  Server: verify signature with stored public key  ✓
```

Libraries: `@simplewebauthn/server` (Node), `py_webauthn` (Python), `webauthn` gem (Ruby).

---

### Tip 4 — Use Leveled API Keys

One master API key that does everything is a single point of total compromise. Issue keys with the minimum scope needed.

```
Key Type        Scope                    TTL         Example Use
─────────────────────────────────────────────────────────────────
read-only       GET endpoints only       90 days     Analytics dashboard
write           POST / PUT / PATCH       30 days     Partner integration
admin           All endpoints            7 days      Internal CI/CD deploy
scoped-webhook  POST /webhooks only      365 days    Third-party webhook
```

Implementation checklist:
- Hash keys at rest (SHA-256); never store plaintext.
- Log every key usage with timestamp, IP, and endpoint.
- Support programmatic rotation without downtime.
- Expire keys automatically; alert before expiry.

---

### Tip 5 — Authorization (BOLA / IDOR Prevention)

Authentication proves *who* you are; authorization proves *what* you can touch. The OWASP API #1 vulnerability is Broken Object Level Authorization (BOLA), also called IDOR (Insecure Direct Object Reference).

Bad pattern:
```http
GET /api/invoices/4821
Authorization: Bearer <user-A-token>
```
If the server returns invoice 4821 without checking that user A owns it, any authenticated user can iterate invoice IDs.

Correct pattern — always re-check ownership:
```python
@app.get("/api/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, current_user: User = Depends(get_current_user)):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or invoice.owner_id != current_user.id:
        raise HTTPException(status_code=403)  # not 404 — avoid oracle
    return invoice
```

Use UUIDs or opaque identifiers instead of sequential integers to make enumeration harder (defense in depth, not a substitute for authorization checks).

---

### Tip 6 — Rate Limiting

Rate limiting caps how many requests a client can make in a time window. It defeats brute force on login endpoints, scraping, and volumetric DDoS.

Common algorithms:

| Algorithm | How it works | Best for |
|-----------|--------------|----------|
| Fixed Window | Counter resets every N seconds | Simple, slight burst risk at window edge |
| Sliding Window Log | Track timestamps of recent requests | Accurate, higher memory cost |
| Token Bucket | Tokens accumulate at rate R, capped at burst B | Allows controlled bursts |
| Leaky Bucket | Requests queue and drain at fixed rate | Smooth output rate |

Apply different limits per tier:
```
Endpoint              Unauthenticated   Free tier    Paid tier
POST /login           5 / min           5 / min      5 / min
GET  /products        60 / min          300 / min    3000 / min
POST /orders          —                 10 / min     100 / min
```

Return `429 Too Many Requests` with `Retry-After` and `X-RateLimit-Remaining` headers.

---

### Tip 7 — API Versioning

Versioning separates breaking changes from consumers. Three strategies:

```
URI versioning (most common):
  /v1/users   →  /v2/users

Header versioning:
  Accept: application/vnd.myapi.v2+json

Query param versioning:
  GET /users?api_version=2024-01-01
```

Rules:
- Never mutate the behavior of an existing version without a new version.
- Deprecate old versions with a `Deprecation` and `Sunset` response header.
- Maintain at least two versions in production simultaneously to give clients migration time.

---

### Tip 8 — Whitelisting

Allowlisting restricts which IPs, domains, or clients can call your API. It is especially important for:
- Internal service-to-service calls (use mTLS or VPC peering, not public internet)
- B2B partner integrations (lock to their static egress IPs)
- Webhook endpoints (validate source IP ranges published by the vendor)

Do not rely on IP whitelisting alone for public-facing APIs — IPs can be spoofed or shared via NAT — but it is a strong additional layer for known callers.

```nginx
# Allow only partner IP block; deny all others
location /api/partner/ {
    allow 203.0.113.0/24;
    deny  all;
}
```

---

### Tip 9 — Check OWASP API Security Top 10

The OWASP API Security Top 10 (2023 edition) is a peer-reviewed taxonomy of the most critical API risks. Audit your API against each class before every major release:

| # | Risk | Short description |
|---|------|-------------------|
| API1 | Broken Object Level Authorization | Accessing other users' resources |
| API2 | Broken Authentication | Weak tokens, no expiry, no rate limit on auth |
| API3 | Broken Object Property Level Authorization | Mass assignment, over-fetched fields |
| API4 | Unrestricted Resource Consumption | Missing limits on request size, frequency, cost |
| API5 | Broken Function Level Authorization | Non-admin calling admin endpoints |
| API6 | Unrestricted Access to Sensitive Business Flows | Buying unlimited inventory via bots |
| API7 | Server-Side Request Forgery (SSRF) | API fetching attacker-controlled URL |
| API8 | Security Misconfiguration | Debug mode in prod, permissive CORS |
| API9 | Improper Inventory Management | Undocumented / shadow API versions |
| API10 | Unsafe Consumption of APIs | Trusting third-party API responses without validation |

---

### Tip 10 — Use an API Gateway

An API Gateway centralizes cross-cutting security concerns so individual services do not have to re-implement them.

```
External Clients
       |
       v
  +-----------+
  | API       |  ← TLS termination
  | Gateway   |  ← Auth token validation
  |           |  ← Rate limiting
  |           |  ← Request logging & tracing
  |           |  ← IP whitelisting
  |           |  ← Schema validation
  +-----------+
       |
  +---------+---------+
  |         |         |
Service A  Service B  Service C
```

Popular options: AWS API Gateway, Kong, Apigee, Envoy, Nginx, Traefik. Even a simple reverse proxy centralizes logging and TLS termination, which is better than nothing.

---

### Tip 11 — Error Handling

Verbose errors are a free recon tool for attackers. Stack traces reveal file paths, ORM class names, database versions, and query structure.

Bad response (leaks internals):
```json
{
  "error": "PsycopgError: relation \"users\" does not exist\n  File \"/app/db/queries.py\", line 47"
}
```

Good response (generic to client, detailed in logs):
```json
{
  "error": "An unexpected error occurred.",
  "request_id": "req_4f3a9b"
}
```

Server-side log (full detail, never sent to client):
```
2024-01-15T10:32:01Z ERROR request_id=req_4f3a9b user_id=92 PsycopgError: ...
```

Rules:
- Use generic error messages in API responses.
- Include a `request_id` so support can correlate.
- Never return stack traces, SQL, or internal paths to the client.
- Log the full error context server-side with structured logging.

---

### Tip 12 — Input Validation

Every field accepted by your API is a potential injection vector. Validate at the schema level before business logic ever runs.

```python
from pydantic import BaseModel, constr, conint, EmailStr

class CreateOrderRequest(BaseModel):
    customer_email: EmailStr                          # format validation
    item_id: int                                      # type enforcement
    quantity: conint(ge=1, le=1000)                   # range check
    promo_code: constr(max_length=20, pattern=r'^[A-Z0-9]+$')  # allowlist chars
```

For SQL, always use parameterized queries — never string interpolation:
```python
# WRONG
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# CORRECT
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

Validate:
- Type (string, integer, boolean)
- Length / range bounds
- Format (regex, email, UUID)
- Allowed values (enum)
- File uploads: MIME type, size limit, virus scan

---

## Use It

### How Real Systems Apply These Tips

| Technology / Platform | Which tips it covers out of the box |
|----------------------|-------------------------------------|
| **AWS API Gateway** | Rate limiting, TLS termination, API keys, WAF integration (tips 1, 4, 6, 10) |
| **Kong Gateway** | Auth plugins (OAuth2, JWT), rate limiting, IP restriction, logging (tips 2, 4, 6, 8, 10, 11) |
| **Auth0 / Okta** | OAuth 2.0 authorization server, WebAuthn support, scoped tokens (tips 2, 3) |
| **Pydantic / Zod** | Schema-based input validation at the request boundary (tip 12) |
| **Nginx + ModSecurity** | WAF rules covering OWASP Top 10, rate limiting, TLS (tips 1, 6, 8, 9) |
| **HashiCorp Vault** | API key and secret rotation, short-lived tokens (tip 4) |
| **Datadog / Honeycomb** | Structured error logging and distributed tracing with request IDs (tip 11) |

### Decision Guide: Which Controls First?

If you are hardening an existing API and can only do a subset now, prioritize in this order:

1. **HTTPS** — free via Let's Encrypt; no excuse to skip.
2. **Input validation** — stops the widest class of attacks (injection).
3. **Authorization checks** — BOLA is OWASP #1 for a reason.
4. **Rate limiting** — a few lines of middleware; huge impact.
5. **Error handling** — remove stack traces from responses today.

---

## Common Pitfalls

- **Treating authentication as authorization.** Verifying a JWT proves identity; it does not prove the caller is allowed to access the specific resource. Always check object-level ownership in business logic, not just token validity at the middleware layer.

- **Global rate limits instead of per-endpoint limits.** A 1000 req/min global limit still lets an attacker hammer `POST /login` 1000 times. Rate limit sensitive endpoints (login, password reset, OTP verification) at a much lower threshold, separate from the global limit.

- **Returning 404 on authorization failures.** Returning `404 Not Found` instead of `403 Forbidden` when a user accesses another user's resource seems safer but creates a timing oracle — a different response shape can reveal whether the resource exists. Return `403` consistently; document the policy.

- **Long-lived API keys with no rotation.** An API key issued three years ago that has never been rotated has probably been committed to a git repo, shared in a Slack message, or included in a log file. Enforce TTLs and automated rotation.

- **Schema validation only at the edge.** Validating input at the API gateway but not inside services means an attacker who bypasses the gateway (internal traffic, misconfigured route) hits unvalidated business logic. Validate at every trust boundary, not just the outermost one.

---

## Exercises

1. **Easy — Rate limit a login endpoint.** Take any web framework you know (Express, FastAPI, Django). Add a rate limit of 5 requests per minute per IP on `POST /login`. Return `429` with a `Retry-After: 60` header when the limit is exceeded. Verify the behavior with `curl` in a loop.

2. **Medium — Fix a BOLA vulnerability.** Given this endpoint: `GET /api/orders/{order_id}` that returns an order if the user is authenticated (but does not check ownership), add an ownership check. Test that user A cannot retrieve user B's order even with a valid token. Write a test case for each: authorized access, unauthorized access, and non-existent resource.

3. **Hard — Build a scoped API key system.** Design and implement a simple API key manager: keys are stored as hashed values, each key has a scope list (`["read:products", "write:orders"]`), and every request validates that the key's scope covers the required permission. Add automatic expiry and a rotation endpoint. Measure latency of the lookup and discuss how you would cache it at scale.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Authentication** | Checking the user's password | Proving the identity of the caller (who are you?) |
| **Authorization** | Same as authentication | Deciding what the authenticated caller is allowed to do (what can you do?) |
| **BOLA / IDOR** | An exotic advanced attack | Accessing another user's object by guessing or iterating its ID; OWASP API #1 |
| **OAuth 2.0** | An authentication protocol | A delegation *authorization* framework; OpenID Connect adds authentication on top |
| **WebAuthn** | Hardware MFA only | A browser/OS API for public-key credentials; works with platform authenticators (Face ID, Touch ID) too |
| **Rate Limiting** | Blocking abusive IPs | Capping request frequency per client/endpoint within a time window, regardless of IP |
| **Leveled API Keys** | A paid-tier feature | Scoped credentials issued with minimum necessary permissions and defined TTLs |

---

## Further Reading

- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) — The definitive taxonomy of API vulnerabilities, with detailed examples and prevention guidance.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — The authoritative specification for OAuth 2.0 flows and token handling.
- [Web Authentication (WebAuthn) W3C Spec](https://www.w3.org/TR/webauthn-3/) — Full specification for the WebAuthn API, including registration and authentication ceremonies.
- [Google Cloud API Design Guide — Authentication](https://cloud.google.com/apis/design/security) — Practical guidance from Google on securing production APIs at scale.
- [NIST SP 800-204B — Attribute-based Access Control for Microservices](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-204B.pdf) — In-depth coverage of authorization patterns including RBAC and ABAC in distributed systems.
