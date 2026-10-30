# Fetch and analysis recovery report — 29 October 2026

## Findings

| Problem | Evidence | Effect |
| --- | --- | --- |
| Interrupted network navigation | Latest original worker error: `net::ERR_NETWORK_CHANGED` on MUJ home navigation | The fetch stopped before it could check attachments. This identifies a connection change; the logs cannot establish whether Wi-Fi, a VPN, or another network component caused it. |
| Saved login no longer verified | Recovery fetch passed the earlier navigation failure, then failed the authenticated-page check | A new manual MUJ login is needed. A changed login-detection selector remains another possibility if the browser already shows courses. |
| Local request budgets exhausted | Gemini: 100/100 attempts; YouTube search: 80/80 attempts on the current Pacific date | New AI analyses and video searches pause. These local counters do not prove that the provider rejected the key or exhausted its own quota. |
| Legacy PowerPoint files | Five downloaded files have `.ppt` extensions | Supported document readers require `.pptx`, PDF, DOCX, TXT or MD. These five files remain saved but cannot enter the analysis queue. |
| HTML pages incorrectly marked as failures | Existing completed fetch report includes “Linked HTML page recorded” | The content was saved as a teacher link; reporting it as a failed download was misleading. |

## Implemented fixes

- Retry temporary MUJ navigation failures up to three total attempts with 2- and 4-second backoff. Certificate/security errors are not retried or bypassed.
- Provide a retry button after a stopped job; persistent failures do not trigger endless retry loops.
- Distinguish an actual redirect to sign-in from an unverified page layout.
- Check Gemini's local budget before starting automatic analysis. Downloads continue while analysis is paused.
- Count notes skipped after an analysis circuit breaker as deferred, rather than successful or individual failed API calls.
- Count teacher HTML pages as saved links, rather than download failures.
- Display remaining local budgets, unsupported files, current work and errors in the progress panel. Expose the existing Gemini daily budget in Settings without changing its value.
- Preserve downloaded files, completed analyses, cached recommendations and lab exclusions.

## Remaining actions and prevention

1. Complete manual sign-in in the MUJ browser window. University session expiry cannot be prevented by this app; it never stores your password or bypasses SSO/OTP.
2. Keep the network stable during a fetch. Avoid switching Wi-Fi or VPN connections mid-transfer. Bounded retries recover short interruptions; persistent outages still require a later retry.
3. Allow local budgets to reset at Pacific midnight. Review limits in Settings only after checking provider quota and any billing implications. The recovery does not reset counters or increase limits. Cache reuse and the analysis queue preserve completed work.
4. Save each legacy `.ppt` as `.pptx` or PDF using PowerPoint or LibreOffice, then import it into its matching subject. Originals remain intact.

No provider quota increase, credential change, automatic login, or legacy-file conversion was performed.

## Recovery verification

The manual MUJ login completed successfully. The following recovery batch finished with **60/60 attachments checked, 4 new downloads, 51 unchanged files, 5 teacher pages saved as links, and zero download failures**. The content tree contains 137 attachments; 77 checks remain for later paced batches. Six non-lab subjects were selected, with no unassigned subjects.

Gemini's exhausted local budget was detected before analysis started. No new analysis requests were launched by this recovery batch. The full regression suite passed **46 tests**. The website remains available at `http://127.0.0.1:8502/`.
