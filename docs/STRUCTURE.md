# Project structure

| Path | Responsibility |
| --- | --- |
| `dashboard.py` | Streamlit entrypoint, navigation, settings and note study tabs |
| `muj_study/core.py` | Configuration, SQLite schema, cache, quota counters and private persistence |
| `muj_study/lms.py`, `lms_ui.py`, `library.py` | Manual sign-in, discovery, downloads, catalog and semester filtering |
| `muj_study/jobs.py`, `worker.py`, `pipeline.py` | Background processes and concurrent fetch/analysis |
| `muj_study/gemini.py`, `agents.py`, `document_media.py` | Gemini work, configured API workers and document extraction |
| `muj_study/youtube.py` | Topic query planning, video search, ranking and feedback |
| `muj_study/planner.py`, `planner_ui.py` | Capacity-aware exam plans and saved completion state |
| `muj_study/ui.py`, `appearance.py`, `assets/` | Presentation, sidebar, native theme and CSS |
| `muj_study/cli.py` | Local command-line workflows |
| `tests/` | Offline unit and Streamlit interaction tests |
| `deploy/start.py`, `Dockerfile`, `compose.yaml` | Persistent single-user container deployment |
| `web/` | Dependency-free Vercel website; embeds/opens the full persistent workspace |
| `companion/`, `scripts/package_companion.py` | User-installed Windows companion and source-only downloadable ZIP |
| `compose.gateway.yaml`, `deploy/Caddyfile` | Optional authenticated HTTPS gateway for that workspace |
| `.github/workflows/ci.yml` | Tests, source secret check and container smoke test |
| `scripts/check_publish.py` | Check staged/tracked files without displaying secret values |
| `config.example.json` | Safe defaults; no actual credentials |

`config.json`, `data/`, `.venv/`, private credentials and personal screenshots are runtime artifacts, not repository sources. Repository sources remain in `/opt/studyspace` inside the container; mutable state lives separately under `/state`. This preserves the existing desktop layout while providing writable deployment paths and keeping session protection outside the repository.

The UI uses native Streamlit widgets and subprocess workers. One replica with persistent local SQLite storage is supported. Do not add multiple web replicas sharing these files without redesigning locking, job ownership, credentials and database access. A static-site build or generic serverless function is unsuitable for the current architecture.
