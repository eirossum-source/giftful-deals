# Codebase Security & Quality Review

**Scope:** `scraper/*.py` (all 10 modules) + `.github/workflows/run_deals.yml` + `scraper/requirements.txt`
**Date:** 2026-05-05
**Method:** Manual file-by-file read. Every finding cites a file path and was verified by reading the source — no agent-generated findings included.

## Summary
- **HIGH: 2**
- **MEDIUM: 5**
- **LOW: 4**
- **Categories explicitly clean (no findings):** HTML/XSS injection (every interpolation in `html_builder.py` and `emailer.py` already wraps with `html.escape()`), email header injection, secret logging, subprocess/shell execution, `eval`/`pickle`/`yaml.load`, mutable dataclass defaults (`filter.py` uses `field(default_factory=list)`), bare `except:` clauses, fixture-path portability (`conftest.py` uses `Path(__file__).parent`), `.gitignore` correctly excludes `errors.log`.

## Findings

### F-01 — Non-atomic JSON state writes can corrupt inventory and review log
**Severity:** HIGH
**Category:** bug
**Files:**
- `scraper/inventory.py:66` — `p.write_text(json.dumps(state, ...))`
- `scraper/main.py:354` — `output_path.write_text(html, ...)` for `docs/index.html`
- `scraper/main.py:360-370` — `review_log_path.write_text(...)` for `state/review_log.json`

**Description:** All three files are written with `Path.write_text(...)`, which truncates the destination and writes in a single non-atomic call. If the GitHub Actions runner is killed mid-write (cancel button, 6h timeout, OOM), the destination is left truncated or empty.

**Impact:** A truncated `state/inventory.json` causes `load_state` to fall back to `{"items": {}}` on the next run, which means **every in-stock item triggers a spurious BACK_IN_STOCK alert** and all sold-out history is lost. A corrupted `docs/index.html` ships an empty page to GitHub Pages until the next successful run.

**Fix:** Add a small helper:
```python
def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
```
Use it in `inventory.save_state`, the `output_path.write_text` call, and the `review_log_path.write_text` call.
**Auto-fixable:** yes
**Reason:** Single-helper change applied at three call sites, no design decisions, behavior-preserving.

---

### F-02 — Retailer HTTP fetches have no response-size cap
**Severity:** HIGH
**Category:** security
**Files:**
- `scraper/price_checker.py:348` — `resp = session.get(url, headers=headers, timeout=20)` followed by `resp.text` at line 373
- `scraper/coupon_checker.py:250` — `resp = session.get(url, headers=headers, timeout=20)` followed by `resp.text` at line 262

**Description:** Both fetch wrappers read the full response body into memory via `resp.text`. There is no `stream=True`, no `Content-Length` check, no byte cap. A retailer (or an upstream redirect target) returning a multi-GB body will OOM the GitHub Actions runner.

**Impact:** A single hostile or misconfigured retailer URL DoS's the entire weekly pipeline. Recovery requires manually killing the workflow.

**Fix:** Switch to streaming with a byte cap:
```python
with session.get(url, headers=headers, timeout=20, stream=True) as resp:
    body = resp.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(body) > MAX_BYTES:
        error_log.error(f"oversized response from {url}")
        return None
    html = body.decode(resp.encoding or "utf-8", errors="replace")
```
Set `MAX_BYTES = 5_000_000` (5MB — generous for a product page).
**Auto-fixable:** yes
**Reason:** Mechanical refactor at two known call sites, identical pattern.

---

### F-03 — SSRF: scraped URLs flow into HTTP fetch with no scheme/host guard
**Severity:** MEDIUM
**Category:** security
**Files:**
- `scraper/giftful.py:232` — `resp = session.head(url, allow_redirects=True, timeout=15)` (no scheme allowlist, unbounded redirects)
- `scraper/price_checker.py:293, 348` — `page.goto(url, ...)` and `session.get(url, ...)` accept whatever resolved URL came from giftful.py
- `scraper/coupon_checker.py:509, 518, 527` — fetches `couponfollow.com`/`dealspotr.com`/`retailmenot.com` URLs assembled from a domain slug

