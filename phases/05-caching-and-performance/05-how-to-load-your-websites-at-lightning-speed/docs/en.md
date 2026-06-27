# How to load your websites at lightning speed

> Sending less, loading smarter, and rendering only what the user can see makes every millisecond count.

**Type:** Learn
**Prerequisites:** HTTP caching basics, CDN fundamentals, JavaScript module system
**Time:** ~35 minutes

---

## The Problem

A typical modern web application ships a single JavaScript bundle that can easily balloon to 3–5 MB before minification. When a first-time visitor opens your site on a mid-range Android phone over a 4G connection, that bundle must be downloaded, parsed, and executed before a single pixel of meaningful UI appears. According to Google's research, each additional second of load time on mobile increases bounce rates by roughly 32%. At 3 seconds the probability of a bounce nearly triples compared to a 1-second load.

Consider an e-commerce product page: you have above-the-fold product images, a buy button, and a price. You also have a 400 KB charting library for the analytics dashboard only your marketing team uses, a full-featured rich-text editor for customer reviews (which loads even for logged-out visitors), and a date-picker widget embedded three screens below the fold. None of that secondary code affects what the visitor sees in the first second, yet the browser must process all of it before it can become interactive.

The root problem is a mismatch between *what you ship* and *what the user needs right now*. Fixing it requires a set of coordinated techniques — compression, code splitting, selective rendering, smart prefetching — that together collapse perceived and actual load time. Understanding how each technique works, and where each one fits in the delivery pipeline, is what this lesson is about.

---

## The Concept

### The delivery pipeline

Every byte your site sends travels through this pipeline before it appears on screen:

```
Browser                    Network Edge           Origin Server
  |                             |                       |
  |--- HTTP GET /index.html --->|---------------------> |
  |<-- 200 HTML (gzip) --------|<--------------------- |
  |                             |                       |
  |--- parse HTML               |                       |
  |--- GET /bundle.js --------->|---------------------> |
  |    GET /hero.jpg  --------->|---------------------> |
  |<-- bundle.js (br) ----------|<--------------------- |
  |<-- hero.jpg (webp) ---------|<--------------------- |
  |                             |                       |
  |--- parse + compile JS       |                       |
  |--- layout + paint           |                       |
  |=== First Contentful Paint ========================= |
  |--- hydrate / execute JS     |                       |
  |=== Time to Interactive ===========================  |
```

Each technique in this lesson attacks a specific segment of that pipeline.

### The eight techniques

| Technique | Pipeline stage attacked | Typical gain |
|---|---|---|
| Compression | Transfer size | 60–80% size reduction |
| Code splitting | Parse + execute | 40–70% faster TTI |
| Tree shaking | Transfer + parse | 20–60% smaller bundle |
| Dynamic imports | Parse + execute | Defers non-critical code |
| Priority-based loading | Network scheduling | Faster LCP |
| Preloading | Network scheduling | Eliminates late discovery |
| Prefetching | Idle-time network | Near-instant subsequent pages |
| Selective rendering / windowing | Paint + layout | Smooth scrolling on large lists |

### Compression

The browser and server negotiate a transfer encoding via `Accept-Encoding` / `Content-Encoding` headers. The two dominant algorithms today are **gzip** (universal support, good ratio) and **Brotli** (`br`, supported by all modern browsers, 15–25% better compression than gzip at equal CPU cost).

```
Original bundle.js    1,200 KB
After minification      420 KB
After gzip              130 KB
After Brotli             98 KB
```

Compression is a free win — serve Brotli where supported, fall back to gzip. The cost is CPU time on the server or, preferably, pre-compressed static files on a CDN.

### Code splitting

A single bundle means the browser must parse and compile code for the entire application before executing any of it. Code splitting breaks the bundle into chunks that load on demand.

```
BEFORE splitting:
  bundle.js  3.2 MB  ← everything loaded on every page

AFTER splitting:
  main.js          180 KB  ← shell, routing, critical components
  product.js       240 KB  ← lazy-loaded when /product route activates
  checkout.js      310 KB  ← lazy-loaded when /checkout route activates
  dashboard.js     620 KB  ← lazy-loaded when authenticated user visits /dashboard
  vendor.react.js  140 KB  ← shared chunk, cached across pages
```

Route-based splitting is the highest-leverage default split point. Component-based splitting (per heavy UI widget) is the next layer.

### Tree shaking

Bundlers (Webpack, Rollup, esbuild) perform static analysis of ES module `import`/`export` graphs to remove code paths that are never reachable. This is called dead code elimination or tree shaking.

```js
// utils.js — exports three functions
export function add(a, b) { return a + b; }
export function subtract(a, b) { return a - b; }
export function formatCurrency(n) { /* 2 KB of locale logic */ }

// app.js — only imports add
import { add } from './utils';
```

