# MCP ChatGPT Web Server

Minimal [Model Context Protocol](https://modelcontextprotocol.io/) server that drives **ChatGPT Web** through **Playwright**, so agents in Cursor (or other MCP clients) can send prompts and read structured replies.

The server keeps a **single shared Chromium + browser context** between tool calls (serialized with a lock so only one prompt runs at a time). Each call opens a **new tab** (`BrowserContext.new_page()`), then closes it, so cookies/session stay warm without leaving stale UI state attached to one page forever.

## Requirements

- Python 3.10+
- Chromium via Playwright (`playwright install chromium`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Create `auth/storage_state.json` once by signing in with a headed browser and saving storage state (see **Session** below). The file is gitignored.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATGPT_URL` | `https://chat.openai.com` | Chat entry URL |
| `BROWSER_HEADLESS` | `false` | Run Chromium headless |
| `SESSION_PATH` | `auth/storage_state.json` | Playwright storage state path |
| `TIMEOUT` | `60` | Default tool timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |

Optional `.env` in the project root is picked up by [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Run (stdio / Cursor)

From the repository root:

```bash
python -m server.main
```

**Cursor MCP** example (adjust paths):

```json
{
  "mcpServers": {
    "chatgpt-web": {
      "command": "/absolute/path/to/mcp-chatgpt-web/.venv/bin/python",
      "args": ["-m", "server.main"],
      "cwd": "/absolute/path/to/mcp-chatgpt-web"
    }
  }
}
```

## Tool: `chatgpt_web_research`

**Arguments**

- `prompt` (string, required)
- `timeout` (integer, optional) — overrides `TIMEOUT` for that call

**Returns** (JSON object; also advertised to MCP clients via `output_schema`)

- `summary` — short preview of the reply (or `[error_code] detail` on failure)
- `full_response` — full assistant text when `status` is `ok`
- `status` — `"ok"` or `"error"`
- `execution_time` — seconds (wall clock)
- `error_code` — machine-readable code when `status` is `"error"` (e.g. `session_expired`, `timeout`, `selector_changed`); `null` when ok
- `error_detail` — full error message when `status` is `"error"`; `null` when ok

Agents should prefer branching on **`error_code`** (stable) over parsing **`summary`** (human-oriented).

Failures (login redirect, timeouts, selector drift, network) still return this shape with `status: "error"`.

## Session (one-time login)

1. Run Chromium with Playwright and open ChatGPT (headed).
2. Complete login in the browser.
3. Save storage state to `auth/storage_state.json`.

Example snippet (run from repo root with the same venv):

```python
from pathlib import Path
from playwright.sync_api import sync_playwright

path = Path("auth/storage_state.json")
path.parent.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://chat.openai.com")
    input("Log in, then press Enter here to save session…")
    context.storage_state(path=str(path))
    browser.close()
```

## Tests

```bash
pytest
```

**Unit tests** run by default (config, output model, session fingerprint logic, MCP import).

**Browser integration tests** (marked `@pytest.mark.browser`) hit the real ChatGPT UI and catch composer/selector drift early. They are skipped unless you opt in:

```bash
export RUN_BROWSER_INTEGRATION=1
# optional: export SESSION_PATH=/path/to/storage_state.json
# optional: export BROWSER_TEST_TIMEOUT=120
pytest -m browser
```

Requires `playwright install chromium` and a valid `auth/storage_state.json`. Use `pytest -m "not browser"` in CI to exclude them.

## License

MIT — see [LICENSE](LICENSE).