**Description:** URLs originate from the user's own Giftful profile (modal "View online" links), then unwrapped via `resolve_redirect` and re-fetched downstream. There is no scheme allowlist (`file://`, `gopher://`, `ftp://` would all be followed by some clients) and no block on RFC1918/loopback/link-local addresses. The redirect-following HEAD in `giftful.py:232` will chase any number of hops to any final destination.

**Impact:** Limited by threat model — only the user can add items to their own Giftful wishlist, so the realistic attack surface is (a) Giftful itself being compromised, or (b) an affiliate redirector being hijacked. On GitHub-hosted runners IMDS isn't directly exposed, so cloud-metadata theft is not on the table — but the runner can still be coerced into reaching arbitrary internal services. On private/self-hosted runners, this is exploitable to reach internal infra.

**Fix:**
1. In `giftful.resolve_redirect`, validate `urlparse(final_url).scheme in ("http", "https")` and reject if not.
2. Optionally check the final hostname does not resolve to an RFC1918/loopback/link-local IP.
3. Cap the redirect chain (`session.head(..., allow_redirects=False)` and follow manually with hops ≤ 5).

**Auto-fixable:** no
**Reason:** Choosing the right validation point (caller vs fetch wrapper) and how strict to be on internal IPs is a design call. The mechanical part (scheme allowlist + hop cap) is auto-fixable; the IP allowlist needs review.

---

### F-04 — Naive datetime in main.py masks DST bugs and silently relies on UTC runners
**Severity:** MEDIUM
**Category:** bug
**File:** `scraper/main.py:135`
```python
now = now or datetime.now(timezone.utc).replace(tzinfo=None)
```
**Description:** The orchestrator constructs a tz-aware UTC `datetime` and then deliberately strips the tzinfo, producing a naive datetime. This `now` is later passed into `html_builder.render` (line 352) and `emailer.send` (line 373). When `html_builder` localizes to ET via `ZoneInfo("America/New_York")`, it must either re-attach UTC or treat the naive value as system-local — both fragile. Works today only because GitHub runners are UTC.

**Impact:** Local dev runs with a non-UTC system clock display timestamps off by the local-vs-UTC offset. A future runner-image change could flip this silently.

**Fix:** Drop the `.replace(tzinfo=None)`. Keep `now` tz-aware throughout; let consumers convert.
**Auto-fixable:** yes
**Reason:** One-line change, downstream consumers already handle aware datetimes.

---

### F-05 — Broad `except Exception` per item hides real bugs
**Severity:** MEDIUM
**Category:** quality
**File:** `scraper/main.py:270, 349`
```python
except Exception as exc:
    log.error(f"{item.name} ({store.url}): {exc}")
```
**Description:** Both per-item processing branches catch every exception and continue. A `KeyError` / `AttributeError` / `TypeError` from a regression in `filter.py` or `validator.py` is silently swallowed and only manifests as "0 deals this week" with cryptic log lines.

**Impact:** Real defects go undetected for at least a week per regression.

**Fix:** Distinguish transient errors from programmer errors:
```python
except (requests.RequestException, playwright.async_api.TimeoutError, OSError) as exc:
    log.error(f"{item.name} ({store.url}): {exc}")
```
Let `AttributeError`/`TypeError`/`KeyError` propagate.

**Auto-fixable:** no
**Reason:** Requires judgment on which exception classes are "transient" vs "regression"; current behavior is intentional defensive coding that may be load-bearing for retailer-side flakiness.

---

### F-06 — Unbounded redirect chain in `resolve_redirect`
**Severity:** MEDIUM
**Category:** security
**File:** `scraper/giftful.py:232`
```python
resp = session.head(url, allow_redirects=True, timeout=15)
```
**Description:** No `max_redirects` configured on the session; `requests` defaults to 30 hops. Combined with F-03, an attacker who controls any link in the redirect chain can pivot to any URL.

**Impact:** Pairs with F-03 to broaden the SSRF surface. On its own, low impact.

**Fix:** Set `session.max_redirects = 5` before this call (or on the shared session in `main.py`).

**Auto-fixable:** yes
**Reason:** One-line bound is safe and behavior-preserving for normal traffic.

---

