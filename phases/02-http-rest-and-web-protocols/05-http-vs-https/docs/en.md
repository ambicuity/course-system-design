# HTTP vs. HTTPS

> HTTPS is not "HTTP with a lock icon" — it is a completely different transport layer that prevents eavesdropping, tampering, and impersonation.

**Type:** Learn
**Prerequisites:** How TCP Works, DNS Resolution, HTTP Request/Response Lifecycle
**Time:** ~25 minutes

---

## The Problem

Imagine a user logs into your banking app over hotel Wi-Fi. The network owner — or any device on that subnet — can run a passive packet capture. With plain HTTP every byte of that request, including the `Authorization` header and the form fields containing the account number, is sent in readable ASCII. No exploit required; `tcpdump` and a text editor are enough.

This is not a theoretical threat. Coffee-shop eavesdropping, ISP injection of ads into HTTP responses, and BGP-level man-in-the-middle attacks are all documented in the wild. Even without a malicious actor, transparent proxies silently rewrite HTTP responses, which means the page your user sees is not necessarily the page your server sent.

The second problem is identity. HTTP has no mechanism to prove the server is who it claims to be. A DNS hijack or ARP spoofing attack can silently redirect `http://bank.com` to an attacker's machine, and the client has no way to detect it. HTTPS solves both confidentiality and identity in a single handshake before any application data is exchanged.

---

## The Concept

### The Two Layers

HTTPS is HTTP running over TLS (Transport Layer Security). TLS itself sits between TCP and HTTP in the protocol stack:

```
Application Layer:   HTTP (GET /login, 200 OK, headers, body)
                        |
Security Layer:      TLS (encrypt/decrypt, certificate, MAC)
                        |
Transport Layer:     TCP (SYN / SYN-ACK / ACK, segments)
                        |
Network Layer:       IP (routing)
```

Plain HTTP skips the TLS row entirely. Everything else stays the same — the same HTTP methods, headers, and status codes work identically over HTTPS.

### Why Two Types of Encryption?

TLS uses **asymmetric encryption** to bootstrap a shared secret, then switches to **symmetric encryption** for bulk data. Understanding why requires knowing the trade-off:

| Property | Asymmetric (RSA / ECDH) | Symmetric (AES-GCM) |
|---|---|---|
| Key count | Public + private key pair | Single shared key |
| Speed | Slow (10–100× slower) | Fast (hardware accelerated) |
| Key distribution | Safe over untrusted channel | Requires a prior shared secret |
| Use in TLS | Key exchange only | All application data |

You cannot use symmetric encryption to start a conversation with a stranger — you have no safe way to share the key. You cannot use asymmetric encryption for bulk data — it is too slow and has message-size limits. TLS solves this by using asymmetric crypto to agree on a symmetric key, then throwing it away and using the symmetric key for everything else.

### The TLS 1.3 Handshake

Modern TLS (1.3, used since ~2018) completes in **one round trip** after the TCP handshake:

```
Client                                    Server
  |                                         |
  |---TCP SYN-------------------------->    |
  |<--TCP SYN-ACK-----------------------   |
  |---TCP ACK-------------------------->    |
  |                                         |
  |---ClientHello (supported ciphers,   --> |
  |   key_share: ephemeral public key)      |
  |                                         |
  |<--ServerHello (chosen cipher,       --- |
  |   key_share: server ephemeral key,      |
  |   Certificate, CertificateVerify,       |
  |   Finished)                             |
  |                                         |
  |   [Both derive session keys from        |
  |    the ECDH key exchange — no           |
  |    encrypted pre-master secret]         |
  |                                         |
  |---Finished + HTTP GET-------------> --- |
  |<--HTTP 200 OK (encrypted)----------     |
```

Key steps:

1. **ClientHello** — the client advertises TLS version, supported cipher suites (e.g., `TLS_AES_128_GCM_SHA256`), and its ephemeral Diffie-Hellman public key.

2. **ServerHello + Certificate** — the server picks a cipher, sends its ephemeral DH public key, and attaches its X.509 certificate. The certificate binds the server's identity (domain name) to its long-term public key, signed by a trusted Certificate Authority (CA).

3. **Key derivation (ECDH)** — each side computes the same shared secret from the other's public key and its own private key. Neither the client's DH private key nor the server's DH private key ever leaves its owner. The shared secret is used to derive the symmetric session keys (one for each direction).

4. **Certificate verification** — the client checks: (a) the certificate was signed by a CA in its trust store, (b) the hostname matches the certificate's Subject Alternative Name, and (c) the certificate has not expired or been revoked.

