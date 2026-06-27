# 30 Free APIs for Developers

> Free-tier APIs are prototyping accelerants — know their constraints before you build around them.

**Type:** Learn
**Prerequisites:** REST API Design, HTTP Methods and Status Codes, API Authentication Patterns
**Time:** ~25 minutes

---

## The Problem

Every project starts with the same question: where does the data come from? Building a weather dashboard, a sports tracker, or an AI-powered tool from scratch means sourcing real data, which costs money, time, or both. Developers burn days signing contracts with data vendors, only to find that free tiers have undocumented rate limits or that the authentication flow is incompatible with their architecture.

The deeper problem is architectural: the wrong API choice early in a project creates hard coupling. If you hard-code against a vendor's proprietary payload shape, migrating to an alternative later requires rewriting every consumer. Developers who understand the landscape of available free APIs — what they provide, how they authenticate, what their limits are, and where they break — make better up-front decisions.

This lesson catalogs 30 production-relevant free (or free-tier) APIs across six categories, with enough detail to evaluate trade-offs rather than just discover they exist.

---

## The Concept

### How Free APIs Actually Work

Nearly every "free" API is one of three models:

```
Model 1: Truly Free (Open Data)
  No key required → No auth overhead → Rate-limited by IP
  Example: OpenStreetMap Nominatim, Open Library

Model 2: Free Tier with API Key
  Key required → Tracks usage → Upgrade path exists
  Example: OpenWeather, NewsAPI, Unsplash
  Rate limits: typically 500–1,000 req/day on free plan

Model 3: Free Research / Developer Tier
  Key + approval required → Access to richer models
  Example: OpenAI, Claude, Gemini (credits expire)
```

Understanding the model determines your architecture:

| Model | Auth Pattern | Caching Strategy | Risk |
|-------|-------------|-----------------|------|
| Truly Free | None / IP-based | Cache aggressively (CDN) | IP block if abusive |
| Free Tier w/ Key | API key in header | Cache per quota window | Key exposure in client code |
| Credits-based AI | Bearer token | Cache completions by prompt hash | Credits exhaust silently |

### Authentication Patterns Across These APIs

Most free APIs use one of three authentication patterns:

```
1. Query Parameter Key
   GET /data?appid=YOUR_KEY&q=London
   Risk: key visible in server logs and browser history

2. Authorization Header
   GET /headlines
   Authorization: Bearer YOUR_KEY
   Best practice: keeps key out of URLs

3. No Auth (Open)
   GET https://nominatim.openstreetmap.org/search?q=Paris&format=json
   Risk: none for key exposure; IP rate-limited instead
```

---

## In Depth

### Category 1 — Public APIs for Open Data

These APIs require no key and are backed by non-profits or government bodies. The data is openly licensed (usually CC-BY or public domain).

| API | Base URL | What It Provides | Rate Limit |
|-----|----------|-----------------|------------|
| **OpenStreetMap** (Nominatim) | `nominatim.openstreetmap.org` | Geocoding: address → lat/lng, reverse geocoding | 1 req/sec; must set `User-Agent` |
| **NASA APIs** | `api.nasa.gov` | Astronomy Picture of the Day, Mars rover photos, Near-Earth Objects | 1,000 req/day with key; 30/hr without |
| **World Bank** | `api.worldbank.org/v2` | GDP, population, economic indicators for 200+ countries | Effectively unlimited |
| **GeoNames** | `api.geonames.org` | City, timezone, postal code, elevation lookups | 1,000 credits/day (free account) |
| **Open Library** | `openlibrary.org/api` | Book metadata, covers, author data from 20M+ records | No documented limit; be courteous |

**Practical pattern for OpenStreetMap geocoding:**

```bash
# Forward geocode: address → coordinates
curl "https://nominatim.openstreetmap.org/search \
  ?q=1600+Pennsylvania+Ave,+Washington+DC \
  &format=json \
  &limit=1" \
  -H "User-Agent: MyApp/1.0 (contact@example.com)"

# Response excerpt
# [{"lat":"38.8976763","lon":"-77.0365298","display_name":"..."}]
```

> **Critical:** OSM's usage policy requires a valid `User-Agent`. Omitting it causes 429s in production.

---

### Category 2 — Weather APIs

Weather data comes from the same underlying sources (NOAA, ECMWF, DWD models). Vendor differentiation is in forecast resolution, historical depth, and SDK quality.

| API | Free Tier Limit | Unique Strength |
|-----|----------------|-----------------|
| **OpenWeatherMap** | 1,000 calls/day; 60/min | Most used; huge community; onecall endpoint bundles current + forecast |
| **WeatherAPI.com** | 1M calls/month | Historical back to 2010 on free plan |
| **StormGlass** | 10 req/day | Marine and offshore data (wave height, wind at sea) |
| **Visual Crossing** | 1,000 records/day | Clean CSV/JSON; historical + forecast in one call |
| **Weatherbit** | 500 calls/day | Air quality index bundled with weather |

