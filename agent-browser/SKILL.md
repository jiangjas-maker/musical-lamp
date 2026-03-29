---
name: agent-browser
description: >
  Headless browser automation for AI agents using the agent-browser CLI.
  Use this skill whenever you need to interact with live web pages — browsing URLs,
  reading page content, clicking buttons, filling forms, taking screenshots, scraping data,
  or verifying web UI behavior. Triggers on: "open this website", "browse to", "check this page",
  "scrape", "screenshot this URL", "fill out the form", "click the button on",
  "what does this webpage say", "log into", "interact with this site", "web automation",
  "test this website", "read this web page", or any task requiring live browser interaction
  with a real URL. Also use when the user provides a URL and wants information extracted from it,
  or when you need to verify something on a live website. Prefer this over writing raw Playwright
  scripts — agent-browser is a single CLI command per action, designed for step-by-step AI reasoning.
---

# Browser Automation with agent-browser

## Local Environment Setup (MUST READ FIRST)

**Chromium is pre-installed on this machine.** Every command MUST set the executable path.
Use **forward slashes** on Windows to avoid path escaping issues:

**Node.js v22 must be in PATH** — the daemon hangs under Node v25. Use nvm to ensure v22:

```bash
set "PATH=C:\Users\hanzhi.jiang\AppData\Local\nvm\v22.22.1;C:\Users\hanzhi.jiang\AppData\Roaming\npm;%PATH%" && set "AGENT_BROWSER_EXECUTABLE_PATH=D:/chrome-win/chrome-win/chrome.exe" && agent-browser <command>
```

Shorter form if Node v22 is already the default in PATH:
```bash
set "AGENT_BROWSER_EXECUTABLE_PATH=D:/chrome-win/chrome-win/chrome.exe" && agent-browser <command>
```

Chain multiple commands after a single `set` block:
```bash
set "PATH=C:\Users\hanzhi.jiang\AppData\Local\nvm\v22.22.1;C:\Users\hanzhi.jiang\AppData\Roaming\npm;%PATH%" && set "AGENT_BROWSER_EXECUTABLE_PATH=D:/chrome-win/chrome-win/chrome.exe" && agent-browser open https://example.com && agent-browser snapshot -i --json
```

Always use `agent-browser` directly — never `npx agent-browser`. The direct binary uses the fast Rust client.

## Core Workflow

Every browser automation follows this pattern:

1. **Navigate**: `agent-browser open <url>`
2. **Snapshot**: `agent-browser snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs

```bash
agent-browser open https://example.com/form
agent-browser snapshot -i
# Output: @e1 [input type="email"], @e2 [input type="password"], @e3 [button] "Submit"

agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "password123"
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i  # Check result
```

## Command Chaining

Commands can be chained with `&&` in a single shell invocation. The browser persists between commands via a background daemon, so chaining is safe and more efficient than separate calls.

```bash
# Chain open + wait + snapshot in one call
agent-browser open https://example.com && agent-browser wait --load networkidle && agent-browser snapshot -i

# Chain multiple interactions
agent-browser fill @e1 "user@example.com" && agent-browser fill @e2 "password123" && agent-browser click @e3

# Navigate and capture
agent-browser open https://example.com && agent-browser wait --load networkidle && agent-browser screenshot page.png
```

**When to chain:** Use `&&` when you don't need to read the output of an intermediate command before proceeding (e.g., open + wait + screenshot). Run commands separately when you need to parse the output first (e.g., snapshot to discover refs, then interact using those refs).

## Essential Commands

```bash
# Navigation
agent-browser open <url>              # Navigate (aliases: goto, navigate)
agent-browser close                   # Close browser

# Snapshot
agent-browser snapshot -i             # Interactive elements with refs (recommended)
agent-browser snapshot -i -C          # Include cursor-interactive elements (divs with onclick, cursor:pointer)
agent-browser snapshot -s "#selector" # Scope to CSS selector

# Interaction (use @refs from snapshot)
agent-browser click @e1               # Click element
agent-browser click @e1 --new-tab     # Click and open in new tab
agent-browser fill @e2 "text"         # Clear and type text
agent-browser type @e2 "text"         # Type without clearing
agent-browser select @e1 "option"     # Select dropdown option
agent-browser check @e1               # Check checkbox
agent-browser press Enter             # Press key
agent-browser keyboard type "text"    # Type at current focus (no selector)
agent-browser keyboard inserttext "text"  # Insert without key events
agent-browser scroll down 500         # Scroll page
agent-browser scroll down 500 --selector "div.content"  # Scroll within a specific container

# Get information
agent-browser get text @e1            # Get element text
agent-browser get url                 # Get current URL
agent-browser get title               # Get page title

# Wait
agent-browser wait @e1                # Wait for element
agent-browser wait --load networkidle # Wait for network idle
agent-browser wait --url "**/page"    # Wait for URL pattern
agent-browser wait 2000               # Wait milliseconds

