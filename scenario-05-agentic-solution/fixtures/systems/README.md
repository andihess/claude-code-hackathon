# Fake systems-of-record (Track A)

Synthetic data the read tools query. **No real or internal data.**

- `kb/` — knowledge-base articles for `kb_lookup`. `index.json` holds metadata +
  keywords (drives matching); each `KB-XXXX.md` is the article body. Covers all five
  categories, including the auto-resolve path (`KB-1001`) and the security-escalate
  rule (`KB-5001`).
- `requesters.json` — requester directory (email → profile, VIP, `identity_verified`,
  `mfa_enrolled`, `account_status`) for `lookup_requester`. Keyed by lowercase email.
  Includes a suspended/unverified contractor to exercise the "do not auto-resolve" path.
- `assets.json` — device/asset records for `lookup_asset`. Keyed by asset tag.
- `queues.json` — queue-load snapshot for `check_queue_load`. Queue names match
  `CATEGORY_QUEUE_MAP` in `schema.py`; `network-ops` is intentionally backlogged.

All synthetic — emails use the `@acme-synthetic.example` domain. Loaded by the tools in
`helpdesk_agent/tools/`; override the directory with `HELPDESK_FIXTURES_DIR`.
Verify the tools against this data with:

```bash
python -m helpdesk_agent.tools.smoke_test
```
