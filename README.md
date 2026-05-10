# Apartment scraper

Polls one or more apartment listing sites on a schedule, sends the HTML to an
LLM to extract structured availability, and pushes a phone notification the
first time a matching unit appears. State is persisted so each unit alerts
exactly once.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # edit NTFY_TOPIC to a long random string
.venv/bin/python run.py --once --no-notify   # smoke test
.venv/bin/python run.py                       # poll forever
```

Install the **ntfy** app on iOS or Android, subscribe to the same topic you
put in `.env`, and you're set. Anyone who knows the topic can publish to it,
so make it unguessable.

CLI flags:

| Flag | Meaning |
| --- | --- |
| `--once` | run a single cycle and exit (good for cron / debugging) |
| `--no-notify` | extract and log, but don't actually push — handy when iterating |
| `--config foo.yaml` | use a different config file |

## How it works

```
config.yaml ──┐
              ▼
         ┌─────────┐    fetch_html       ┌─────────┐    extract      ┌────────┐
         │  Site   │  ───────────────►   │ Fetcher │  ─────────────► │  LLM   │
         │ adapter │                     │ (http / │                 │(Google │
         │         │  ◄──── HTML ─────── │ browser)│  ◄── Unit[] ─── │ Gemma) │
         └─────────┘    narrow()         └─────────┘                 └────────┘
              │
              ▼
       Filter ──► StateStore (dedup) ──► Notifier (ntfy)
```

- **Site adapter** owns site-specific knowledge: which URL, which fetcher to
  use, optional `narrow()` to trim noise before the LLM sees the HTML.
- **Fetcher** owns the "get me the bytes" problem — UA spoofing, cookies, JS
  execution. Sites pick `"http"` (httpx) or `"browser"` (playwright).
- **LLMProvider** owns "give me a list of `Unit`s." Provider, model, and API
  key are all swappable in `config.yaml`.
- **Runner** ties them together, applies the user's bedroom/bath/price
  filter, dedups against `state.json`, and pushes via the **Notifier**.

## Project layout

```
scraper/
├── run.py                       # entry point
├── config.yaml                  # main config (env vars are interpolated via ${VAR})
├── .env                         # secrets — never commit
├── com.zwu.aptscraper.plist     # launchd agent template (macOS)
└── apt_scraper/
    ├── config.py                # YAML + env loader → typed Config
    ├── runner.py                # poll loop + per-site processing
    ├── state.py                 # JSON-backed dedup
    ├── notify.py                # ntfy push notifications
    ├── models.py                # Unit dataclass
    ├── fetchers/
    │   ├── base.py              # Fetcher Protocol
    │   ├── http.py              # httpx + realistic browser headers
    │   ├── browser.py           # playwright + lightweight stealth (Cloudflare-tier)
    │   └── stealth.py           # patchright + real Chrome + offscreen window (PerimeterX-tier)
    ├── llm/
    │   ├── base.py              # LLMProvider Protocol
    │   ├── _shared.py           # provider-agnostic helpers (prompt, JSON parse, retry)
    │   ├── google.py            # Gemini / Gemma via google-genai
    │   └── xai.py               # Grok via the OpenAI-compatible xAI endpoint
    └── sites/
        ├── base.py              # Site abstract base
        ├── _html.py             # shared HTML noise-stripping helpers
        ├── rentnema.py          # rentnema.com (http fetcher)
        ├── rentjasper.py        # rentjasper.securecafe.com (browser fetcher, CF)
        ├── modera_rincon_hill.py  # moderarinconhill.com (browser fetcher, CF)
        └── zillow.py            # zillow.com (stealth fetcher, PerimeterX)