5. **Finished + application data** — both sides send a `Finished` message (a MAC over the entire handshake transcript), confirming no tampering occurred. TLS 1.3 then allows the first HTTP request to be sent with the `Finished` message — that is the one-round-trip win.

### Forward Secrecy

TLS 1.3 mandates ephemeral key exchange (ECDHE). This means the key used to derive the session key is generated fresh for each connection and discarded afterwards. Consequence: recording encrypted traffic today and later stealing the server's long-term private key does not decrypt past sessions. TLS 1.2 with RSA key exchange did not have this property — a stolen private key could retroactively decrypt all past sessions.

### HTTP vs. HTTPS at a Glance

| Dimension | HTTP | HTTPS |
|---|---|---|
| Default port | 80 | 443 |
| Encryption | None | TLS 1.2 / 1.3 |
| Authentication | None | Server certificate (+ optionally client cert) |
| Integrity | None | AEAD cipher (AES-GCM, ChaCha20-Poly1305) |
| Latency overhead | 0 extra RTT | 1 extra RTT (TLS 1.3); 2 RTT (TLS 1.2) |
| CPU overhead | Negligible | Negligible (AES-NI hardware support) |
| Required for HTTP/2 | No | Yes (all major browsers enforce it) |
| Required for PWAs / Service Workers | — | Yes |

---

## Build It / In Depth

### Generating a Self-Signed Certificate (local dev)

```bash
# Generate a 2048-bit RSA private key and self-signed cert valid for 365 days
openssl req -x509 -newkey rsa:2048 \
  -keyout key.pem \
  -out cert.pem \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

### Serving HTTPS with Python (no framework)

```python
import http.server
import ssl

server = http.server.HTTPServer(("0.0.0.0", 4443), http.server.SimpleHTTPRequestHandler)

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("cert.pem", "key.pem")
server.socket = ctx.wrap_socket(server.socket, server_side=True)

print("Listening on https://localhost:4443")
server.serve_forever()
```

### Inspecting the Handshake

```bash
# Show the full TLS handshake, protocol version, and cipher negotiated
openssl s_client -connect example.com:443 -tls1_3 2>&1 | head -50

# Confirm certificate chain and expiry
openssl s_client -connect example.com:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -subject -issuer
```

### Obtaining a Free Production Certificate (Let's Encrypt)

```bash
# Install certbot and get a certificate for your domain (nginx example)
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com

# Certbot auto-renews via a systemd timer or cron; verify with:
sudo certbot renew --dry-run
```

Let's Encrypt uses the ACME protocol: your server proves domain ownership by serving a challenge file over HTTP (HTTP-01 challenge) or via a DNS TXT record (DNS-01 challenge). The CA then signs a 90-day certificate.

### Nginx TLS Configuration (production-grade)

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # TLS 1.2 + 1.3 only; disable older protocols
    ssl_protocols TLSv1.2 TLSv1.3;

    # Strong cipher suites; let the server prefer order
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;  # TLS 1.3 ignores this; leave off for 1.3

    # OCSP stapling avoids a client round-trip for revocation check
    ssl_stapling on;
    ssl_stapling_verify on;

    # HSTS: tell browsers to only use HTTPS for 1 year
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}

# Redirect all HTTP traffic to HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$host$request_uri;
}
```

---

## Use It

### Where These Technologies Show Up

| Technology / Context | What it does with TLS |
|---|---|
| **Let's Encrypt** | Free, automated CA. Dominates public-web cert issuance (~350M certs). |
| **AWS Certificate Manager (ACM)** | Provisions and auto-renews TLS certs for ALB, CloudFront, API Gateway. Zero cost on AWS-managed endpoints. |
| **Cloudflare** | Terminates TLS at the edge (Full or Full-Strict mode). Handles cert renewal, TLS 1.3, and HTTP/2 automatically. |
| **mTLS (mutual TLS)** | Both client and server present certificates. Used in service meshes (Istio, Linkerd) for zero-trust service-to-service auth. |
| **HSTS Preloading** | Browsers ship a hardcoded list of domains that must use HTTPS. Visit hstspreload.org to submit your domain. |
| **Certificate Transparency (CT)** | All publicly trusted certs must be logged in a public CT log. Browsers reject certs not in CT logs. Mitigates misissuance. |
| **OCSP / CRL** | Revocation mechanisms. OCSP stapling lets the server cache and serve the revocation response, saving a client round-trip. |

### When HTTP Is Still Acceptable

- Internal, isolated networks with no sensitive data and no internet exposure (rare in practice).
- Health-check endpoints behind a load balancer that does TLS termination at the edge.
- Local developer tooling where self-signed certs add friction with no security value.