After tree shaking, `subtract` and `formatCurrency` are absent from the output. The gain is large when you import from a library that exports hundreds of functions (e.g., lodash-es, date-fns) but only use a handful.

**Critical requirement:** Tree shaking only works on ES modules (static `import`/`export`). CommonJS (`require`) prevents it because imports are dynamic and unanalyzable at build time.

### Dynamic imports

ES2020 `import()` returns a Promise, deferring the fetch and parse of a module to runtime — triggered by user action rather than page load.

```js
// Without dynamic import: charting library loads on every page
import { Chart } from 'chart.js';

// With dynamic import: loads only when user opens the analytics panel
async function openAnalyticsPanel() {
  const { Chart } = await import('chart.js');
  new Chart(canvas, config);
}
```

Bundlers automatically split at every dynamic import boundary, so this also creates a new chunk automatically.

### Priority-based loading and preloading

The browser's preload scanner discovers resources by parsing HTML. Resources mentioned deep in the document are discovered late. `<link rel="preload">` tells the browser to start fetching a resource at the highest priority before the parser reaches the tag that would normally trigger it.

```html
<!-- Preload the hero image — discovered immediately, not when the <img> tag is parsed -->
<link rel="preload" as="image" href="/hero.avif" fetchpriority="high">

<!-- Preload the critical font -->
<link rel="preload" as="font" href="/fonts/Inter-Regular.woff2" crossorigin>

<!-- Preload a JS chunk that will be needed on the next interaction -->
<link rel="modulepreload" href="/chunks/checkout.js">
```

Use `fetchpriority="high"` on the LCP image (the largest visible element on initial load). Use `fetchpriority="low"` on below-the-fold images to explicitly deprioritize them.

### Prefetching

Prefetching is speculative: you hint to the browser to fetch a resource you *expect* the user will need next, during idle time, so when they actually navigate there the resource is already in cache.

```html
<!-- Low-priority background fetch; browser decides when based on idle bandwidth -->
<link rel="prefetch" href="/chunks/product-detail.js">

<!-- DNS + TCP connection to a third-party origin opened in advance -->
<link rel="preconnect" href="https://api.payments.example.com" crossorigin>
```

The key difference from preloading:

| | `preload` | `prefetch` |
|---|---|---|
| Priority | High (blocks current page) | Low (background idle) |
| Scope | Current navigation | Future navigation |
| Cache | Memory cache | HTTP disk cache |
| Risk | Wastes bandwidth if unused | Lower waste risk |

### Selective rendering / windowing

Rendering 10,000 list items into the DOM at once means 10,000 DOM nodes, all of which the browser must lay out, paint, and keep in memory. Windowing (also called virtual scrolling) maintains a fixed DOM window of ~20–50 items and swaps content as the user scrolls.

```
Full DOM (10,000 rows):
┌──────────────────────────────────┐
│ row 1  <tr>...</tr>              │
│ row 2  <tr>...</tr>              │
│ ...                              │
│ row 10,000  <tr>...</tr>         │  ← all in DOM, huge memory & layout cost
└──────────────────────────────────┘

Windowed (virtual scroll):
┌──────────────────────────────────┐
│ spacer div (height = rows 1–49)  │  ← no DOM nodes, just empty height
│ row 50  <tr>...</tr>             │
│ row 51  <tr>...</tr>             │
│ ...                              │
│ row 70  <tr>...</tr>             │  ← only ~20 rows in DOM at any time
│ spacer div (height = rows 71–10,000)
└──────────────────────────────────┘
```

The scroll position determines which rows are rendered. Memory usage stays constant regardless of list size.

---

## Build It / In Depth

### Step 1 — Enable Brotli on your CDN / server

**Nginx (origin server):**
```nginx
# nginx.conf
brotli on;
brotli_comp_level 6;           # 1–11; 6 is sweet spot for on-the-fly
brotli_types text/css application/javascript application/json image/svg+xml;

gzip on;                       # fallback for browsers without brotli
gzip_types text/css application/javascript application/json;
```

**Better: pre-compress at build time and serve static files:**
```bash
# Vite / Rollup post-build step
find dist/ -name "*.js" -o -name "*.css" | xargs brotli --best
# Now upload dist/ to S3 + CloudFront; set Content-Encoding: br header
```

### Step 2 — Route-based code splitting (React + Vite)

```jsx
// router.jsx
import { lazy, Suspense } from 'react';
import { createBrowserRouter } from 'react-router-dom';

// Each lazy() call creates a separate bundle chunk
const ProductPage   = lazy(() => import('./pages/ProductPage'));
const CheckoutPage  = lazy(() => import('./pages/CheckoutPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));

export const router = createBrowserRouter([
  { path: '/product/:id', element: (
      <Suspense fallback={<PageSkeleton />}>
        <ProductPage />
      </Suspense>
    )
  },
  { path: '/checkout', element: (
      <Suspense fallback={<PageSkeleton />}>
        <CheckoutPage />
      </Suspense>
    )
  },
]);
```