### F-07 — Dependencies in `requirements.txt` are fully unpinned
**Severity:** MEDIUM
**Category:** quality
**File:** `scraper/requirements.txt`
```
playwright
requests
beautifulsoup4
lxml
resend
python-dateutil
```
**Description:** No version pins. The CI workflow caches by file hash, but the file's hash never changes, so each weekly run can resolve to a different transitive set if PyPI publishes new majors.

**Impact:** Reproducibility hole; a transitive break only surfaces during the weekly cron. Supply-chain hardening fits here too.

**Fix:** Pin to current resolved versions:
```bash
.venv/bin/pip freeze | grep -iE "^(playwright|requests|beautifulsoup4|lxml|resend|python-dateutil|certifi|urllib3|charset-normalizer|idna)==" > scraper/requirements.txt
```
Or move to a lockfile (`pip-tools`).

**Auto-fixable:** yes
**Reason:** Mechanical regeneration from current venv.

---

### F-08 — `error_log` writes full URLs (query strings included) to disk
**Severity:** LOW
**Category:** security
**File:** `scraper/error_log.py:12-17`

**Description:** `ErrorLog.error()` writes the raw `msg` — which throughout the codebase includes full URLs (e.g. `f"price fetch failed for {url}: {exc}"` in `price_checker.py:350`). Affiliate/tracking query parameters and any session-bound tokens in the URL end up in `errors.log`. The file is `.gitignore`d (verified) and truncated per-run (`main.py:147`), so it never reaches the repo. Today nothing prints the file's contents.

**Impact:** Bounded — no exposure today. Becomes a leak if (a) the workflow ever uploads `errors.log` as an artifact, or (b) the file is printed during a debug run.

**Fix:** In `error_log.py`, redact query strings before writing:
```python
import re
_URL_QS_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
def _redact(msg: str) -> str:
    return _URL_QS_RE.sub(r"\1?[redacted]", msg)
```

**Auto-fixable:** yes
**Reason:** Self-contained, behavior-preserving.

---

### F-09 — Identity-match thresholds are bare literals
**Severity:** LOW
**Category:** quality
**File:** `scraper/validator.py:225`
```python
matches = best >= 0.5 or prefix_score >= 0.67
```
**Description:** Two thresholds (`0.5`, `0.67`) inline; tuning requires hunting through the file.

**Impact:** Maintainability only.

**Fix:** Hoist to module constants:
```python
_IDENTITY_OVERLAP_THRESHOLD = 0.5
_IDENTITY_PREFIX_THRESHOLD = 0.67
```

**Auto-fixable:** yes
**Reason:** Cosmetic, deterministic.

---

### F-10 — Hot-path regexes recompiled inside loops
**Severity:** LOW
**Category:** quality
**File:** `scraper/coupon_checker.py:135, 155, 162`

**Description:** Patterns like `re.compile(r"(^|\s)(code|coupon-code)(\s|$)", re.I)` are constructed on every card. Python's internal `re` cache (LRU 512) absorbs the cost in practice, but module-level compilation is idiomatic and self-documenting.

**Impact:** Negligible.

**Fix:** Hoist to module-level `_CODE_CLASS_RE = re.compile(...)`.

**Auto-fixable:** yes
**Reason:** Mechanical, no behavior change.

---

### F-11 — Identity-retry path re-derives inventory key from raw URL
**Severity:** LOW
**Category:** bug
**File:** `scraper/main.py:101-110`
```python
prev = (prev_state or {}).get("items", {}).get(normalize_url(url)) or {}
```
**Description:** Works correctly today — `normalize_url` is idempotent, so calling it on the raw URL passed in produces the same key as the loop's `norm = normalize_url(store.url)`. But the lookup re-derives the key from the *raw* `url` parameter rather than reusing the already-computed `norm`, so any future change to `normalize_url` semantics could split the two derivation sites.

**Impact:** Latent — risks emerging only if `normalize_url` evolves.

**Fix:** Hoist `norm = normalize_url(store.url)` once at the top of each loop iteration and pass `norm` into `_resolve_identity`.

**Auto-fixable:** no
**Reason:** Function-signature change touching two call sites; small but worth a deliberate review.

---

## Auto-Fix Classification