# Downloads
agent-browser download @e1 ./file.pdf          # Click element to trigger download
agent-browser wait --download ./output.zip     # Wait for any download to complete
agent-browser --download-path ./downloads open <url>  # Set default download directory

# Capture
agent-browser screenshot              # Screenshot to temp dir
agent-browser screenshot --full       # Full page screenshot
agent-browser screenshot --annotate   # Annotated screenshot with numbered element labels
agent-browser pdf output.pdf          # Save as PDF

# Diff (compare page states)
agent-browser diff snapshot                          # Compare current vs last snapshot
agent-browser diff snapshot --baseline before.txt    # Compare current vs saved file
agent-browser diff screenshot --baseline before.png  # Visual pixel diff
agent-browser diff url <url1> <url2>                 # Compare two pages
agent-browser diff url <url1> <url2> --wait-until networkidle  # Custom wait strategy
agent-browser diff url <url1> <url2> --selector "#main"  # Scope to element
```

## Common Patterns

### Form Submission

```bash
agent-browser open https://example.com/signup
agent-browser snapshot -i
agent-browser fill @e1 "Jane Doe"
agent-browser fill @e2 "jane@example.com"
agent-browser select @e3 "California"
agent-browser check @e4
agent-browser click @e5
agent-browser wait --load networkidle
```

### Authentication with Auth Vault (Recommended)

```bash
# Save credentials once (encrypted with AGENT_BROWSER_ENCRYPTION_KEY)
# Recommended: pipe password via stdin to avoid shell history exposure
echo "pass" | agent-browser auth save github --url https://github.com/login --username user --password-stdin

# Login using saved profile (LLM never sees password)
agent-browser auth login github

# List/show/delete profiles
agent-browser auth list
agent-browser auth show github
agent-browser auth delete github
```

### Authentication with State Persistence

```bash
# Login once and save state
agent-browser open https://app.example.com/login
agent-browser snapshot -i
agent-browser fill @e1 "$USERNAME"
agent-browser fill @e2 "$PASSWORD"
agent-browser click @e3
agent-browser wait --url "**/dashboard"
agent-browser state save auth.json

# Reuse in future sessions
agent-browser state load auth.json
agent-browser open https://app.example.com/dashboard
```

### Session Persistence

```bash
# Auto-save/restore cookies and localStorage across browser restarts
agent-browser --session-name myapp open https://app.example.com/login
# ... login flow ...
agent-browser close  # State auto-saved to ~/.agent-browser/sessions/

# Next time, state is auto-loaded
agent-browser --session-name myapp open https://app.example.com/dashboard

# Encrypt state at rest
export AGENT_BROWSER_ENCRYPTION_KEY=$(openssl rand -hex 32)
agent-browser --session-name secure open https://app.example.com

# Manage saved states
agent-browser state list
agent-browser state show myapp-default.json
agent-browser state clear myapp
agent-browser state clean --older-than 7
```

### Data Extraction

```bash
agent-browser open https://example.com/products
agent-browser snapshot -i
agent-browser get text @e5           # Get specific element text
agent-browser get text body > page.txt  # Get all page text

# JSON output for parsing
agent-browser snapshot -i --json
agent-browser get text @e1 --json
```

### Parallel Sessions

```bash
agent-browser --session site1 open https://site-a.com
agent-browser --session site2 open https://site-b.com

agent-browser --session site1 snapshot -i
agent-browser --session site2 snapshot -i

agent-browser session list
```

### Connect to Existing Chrome

```bash
# Auto-discover running Chrome with remote debugging enabled
agent-browser --auto-connect open https://example.com
agent-browser --auto-connect snapshot

# Or with explicit CDP port
agent-browser --cdp 9222 snapshot
```

### Color Scheme (Dark Mode)

```bash
agent-browser --color-scheme dark open https://example.com
# Or via environment variable
AGENT_BROWSER_COLOR_SCHEME=dark agent-browser open https://example.com
# Or set during session
agent-browser set media dark
```

### Visual Browser (Debugging)

```bash
agent-browser --headed open https://example.com
agent-browser highlight @e1          # Highlight element
agent-browser record start demo.webm # Record session
agent-browser profiler start         # Start Chrome DevTools profiling
agent-browser profiler stop trace.json # Stop and save profile
```

### Local Files (PDFs, HTML)

```bash
agent-browser --allow-file-access open file:///path/to/document.pdf
agent-browser --allow-file-access open file:///path/to/page.html
agent-browser screenshot output.png
```

## Security

All security features are opt-in.

### Content Boundaries (Recommended for AI Agents)

```bash
export AGENT_BROWSER_CONTENT_BOUNDARIES=1
agent-browser snapshot
# Output wrapped in boundary markers to distinguish tool output from untrusted content
```

### Domain Allowlist

```bash
export AGENT_BROWSER_ALLOWED_DOMAINS="example.com,*.example.com"
agent-browser open https://example.com        # OK
agent-browser open https://malicious.com       # Blocked
```

### Action Policy

```bash
export AGENT_BROWSER_ACTION_POLICY=./policy.json
# policy.json: {"default": "deny", "allow": ["navigate", "snapshot", "click", "scroll", "wait", "get"]}
```

### Output Limits

```bash
export AGENT_BROWSER_MAX_OUTPUT=50000
```

## Diffing (Verifying Changes)

Use `diff snapshot` after performing an action to verify it had the intended effect:

```bash
agent-browser snapshot -i          # Take baseline snapshot
agent-browser click @e2            # Perform action
agent-browser diff snapshot        # See what changed