Vite automatically creates separate chunks for each `lazy(() => import(...))` call. The `Suspense` fallback (a skeleton UI) shows while the chunk loads, preventing a blank screen.

### Step 3 — Verify tree shaking with bundle analysis

```bash
# Install rollup-plugin-visualizer (works with Vite)
npm install --save-dev rollup-plugin-visualizer

# vite.config.js
import { visualizer } from 'rollup-plugin-visualizer';

export default {
  plugins: [
    visualizer({ open: true, gzipSize: true, brotliSize: true })
  ]
};

# Build and inspect
npm run build
# Opens treemap in browser — look for unexpectedly large chunks
```

Common finding: `moment.js` pulling in all locale files (300+ KB). Fix: switch to `date-fns` (tree-shakeable) or use `moment/locale/en` explicit import.

### Step 4 — Add resource hints in HTML

```html
<head>
  <!-- 1. Preconnect to critical third-party origins -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>

  <!-- 2. Preload LCP hero image -->
  <link rel="preload" as="image" href="/images/hero.avif"
        fetchpriority="high" type="image/avif">

  <!-- 3. Preload critical font -->
  <link rel="preload" as="font" href="/fonts/inter-var.woff2"
        crossorigin type="font/woff2">

  <!-- 4. Prefetch next likely route (added by JS after interaction) -->
  <!-- <link rel="prefetch" href="/chunks/checkout.js"> -->
</head>
```

### Step 5 — Virtual scrolling for large lists

```jsx
// Using @tanstack/react-virtual (TanStack Virtual v3)
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef } from 'react';

function ProductList({ products }) {  // products.length = 50,000
  const parentRef = useRef(null);

  const virtualizer = useVirtualizer({
    count: products.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 72,   // estimated row height in px
    overscan: 5,              // render 5 extra rows above/below viewport
  });

  return (
    <div ref={parentRef} style={{ height: '600px', overflowY: 'auto' }}>
      {/* Total scroll height — only this div has the full height */}
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
        {virtualizer.getVirtualItems().map(virtualRow => (
          <div
            key={virtualRow.key}
            style={{
              position: 'absolute',
              top: 0,
              transform: `translateY(${virtualRow.start}px)`,
              width: '100%',
              height: `${virtualRow.size}px`,
            }}
          >
            <ProductRow product={products[virtualRow.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

Regardless of whether `products` has 100 or 100,000 items, the DOM contains approximately `visibleRows + overscan * 2` elements.

### Step 6 — Measure the result

```bash
# Lighthouse CLI (headless Chrome)
npx lighthouse https://yoursite.com \
  --preset=desktop \
  --output=json \
  --output-path=./lh-report.json \
  --chrome-flags="--headless"

# Extract Core Web Vitals
node -e "
  const r = require('./lh-report.json');
  const audits = r.lhr.audits;
  console.log('LCP:', audits['largest-contentful-paint'].displayValue);
  console.log('TBT:', audits['total-blocking-time'].displayValue);
  console.log('CLS:', audits['cumulative-layout-shift'].displayValue);
