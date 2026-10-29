# Read-back prompt (after every send, a separate read-only run)

Run: `<bridge_command> -p --allowedTools comm "<prompt below>"`

```
Read the newest message of conversation <conversation_id> with the comm tool
(getMessages). Do NOT send anything. Print its id, sender and its full text exactly.
```

Compare the text with what was meant to be sent. Equal: tell the owner it was sent. Empty or different: resend once with `send.md` and say so; if the second read-back fails too, stop and tell the owner.