```

## Fetcher selection

Sites declare `fetcher_kind` based on how aggressive their bot detection is:

| Kind | Backend | Use when |
| --- | --- | --- |
| `http` | httpx + realistic UA/headers | Server-rendered, no bot challenge (rentnema). |
| `browser` | playwright + Chromium, lightweight stealth | Cloudflare bot challenge or JS-rendered SPA (rentjasper, modera). Headless works. |
| `stealth` | **patchright** + real Chrome + persistent profile + offscreen window | PerimeterX/HUMAN "Press & Hold" (zillow). Headless gets caught — requires a windowed Chrome process to keep the fingerprint clean. |

The `stealth` fetcher requires Chrome (the real browser, not Chromium) installed on the machine. It launches Chrome in headed mode but parks the window at `(-32000, -32000)` so it's invisible. The browser process stays alive across all polls (one launch per `Runner`), so the dock icon shows a single persistent Chrome — not a popup-per-poll.

## Adding a new site

The whole point of the architecture: most new sites should take ~30 lines.

1. **Create `apt_scraper/sites/<yoursite>.py`** subclassing `Site`:

   ```python
   from .base import Site

   class YourSite(Site):
       name = "yoursite"
       fetcher_kind = "http"        # use "browser" if the site is JS-heavy
                                    # or hits you with a Cloudflare challenge

       def fetch_hints(self) -> dict:
           # Forwarded as kwargs to fetcher.fetch(url, **hints).
           # For browser fetcher, useful keys:
           #   wait_for: CSS selector to wait on before snapshotting
           #   wait_ms:  extra wait after networkidle (ms)
           return {}

       def narrow(self, html: str) -> str:
           # Optional. Trim the HTML to just the listings region so the LLM
           # gets a smaller, focused chunk. Keep it conservative — better to
           # send more than to accidentally cut off real units.
           return html
   ```

2. **Register it** in `apt_scraper/sites/__init__.py`:

   ```python
   if cfg.type == "yoursite":
       from .yoursite import YourSite
       return YourSite(cfg)
   ```

3. **Add it to `config.yaml`**:

   ```yaml
   sites:
     - type: rentnema
       url: https://www.rentnema.com/availabilities
     - type: yoursite
       url: https://yoursite.com/listings
   ```

The polling cadence auto-divides the daily LLM budget across all sites, so
adding more sites just slows each one down — you don't have to touch any
timing logic.

### Tips when adding a site

- **Try the http fetcher first** — server-rendered sites are the easy case.
  If you get a 403, an empty body, or a JS shell, switch to `browser`.
- **Check what the LLM sees**: run `.venv/bin/python run.py --once --no-notify` with
  log level set to DEBUG and inspect what `narrow()` returns. The shorter
  and more focused, the better the LLM's output.
- **Make `unit_id` stable.** The default prompt instructs the LLM to prefer
  the printed unit number and never embed price or date. If your site
  doesn't expose unit numbers, override the prompt or return an
  apartment-specific identifier.
- Anti-bot pages are usually best handled by the browser fetcher; for
  harder ones (Datadome, PerimeterX, aggressive Cloudflare bot management),
  swap in `playwright-stealth` or `rebrowser-playwright` inside
  `fetchers/browser.py`.
- For Cloudflare-protected pages (e.g. `*.securecafe.com`), use
  `wait_until="domcontentloaded"` rather than `networkidle` — the CF
  challenge keeps the network busy so `networkidle` never fires. Then
  combine with `wait_for=<a selector that only exists post-render>` so
  the snapshot is taken after the real content has loaded.
- The LLM call has built-in retries (4 attempts, exponential backoff) for
  transient 500/503 errors common on `gemma-4-31b-it`. If you see sustained
  failures, swap `llm.model` to `gemini-2.0-flash` or similar and update
  `daily_request_budget` to that model's free-tier cap.

## Adding a new LLM provider

1. Create `apt_scraper/llm/<provider>.py` with a class that implements
   `extract(*, site, url, html) -> ParseResult`. Look at `google.py` as
   the reference — the JSON-extraction helpers there are reusable.
2. Register it in `apt_scraper/llm/__init__.py`.
3. Switch `llm.provider` and `llm.model` in `config.yaml`. Update
   `daily_request_budget` to match the new tier.

## Adding a new notifier

`apt_scraper/notify.py` already follows a `Notifier` Protocol. Add a class
with a `send(unit)` method, register it in `make_notifier`, and switch
`notification.provider` in the config.

## Configuration reference

```yaml
llm:
  provider: google                 # google | (future) openai, anthropic, ...
  model: gemma-4-31b-it            # any model id served by the provider
  api_key: ${LLM_API_KEY}          # ${...} = env interpolation
  daily_request_budget: 1500       # provider's free-tier daily cap
  budget_safety_factor: 0.8        # leave headroom for retries

filters:
  min_bedrooms: 3                  # unit must have at least this many
  min_bathrooms: 3
  max_price_usd: null              # null = no price ceiling

notification:
  provider: ntfy
  ntfy_server: https://ntfy.sh    # self-host if you want to
  ntfy_topic: ${NTFY_TOPIC}
  ntfy_priority: 5                 # 1..5; 5 = max, vibrates phone

state:
  path: state.json                 # dedup file. Delete to re-alert everything.

logging:
  level: INFO                      # DEBUG when troubleshooting

sites:
  - type: rentnema
    url: https://www.rentnema.com/availabilities
  - type: rentjasper
    url: https://rentjasper.securecafe.com/onlineleasing/jasper-1/oleapplication.aspx?stepname=floorplan
```

Anything in `${...}` is filled from env or `.env`. Secrets belong in `.env`,
not `config.yaml`.

## Polling rate

The runner divides the effective budget (`daily_request_budget *
budget_safety_factor`) by the number of sites to compute a per-site
interval. With 1 site and a 1500 budget, that's a poll every ~72s; with
3 sites, every ~216s per site.

In practice the LLM call itself is the bottleneck: `gemma-4-31b-it` takes
~5–6 minutes per request, so the real cadence is ~10 polls/hour per site
regardless of the budget calculation. If you swap in a faster model (e.g.
`gemini-2.0-flash`) the budget calc starts mattering — be sure to update
`daily_request_budget` to that model's free-tier cap.

## Operations

### Running it on macOS with launchd (recommended)

```bash
cp com.zwu.aptscraper.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zwu.aptscraper.plist
tail -f stdout.log
```

Stop it:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.zwu.aptscraper.plist
```

The Mac must stay awake. Set Energy Saver → "Prevent automatic sleeping
when display is off", or wrap the script in `caffeinate -i`.

### Running it elsewhere

- **Linux / PC** — same idea but with systemd. A unit file with
  `ExecStart=/path/to/.venv/bin/python /path/to/run.py`, `Restart=always`,
  and you're set.
- **Cloud, free tier** — Oracle Cloud Always-Free gives you a permanent
  Ampere VM that's far more than enough for this. Fly.io free tier also
  works.

### Resetting state

```bash
rm state.json    # re-notify on the next match
```

## Adding playwright (only if a site needs it)

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

Then set `fetcher_kind = "browser"` on the site adapter that needs it. The
http-based path keeps working without playwright installed — the import is
deferred until a browser-based site actually runs.

## Files to .gitignore (already done)

- `.env` (contains the API key)
- `state.json` (changes constantly)
- `*.log`, `__pycache__/`, `.venv/`
