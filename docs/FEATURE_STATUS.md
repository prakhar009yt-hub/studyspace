# Status against the supplied specification

This is a working local implementation, with offline verification. Live services require your keys and manual LMS login. No claim is made that all advanced ideas have been completed or that recommendation quality has been benchmarked.

| Area | Implemented | Limits / follow-up |
|---|---|---|
| Login/session | Manual browser sign-in, preflight check, expiry stop, private storage, reset | MUJ authenticated testing pending; site-specific SSO/storage may need adapter changes |
| Discovery | Brightspace version negotiation, paginated courses, recursive modules; selector fallback | University can deny API access; JS-only custom UI may need extension |
| Downloads | Conditional requests, hash changes, folder mirroring, pacing, cap, retries, report | Linked HTML recorded, not extracted; download size checked after buffering |
| File analysis | Native PDF chunks with page offsets, ordered topic merge, summaries, concepts, definitions, prerequisites, difficulty | DOC/PPT need manual conversion; DOCX/PPTX extraction omits diagrams |
| Personalization | Subject/semester/level/languages, syllabus comparison, weak/covered flags, exam ordering | Same normalized topic shares state across courses; syllabus PDF chunks report gaps independently |
| Study aids | MCQ/short-answer quizzes, explanations, flashcards, source-based Q&A, revision text | Cheat sheet is per-note/chunk text, not a verified one-page per-unit PDF |
| YouTube search | 3–4 contextual queries/topic/language, dedup, broader fallback, optional playlist search with suggested lesson ranges, reuse of queries behind helpful/watched picks, extra worked-example query for weak topics | Playlist alignment uses titles from up to 200 lessons in each of the top two playlists; learned query wording is reused, not a trained model |
| Filtering | Duration by topic scope, views, available likes/views, clickbait/caps, known language, blocked channels, freshness penalty; channel description/age/subscribers supplied to scorer | Language may be unknown or misclassified; channel education focus inferred from description, not full upload history |
| Ranking | Structured criterion scores combined in code, varied roles, ordering, reasons, confidence, preferred channels | Metadata estimates cannot establish actual teaching clarity/depth; no quality benchmark supplied |
| Transcript | Supplied transcript comparison, missing concepts, terminology warnings, coverage ranking bonus, jump links, description chapter links | No arbitrary captions download; automatic note-to-chapter section mapping pending |
| Cache/budgets | Separate search/metadata/model/video-topic score/recommendation caches, manual refresh, cross-note reuse, local daily budgets, queue, stale fallback | Local request meter is not provider-wide/billing; queue requires retry/scheduled command |
| Feedback | Watched/skipped/blocked, rating/reasons, channel score adjustments, query reuse, history | Reason tags stored; specific accent/teaching-style learning pending |
| Interface | CLI and responsive Streamlit dashboard, LMS connection/discovery/sync controls, semester/subject/module navigation, thumbnails, aids, progress | UI has no authentication and binds to loopback; authenticated MUJ acceptance test needs your manual sign-in |
| Scheduling/digest | Automatic selected-semester website sync while open, daily terminal scheduler, one-shot pipeline, Telegram digest with explicit flag | Website sync needs the page open; no OS task installed automatically; email delivery pending |
| Export | Offline Markdown plan, watch-time estimate | PDF export and per-unit single-page layout pending |
| Other sources | YouTube can return NPTEL/university channels | Dedicated OCW/written/practice-resource discovery pending (optional in brief) |
| Watch Later | Open video on YouTube and save using its UI | Account OAuth integration/custom playlists pending; special Watch Later API operations restricted |
| Quality monitoring | Deterministic offline tests and filter logs | Requires your ten-topic known-good benchmark; no fabricated gold-standard videos |

For the first live acceptance test: add keys, import a small PDF, inspect the analysis, find videos, mark one watched, rerun and confirm it is hidden. Then log into MUJ, list your courses, track one, sync twice, and compare the incremental reports. Finish with a ten-topic recommendation spot-check before enabling daily runs.
