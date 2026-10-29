# Send prompt

Run: `<bridge_command> -p --allowedTools comm_send "<prompt below>"`

```
Call comm_send once with endpoint "<conversation_id>" and content set to this single
plain string (the @names are plain text, no mention objects, no content array):

<@name text of the message>

Do nothing else. Answer with the id comm_send returned.
```

Use an ASCII `@name`: a full-width character is not a mention. Keep the id it returned for the read-back. Over REST the body is typed (`type`, `content.body.text`), not a string. Never use `comm` with `method: send`. Then run the read-back; do not report "sent" before it.
