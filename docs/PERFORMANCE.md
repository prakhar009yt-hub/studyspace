# Dashboard optimization — 30 October 2026

The Notes page previously registered downloads by reading all 132 saved files during every render, including inside a collapsed expander. The catalog contained approximately 412 MB of files. It also rendered every topic and all five study tabs eagerly.

## Changes

- Download contents are generated only when clicked, using Streamlit's deferred downloads. Clicking a download does not rerun the study page.
- The file library has search and pages of 12 files. Notes show 8 topics per page, and the Topics destination shows 20 results per page. All matching items remain accessible through pagination and search.
- Only the selected study tab executes. Existing quiz, chat, syllabus and history features remain available.
- Note pickers pass stable note IDs instead of full serialized analysis dictionaries.
- Progress polling queries a small version snapshot instead of loading all analysis JSON into Python. Topic state reads are batched, duplicate job-status reads are reduced, and routine cache-hit logging uses debug level.
- Schema setup runs once per database migration, with indexes for semester and note-history queries. Ordinary refreshes no longer repeat schema setup writes.
- Streamlit 1.66 or newer is required for the native lazy-tab and deferred-download APIs.

## Measurement

`scripts/benchmark_dashboard.py` copies the current database to a temporary directory, disables automatic LMS and AI work, and renders Notes through Streamlit AppTest. File paths remain local. It measures a cold page render under Python tracemalloc; these values are not browser network timings or a guarantee for every computer.

| Metric | Before | After |
| --- | ---: | ---: |
| Render time | 61.89 seconds | 13.33 seconds |
| Peak traced Python memory | 456.2 MB | 43.5 MB |
| Initial download buttons | 132 | 12 |

This run measured approximately 78% lower render time and 90% lower peak traced memory. No API requests were made for the benchmark. The full regression suite passed 76 tests, including deferred file loading, pagination, lazy study tabs and read-only database reopen behavior.
