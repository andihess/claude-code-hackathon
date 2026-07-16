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

Cover the categories and at least: a password reset (auto_resolve), a P1
(business-down), and one that looks urgent but isn't. **No real data.**

TODO(Track C): add the labeled sample set.
