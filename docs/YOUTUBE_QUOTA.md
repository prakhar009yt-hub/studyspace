# YouTube quota mode

Settings → **Use Google quota directly (no local YouTube cap)** removes both local search and metadata request caps. Existing counters remain recorded. Saved recommendations and request caches continue to be reused; the finder does not spend quota solely to reach a limit.

The app does not know Google's remaining quota from its local request count. Google enforces the project quota, and requests can consume different amounts of provider quota. When Google returns a daily quota error, new requests pause until the daily reset while cached videos remain available. Failed requests stay queued for retry. Key/access errors remain visible and are not treated as a local budget limit.

This option is separate from Gemini's provider-quota mode. Turn it off to restore the saved local YouTube request budgets.
