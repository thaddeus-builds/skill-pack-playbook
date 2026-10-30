# Read-back prompt (after every send, a separate read-only run)

Run: `<bridge_command> -p "<prompt below>" --allowedTools mcp__plugin_openmax-channel_openmax__comm </dev/null`

The prompt comes **before** `--allowedTools` (that flag takes every word after it as a tool name), the tool is named in full (a bare `comm` is refused as not granted), and `</dev/null` stops `claude -p` waiting for input.

```
Read message <sent_id> of conversation <conversation_id> with the comm tool
(getMessage). Do NOT send anything. Print its id, sender and its full text exactly.
```

Compare the text with what was meant to be sent. Equal: tell the owner it was sent. Empty or different: resend once with `send.md` and say so; if the second read-back fails too, stop and tell the owner.
