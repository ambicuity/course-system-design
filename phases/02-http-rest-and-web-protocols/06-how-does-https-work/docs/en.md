# How does HTTPS work?

> Encryption is only half the story — identity verification is what makes it trustworthy.

**Type:** Learn
**Prerequisites:** How HTTP works, What is TLS/SSL, Public-key cryptography basics
**Time:** ~25 minutes

---

## The Problem

Plain HTTP sends every byte as readable text over the wire. If you log into your bank over HTTP, your credentials travel through routers, ISPs, and potentially dozens of intermediate hops — any one of which can read, copy, or modify them. This is not a theoretical risk: coffee-shop Wi-Fi, corporate proxies, and nation-state interceptors all exploit it routinely.

But confidentiality alone is not enough. Even if you encrypt your traffic, how do you know the server you are talking to is actually your bank and not an attacker who intercepted the TCP connection? Without authentication, you can have a perfectly encrypted channel straight to a thief.

HTTPS solves both problems at the same time: it encrypts the data in transit so it cannot be read, and it authenticates the server (and optionally the client) so you know who you are talking to. Understanding how it achieves both — and why the design involves two phases of cryptography — is essential for anyone building or operating web services.

---

## The Concept

### Two Layers of Cryptography

HTTPS uses **two fundamentally different encryption schemes** in sequence, each chosen for what it does best.

| Property | Asymmetric (RSA / ECDSA / ECDH) | Symmetric (AES-GCM / ChaCha20) |
|---|---|---|
| Key setup | No pre-shared secret needed | Both sides must have the same key |
| Speed | ~1000× slower | Near wire speed |
| Key length for equivalent security | 2048-bit RSA ≈ 128-bit AES | Short keys, fast operations |
| Use in HTTPS | Handshake only — authenticate & exchange key | All application data |

The handshake uses asymmetric cryptography to authenticate the server and establish a shared secret. The bulk data transfer then switches to symmetric encryption. This combination gives you security without sacrificing throughput.

### The Certificate Chain (PKI)

A TLS certificate is a signed document that binds a public key to an identity (domain name). The signature comes from a **Certificate Authority (CA)** — a third party that both sides already trust.

```
Root CA (self-signed, pre-installed in OS/browser)
  └── Intermediate CA (cross-signed by Root CA)
        └── End-Entity Certificate (your domain, signed by Intermediate CA)
```

When your browser receives a server certificate, it walks up this chain until it finds a root it already trusts. If no trusted root is reachable, or if any signature is invalid, the connection is aborted.

Key fields in a certificate:
- **Subject / SAN** — the domain(s) this cert is valid for
- **Public key** — used during the handshake
- **Issuer** — which CA signed it
- **Validity period** — `notBefore` and `notAfter` timestamps
- **Signature** — the CA's cryptographic endorsement

### TLS 1.3 Handshake (Mental Model)

TLS 1.3 (RFC 8446, 2018) is the current standard. It completes in **1 round-trip** (vs. 2 in TLS 1.2), making it both faster and more secure.

```
Client                                   Server
  |                                         |
  |------- ClientHello ------------------>  |
  |   (TLS version, cipher suites,          |
  |    key_share: client ECDH public key)   |
  |                                         |
  |  <------ ServerHello ---------------   |
  |   (chosen cipher suite,                 |
  |    key_share: server ECDH public key,   |
  |    Certificate, CertificateVerify,      |
  |    Finished)                            |
  |                                         |
  |------- Finished ------------------>     |
  |                                         |
  |======= Encrypted Application Data ===  |
```

At this point the server is **authenticated** (via certificate) and both sides hold the **same symmetric session keys** derived from the ECDH exchange — without ever transmitting the key itself.

### How the Session Key Is Established (ECDH)

Modern TLS uses **Ephemeral Elliptic-Curve Diffie-Hellman (ECDHE)** rather than RSA key exchange. The key properties:

- Each side generates a fresh key pair per connection.
- They exchange public keys; each computes the same shared secret locally.
- The private keys never leave either machine.
- **Forward secrecy**: if the server's long-term private key is later compromised, past sessions cannot be decrypted because each session had its own ephemeral keys.