# Visual regression testing
agent-browser screenshot baseline.png
# ... time passes ...
agent-browser diff screenshot --baseline baseline.png

# Compare two URLs
agent-browser diff url https://staging.example.com https://prod.example.com --screenshot
```

## Timeouts and Slow Pages

Default Playwright timeout is 25 seconds. Override with `AGENT_BROWSER_DEFAULT_TIMEOUT` (ms).
For slow pages, use explicit waits:

```bash
agent-browser wait --load networkidle       # Wait for network to settle
agent-browser wait "#content"               # Wait for specific element
agent-browser wait --fn "window.ready"      # Wait for JS condition
agent-browser wait 5000                     # Fixed duration (last resort)
```

## Session Management and Cleanup

Always use named sessions for concurrent work and close when done:

```bash
agent-browser --session agent1 open site-a.com
agent-browser --session agent1 close   # Always clean up
```

## Ref Lifecycle (Important)

Refs (`@e1`, `@e2`, etc.) are invalidated when the page changes. Always re-snapshot after:
- Clicking links/buttons that navigate
- Form submissions
- Dynamic content loading (dropdowns, modals)

## Annotated Screenshots (Vision Mode)

Use `--annotate` for screenshots with numbered labels on interactive elements.
Each label `[N]` maps to ref `@eN`. Also caches refs for immediate interaction.

```bash
agent-browser screenshot --annotate
# Output: [1] @e1 button "Submit", [2] @e2 link "Home", ...
agent-browser click @e2  # Use ref directly
```

## Semantic Locators (Alternative to Refs)

```bash
agent-browser find text "Sign In" click
agent-browser find label "Email" fill "user@test.com"
agent-browser find role button click --name "Submit"
agent-browser find placeholder "Search" type "query"
agent-browser find testid "submit-btn" click
```

## JavaScript Evaluation (eval)

**Shell quoting can corrupt complex expressions** — use `--stdin` or `-b`:

```bash
# Simple expressions
agent-browser eval 'document.title'

# Complex JS: use --stdin with heredoc (RECOMMENDED)
agent-browser eval --stdin <<'EVALEOF'
JSON.stringify(
  Array.from(document.querySelectorAll("img"))
    .filter(i => !i.alt)
    .map(i => ({ src: i.src.split("/").pop(), width: i.width }))
)
EVALEOF

# Or base64 encoding
agent-browser eval -b "$(echo -n 'Array.from(document.querySelectorAll("a")).map(a => a.href)' | base64)"
```

## Configuration File

Create `agent-browser.json` for persistent settings:

```json
{
  "headed": true,
  "proxy": "http://localhost:8080",
  "profile": "./browser-data"
}
```

Priority: `~/.agent-browser/config.json` < `./agent-browser.json` < env vars < CLI flags.

## Experimental: Native Mode

```bash
agent-browser --native open example.com
# Or: export AGENT_BROWSER_NATIVE=1
```

Native Rust daemon communicates with Chrome directly via CDP, bypassing Node.js/Playwright.

## Browser Engine Selection

```bash
agent-browser --engine lightpanda open example.com  # 10x faster, 10x less memory
# Supported: chrome (default), lightpanda
```

## Deep-Dive Documentation

| Reference | When to Use |
|-----------|-------------|
| [references/commands.md](references/commands.md) | Full command reference with all options |
| [references/snapshot-refs.md](references/snapshot-refs.md) | Ref lifecycle, invalidation rules, troubleshooting |
| [references/session-management.md](references/session-management.md) | Parallel sessions, state persistence, concurrent scraping |
| [references/authentication.md](references/authentication.md) | Login flows, OAuth, 2FA handling, state reuse |
| [references/video-recording.md](references/video-recording.md) | Recording workflows for debugging and documentation |
| [references/profiling.md](references/profiling.md) | Chrome DevTools profiling for performance analysis |
| [references/proxy-support.md](references/proxy-support.md) | Proxy configuration, geo-testing, rotating proxies |

## Ready-to-Use Templates

| Template | Description |
|----------|-------------|
| [templates/form-automation.sh](templates/form-automation.sh) | Form filling with validation |
| [templates/authenticated-session.sh](templates/authenticated-session.sh) | Login once, reuse state |
| [templates/capture-workflow.sh](templates/capture-workflow.sh) | Content extraction with screenshots |
