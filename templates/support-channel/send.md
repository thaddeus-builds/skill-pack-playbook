# Send prompt

Run: `<bridge_command> -p --allowedTools comm_send "<prompt below>"`

```
Call comm_send once with endpoint "<conversation_id>" and content set to this single
plain string (the ＠names are plain text, no mention objects, no content array):

<＠name text of the message>

Do nothing else. Answer with the id comm_send returned.
```

Never use `comm` with `method: send`. Then run the read-back; do not report "sent" before it.
