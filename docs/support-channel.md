# Working with a client's agents through the OpenMax bridge

A skill pack's agent sometimes needs a client's own agents: their support agent, their onboarding agent, the agents that hold the data. The way is a support group on OpenMax, reached through a bridge. Learned in practice in the Google Ads skill pack (2026-10-27 to 29) and used again by the Meta Ads skill pack (2026-10-29): two packs, so the send-and-read-back wrapper is `kit.bridge` (pack `bridge`, `docs/kit-and-tools.md`). This is the guide and templates around it. No client name, person, group or id belongs in this repository: the per-client part is a config the pack keeps outside the repo ([templates/support-channel/config.example.md](../templates/support-channel/config.example.md)).

## 1. What the bridge is

A Claude Code plugin from OpenMax. There is one shell function and one plugin config **per client organization** (one for OpenMax's own organization, one for each client's), so a pack may hold several. If the config is not known, look in the shell profile for the bridge function and in `~/.config/claude-openmax/*.json` for the identity and the organization id (the default organization's member search finds nothing). Write down the file's path and the organization id, never a key from it. *Why:* the default session sees only its own organization's groups; a client's group is invisible until the session is started through that client's bridge.

**Every bridge sets both `CLAUDE_OPENMAX_CONFIG` and `CLAUDE_OPENMAX_DATA_DIR`, and the pair is unique per identity.** The data dir holds the token cache (keyed by organization only) and the sync cursor; without it every bridge shares `~/.local/share/claude-openmax`, and a second identity in the same organization is handed the first one's token. One identity is resident (listening) in **one** place at a time: a second live connection of the same identity, in a sibling session or on another device, gets the same wake notices, can answer twice and races on the cursor and the config write-back. Another device uses its own `device_id` and never starts a second resident bridge for an identity that already has one. *Why:* read in the plugin's source (2026-10-30), not seen to fail; `kit.bridge.check_isolation` refuses a pair that breaks this before anything is sent.

## 2. Headless use

**Send and read back with `kit.bridge.send_to`** (HTTP; no `claude` process, no model call, no extra connection; it needs the identity's config file, 0600, outside the repo). It runs `check_isolation` first. On a machine with no key file, run one step at a time with `claude -p` and `--allowedTools` listing only what that step needs: a read step allows only the plugin's `comm`, a send step only its `comm_send`, **by full name** (`mcp__plugin_openmax-channel_openmax__comm`), the prompt placed before the flag (templates below). *Why:* a step that can only read cannot send by mistake, and a step that can only send cannot wander through the group.

## 3. Sending

`comm_send` with `endpoint` = the conversation id and `content` = **one plain string**, the @names written as plain text, with an ASCII `@` (only an ASCII `@name` becomes a member mention that wakes the agent). Do not use the generic `comm` tool with `method: send` and a structured content array of mention and text parts: it was accepted and stored as an **empty** message (seen once). So: always read that message back, by the id `comm_send` returned, in a separate read-only run and compare it with what was meant before telling the owner it was sent. If it is empty or wrong, resend at most once and say so. Templates: [send](../templates/support-channel/send.md), [read-back](../templates/support-channel/read-back.md). *Why:* the bridge answers "ok" for a message that holds nothing. Without a bridge in the session, the same flow works over the REST API with the client identity's key (token exchange, then `/api/v1/conversations/...`); there the body must be typed (`type` and `content.body.text`) and a plain string in `content` returns 422. The read-back applies there too.

## 4. Polling

**Prefer `kit.bridge.wait_for_reply_to(target, sent.id, from_ids=[the asked agent's member id])`:** it reads the group over REST (no model call) until a reply to that message appears or 30 minutes pass, and returns `replied`, `timeout` or `unreadable` ([design](design/bridge-reply.md)). Run it in the background so the session is not blocked. An agent often answers without any mention, which is why `from_ids` is needed. Whether the reply answers the question is for the agent to judge; a follow-up needs `kit.bridge.next_round(used, why)`: at most three requests, each with the reason the last answer fell short. The 10-minute poll below is for a machine with no key file.

Every 10 minutes, read-only ([check template](../templates/support-channel/check.md)). Keep the newest message id seen in a scratchpad file (outside git) and ask only for what is newer. Nothing new is one line, not a report. *Why:* the cutoff keeps a long thread out of the context and the one-line answer keeps the owner's page quiet.

## 5. Who to ask

1. The client's **support agent** and **onboarding agent** first.
2. Then the client's own **working agents**, through the group.

An @ in the group works. Before asking, read the member's online state: an agent the client switched off answers nothing, in a group or directly. Then do not poll every 10 minutes: report once and ask our own support/FDE team to have the client switch it on, not the client's staff. A direct message to an agent that has not allowed the sender is **silently dropped**: the symptom is zero replies for days, and the check is whether a group @ to the same agent is answered. Never the client's human staff for routine tests: their time is the client's, not the pack's.

Real data leaving the client's organization needs the client's lead to agree **once**. Ask for the whole data set in one message with a few options (all real, names as codes, structure and text only, none), not query by query. The client's own agent may refuse to withdraw a question it already has pending: accept that and do not argue. *Why:* each separate ask costs the lead a decision; one ask with options costs one.

## 6. Data rules

- Real values never go to git. Only a faked copy with the real field structure becomes a fixture.
- The page the client's lead reads opens with one line on **why**, then **what** is asked, then the **options** (`docs/page-style.md`).

## 7. A defect to report to OpenMax

The server rejects a malformed body; the empty stored message comes from the plugin's path. The plugin should **refuse** a send whose content it does not accept, instead of storing an empty message. Report it to the plugin's maker. Until it does, the read-back in section 3 is the only protection.

## Per client, outside the repo

Which bridge command, the conversation id, the member ids and the last-seen file are the pack's config, kept where its other secrets and ids are (never committed; `templates/gitignore`). The empty shape is [config.example.md](../templates/support-channel/config.example.md).
