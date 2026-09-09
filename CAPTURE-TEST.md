# Capture test — 8x assignment

**Author:** Zaghum Abbas (`zaghum-abbas`)  
**Project:** `naano-rebuild`  
**Date:** 2026-09-09  
**Result:** PASS

## What was verified

Automatic agent capture via Cursor project hooks:

| Piece | Path |
|---|---|
| Hook config | `.cursor/hooks.json` |
| Capture script | `.cursor/hooks/capture-agent-log.py` |
| Log output | `.agent-logs/` (tracked; not gitignored) |
| Hook runtime state | `.cursor/hooks/state/` (gitignored) |

Events: `beforeSubmitPrompt` → PROMPT entry; `afterAgentResponse` → RESPONSE entry.

## Canaries

Exact prompt used in both chats:

```
CAPTURE TEST — 8x assignment, Zaghum Abbas
```

| # | Session | Log file | PROMPT | RESPONSE |
|---|---|---|---|---|
| 1 | `7fb65208` (setup chat) | `.agent-logs/2026-09-09_15-42-49_7fb65208-f5a9-498c-98d9-a8f792e72083.md` | yes (`num=2`) | yes |
| 2 | `937f468d` (new Agent chat) | `.agent-logs/2026-09-09_15-46-00_937f468d-f272-4105-b637-7fe0a9c56d4c.md` | yes (`num=1`) | yes (this turn) |

Two different `session_id`s and two log files prove capture is **project-installed**, not session-local.

## Status

Capture is ready for the 8x assignment. Assignment work has not started.