"
```

Target: LCP < 2.5s, TBT < 200ms, CLS < 0.1.

---

## Use It

### Framework / tooling support matrix

| Tool | Code splitting | Tree shaking | Dynamic import | Built-in compression |
|---|---|---|---|---|
| **Vite** | Automatic per `import()` | Yes (Rollup) | Native | Plugin (vite-plugin-compression) |
| **Webpack 5** | Manual `splitChunks` or `import()` | Yes (module mode) | Native | CompressionWebpackPlugin |
| **Next.js** | Automatic per route + `dynamic()` | Yes | `next/dynamic` | Built-in (Vercel/Netlify) |
| **Remix** | Automatic per route | Yes (esbuild) | Route-based | CDN/adapter |
| **Angular** | Lazy modules (`loadChildren`) | Yes | `import()` | CLI + CDN |

### When to reach for each technique

- **Compression:** Always. Zero exceptions. Configure at CDN level so origin is not CPU-bound.
- **Code splitting:** Any SPA with more than two distinct routes. Worth doing from day one.
- **Tree shaking:** Ensure your bundler config uses `"module"` field resolution and ESM. Audit with a bundle analyzer quarterly.
- **Dynamic imports:** Heavy widgets (maps, charts, video players, rich-text editors) loaded conditionally.
- **Preload:** Hero image, critical web font, above-the-fold JS chunk. Limit to 3–5 resources; more preloads compete with each other.
- **Prefetch:** Next likely navigation (product → checkout, login → dashboard). Safe to add after the page is interactive.
- **Virtual scrolling:** Any list likely to exceed 200–300 items at once. Use TanStack Virtual, react-window, or AG Grid's virtual row model.

---

## Common Pitfalls

- **Preloading too many resources.** Every `<link rel="preload">` competes for bandwidth at high priority. Preloading five fonts plus three images plus two JS chunks defeats the purpose — the browser deprioritizes them all equally. Keep preloads to 2–3 truly critical resources per page.

- **Tree shaking broken by CommonJS interop.** Importing from a library that ships only CJS (`require`) disables tree shaking for that entire module. Check `package.json` for a `"module"` or `"exports"` field pointing to an ESM build. For libraries without ESM builds, use bundler-specific plugins (`babel-plugin-import`, `esbuild-plugin-lodash`) to rewrite imports at build time.

- **Code splitting creating too many small chunks.** Over-splitting leads to a waterfall of HTTP/1.1 requests. If you split every component individually you may end up with 200 tiny chunks and a sequential loading chain. Group related components into feature-level chunks and use `output.manualChunks` in Vite/Rollup to control granularity.

- **Virtual scroll breaking accessibility.** Screen readers and `Ctrl+F` in-page search only see what is in the DOM. A virtualised list hides off-screen rows from assistive technologies. Mitigate by implementing ARIA live regions, keeping visible-but-offscreen rows for a small buffer, and testing with VoiceOver / NVDA before shipping.

- **Prefetching on metered connections.** Prefetch is bandwidth speculation. On slow or metered mobile connections it wastes data for a page the user may never visit. Respect the `navigator.connection.saveData` flag and avoid prefetching when it is set, or when `navigator.connection.effectiveType` is `'2g'` or `'slow-2g'`.

---

## Exercises

1. **Easy — Measure your bundle before and after.** Take any existing React or Vue project, run a production build, and use a bundle analyzer (Rollup's `--visualize` or `webpack-bundle-analyzer`) to identify the three largest modules. Look up whether each one ships an ESM build. Report the gzip and Brotli sizes.

2. **Medium — Add route-based code splitting.** In the same project, convert at least two page-level components to use `React.lazy` + `Suspense` (or the equivalent for your framework). Measure the reduction in the initial bundle's parsed + executed JavaScript using Chrome DevTools → Performance panel. Compare Time to Interactive before and after.

3. **Hard — Build a prefetch-on-hover system.** Implement a React hook `usePrefetchRoute(route: string)` that, when a navigation link is hovered for more than 100ms, dynamically inserts a `<link rel="prefetch">` for that route's JS chunk into the document head. De-duplicate so the same link is not inserted twice. Test with Chrome Network throttling set to "Fast 3G" and measure the latency difference for the subsequent navigation.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Tree shaking** | The bundler magically removes unused code from any library | Static elimination of unreachable ES module exports; does not work on CommonJS code or anything dynamically referenced |
| **Code splitting** | Breaking code into files | Structuring the dependency graph so chunks load only when a route or component is actually needed, not at startup |
| **Preload** | Cache for future visits | A high-priority hint to fetch a resource for the *current* page navigation that the parser would otherwise discover late |
| **Prefetch** | Same as preload | A low-priority idle-time hint for resources needed on *future* navigations; stored in disk cache, not memory cache |
| **Brotli** | A better gzip | A dictionary-based compression algorithm (RFC 7932) that achieves 15–25% better ratios than gzip; requires HTTPS and modern browser |
| **Virtual scrolling** | Lazy loading list items | Maintaining a fixed-size DOM window of visible rows while using spacer elements to preserve scroll height for the full dataset |
| **LCP (Largest Contentful Paint)** | How long the page takes to load | The render time of the largest image or text block visible in the viewport; Google's primary loading performance metric |

---

## Further Reading

- [web.dev — Core Web Vitals](https://web.dev/vitals/) — Google's authoritative definitions and tooling for LCP, INP, and CLS.
- [MDN — Resource hints: preload, prefetch, preconnect](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/preload) — Spec-accurate documentation for all `<link rel>` performance hints.
- [Vite — Code Splitting](https://vitejs.dev/guide/build#chunking-strategy) — Official Vite documentation on chunk strategy and `manualChunks` configuration.
- [TanStack Virtual](https://tanstack.com/virtual/latest) — Framework-agnostic virtual scrolling library used in production at major scale (React, Vue, Solid, Svelte adapters).
- [web.dev — Reduce JavaScript payloads with tree shaking](https://web.dev/reduce-javascript-payloads-with-tree-shaking/) — Practical walkthrough of enabling and verifying tree shaking with Webpack and Rollup.
