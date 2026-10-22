"""The hub's verb table (kit.verbs): the kit's facts verbs and pending."""

from kit.verbs import Verb

VERBS = [
    Verb(("facts", "init"), "facts.py", "human", False,
         answers="Declare a market (pending until a person confirms it)"),
    Verb(("facts", "list"), "facts.py", "read",
         answers="Every fact of the hub (* = pending)",
         examples=("facts list --json",), keys=("declared_markets",
                                                 "pending_markets", "facts")),
    Verb(("facts", "get"), "facts.py", "read", answers="One fact"),
    Verb(("facts", "history"), "facts.py", "read",
         answers="Who changed which fact, when and why"),
    Verb(("facts", "set"), "facts.py", "human",
         answers="Record a value, pending until a person confirms it"),
    Verb(("facts", "unconfirm"), "facts.py", "human",
         answers="Doubt a confirmed value (lowers trust)"),
    Verb(("facts", "rollback"), "facts.py", "human",
         answers="Propose an earlier value again, pending"),
    Verb(("facts", "confirm"), "facts.py", "gated",
         answers="A person confirms a value: every pack copies it"),
    Verb(("facts", "restore"), "facts.py", "gated", False,
         answers="Replay a backup (a person at the terminal)"),
    Verb(("pending",), "pending.py", "read",
         answers="What waits on a person, as ready console asks",
         examples=("pending --hub --json",)),
]
