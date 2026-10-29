# Support channel config (one per client organization; keep OUTSIDE the repo)

Fill in on the pack's machine. Never commit the filled copy. Guide: `docs/support-channel.md`.

| Key | Value |
| --- | --- |
| bridge_command | `<the shell function for this client's organization>` |
| conversation_id | `<id of the support group>` |
| members | `<role: member id>` for the support agent, the onboarding agent, each working agent you may ask |
| identity_config | `<path of the identity config under ~/.config/claude-openmax/ (the path only, never a key)>` |
| organization_id | `<the client organization's id>` |
| last_seen_file | `<scratchpad path holding the newest message id read>` |
| poll_every | 10 minutes |
| data_release | `<none yet | agreed on DATE by the client's lead: option chosen>` |
