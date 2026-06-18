# Dreaming Spanish Stats — MCP Server

Exposes your [Dreaming Spanish](https://app.dreaming.com) progress data as MCP
tools, so an MCP client (e.g. Claude Desktop) can answer questions like
"What's my DS progress?" or "When will I reach 300 hours?".

Self-contained — the only dependency is the official MCP SDK. All API access
uses Python's standard library.

> **Note:** This talks to an unofficial, internal Dreaming Spanish endpoint
> (`app.dreaming.com/.netlify/functions/...`). It may change or break at any time.

---

## Tools

The server provides five MCP tools:

| Tool | Description |
| --- | --- |
| `progress_summary` | Human-readable summary: total hours, streaks, pace (7/30/60-day + all-time), and milestone ETAs at the 60-day pace. |
| `progress_stats` | Structured metrics: current total hours, pace per window (min/day), streaks, active days, daily-goal hit rate, and date range. |
| `predict_milestone(target_hours, pace_window="60d")` | Predicts the date for an hours milestone. `pace_window` is one of `"7d"`, `"30d"`, `"60d"`, `"all"`. |
| `milestone_table` | All standard milestones (50/150/300/600/1000/1500 h) with ETAs under three pace scenarios (7/30/60 days). |
| `daily_data(last_n_days=30)` | Raw per-day data: date, minutes, goal reached, cumulative hours. |

All projections are simple linear extrapolations — the further out the
milestone, the less reliable the estimate.

---

## Prerequisites

- **Python 3.10 or newer** (the code uses `list[dict]` / `int | None` syntax).
- The official MCP SDK.

Install the dependency:

```bash
pip install "mcp[cli]"        # or: uv add "mcp[cli]"
```

> **Windows tip:** install into the *same* Python that your MCP client will
> launch. If `python`/`py` is ambiguous on your machine, install explicitly with
> the full path, e.g.
> `C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe -m pip install "mcp[cli]"`.

---

## Authentication token

The server reads a Bearer token from the `DS_TOKEN` environment variable. It is
**never** stored in code. How to find it:

1. Log in at [app.dreaming.com](https://app.dreaming.com).
2. Open DevTools (**F12**) → **Network** tab.
3. Reload the page.
4. Click any request to `.netlify/functions/...` and open the **Request Headers**.
5. Copy the value of `Authorization: Bearer XXXX` — only the part **after**
   `Bearer ` (the token itself).

`DS_TOKEN` accepts either the bare token or the full `Bearer XXXX` string.

---

## Run locally

```bash
# macOS / Linux
export DS_TOKEN="your_token"
python ds_mcp_server.py

# Windows PowerShell
$env:DS_TOKEN="your_token"
python ds_mcp_server.py
```

The server starts on the **stdio** transport and waits for an MCP client. (You
won't see normal output — that's expected; it communicates over stdio.) If the
token is missing or invalid, calling a tool returns a clear error.

---

## Add to Claude Desktop

Edit `claude_desktop_config.json`:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "dreaming-spanish": {
      "command": "python",
      "args": ["C:\\path\\to\\ds_mcp_server.py"],
      "env": { "DS_TOKEN": "your_token_here" }
    }
  }
}
```

Restart Claude Desktop completely (including the tray icon → Quit) so it
reconnects to the server.

> **Recommended on Windows:** use the **absolute path** to your Python
> executable for `command` instead of `"python"` or `"py"`. This guarantees the
> client launches the exact interpreter where you installed `mcp`, e.g.:
>
> ```json
> "command": "C:\\Users\\you\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
> ```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'mcp'`**
The interpreter launching the server doesn't have the MCP SDK installed. This
almost always means `command` points to a different Python than the one you ran
`pip install` with. Fix it by installing `mcp[cli]` into that exact interpreter,
or by setting `command` to its absolute path (see the tip above). To verify:

```bash
"C:\path\to\python.exe" -c "import mcp; print('mcp OK')"
```

**`HTTP 401`/`403` or "no daily data"**
The token is missing, wrong, or expired. Grab a fresh `DS_TOKEN` from the
browser (see [Authentication token](#authentication-token)).

**Changes not picked up**
Data is cached for up to 5 minutes (TTL), and Claude Desktop caches the server
connection — restart the client after config changes.
