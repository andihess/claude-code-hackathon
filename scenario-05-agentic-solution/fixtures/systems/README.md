# Fake systems-of-record (Track A)

Synthetic data the read tools query. **No real or internal data.**

- `kb/` — knowledge-base articles / runbooks for `kb_lookup`.
- `requesters.json` — requester directory (email → profile, VIP, org unit) for `lookup_requester`.
- `assets.json` — device/asset records for `lookup_asset`.
- `queues.json` — queue load numbers for `check_queue_load`.

TODO(Track A): populate these with a small, realistic synthetic set.
