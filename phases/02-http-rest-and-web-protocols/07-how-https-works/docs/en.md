# How HTTPS Works?

> HTTPS is HTTP with a security layer bolted on: asymmetric crypto to agree on a secret, symmetric crypto to use it fast.

**Type:** Learn
**Prerequisites:** How HTTP Works, TCP/IP Fundamentals, Public-Key Cryptography Basics
**Time:** ~25 minutes

---

## The Problem

Imagine you log in to your bank. Your browser sends your username and password to the server. Without encryption, every router, ISP, and potential attacker between you and the server sees those bytes verbatim. This is not a theoretical risk — tools like Wireshark make it trivial. On a coffee-shop Wi-Fi network, a passive listener can harvest credentials from every unencrypted HTTP request on the same subnet in minutes.

Encryption alone is not enough, though. Even if you encrypted your messages, how do you know the server you're talking to is actually your bank and not an attacker who hijacked the DNS response or performed a BGP route injection? Without identity verification, an attacker can sit in the middle, decrypt your traffic, re-encrypt it, and forward it on — a man-in-the-middle (MITM) attack. You'd never know.

HTTPS solves both problems: it encrypts data in transit so eavesdroppers see ciphertext, and it authenticates the server via a chain of trust rooted in Certificate Authorities (CAs) that your OS and browser vendor already trust. TLS (Transport Layer Security) is the protocol that provides both guarantees. HTTPS is simply HTTP running over a TLS connection.

---

## The Concept

### Two Types of Encryption

HTTPS uses two families of cryptography, each chosen for what it's good at:

| Type | Algorithm Examples | Speed | Key Distribution | Used For |
|---|---|---|---|---|
| **Asymmetric** | RSA-2048, ECDSA P-256 | Slow (1000x) | Public key is shareable | Key exchange, identity proof |
| **Symmetric** | AES-128-GCM, ChaCha20-Poly1305 | Fast | Both sides need the same key | Bulk data encryption |

The fundamental insight of HTTPS: use asymmetric crypto to *securely agree on* a symmetric session key, then use that fast symmetric key for everything else.

### The Certificate Chain of Trust

A TLS certificate is a signed document that binds a public key to a domain name. The signature comes from a Certificate Authority (CA). Your OS ships with a list of ~150 trusted root CAs (Mozilla, Google, Apple, and Microsoft each maintain their own). When a server presents a certificate, the browser verifies the chain:

```
Root CA (self-signed, in browser trust store)
    └── Intermediate CA (signed by Root CA)
            └── leaf cert for example.com (signed by Intermediate CA)
```

Browsers never trust leaf certs directly from root CAs in practice — intermediates act as a buffer so root private keys can stay offline (air-gapped HSMs). If an intermediate is compromised, it can be revoked without retiring the root.

A certificate contains:
- Subject (domain name / CN / SANs)
- Public key
- Issuer (CA name)
- Validity period (NotBefore / NotAfter)
- Signature from issuer
- Serial number + revocation pointer (CRL or OCSP URL)

### TLS 1.2 Handshake (Classic Flow)

```
Client                                          Server
  |                                               |
  |------ ClientHello (TLS version, cipher list, random-C) ----->|
  |                                               |
  |<----- ServerHello (chosen cipher, random-S) --|
  |<----- Certificate (server cert chain) --------|
  |<----- ServerHelloDone -----------------------|
  |                                               |
  |  [Client verifies cert chain → extracts server public key]
  |                                               |
  |------ ClientKeyExchange (pre-master secret, RSA-encrypted) ->|
  |                                               |
  |  [Both derive session key from:               |
  |   pre-master secret + random-C + random-S]    |
  |                                               |
  |------ ChangeCipherSpec ---------------------->|
  |------ Finished (MAC over handshake) --------->|
  |                                               |
  |<----- ChangeCipherSpec -----------------------|
  |<----- Finished (MAC over handshake) ----------|
  |                                               |
  |====== Encrypted HTTP data (AES-GCM) =========|
```

Two full round trips before a byte of application data flows. That latency cost matters for performance.

### TLS 1.3 Handshake (Streamlined)

TLS 1.3 (RFC 8446, 2018) cut the handshake to **1 round trip** by removing legacy mechanisms and mandating ephemeral Diffie-Hellman:

```
Client                                          Server
  |                                               |
  |------ ClientHello (TLS 1.3, key_share, supported_groups) --->|
  |                                               |
  |<----- ServerHello + key_share ----------------|
  |<----- {Certificate + CertVerify + Finished} (already encrypted)
  |                                               |
  |------ {Finished} --------------------------->|
  |                                               |
  |====== Encrypted HTTP data ====================|
```

TLS 1.3 also supports **0-RTT resumption**: if the client has previously connected, it can send application data on the very first packet (at the cost of no replay protection — risky for non-idempotent requests).

### Key Differences: TLS 1.2 vs TLS 1.3

| Feature | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Handshake round trips | 2 | 1 |
| RSA key exchange | Allowed | Removed |
| Forward secrecy | Optional | Mandatory (ECDHE) |
| Cipher suite negotiation | Client ↔ Server | Client proposes; server picks from short list |
| Weak algorithms | RC4, SHA-1, MD5 possible | Banned |
| 0-RTT resumption | No | Yes (with caveats) |

