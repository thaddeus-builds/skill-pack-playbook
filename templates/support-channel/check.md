# Read-only check prompt (every 10 minutes)

Run: `<bridge_command> -p --allowedTools comm "<prompt below>"`

```
Read the conversation <conversation_id> with the comm tool (getMessages). Do NOT send
anything. The last message id I have seen is <last_seen_id>.
List only messages with a newer id: id, sender, time, text. If there are none, answer
exactly one line: "nothing new since <last_seen_id>". End with "newest id: <id>".
```

Then write the newest id to `last_seen_file`. Nothing new is one line to the owner.