The certificate's private key is used only to sign the `CertificateVerify` message — proving the server owns the private key corresponding to the public key in the certificate. It does not encrypt the session key.

---

## Build It / In Depth

### Step-by-Step: TLS 1.3 Connection

**Step 1 — TCP handshake**

Before TLS starts, a standard TCP three-way handshake establishes the transport connection. HTTPS listens on port 443.

**Step 2 — ClientHello**

The client sends its capabilities:
```
TLS version: TLS 1.3
Cipher suites: [TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256]
key_share extension: client's ECDH public key (e.g., X25519 curve)
server_name extension (SNI): "api.example.com"
```

SNI lets the server serve the correct certificate when hosting multiple domains on one IP.

**Step 3 — ServerHello + Certificate + Finished**

The server responds in a single flight:
1. **ServerHello** — selects cipher suite, sends its ECDH public key.
2. Both sides now compute the **shared secret** via ECDH and derive symmetric keys.
3. Remaining server messages are already encrypted with the handshake key.
4. **Certificate** — the server's X.509 certificate (public key + identity).
5. **CertificateVerify** — a signature over the entire handshake transcript, proving the server holds the private key.
6. **Finished** — HMAC of the handshake transcript; confirms no tampering.

**Step 4 — Client Finished**

The client verifies the certificate chain, checks the `CertificateVerify` signature, and sends its own `Finished` message. Both sides now derive the **application traffic keys**.

**Step 5 — Encrypted application data**

Every HTTP request and response from here on is encrypted with AES-GCM (or ChaCha20-Poly1305), authenticated, and integrity-protected. An attacker watching the wire sees only opaque ciphertext of known length.

### Observing the Handshake with OpenSSL

```bash
# Inspect a real TLS handshake
openssl s_client -connect api.example.com:443 -tls1_3 -showcerts

# Key output fields to read:
# - Certificate chain (depth 0 = leaf, depth 1 = intermediate, depth 2 = root)
# - Server public key
# - SSL-Session: Protocol, Cipher, Session-ID, TLSv1.3
# - Verification: return code: 0 (ok)
```

```bash
# Check a cert's expiry
openssl s_client -connect api.example.com:443 2>/dev/null \
  | openssl x509 -noout -dates
```

### TLS 0-RTT (Session Resumption)

TLS 1.3 supports **0-RTT** for resuming sessions. The server issues a **PSK (pre-shared key)** ticket at the end of a session. On the next connection the client can send application data in its very first message, before the handshake completes. Trade-off: 0-RTT data is **replay-vulnerable** — use it only for idempotent, read-only requests.

---

## Use It

### Where HTTPS Configuration Lives

| Layer | Tool / Service | What to configure |
|---|---|---|
| Web server | Nginx, Apache | `ssl_certificate`, `ssl_certificate_key`, `ssl_protocols TLSv1.2 TLSv1.3`, cipher suite order |
| Load balancer | AWS ALB, GCP LB, Cloudflare | TLS termination point; choose minimum TLS version |
| Cert management | Let's Encrypt + Certbot, AWS ACM | Auto-renewal, wildcard certs (`*.example.com`) |
| CDN / edge | Cloudflare, Fastly, Akamai | Handles TLS for you; controls edge-to-origin TLS separately |
| mTLS | Envoy, Istio, Kong | Mutual authentication — both client and server present certs |

