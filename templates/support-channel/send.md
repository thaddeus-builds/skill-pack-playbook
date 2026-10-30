# Send prompt

Run: `<bridge_command> -p "<prompt below>" --allowedTools mcp__plugin_openmax-channel_openmax__comm_send </dev/null`

The prompt comes **before** `--allowedTools` (that flag takes every word after it as a tool name), the tool is named in full (a bare `comm_send` is refused as not granted), and `</dev/null` stops `claude -p` waiting for input.

```
Call comm_send once with endpoint "<conversation_id>" and content set to this single
plain string (the @names are plain text, no mention objects, no content array):

<@name text of the message>

Do nothing else. Answer with the id comm_send returned.
```

Use an ASCII `@name`: a full-width character is not a mention. Keep the id it returned for the read-back. Over REST the body is typed (`type`, `content.body.text`), not a string. Never use `comm` with `method: send`. Then run the read-back; do not report "sent" before it.
