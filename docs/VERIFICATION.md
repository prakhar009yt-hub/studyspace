# Verification record

Verified locally on Windows with Python 3.13 on 29 October 2026:

- Installed project dependencies into `.venv` and Chromium via Playwright.
- Passed all 15 offline unit/integration tests, including mock Gemini SDK payloads, binary PDF chunks, cache/context invalidation, budget limits, cached feedback, nested downloads, conditional requests, redirect host validation and dashboard screen/card rendering.
- Launched Streamlit on loopback and received `ok` from its health endpoint.
- Inspected the home and import screens in the in-app browser.
- Redesigned the interface with a violet sidebar, lavender hero, warm paper background, mint accents, responsive statistic cards, recent notes, and working Home shortcuts. Verified the new import shortcut in the browser. Settings now accepts masked API keys and retains private storage outside the repository.
- Verified `doctor` finds dependencies and uses `%LOCALAPPDATA%\MUJStudyAssistant` with the normal Windows profile.

Responsive layout checks:

- Checked Home at 320, 390, 768, 1024, 1440 and 1920 CSS pixels without horizontal main-page overflow.
- Restored the mobile sidebar toggle, with a 44-pixel touch target, and verified opening/closing the navigation drawer at 320 pixels.
- Checked upload fields at 320 pixels, including 16-pixel input text to avoid focus zoom on mobile browsers.
- Used `python -m tests.preview_fixture` and a separate data directory/server to inspect long filenames, video descriptions, feedback controls and all study tabs without touching primary study records.
- Checked the isolated Notes page at 320, 390, 768, 1024 and 1440 pixels. Tabs and long SQL code scroll within their own panels; the main page does not overflow horizontally.
- Layouts now use the available main content width for breakpoints, so sidebar and split-screen layouts adapt independently of total screen width. Browser checks used Chromium; other browser engines and physical devices were not tested.

Not live-verified: Gemini responses, YouTube API results/quotas, Telegram delivery, or authenticated MUJ course discovery/downloads. Keys and a saved LMS login were not provided. Recommendation quality needs a real known-good topic set; offline tests do not measure it.

LMS website update:

- Added GUI manual login, background jobs, subject discovery, automatic selected-semester syncing, downloaded-file browsing before AI analysis, and subject/module categorization.
- Expanded offline coverage to 25 tests, including excluding older/unassigned semesters from sync, independent semester libraries, preserving manual subject assignments, login-to-sync chaining, and one background job at a time.
- Confirmed the new LMS page renders in the live website and started manual sign-in. Bundled Chromium was blocked with `spawn UNKNOWN`; browser selection now prefers installed Chrome/Edge. The installed Chrome successfully opened **Login - MUJ Campus**.
- Actual subject discovery and downloads still require completing the MUJ sign-in. A visible login window is not proof of authenticated LMS access.

Semester identifier regression:

- Fixed parsing of MUJ group identifiers such as `BTECH-0005_Sem_III_July_Dec_2026` and `BTECH-FIRST_Sem_II_Jan_May_2026`. Regex word boundaries previously treated underscores as part of the word and missed the semester label.
- Normalize underscores and Unicode Roman numerals before matching; preserve the rule against inferring semesters from years or subject codes.
- All 26 offline tests pass, including a course inheriting Semester 3 from the exact parent-group label shown in the screenshot.
- Added the explicit course-to-semester parent relationship lookup before ancestor fallbacks. Live discovery now identifies 8 Semester 3 courses and 9 Semester 2 courses in the user's MUJ account; the Semester 3 worker has begun downloading files. Only the eight selected-semester courses were passed to content syncing. All 27 tests pass.

Concurrent pipeline and Home tile update:

- All 31 tests pass, including event/barrier tests proving analysis starts before downloads finish, three request workers overlap, and each Home tile routes to its intended page/filter.
- Each download thread owns its request context and SQLite connection. Request starts share a global pacer; AI work is capped at two workers. File-version checks prevent an analysis from being saved against changed content.
- Verified both supplied API keys against their providers without echoing their values. Keys were saved through hidden input to the private configuration outside this repository.
- The previous model's live generation returned HTTP 504 even for a tiny prompt. Switched bulk analysis to the available `gemini-3.1-flash-lite`, which completed a structured sample analysis in 4.3 seconds. This is a small sample result, not an end-to-end throughput benchmark.
- Added embedded PowerPoint slide images to AI input and verified that image-only slide content is retained in the API payload.
- Live library contained 155 downloaded files when checked. Real note analyses and topics began completing on the new model while fetching continued.
- Verified in the browser that each Home tile's click target covers its full card width. Read-only Home/Topics/Progress dashboards refresh as analysis results arrive.

Videos loading fix:

- Videos now defaults to recommendations, with a separate Watched view. The Home watched-count tile selects Watched explicitly.
- Found 25 saved recommendations hidden by the prior watched-only page. These now render immediately without additional API requests.
- Website search targets one topic per background job rather than an entire note, using a separate job channel so it can run while notes sync.
- When Gemini ranking hits its local budget or fails, eligible YouTube candidates remain available with low-confidence metadata ranking and an explicit unverified-language label when needed. A failed refresh retains saved recommendations.
- All 33 tests pass, including Videos rendering, exhausted-AI-budget fallback and preservation of other topics during an unsuccessful refresh.

Run the suite again with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