```python
import httpx

# OpenWeatherMap — current weather
resp = httpx.get(
    "https://api.openweathermap.org/data/2.5/weather",
    params={"q": "Tokyo", "appid": "YOUR_KEY", "units": "metric"},
)
data = resp.json()
print(f"{data['name']}: {data['main']['temp']}°C, {data['weather'][0]['description']}")
```

**Decision guide:**
- General consumer app → **OpenWeatherMap** (widest support, SDKs everywhere)
- Historical analysis → **WeatherAPI.com** (most history on free plan)
- Marine/sailing project → **StormGlass** (the only real option here)

---

### Category 3 — News APIs

News APIs differ on source coverage, geographic reach, and how long articles stay in the index.

| API | Free Tier | Coverage |
|-----|-----------|----------|
| **NewsAPI.org** | 100 req/day; 1-month-old articles only | 80,000+ sources; strong English coverage |
| **GNews** | 100 req/day | Multilingual; topic-based search |
| **The Guardian** | 5,000 req/day | Full article text available (unusual) |
| **Current News API** | 100 req/day | Real-time; low latency |
| **NYT API** | 500 req/day; 5 req/min | Searchable archive back to 1851 |

The Guardian API stands out: it is one of the few that returns full article body text on the free tier rather than just headlines and snippets — useful for NLP pipelines.

```bash
# Guardian API — search full content
curl "https://content.guardianapis.com/search \
  ?q=climate+change \
  &show-fields=bodyText \
  &api-key=YOUR_KEY"
```

---

### Category 4 — AI and NLP APIs

All major AI providers offer free access via credits that expire or throttled rate limits on a free tier.

| API | Free Allowance | Model Access |
|-----|---------------|-------------|
| **OpenAI** | $5 credit (new accounts, time-limited) | GPT-4o-mini on free; GPT-4o requires payment |
| **Google Gemini** | 15 RPM / 1M tokens/day on Flash | Gemini 1.5 Flash free; Pro is paid |
| **HuggingFace Inference API** | Rate-limited inference on hosted models | 1,000+ open-source models (BERT, LLaMA variants) |
| **Anthropic Claude** | $5 credit (new accounts) | Claude Haiku free-tier; Sonnet/Opus requires payment |
| **Grok (xAI)** | Free during beta (rate-limited) | Grok-beta; context window varies |

```python
# HuggingFace Inference API — zero-shot classification (no credits needed)
import httpx

payload = {
    "inputs": "This tutorial is excellent.",
    "parameters": {"candidate_labels": ["positive", "negative", "neutral"]},
}
resp = httpx.post(
    "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
    headers={"Authorization": "Bearer HF_TOKEN"},
    json=payload,
)
print(resp.json())
# {"labels": ["positive", "neutral", "negative"], "scores": [0.97, 0.02, 0.01]}
```

**HuggingFace is unique**: you get access to thousands of open-source models without credit burn, making it the best option for NLP experimentation on a zero budget.

---

### Category 5 — Sports APIs

Sports data is commercially valuable, so free tiers are restrictive. Plan for caching.

| API | Free Plan | Sports Covered |
|-----|-----------|---------------|
| **Football-Data.org** | 10 req/min; top-tier leagues | Soccer/football (Europe-focused) |
| **NBA API** (stats.nba.com) | Unofficial but open; no key | NBA stats back to 1946 |
| **AllSportsAPI** | 100 req/day | 30+ sports |
| **ESPN API** (unofficial) | No key; JSON endpoints | Scores, standings (undocumented) |
| **API-Football** | 100 req/day | 1,000+ leagues; best coverage |

```python
# Football-Data.org — Premier League standings
import httpx

resp = httpx.get(
    "https://api.football-data.org/v4/competitions/PL/standings",
    headers={"X-Auth-Token": "YOUR_KEY"},
)
standings = resp.json()["standings"][0]["table"]
for team in standings[:5]:
    print(f"{team['position']}. {team['team']['name']} — {team['points']} pts")
```

---

### Category 6 — Miscellaneous Utilities

Small, single-purpose APIs that solve recurring needs without requiring you to build the logic yourself.

| API | Base URL | What It Does |
|-----|----------|-------------|
| **TimeZone API** | `timezoneapi.io` | lat/lng or city → timezone + UTC offset |
| **Unsplash API** | `api.unsplash.com` | 5M+ royalty-free photos; 50 req/hr free |
| **Marvel API** | `gateway.marvel.com` | Characters, comics, events data |
| **Dictionary API** | `api.dictionaryapi.dev` | Definitions, phonetics, examples — no key required |
| **QR Code API** | `api.qrserver.com` | Generate QR codes via URL; truly free |

```bash
# QR Code API — no key, no SDK, just a URL
curl "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://example.com" \
  --output qr.png

# Dictionary API — no key required
curl "https://api.dictionaryapi.dev/api/v2/entries/en/ephemeral" | jq '.[0].meanings[0]'
```

---