In every public-facing scenario, use HTTPS. The CPU cost of TLS on modern hardware is negligible — AES-NI hardware acceleration makes symmetric encryption fast enough that it no longer registers in latency profiles.

---

## Common Pitfalls

- **Mixed content**: Serving an HTTPS page that loads images, scripts, or API calls over HTTP. Browsers block or warn on this. Audit with browser DevTools → Network → filter by http://. Fix by making all sub-resource URLs relative or HTTPS-absolute.

- **Certificate expiry**: TLS certificates have a defined validity period (90 days for Let's Encrypt, up to 1 year for paid CAs). Forgetting to automate renewal is one of the most common production outages. Always configure certbot renew as a cron job or use a managed service (ACM, Cloudflare) that renews automatically.

- **Using TLS 1.0 or 1.1**: Both are deprecated (RFC 8996, 2021) and have known vulnerabilities (BEAST, POODLE). Configure your server to reject them explicitly. PCI-DSS compliance has required TLS 1.2+ since 2018.

- **Trusting self-signed certs in production code**: Disabling certificate verification (`verify=False` in Python requests, `CURLOPT_SSL_VERIFYPEER = 0`) defeats the entire purpose of TLS. The client can no longer detect a man-in-the-middle. In dev, add the self-signed cert to the trust store instead.

- **Forgetting HTTP→HTTPS redirect**: Issuing an HTTPS cert without also redirecting port 80 leaves users who type bare domain names on unencrypted HTTP. Always add the 301 redirect and pair it with an HSTS header so browsers remember to use HTTPS directly next time.

---

## Exercises

1. **Easy** — Run `openssl s_client -connect google.com:443` and identify: (a) the TLS version negotiated, (b) the cipher suite, and (c) the certificate expiry date. Explain what each field means.

2. **Medium** — Set up a local Nginx server with a self-signed certificate. Configure it to redirect HTTP (port 80) to HTTPS (port 443), add an HSTS header, and disable TLS 1.0/1.1. Verify all three behaviors using `curl -v` and `openssl s_client`.

3. **Hard** — Compare TLS 1.2 (with RSA key exchange) and TLS 1.3 in terms of handshake round trips, forward secrecy, and cipher suite negotiation. Then explain why a recorded TLS 1.2 session with RSA key exchange can be decrypted retroactively if the server's private key is ever leaked, but a recorded TLS 1.3 session cannot. What property of ECDHE prevents this?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **SSL** | An active encryption protocol used today | SSL (SSL 2.0 / 3.0) is deprecated and broken. Modern "SSL" is actually TLS 1.2 or 1.3. The terms are used interchangeably in marketing but SSL itself is dead. |
| **Certificate** | A file that enables encryption | An X.509 document that binds a public key to an identity (domain name), signed by a CA. It proves who you're talking to, not what you're encrypting with. |
| **Certificate Authority (CA)** | A company that sells security | A trusted third party whose public key is pre-installed in browsers and OSes. When a CA signs your cert, browsers automatically trust it. |
| **Session key** | The same key reused forever | A short-lived symmetric key derived fresh for each TLS connection and discarded after the session ends. Never stored, never transmitted. |
| **Forward Secrecy** | A nice-to-have TLS feature | The property that compromising the server's long-term private key in the future cannot decrypt past recorded sessions. Requires ephemeral (ECDHE) key exchange. |
| **HSTS** | An optional performance header | HTTP Strict Transport Security. A response header instructing browsers to never connect to this domain over HTTP, for a specified duration. |
| **mTLS** | HTTPS with extra steps | Mutual TLS: both the client and server present and verify certificates. Standard in zero-trust architectures and service meshes. |

---

## Further Reading

- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) — The canonical specification. Section 2 (overview) and Section 4 (handshake) are readable without implementing the protocol.
- [Let's Encrypt — How It Works](https://letsencrypt.org/how-it-works/) — Clear explanation of the ACME protocol and domain validation challenges.
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/) — Generates production-grade TLS configs for Nginx, Apache, HAProxy, and others, with modern cipher suites and HSTS enabled.
- [High Performance Browser Networking — TLS chapter (Ilya Grigorik)](https://hpbn.co/transport-layer-security-tls/) — Deep dive into TLS performance, session resumption, OCSP stapling, and False Start. Free online.
- [SSL Labs Server Test](https://www.ssllabs.com/ssltest/) — Paste any public domain to get a graded report on TLS configuration, cipher strength, certificate chain, and protocol support.