### Typical Nginx TLS Config

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # Enforce modern TLS only
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;        # Let client pick in TLS 1.3
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    # HSTS — tell browsers to always use HTTPS for 1 year
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # OCSP stapling — server fetches and caches revocation status
    ssl_stapling on;
    ssl_stapling_verify on;
}
```

### HTTP/2 and HTTP/3

HTTP/2 is almost always negotiated over TLS using the **ALPN** extension in the ClientHello. The server advertises `h2` support; if both sides agree, HTTP/2 is used for the session. HTTP/3 replaces TCP+TLS with **QUIC**, which bakes TLS 1.3 into the transport layer — the handshake and the first data can arrive in a single round-trip even on a new connection.

---

## Common Pitfalls

- **Mixing HTTP and HTTPS on the same origin.** A single HTTP resource loaded on an HTTPS page (mixed content) destroys the security guarantee. Browsers block active mixed content (scripts, iframes) and warn on passive (images). Audit with browser DevTools → Security tab.

- **Expired or mismatched certificates.** Certificates have validity windows (typically 90 days for Let's Encrypt, up to 1 year for commercial CAs). Automate renewal; don't rely on calendar reminders. A mismatch between the certificate's SAN and the requested hostname causes an immediate hard error for users.

- **Disabling certificate verification in code.** `verify=False` in Python `requests`, `InsecureSkipVerify: true` in Go's `http.Transport`, or `-k` with curl all remove the authentication that makes HTTPS meaningful. Never ship this in production; use a proper CA bundle or self-signed cert import instead.

- **Using TLS 1.0 / 1.1.** Both are deprecated (RFC 8996). They are vulnerable to BEAST, POODLE, and related attacks. Enforce a minimum of TLS 1.2; prefer TLS 1.3 where possible. Many compliance frameworks (PCI-DSS 4.0) require it.

- **Not enabling HSTS.** Without `Strict-Transport-Security`, a user who types `example.com` into a browser bar makes an initial HTTP request before being redirected to HTTPS. An attacker can intercept that first request (SSL stripping). HSTS tells browsers to upgrade all requests to HTTPS automatically.

---

## Exercises

1. **Easy** — Use `openssl s_client -connect github.com:443` to inspect GitHub's certificate. Identify the certificate chain depth, the issuing CA, and the expiry date. Confirm the cipher suite negotiated.

2. **Medium** — Set up a local Nginx server with a self-signed certificate (generated with `openssl req -x509`). Configure it to enforce TLS 1.3 only, redirect HTTP to HTTPS, and send an HSTS header. Use `curl -v` to verify the handshake and headers. Then try connecting with `curl --cacert` pointing to your self-signed cert vs. without it — explain the difference.

3. **Hard** — Implement mutual TLS (mTLS) between two local services: generate a CA, issue a server cert and a client cert signed by that CA, configure one service to require client certificate authentication, and have a second service present its cert on connection. Trace the additional `CertificateRequest` message that appears in the handshake and explain how this differs from standard one-way TLS. Consider: how would you rotate the client certificate without downtime?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| SSL | The protocol securing HTTPS | SSL (SSLv3 and earlier) is deprecated and broken; the protocol in use is TLS. "SSL certificate" is a colloquial holdover — the file is an X.509 certificate used by TLS. |
| HTTPS | "HTTP with encryption" | HTTP over TLS — it adds both encryption of data in transit and authentication of the server's identity. |
| Session key | The server's private key used per session | A short-lived symmetric key derived fresh each connection via ECDH; it is never transmitted. |
| Certificate Authority (CA) | A company that charges money to issue certs | A trusted third party whose root certificate is pre-installed in operating systems and browsers, whose signature on a leaf certificate bootstraps trust. |
| Forward secrecy | Keeping old keys around for later decryption | The property that compromise of a long-term private key cannot decrypt past sessions, because ephemeral ECDHE keys were used and discarded. |
| SNI | Something the server does | A TLS extension sent by the **client** that names the target hostname, enabling one IP to host multiple TLS sites. |
| OCSP Stapling | Checking certificate revocation at the CA | The server proactively fetches and caches the CA's revocation response and "staples" it to the TLS handshake, eliminating a client round-trip to the CA. |

---

## Further Reading

- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3** — https://www.rfc-editor.org/rfc/rfc8446 (the definitive specification; Appendix D summarizes differences from TLS 1.2)
- **"The Illustrated TLS 1.3 Connection" by Michael Driscoll** — https://tls13.xargs.org — byte-level walkthrough of every field in a real TLS 1.3 handshake
- **Mozilla SSL Configuration Generator** — https://ssl-config.mozilla.org — generates production-ready Nginx, Apache, and HAProxy TLS configs for Modern, Intermediate, and Old compatibility profiles
- **Let's Encrypt Documentation** — https://letsencrypt.org/docs — covers ACME protocol, Certbot usage, wildcard certificates, and renewal automation
- **Cloudflare Learning Center: What is TLS?** — https://www.cloudflare.com/learning/ssl/transport-layer-security-tls — accessible prose overview with diagrams; good companion to this lesson