## Use It

### When to Reach for Each Category

```
[User requests location feature]
         │
         ├─ Need geocoding only?        → OpenStreetMap Nominatim (free, no key)
         ├─ Need timezone too?          → GeoNames (1 API, covers both)
         └─ Need maps rendered?         → OpenStreetMap tiles + Leaflet.js

[User requests content enrichment]
         │
         ├─ Need article full-text?     → The Guardian API
         ├─ Need breaking news?         → NewsAPI or Current News API
         └─ Need multilingual news?     → GNews

[User requests AI feature]
         │
         ├─ Need classification/NLP?    → HuggingFace (no credit burn)
         ├─ Need generation/chat?       → Gemini Flash (most generous free tier)
         └─ Need highest quality?       → Claude or GPT-4o (use credits wisely)
```

### Caching Strategy by API Type

| API Type | Cache Duration | Cache Key |
|----------|---------------|-----------|
| Open Data (World Bank, Open Library) | 24–72 hours | URL + params |
| Weather | 10–30 minutes | city/lat-lng + unit |
| News | 5–15 minutes | query + source |
| Sports standings | 60 minutes | league + season |
| QR / Dictionary | Indefinitely (static output) | input string |

---

## Common Pitfalls

- **Embedding API keys in frontend code.** A key in JavaScript source or a mobile binary is a public key. Always proxy through your backend or use environment variables with a server-side function. Rotate any key that has been committed to a public repo.

- **Ignoring rate limit headers.** Free APIs return `X-RateLimit-Remaining` and `Retry-After` headers. Ignoring them leads to cascading 429s that take down a feature. Implement exponential backoff and surface quota exhaustion as a specific error type, not a generic 5xx.

- **Fetching on every request instead of caching.** A weather API returning the same data 500 times per minute for the same city wastes quota. Introduce a short TTL cache (Redis, in-memory, or even a simple file cache) from day one.

- **Using unofficial/undocumented APIs in production.** The ESPN API and NBA `stats.nba.com` endpoints are not officially documented. They change without notice and have blocked bots in the past. Use them for prototypes, not production SLAs.

- **Assuming free tiers are permanent.** OpenAI has changed and removed free tiers multiple times. Build a thin abstraction layer (an interface/adapter) around external AI APIs so you can swap providers without rewriting business logic.

---

## Exercises

1. **Easy — Rate Limit Awareness:** Pick OpenWeatherMap. Fetch current weather for five cities in a loop. Add logic to read the `X-RateLimit-Remaining` response header and pause if it drops below 10. Print remaining quota after each call.

2. **Medium — Data Aggregation Pipeline:** Build a Python script that fetches today's top 5 headlines from NewsAPI, passes each headline to the HuggingFace zero-shot classifier to label it as "politics", "sports", "technology", or "other", and outputs a sorted summary. Handle rate limits for both APIs independently.

3. **Hard — Abstracted Weather Service:** Design a `WeatherProvider` interface with a single method `get_current(city: str) -> WeatherReading`. Implement it for both OpenWeatherMap and WeatherAPI.com. Write a factory that selects the provider based on an environment variable. Add a Redis-backed cache layer that is shared between both implementations. Benchmark cache hit vs. miss latency.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **Free tier** | Unlimited usage at no cost | A capped usage band that triggers billing or blocks when exceeded |
| **Rate limit** | A hard wall that stops all requests | A per-window counter; resets on a rolling or fixed window; can be per-key, per-IP, or both |
| **API key** | A password | A non-secret identifier for quota tracking; it IS secret, but it does not cryptographically authenticate you the way OAuth does |
| **Quota** | Daily request count | Any combination of requests, data volume, compute units, or tokens that the vendor measures |
| **429 Too Many Requests** | "Try again later" | The server is enforcing your rate limit; `Retry-After` header tells you exactly when to retry |
| **Unofficial API** | A hidden gem | An undocumented internal API that the vendor did not intend for external use and may block or change at any time |
| **Open Data** | Free as in free beer | Free as in freedom — openly licensed data that may still have attribution requirements |

---

## Further Reading

- [Public APIs GitHub Repository](https://github.com/public-apis/public-apis) — Community-maintained list of 1,400+ free APIs with auth type, CORS support, and HTTPS status.
- [OpenWeatherMap API Docs](https://openweathermap.org/api/one-call-3) — OneCall 3.0 reference; covers how to combine current, forecast, and historical in a single request.
- [HuggingFace Inference API Documentation](https://huggingface.co/docs/api-inference/index) — Explains model selection, token limits, and the difference between hosted inference and serverless endpoints.
- [The Guardian Open Platform](https://open-platform.theguardian.com/documentation/) — One of the most generous news APIs; full-text content, tag taxonomy, and section filtering documented here.
- [NASA APIs Portal](https://api.nasa.gov/) — Central registry for all NASA public APIs, including APOD, Mars Rover Photos, DONKI space weather events, and EONET (Earth Observatory Natural Event Tracker).
