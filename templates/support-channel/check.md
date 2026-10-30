# Read-only check prompt (every 10 minutes)

Run: `<bridge_command> -p "<prompt below>" --allowedTools mcp__plugin_openmax-channel_openmax__comm </dev/null`

The prompt comes **before** `--allowedTools` (that flag takes every word after it as a tool name), the tool is named in full (a bare `comm` is refused as not granted), and `</dev/null` stops `claude -p` waiting for input.

```
Read the conversation <conversation_id> with the comm tool (getMessages). Do NOT send
anything. The last message id I have seen is <last_seen_id>.
List only messages with a newer id: id, sender, time, text. If there are none, answer
exactly one line: "nothing new since <last_seen_id>". End with "newest id: <id>".
```

Then write the newest id to `last_seen_file`. Nothing new is one line to the owner.