### Forward Secrecy

If an attacker records encrypted traffic today and later steals the server's private key, can they decrypt the old sessions? With RSA key exchange (TLS 1.2 default), yes — the session key was encrypted with the long-lived private key. With **ephemeral Diffie-Hellman (ECDHE)**, each session generates throwaway key pairs; compromising the server key later reveals nothing about past sessions. TLS 1.3 makes this mandatory.

---

## Build It / In Depth

### Step 1: Obtain a Certificate

For production, use **Let's Encrypt** (free, automated, 90-day certs renewed by ACME clients like Certbot):

```bash
# Install Certbot and obtain a cert for nginx
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com

# Certbot automatically edits nginx config and sets up renewal cron
sudo certbot renew --dry-run
```

For local development, generate a self-signed cert (browsers will warn — use mkcert for trusted local certs):

```bash
# Generate self-signed cert (dev only)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem \
  -days 365 -nodes -subj "/CN=localhost"

# Better: use mkcert (installs a local CA your browser trusts)
brew install mkcert
mkcert -install
mkcert localhost 127.0.0.1
```

### Step 2: Configure TLS on nginx

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # TLS 1.2 + 1.3 only; drop 1.0 and 1.1
    ssl_protocols TLSv1.2 TLSv1.3;

    # Strong cipher suite order (TLS 1.2 fallback)
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;

    # HSTS: tell browsers to only connect via HTTPS for 1 year
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # OCSP stapling: server fetches revocation status and includes it in handshake
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/example.com/chain.pem;
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$host$request_uri;
}
```

### Step 3: Inspect a Real Handshake

```bash
# See the full TLS handshake details
openssl s_client -connect example.com:443 -tls1_3 -showcerts

# Quick summary: protocol, cipher, cert expiry
curl -v --silent https://example.com 2>&1 | grep -E "SSL|TLS|subject|expire"

# Check cert expiry date
echo | openssl s_client -connect example.com:443 2>/dev/null \
  | openssl x509 -noout -dates
```

### Step 4: OCSP Stapling in Action

Without stapling, the browser must make a separate HTTP request to the CA's OCSP server to check if the cert is revoked — adding latency and leaking which sites you visit to the CA. With stapling, the server fetches the OCSP response and includes it in the TLS handshake. The browser validates it cryptographically without phoning home.

### End-to-End Flow Recap

```
Browser                       DNS         CA (OCSP)       Web Server
   |                           |               |               |
   |-- DNS query: example.com ->|               |               |
   |<- IP: 93.184.216.34 ------|               |               |
   |                                           |               |
   |-- TCP SYN ---------------------------------------->|      |
   |<- TCP SYN-ACK ------------------------------------<|      |
   |-- TCP ACK ------------------------------------------->    |
   |                                                           |
   |-- TLS ClientHello ---------------------------------------->|
   |<- TLS ServerHello + Certificate + OCSP staple ------------|
   |   [verify chain: leaf → intermediate → root CA in trust store]
   |-- TLS Finished ------------------------------------------>|
   |<- TLS Finished -------------------------------------------|
   |                                                           |
   |== GET /index.html (AES-256-GCM encrypted) ===============>|
   |<= 200 OK + HTML (encrypted) ============================--|
```

---

## Use It

### Where HTTPS Termination Happens

In real systems, TLS is typically terminated at the edge, not at the application server:

| Termination Point | Example Products | When to Use |
|---|---|---|
| CDN / Edge | Cloudflare, Fastly, CloudFront | Global, DDoS protection, caching |
| Load Balancer | AWS ALB, GCP HTTPS LB, nginx | Multi-instance apps |
| API Gateway | AWS API GW, Kong, Apigee | Microservice ingress |
| Reverse Proxy | nginx, Caddy, Traefik | Self-hosted |
| App Server (direct) | Express + node-tls, Gunicorn | Simple / dev setups |

**Caddy** is notable for its zero-config automatic HTTPS — it fetches Let's Encrypt certs and renews them without any extra tooling:

```caddy
example.com {
    reverse_proxy localhost:8080
}
```

That's the entire Caddyfile. Caddy handles cert issuance, renewal, OCSP stapling, and HTTP→HTTPS redirect automatically.

### Certificate Management at Scale

| Tool / Service | Approach |
|---|---|
| Let's Encrypt + Certbot | ACME protocol, free 90-day certs, auto-renewal |
| AWS Certificate Manager | Free certs for AWS services, auto-renewal |
| Vault PKI | Internal CA for service-to-service mTLS |
| cert-manager (k8s) | Kubernetes-native cert lifecycle management |
| DigiCert / Sectigo | Paid certs — needed for EV or OV validation |

### mTLS for Service-to-Service

HTTPS authenticates the *server* to the *client*. **Mutual TLS (mTLS)** adds client authentication — both sides present certificates. This is the foundation of zero-trust networking:

- Service mesh: Istio, Linkerd inject sidecar proxies that handle mTLS transparently
- Internal APIs use mTLS instead of bearer tokens for machine identity

---

## Common Pitfalls

- **Mixed content blocks your page silently.** Loading any `http://` sub-resource (image, script, XHR) on an `https://` page causes browsers to block or warn. Audit with `Content-Security-Policy: upgrade-insecure-requests` and scan with browser DevTools → Security tab.

