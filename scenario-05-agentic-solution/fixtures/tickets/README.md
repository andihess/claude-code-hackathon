# Sample inbound tickets (Track C)

Synthetic requests the agent triages. One JSON file per ticket:

```json
{
  "subject": "Can't log in",
  "body": "...",
  "channel": "email | chat | web_form",
  "requester_email": "user@example.com"
}
```

**Naming scheme:** `NNN-slug.json` — zero-padded 3-digit prefix for stable sort order,
slug = short kebab-case description. The filename stem (e.g. `001-password-reset-verified`)
is used as the `id` in `eval/dataset.jsonl` to join a ticket to its labeled expectation.

## Index

| id | category | severity | expected action | why it's included |
|---|---|---|---|---|
| `001-password-reset-verified` | access | P4 | auto_resolve | clean password-reset case |
| `002-password-reset-unverified` | access | P4 | escalate | boundary: identity not verifiable via channel/email |
| `003-office-network-outage-p1` | network | P1 | escalate | business-down, clear P1 |
| `004-urgent-language-cosmetic` | software | P4 | route (app-support) | "urgent" language, but cosmetic/no impact |
| `005-suspicious-login-security` | security | P2 | escalate | security category must always escalate |
| `006-phishing-clicked-security-p1` | security | P1 | escalate | active security incident |
| `007-laptop-dead-before-meeting-hardware` | hardware | P2 | route (desktop-support) | one user fully blocked, no workaround |
| `008-shared-drive-down-team-network` | network | P2 | route (network-ops) | team degraded, no workaround |
| `009-vpn-slow-workaround-network` | network | P3 | route (network-ops) | degraded, has workaround |
| `010-software-license-request-routine` | software | P4 | route (app-support) | routine, non-urgent request |
| `011-flaky-printer-hardware-workaround` | hardware | P3 | route (desktop-support) | degraded, has workaround |
| `012-new-access-request-nonurgent` | access | P4 | route (identity-access) | access request that isn't a password reset — does not qualify for auto_resolve |

All requester emails are invented and use `@example.com` or an obviously-fake domain — **no real data**.