| ID | Severity | Category | Auto-fixable | One-line scope |
|----|----------|----------|--------------|----------------|
| F-01 | HIGH | bug | **yes** | atomic-write helper at 3 call sites |
| F-02 | HIGH | security | **yes** | streaming + byte cap at 2 call sites |
| F-03 | MEDIUM | security | no | needs design call on internal-IP policy |
| F-04 | MEDIUM | bug | **yes** | drop `.replace(tzinfo=None)` |
| F-05 | MEDIUM | quality | no | needs judgment on transient vs bug |
| F-06 | MEDIUM | security | **yes** | `session.max_redirects = 5` |
| F-07 | MEDIUM | quality | **yes** | `pip freeze` regen |
| F-08 | LOW | security | **yes** | redact query strings in `error_log.py` |
| F-09 | LOW | quality | **yes** | hoist 2 thresholds to constants |
| F-10 | LOW | quality | **yes** | hoist regexes to module level |
| F-11 | LOW | bug | no | small signature change |

**Auto-fixable count:** 8/11
**Manual-only count:** 3/11 (F-03, F-05, F-11)

## Workflow & False-Positive Safety

This section answers a separate question from "is it auto-fixable": does applying the fix risk **breaking the weekly GitHub Actions run**, or **producing false-positive deals, promos, or BACK_IN_STOCK alerts**?

| ID | Workflow break risk | False-positive risk (deals/promos/BIS) | Verdict |
|----|---------------------|----------------------------------------|---------|
| F-01 | None | **Reduces** existing risk (truncated state can cause spurious BIS today) | ✅ Apply |
| F-02 | Low (5MB cap is generous; >cap → false negative, not false positive) | None | ✅ Apply |
| F-03 | Low with scheme-allowlist only; higher if RFC1918 block is added | None (blocked URLs are dropped, not fabricated) | ⚠ Apply scheme-allowlist only |
| F-04 | None — verified `html_builder.py:43-45` already handles both naive and aware datetimes | None | ✅ Apply |
| F-05 | **HIGH** — would kill the weekly run on any upstream regression that today is logged-and-skipped | Indirect: a crashed run leaves stale state, causing BIS perturbation on the next successful run | ❌ Skip as written |
| F-06 | Very low at cap=8; cap=5 risks false negatives on legit affiliate chains | Edge: if the cap shortens a redirect chain, the inventory key shifts → one-time spurious BIS on the next run | ✅ Apply, **set cap to 8 (not 5)** |
| F-07 | None today; reduces future breakage from upstream releases | None | ✅ Apply |
| F-08 | None (logging only) | None | ✅ Apply |
| F-09 | None (pure refactor, same numeric values) | None | ✅ Apply |
| F-10 | None (pure refactor, identical patterns) | None | ✅ Apply |
| F-11 | None (`normalize_url` is idempotent, key derivation unchanged) | None | ✅ Apply |

### Caveats and amendments

- **F-03 — apply scheme-allowlist only.** Reject any URL whose final scheme isn't `http` / `https`. Skip the RFC1918/loopback IP block unless this project ever moves to a self-hosted runner; on GitHub-hosted runners it adds complexity without meaningful threat reduction.
- **F-05 — skip the as-written fix.** Substitute a traceback-logging variant that preserves the broad `except Exception` so the run still survives upstream regressions:
  ```python
  except Exception as exc:
      log.error(f"{item.name} ({store.url}): {exc}\n{traceback.format_exc()}")
  ```
  This makes regressions visible in `errors.log` without losing weekly delivery.
- **F-06 — cap at 8, not 5.** Skimresources / Viglink chains can occasionally exceed 5 hops. A cap of 8 still blocks pathological chains while leaving slack for legit affiliate flows.

**Safe set to authorize:** F-01, F-02, F-03 (scheme-only), F-04, F-06 (cap 8), F-07, F-08, F-09, F-10, F-11.
**Skip as-written:** F-05 (or replace with the traceback variant above).

## Recommended order if fixing
1. F-01 — data loss is the highest-cost failure mode
2. F-02 — single hostile retailer DoSes the pipeline
3. F-04 — silent, easy to ship
4. F-07 — cheap reproducibility win
5. F-06 — partial mitigation of F-03 without the design call
6. F-08, F-09, F-10 — cosmetic batch
7. F-03, F-05, F-11 — when there's time to think