- **Forgetting to renew certificates.** Let's Encrypt certs expire in 90 days. Certbot installs a cron or systemd timer, but it only runs if the server is up. Monitor expiry with an uptime checker or `ssl_expiry` Prometheus exporter — a lapsed cert takes your entire site down hard.

- **Terminating TLS at the load balancer and sending plaintext internally.** Traffic between load balancer and app servers is often unencrypted. Inside a VPC this may be acceptable, but for compliance (PCI-DSS, HIPAA) you need TLS all the way to the app — configure backend HTTPS listeners.

- **Supporting TLS 1.0/1.1 for "legacy clients."** Both are deprecated and contain known vulnerabilities (BEAST, POODLE). Modern browser and OS versions all support TLS 1.2+. Disable 1.0 and 1.1 on all public endpoints. Use Mozilla's SSL Configuration Generator to get a tested baseline.

- **Trusting the server's identity but not verifying the entire chain.** Certificate validation failures (expired intermediate, incomplete chain, wrong hostname) cause hard failures. Always serve the full chain (`fullchain.pem`, not just `cert.pem`) and test with `openssl verify` before deploying.

---

## Exercises

1. **Easy — Certificate Inspection.** Visit `https://github.com` in your browser. Click the padlock → "Connection is secure" → "Certificate is valid". Identify: the issuer CA, the Subject Alternative Names (SANs), and the expiry date. Then repeat with `openssl s_client -connect github.com:443 2>/dev/null | openssl x509 -noout -text` and compare what you see.

2. **Medium — Local HTTPS Server.** Install `mkcert` and set up a trusted local HTTPS server:
   - Run `mkcert -install` to create a local root CA
   - Generate a cert: `mkcert localhost`
   - Stand up a simple server in Python: `python3 -m http.server 8443 --bind 127.0.0.1` won't do HTTPS — instead write a 20-line Node.js or Python `ssl.wrap_socket` server using your generated cert and key
   - Confirm your browser shows the padlock with no warnings

3. **Hard — TLS Debugging Under Load.** Configure nginx with TLS 1.3 only and OCSP stapling on a cloud VM. Use `wrk` or `k6` to apply load. Then: (a) capture the handshake overhead with `openssl s_client -reconnect` to observe session resumption; (b) rotate the certificate mid-load-test using `nginx -s reload` and observe whether existing connections are disrupted; (c) experiment with TLS 1.3 0-RTT and document a scenario where replay attacks would be possible against a non-idempotent endpoint.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **SSL** | The current protocol securing HTTPS | SSL is deprecated (SSLv2/3 broken). TLS 1.2 and 1.3 are what you actually use. "SSL cert" is just industry shorthand for a TLS certificate. |
| **Certificate** | A file that encrypts your traffic | A signed document binding a public key to a domain. The cert itself doesn't encrypt anything — it lets the client trust the server's public key. |
| **CA (Certificate Authority)** | A company you pay for security | An entity whose root certificate is pre-installed in your OS/browser. It verifies domain ownership and signs your cert. It doesn't provide encryption itself. |
| **Session Key** | A permanent key for your connection | A temporary symmetric key generated per-session (or per-handshake). Thrown away after the session ends, which is why forward secrecy works. |
| **Cipher Suite** | An encryption algorithm | A four-part specification: key exchange algorithm + authentication + bulk cipher + MAC. Example: `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`. |
| **HSTS** | Optional security header | HTTP Strict Transport Security. Once sent, browsers refuse all future HTTP connections to that domain for `max-age` seconds — even if the user types `http://`. |
| **mTLS** | Two-way HTTPS | Mutual TLS: the client also presents a certificate, so both sides are authenticated. Standard for service-to-service zero-trust architectures. |

---

## Further Reading

- **Mozilla SSL Configuration Generator** — `https://ssl-config.mozilla.org/` — authoritative, maintained baseline configs for nginx, Apache, HAProxy, and others. Start here before writing any TLS config.
- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3** — `https://datatracker.ietf.org/doc/html/rfc8446` — the spec itself is surprisingly readable; sections 2 and 4 give a clean overview of the 1-RTT handshake.
- **"The Illustrated TLS 1.3 Connection" by XargsNotBombs** — `https://tls13.xargs.org/` — byte-by-byte interactive walkthrough of an actual TLS 1.3 handshake. Indispensable for deep understanding.
- **Let's Encrypt Documentation** — `https://letsencrypt.org/docs/` — covers the ACME protocol, certificate issuance, renewal, and rate limits. Essential for anyone managing their own TLS.
- **"SSL and TLS: Theory and Practice" (2nd ed.) — Rolf Oppliger** — rigorous textbook treatment of the full protocol stack, PKI, and certificate management at depth beyond what blog posts cover.
