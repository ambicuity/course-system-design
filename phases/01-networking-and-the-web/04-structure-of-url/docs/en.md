# Structure of URL

> Every network request starts with an address — understanding its anatomy lets you debug, design, and secure systems faster.

**Type:** Learn
**Prerequisites:** How the Web Works, DNS Resolution, HTTP Basics
**Time:** ~25 minutes

---

## The Problem

You open a ticket: "Users are getting 404 errors when sharing links from the settings page." You look at the URL in question:

```
https://app.example.com/settings?tab=billing&plan=pro#invoices
```

Where exactly does the server routing break down? Is it the path `/settings`? The query parameter `tab=billing`? The fragment `#invoices`? Without a clear mental model of what each piece of a URL does — and which component is resolved by which system — you're guessing.

The same confusion surfaces when you design an API: should filter state live in the path (`/users/active`) or query string (`/users?status=active`)? When you configure a load balancer: which part of the URL does it use for routing? When you debug a CORS error: why does the browser block one origin but not another?

A URL is not a flat string — it is a structured address with precise semantics at each component. Each field is consumed by a different layer of the network stack. Getting this wrong produces bugs that are infuriatingly hard to reproduce because they depend on the full address, not just the hostname.

---

## The Concept

### Anatomy of a URL

A URL (Uniform Resource Locator) is defined by [RFC 3986](https://datatracker.ietf.org/doc/html/rfc3986). Its full syntax is:

```
scheme://[userinfo@]host[:port]/path[?query][#fragment]
```

Broken down against a concrete example:

```
https://alice:secret@api.example.com:8443/v2/users/42?format=json&verbose=true#profile
  │       │       │       │              │       │              │                   │
  │       │       │       │              │       │              │                   └─ fragment
  │       │       │       │              │       │              └─ query string
  │       │       │       │              │       └─ path
  │       │       │       │              └─ port
  │       │       │       └─ host (domain)
  │       │       └─ password (deprecated)
  │       └─ username
  └─ scheme
```

### Component-by-Component Breakdown

#### 1. Scheme (Protocol)

The scheme tells the client **which protocol to use** to retrieve the resource.

| Scheme     | Transport           | Default Port | Notes |
|------------|---------------------|-------------|-------|
| `http`     | Plain TCP           | 80          | Cleartext; avoid for auth/data |
| `https`    | TLS over TCP        | 443         | Standard for all production web |
| `ftp`      | FTP protocol        | 21          | Legacy file transfer |
| `ws`       | WebSocket (plain)   | 80          | Real-time bidirectional channels |
| `wss`      | WebSocket over TLS  | 443         | Secure WebSocket |
| `mailto`   | Email (no TCP conn) | —           | Opens email client |
| `file`     | Local filesystem    | —           | No network; browser-local |

The scheme ends with `://`. The colon separates the scheme from the authority; the double slash signals that an authority (host) follows.

#### 2. Authority: Userinfo, Host, Port

The authority section is `[userinfo@]host[:port]`.

**Userinfo** (`username:password@`) is specified in RFC 3986 but deprecated for passwords in RFC 7235 and all modern browsers. Credentials in URLs appear in server logs, browser history, and referrer headers — never use them.

**Host** is either a registered domain name or an IP address:
- Domain names are resolved via DNS to an IP: `api.example.com`
- IPv4 literals: `192.168.1.1`
- IPv6 literals must be enclosed in brackets: `[2001:db8::1]`

**Port** is optional when using the scheme's default. When present, it overrides the default. The operating system resolves the port to a socket on the target machine after TCP connection is established.

```
api.example.com        → port 443 implied by https://
api.example.com:8443   → explicit port 8443
api.example.com:80     → explicit port 80 (unusual with https)
```

The combination of `scheme + host + port` forms the **origin** — the security boundary enforced by browsers for same-origin policy and CORS.

#### 3. Path

The path (`/v2/users/42`) identifies the specific **resource** within the host. Key rules:

- Segments are separated by `/`
- The path is case-sensitive on most servers (Linux filesystems, most web frameworks)
- An empty path is equivalent to `/`
- Servers are free to map paths however they want — the URL says nothing about whether `/users/42` is a file, a database row, or a computed result

Path design is an API contract. REST conventions treat path segments as **nouns** (resources) and HTTP methods as **verbs** (actions):

```
GET  /users/42          → fetch user 42
PUT  /users/42          → replace user 42
DELETE /users/42        → remove user 42
GET  /users/42/orders   → orders belonging to user 42
```

#### 4. Query String

The query string (`?format=json&verbose=true`) carries **parameters** as key-value pairs separated by `&`. It begins with `?`.

- Values are URL-encoded: spaces become `%20` or `+`, special chars use percent-encoding
- Keys and values are both strings; type interpretation is the application's responsibility
- Query strings are part of the URL and **are sent to the server** (unlike fragments)
- They appear in server logs and browser history — avoid putting secrets here

Typical uses:
- Filtering: `?status=active&role=admin`
- Pagination: `?page=2&limit=50`
- Sorting: `?sort=created_at&order=desc`
- Search: `?q=system+design`
- Format negotiation: `?format=json`

Multiple values for the same key are legal and framework-dependent:
```
?color=red&color=blue   → many frameworks parse as array ["red", "blue"]
?ids[]=1&ids[]=2        → PHP/Rails array convention
```

#### 5. Fragment (Anchor)

The fragment (`#profile`) is fundamentally different from every other URL component:

**The fragment is never sent to the server.** It is resolved entirely by the client (browser) after the resource loads.

Original use — scroll to an element with a matching `id`:
```html
<section id="profile">...</section>
```
Navigating to `#profile` causes the browser to scroll that element into view with no new network request.

Modern use — Single Page Applications (SPAs) hijack fragment navigation for client-side routing:
```
https://app.example.com/#/dashboard
https://app.example.com/#/users/42
```
This was the dominant SPA routing strategy before the HTML5 History API (`pushState`) made path-based client routing practical.

Because fragments never reach the server, they also cannot be logged server-side, making them occasionally used (controversially) for tracking tokens and OAuth redirect state — though this has security implications.

### How Each Layer Uses the URL

```
Full URL:  https://api.example.com:443/v2/users/42?sort=asc#top

DNS resolver:      api.example.com                           → resolves to IP
TCP stack:                              :443                 → opens socket
TLS handshake:     api.example.com                           → SNI extension, cert validation
HTTP layer:        /v2/users/42?sort=asc                     → sent in request line
Browser/client:                                        #top  → handled locally, never sent
```

This decomposition explains why a reverse proxy can route on path without knowing the query string, why CORS checks origin not path, and why fragment-based routing doesn't require server changes.

---

## Build It / In Depth

### Parsing a URL Programmatically

Understanding URL structure becomes practical when you need to inspect or construct URLs in code.

**Python (stdlib `urllib.parse`):**

```python
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

raw = "https://api.example.com:8443/v2/users/42?format=json&tag=a&tag=b#profile"

parsed = urlparse(raw)
print(parsed.scheme)    # https
print(parsed.netloc)    # api.example.com:8443
print(parsed.hostname)  # api.example.com
print(parsed.port)      # 8443
print(parsed.path)      # /v2/users/42
print(parsed.query)     # format=json&tag=a&tag=b
print(parsed.fragment)  # profile

params = parse_qs(parsed.query)
print(params)           # {'format': ['json'], 'tag': ['a', 'b']}

# Rebuild with modified query
new_query = urlencode({'format': 'xml', 'tag': ['a', 'b']}, doseq=True)
rebuilt = urlunparse(parsed._replace(query=new_query, fragment=''))
print(rebuilt)  # https://api.example.com:8443/v2/users/42?format=xml&tag=a&tag=b
```

**JavaScript (browser `URL` API):**

```javascript
const url = new URL("https://api.example.com:8443/v2/users/42?format=json&tag=a#profile");

console.log(url.protocol);   // "https:"
console.log(url.hostname);   // "api.example.com"
console.log(url.port);       // "8443"
console.log(url.pathname);   // "/v2/users/42"
console.log(url.search);     // "?format=json&tag=a"
console.log(url.hash);       // "#profile"

// Safe parameter manipulation — no manual string concatenation
url.searchParams.set('format', 'xml');
url.searchParams.append('tag', 'b');
console.log(url.toString());
// https://api.example.com:8443/v2/users/42?format=xml&tag=a&tag=b#profile
```

### Percent-Encoding Worked Example

URL characters fall into three categories:

| Category       | Characters                          | Rule |
|----------------|-------------------------------------|------|
| Unreserved     | `A-Z a-z 0-9 - . _ ~`              | Safe as-is |
| Reserved       | `: / ? # [ ] @ ! $ & ' ( ) * + , ; =` | Structural meaning; encode when used as data |
| Everything else | Spaces, Unicode, control chars      | Must be percent-encoded |

Encoding `"hello world & co."` as a query value:

```
space → %20
&     → %26   (would be mistaken for parameter separator)
.     → .     (unreserved, safe)

Result: hello%20world%20%26%20co.
```

Always encode values with a library — manual encoding is error-prone. Never encode the full URL at once; encode each component separately before assembling.

### Path vs. Query String: Design Decision

```
Option A: /users/active/admin?page=2
Option B: /users?status=active&role=admin&page=2

                    │ Path segment      │ Query param
────────────────────┼───────────────────┼──────────────────────────
Resource identity   │ ✓ Strong signal   │ ✗ Feels like filter
Cacheability        │ ✓ CDN-friendly    │ △ CDN caches by URL key
Required vs optional│ ✓ Required params │ ✓ Optional modifiers
Human readability   │ ✓ Clean, shareable│ △ Verbose
Bookmarkability     │ ✓                 │ ✓
```

**Rule of thumb:** put resource identity in the path; put filter, sort, pagination, and format options in the query string.

---

## Use It

### Real-System Examples

**CDN routing (Cloudflare, Fastly, CloudFront)**
CDNs cache by the full URL including query string by default. A misconfigured caching rule that strips query params will serve the same cached page for `?user=alice` and `?user=bob`. You can configure cache key normalization to include or ignore specific query parameters.

**Load balancer path-based routing (AWS ALB, nginx)**
Path prefix routing lets you split traffic by URL path without touching the application:

```nginx
location /api/v2/ {
    proxy_pass http://backend-v2;
}
location /api/v1/ {
    proxy_pass http://backend-v1;
}
```

**OAuth 2.0 redirect URIs**
OAuth uses the fragment in the implicit flow to pass access tokens without them hitting the server:
```
https://app.example.com/callback#access_token=abc123&token_type=bearer
```
The JavaScript on the page reads `location.hash` — the token never appears in server logs.

**gRPC and REST gateway (e.g., gRPC-Gateway)**
Path parameters in the URL map directly to proto message fields:
```
GET /v1/projects/{project}/zones/{zone}/instances/{instance}
```

**Browser DevTools**
In the Network panel, the Request URL shows the full URL. The Headers tab splits it into method, path, host, and query params. The fragment is never shown in network logs because it's never sent.

### Comparison: URL Routing Strategies

| Strategy          | Example                            | Use When |
|-------------------|------------------------------------|----------|
| Path-based        | `/reports/monthly`                 | Resource identity, REST APIs |
| Query string      | `/reports?period=monthly`          | Filters, optional params |
| Fragment routing  | `/#/reports/monthly`               | Legacy SPAs without server config |
| History API (SPA) | `/reports/monthly` (pushState)     | Modern SPAs; requires server fallback |
| Subdomain routing | `reports.example.com`              | Tenant isolation, product separation |

---

## Common Pitfalls

- **Putting secrets in the URL.** Query parameters appear in access logs, browser history, referrer headers, and Referer request headers sent to third-party resources on the page. Use POST bodies or Authorization headers for credentials and tokens.

- **Assuming path case-insensitivity.** `/Users/42` and `/users/42` are distinct URLs on case-sensitive file systems (Linux). Web frameworks on macOS (case-insensitive by default) may accept both in development, hiding a bug that breaks in production.

- **Double-encoding or under-encoding.** Encoding the full URL instead of individual components corrupts reserved characters like `?` and `&`. Conversely, failing to encode user-provided values that contain `&` or `=` silently corrupts query parsing.

- **Treating the fragment as server state.** If your application stores important state only in `#fragment`, server-side redirects, analytics, and link previewers will miss it — the server never sees it. Use History API (`pushState`) for shareable, server-aware routing.

- **Not normalizing URLs before comparison or caching.** `HTTP://API.EXAMPLE.COM` and `https://api.example.com` differ in scheme and protocol; `example.com/path` and `example.com/path/` are typically treated as different routes. Canonicalize before deduplication, caching, or signature verification.

---

## Exercises

1. **Easy** — Take the URL `http://shop.example.com/products?category=books&sort=price#top` and write down the value of each component (scheme, host, port, path, query params as key-value pairs, fragment). What port does the server actually listen on?

2. **Medium** — You are designing a REST API for a multi-tenant SaaS application. Customers are identified by `org_id`. Compare these two designs for fetching an org's invoices:
   - `GET /orgs/42/invoices?status=paid&page=2`
   - `GET /invoices?org_id=42&status=paid&page=2`
   Argue which is better for authorization middleware, CDN caching, and URL readability. Are there cases where the second is preferable?

3. **Hard** — A redirect from your login page to `https://app.example.com/dashboard?ref=login#section2` passes through an intermediate redirect (`302 → https://partner.example.com`). Which components survive intact through the redirect? Which are lost, and why? How would you preserve fragment state across a server-side redirect?

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| URL | Just the web address in the browser | A structured string with five distinct components (scheme, authority, path, query, fragment), each consumed by a different layer |
| Origin | The domain name | The **tuple** of (scheme + host + port); `http://example.com` and `https://example.com` are different origins |
| Fragment | A server-side anchor | A client-only bookmark; **never transmitted to the server** in any HTTP request |
| Percent-encoding | URL encoding the whole URL | Encoding **individual component values** that contain reserved or non-ASCII characters, not the assembled URL |
| Query string | A search feature | Key-value parameters for any purpose: filtering, pagination, format negotiation, feature flags, tracking |
| Port | Only relevant for unusual servers | Every TCP connection uses a port; HTTPS implies port 443 and HTTP implies 80, but both can be overridden |
| Path | A file path on a server | An opaque string the server interprets however it wants; may map to a file, database row, or computed response |

---

## Further Reading

- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://datatracker.ietf.org/doc/html/rfc3986) — The authoritative specification for URL syntax and percent-encoding rules.
- [MDN Web Docs: What is a URL?](https://developer.mozilla.org/en-US/docs/Learn/Common_questions/Web_mechanics/What_is_a_URL) — Accessible reference with interactive examples and component diagrams.
- [MDN Web Docs: URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL) — Browser-native URL parsing; covers `URLSearchParams` for safe query string manipulation.
- [WHATWG URL Standard](https://url.spec.whatwg.org/) — The living standard that browsers actually implement, covering edge cases that differ from RFC 3986.
- [Google Web Fundamentals: URL Structure for SEO](https://developers.google.com/search/docs/crawling-indexing/url-structure) — Practical guidance on URL design with caching, canonicalization, and crawlability implications.
