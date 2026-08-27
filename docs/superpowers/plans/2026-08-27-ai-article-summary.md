# AI Article Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hover an AI icon on each news row; click opens a modal that fetches the article URL, summarizes it with the project LLM, and caches the result in `sessionStorage` with a Regenerate button.

**Architecture:** New `POST api/summarize` handled by `server.py`, core logic in `scripts/summarize.py` (fetch HTML → extract text → `llm.call`). Frontend adds hover icon + modal in `index.html`, relative API path for `/dailynews/`.

**Tech Stack:** Python 3.7+ stdlib only (`urllib`, `html.parser`/`re`, `json`, `http.server`); existing `scripts/llm.py`; vanilla JS in `index.html`.

## Global Constraints

- Pure Python standard library — no pip packages.
- Use `llm.config.json` via `scripts/llm.py` (provider `api` or `claude-cli`).
- Relative API paths (`api/summarize`) for subdirectory reverse proxy.
- Session-only cache in browser; do not write summaries to `data.js` or disk.
- Chinese summary, 3–6 bullet-style sentences; not financial advice.
- Reject non-http(s) and private/link-local URLs (SSRF).

**Spec:** `docs/superpowers/specs/2026-08-27-ai-article-summary-design.md`

## File map

| File | Role |
|---|---|
| `scripts/summarize.py` | URL check, fetch, extract, LLM, `summarize(url, title=None) -> dict` |
| `scripts/test_summarize.py` | Unit tests for URL guard + HTML extract (no live LLM) |
| `server.py` | `POST` `/api/summarize` → call `summarize` |
| `index.html` | Hover icon, modal, sessionStorage, fetch |

---

### Task 1: `scripts/summarize.py` + unit tests

**Files:**
- Create: `scripts/summarize.py`
- Create: `scripts/test_summarize.py`

**Interfaces:**
- Produces: `is_safe_url(url: str) -> bool`
- Produces: `extract_text(html: str, limit: int = 12000) -> str`
- Produces: `summarize(url: str, title: str = "") -> dict` with keys `ok`, and either `summary`/`title` or `error`

- [ ] **Step 1: Write failing tests**

```python
# scripts/test_summarize.py
import unittest
import summarize

class TestSafeUrl(unittest.TestCase):
    def test_https_ok(self):
        self.assertTrue(summarize.is_safe_url("https://example.com/a"))
    def test_reject_localhost(self):
        self.assertFalse(summarize.is_safe_url("http://127.0.0.1/x"))
    def test_reject_private(self):
        self.assertFalse(summarize.is_safe_url("http://192.168.1.1/x"))
    def test_reject_file(self):
        self.assertFalse(summarize.is_safe_url("file:///etc/passwd"))

class TestExtract(unittest.TestCase):
    def test_strips_script_and_keeps_article(self):
        html = "<html><script>bad()</script><article><p>Hello world news.</p></article></html>"
        t = summarize.extract_text(html)
        self.assertIn("Hello world news", t)
        self.assertNotIn("bad", t)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — expect fail (module missing)**

Run: `cd scripts && python3 test_summarize.py -v`  
Expected: import error or attribute error

- [ ] **Step 3: Implement `scripts/summarize.py`**

Implement:
- `is_safe_url`: parse with `urllib.parse`; scheme http/https only; hostname not localhost / `*.local` / IP in private ranges (use `ipaddress` stdlib).
- `extract_text`: remove script/style/noscript via regex; prefer article/main content; strip tags; collapse whitespace; truncate to `limit`.
- `fetch_html(url)`: urllib Request with User-Agent, timeout 20, max 2MB.
- `summarize(url, title="")`: validate → fetch → extract → if len(text)<80 return error → `llm.call` with Chinese summary system prompt → `{ok:True, summary, title}`.

- [ ] **Step 4: Re-run unit tests — expect PASS**

Run: `cd scripts && python3 test_summarize.py -v`  
Expected: all OK

- [ ] **Step 5: Commit**

```bash
git add scripts/summarize.py scripts/test_summarize.py
git commit -m "feat: add article summarize backend helper"
```

---

### Task 2: Wire `POST /api/summarize` in `server.py`

**Files:**
- Modify: `server.py`

**Interfaces:**
- Consumes: `summarize.summarize(url, title) -> dict`
- Produces: HTTP JSON on `POST` path starting with `/api/summarize`

- [ ] **Step 1: Extend `do_POST`**

Parse body JSON (`Content-Length`), call summarize, return UTF-8 JSON. Ignore path query string. On exception return `{ok:false, error:str(e)}`.

```python
def _summarize(self):
    try:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        body = json.loads(raw.decode("utf-8") or "{}")
        url = (body.get("url") or "").strip()
        title = (body.get("title") or "").strip()
        sys.path.insert(0, os.path.join(HERE, "scripts"))
        import summarize as summod
        payload = summod.summarize(url, title)
        code = 200 if payload.get("ok") else 400
    except Exception as e:
        payload, code = {"ok": False, "error": str(e)}, 500
    # same JSON write pattern as _refresh
```

Route: `if self.path.split("?",1)[0].rstrip("/").endswith("/api/summarize") or ...` — prefer:

```python
path = self.path.split("?", 1)[0]
if path == "/api/summarize" or path.endswith("/api/summarize"):
    return self._summarize()
```

(Actually under SimpleHTTPRequestHandler path is always from root `/api/summarize` even behind nginx strip — keep `/api/summarize`.)

- [ ] **Step 2: Manual smoke (optional without LLM)**

`python3 -c "import sys; sys.path.insert(0,'scripts'); import summarize; print(summarize.is_safe_url('https://a.com'))"`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: expose POST /api/summarize"
```

---

### Task 3: Frontend icon + modal + session cache

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `POST api/summarize` JSON API
- Produces: UI behavior only

- [ ] **Step 1: CSS** — `.ai-btn` hidden by default, `.row:hover .ai-btn` / `:focus-within` visible; modal overlay `.sum-mask` / `.sum-box`; mobile `@media (hover:none)` always show icon.

- [ ] **Step 2: Modal + logic in `boot()`**

- Cache key: `'invnews:summary:' + url`
- `openSummary({url, titleZh, titleEn})` builds modal
- Read sessionStorage unless `force`
- In-flight Map per url
- `esc()` for all injected text
- Buttons: 重新生成 (`force:true`), 关闭; Esc / mask click closes
- Icon in each row `rmeta`: button with `✦` or similar, `type=button`, stopPropagation

- [ ] **Step 3: Manual UI check**

Run server, hover row, open modal, regenerate.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: AI summary icon and modal on news rows"
```

---

### Task 4: Deploy to pmo

**Files:** none local (rsync + restart)

- [ ] **Step 1:** rsync project to `/opt/investment-news` (preserve `llm.config.json` on server if needed — sync including config if local is source of truth)
- [ ] **Step 2:** `systemctl restart investment-news`
- [ ] **Step 3:** curl `https://pmo.atuofuture.com/dailynews/` and POST summarize smoke

---

## Spec coverage check

- Hover icon + modal → Task 3  
- sessionStorage + regenerate → Task 3  
- POST api/summarize + SSRF + extract + llm → Task 1–2  
- Relative path `/dailynews/` → Task 3 + nginx already strips prefix  
- No data.js persistence → respected  
- Error paths → Task 1 return errors + Task 3 display  

## Execution

User requested immediate implementation — execute inline in this session (executing-plans style), task-by-task.
