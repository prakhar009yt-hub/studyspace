# Studyspace

A local study tool based on the supplied specification: manual Brightspace login, incremental downloads, Gemini note analysis, YouTube discovery/ranking, and a dark local dashboard. Your LMS password is never entered or stored by this tool.

Studyspace includes light/dark glass themes, searchable semester libraries, background download/analysis progress, AI-ranked topic videos, and an exam planner with daily study sessions and CSV export. Subjects ending in `Lab` are excluded throughout. This is a **single-user personal workspace**: it does not isolate different visitors' notes, keys or settings.

## Deploy privately

**Free default: Vercel website + each user's own computer.** Deploy `web/` with `STUDYSPACE_MODE=local`. Visitors download the Windows companion, extract it, run `Setup.cmd` once, and use `Studyspace.cmd` to open their own local app on port 8765. Files, LMS login, keys, downloads and background work remain on that user's PC. No remote backend, Docker, Tailscale, custom domain or hosting subscription is needed for this mode. The companion requires Python 3.11+ and Windows; API usage and electricity/internet are separate. See [the setup guide](docs/LOCAL_COMPANION.md).

**Optional shared/private server mode:** deploy `web/` with `STUDYSPACE_MODE=remote` and `STUDYSPACE_BACKEND_URL` set to an authenticated backend's HTTPS URL. Notes, keys, SQLite and background work then stay on that separate persistent server. See [Vercel deployment modes](docs/VERCEL.md). Importing the Python repository root as a normal Vercel function will not provide persistent storage.

For a Linux server or Docker Desktop:

```sh
docker compose up -d --build
```

Open `http://127.0.0.1:8501`. Named volumes persist notes, preferences and private credentials across container restarts. The port is bound only to loopback. Use an SSH tunnel or an authenticated private gateway for a remote server. Manual MUJ login requires the desktop version; the hosted container has no interactive login window. See [deployment instructions](docs/DEPLOYMENT.md) for setup, secrets, backups and limitations, and [project structure](docs/STRUCTURE.md) for the code layout. No deployment is performed automatically on GitHub pushes; Actions runs verification only.

## Start on Windows

Open PowerShell in this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m muj_study setup
.\.venv\Scripts\python.exe -m muj_study web
```

If your Python installation cannot bootstrap pip, use `uv pip install --python .venv\Scripts\python.exe -e .` after creating the environment. You do not need to activate the environment; all commands below use its Python directly.

`setup` asks for **GEMINI_API_KEY** and **YOUTUBE_API_KEY** with hidden input. Press Enter to retain existing keys. Keys and the LMS session live in `%LOCALAPPDATA%\MUJStudyAssistant`, outside this repository. `config.json` holds learning preferences and the LMS address, not API keys. Keep the private directory outside shared/cloud folders. Windows account permissions protect that folder; Python's mode 0600 alone does not establish a Windows ACL. For a shared PC, use a private Windows user profile and review folder permissions. You may instead set these environment variables for the current terminal:

```powershell
$env:GEMINI_API_KEY = 'your-gemini-key'
$env:YOUTUBE_API_KEY = 'your-youtube-key'
```

Do not paste real keys into source files, screenshots, chats or Git. See [API setup](docs/API_KEYS.md) for obtaining them.

## Use your own notes immediately

The dashboard opens to **Home**, with clickable library, topic, covered-topic and watched-video tiles, recent notes, and study shortcuts. You can add your API keys directly under **Settings → API keys** using the masked fields; keys are stored outside the project. Choose **Import**, supply course/unit names, upload a note, and click **Analyze notes**. Open **Notes** to see summary, ordered topics, definitions and prerequisites. **Find study videos** runs multi-query searches and Gemini scoring. The other tabs provide quizzes, flashcards, note-grounded questions, syllabus gaps and history. Importing/analysis sends note content and your configured study context to Gemini. Ranking sends topic and public YouTube metadata. LMS cookies and passwords are never sent to Gemini.

CLI equivalent:

```powershell
.\.venv\Scripts\python.exe -m muj_study analyze 'C:\Notes\DBMS.pdf' --course DBMS --unit 'Unit 1'
.\.venv\Scripts\python.exe -m muj_study notes
.\.venv\Scripts\python.exe -m muj_study recommend NOTE_ID
.\.venv\Scripts\python.exe -m muj_study aids NOTE_ID
.\.venv\Scripts\python.exe -m muj_study ask NOTE_ID 'Explain page 12 in simpler words'
.\.venv\Scripts\python.exe -m muj_study export NOTE_ID
```

Replace `NOTE_ID` with the ID shown by `analyze` or `notes`. Exports are in `data/exports`. PDF chunks preserve diagrams/scans and original page offsets. PPTX includes extracted text and supported embedded slide images; DOCX uses extracted text. Export to PDF for unsupported vector diagrams. Convert older `.ppt`/`.doc` files in Office/LibreOffice first. Blurry source content is flagged when Gemini detects it; this is not a guaranteed OCR quality detector.

## Connect MUJ LMS

**In the website:** open **LMS → Connect MUJ LMS**. A separate browser opens for your manual login. After you complete SSO/OTP, the app detects your login, saves the session privately and discovers your subjects. It fetches every subject assigned to the semester selected in the top-right menu. Previous semesters are kept separate and fetched when you select them. If MUJ does not expose an explicit semester label, place those subjects once under **LMS → Subject semesters**; unassigned subjects are never silently downloaded into the wrong semester.

Downloads appear in **Notes → Downloaded from MUJ**, organized by **Semester → Subject → Module → File**, even without Gemini. Up to three download workers share a global request pacer. When a Gemini key is configured, up to two analysis workers process saved files while other files are still downloading. Already-downloaded pending notes start first; unchanged file versions are deduplicated. Worker counts are capped at three downloads/two analyses, and daily API budgets still apply. Choose a subject in the sidebar and a unit/module in Notes to narrow the library. PowerPoint analysis includes supported embedded PNG/JPEG/WebP slide images; older DOC/PPT files and unsupported vector drawings may need PDF conversion.

Automatic website syncing checks the selected semester every 15 minutes by default while the app is open. It fetches new notes in paced batches and continues remaining new files in subsequent background runs. Browser/API work runs in a separate process; the UI shows progress and does not require terminal commands. Other semesters are not fetched by that worker. Changing semesters while a job is running does not change its captured target; it finishes that one batch, then the newly selected semester can sync. Expiry/access failures stop automatic retries until you reconnect or retry. This feature does not wake a sleeping computer; the CLI scheduler below remains available for unattended runs.

The default login is `https://mujlms.manipal.edu/d2l/login` and home is `/d2l/home`. The `logout=1` parameter from your supplied link is deliberately omitted to avoid logging you out during setup.

```powershell
.\.venv\Scripts\python.exe -m muj_study login
.\.venv\Scripts\python.exe -m muj_study courses
.\.venv\Scripts\python.exe -m muj_study track 'https://mujlms.manipal.edu/d2l/home/12345' 'DBMS'
.\.venv\Scripts\python.exe -m muj_study sync
.\.venv\Scripts\python.exe -m muj_study analyze
.\.venv\Scripts\python.exe -m muj_study logout
```

Use your actual course URL returned by `courses`, not `12345`. Sign in manually, including SSO/OTP, then press Enter in the terminal. Each LMS operation validates the saved session first. `sync --course DBMS` targets one tracked course. `untrack COURSE_URL` removes it. A session can expire during a long run; checks stop on detected expiry. [LMS configuration and limitations](docs/LMS.md) explains university API permissions and selector fallback. **Authenticated MUJ navigation has not been validated without your login.**

## Tracking, exam preparation and transcripts

```powershell
.\.venv\Scripts\python.exe -m muj_study feedback VIDEO_ID --status watched --rating helpful
.\.venv\Scripts\python.exe -m muj_study feedback VIDEO_ID --status blocked --reason 'wrong topic'
.\.venv\Scripts\python.exe -m muj_study block-channel CHANNEL_ID
.\.venv\Scripts\python.exe -m muj_study topic 'SQL joins' --weak yes
.\.venv\Scripts\python.exe -m muj_study topic 'SQL joins' --covered yes
.\.venv\Scripts\python.exe -m muj_study exam 2026-12-01
.\.venv\Scripts\python.exe -m muj_study progress
.\.venv\Scripts\python.exe -m muj_study gaps DBMS 'C:\Notes\syllabus.pdf'
.\.venv\Scripts\python.exe -m muj_study verify NOTE_ID 'SQL joins' VIDEO_ID 'C:\Notes\transcript.vtt'
```

Provide a transcript you are permitted to use. Verification compares coverage/notation and returns an evidence-based jump link. It does not download arbitrary YouTube transcripts; the official captions API requires permission to edit the video. Plain text without timestamps cannot give a meaningful jump time. Topic state is keyed by normalized topic name globally; the same topic name across courses shares progress. Exam mode prioritizes weak, uncovered and least-reviewed topics. `exam off` disables it.

## Budget, caching and automation

Searches, video metadata, model output and recommendations have separate caches. Results show cache hits. `recommend NOTE_ID --refresh` refreshes that note; `--playlists` enables additional playlist discovery. Watched, skipped and blocked results are hidden even on cache hits. Channel feedback influences subsequent displayed rankings. Search defaults to at most 80 calls/day locally, leaving headroom against the currently documented default of 100 search calls/day; metadata has its own budget. These are local request counts, not a billing or project-wide meter. Verify your actual allocation in Cloud Console. Gemini also has a local call budget; select models and set it in `config.json`.

```powershell
.\.venv\Scripts\python.exe -m muj_study quota
.\.venv\Scripts\python.exe -m muj_study retry-queue
.\.venv\Scripts\python.exe -m muj_study run
.\.venv\Scripts\python.exe -m muj_study notification-setup
.\.venv\Scripts\python.exe -m muj_study watch --at 08:00 --notify
```

`run` syncs, analyzes changed notes, recommends and exports. `watch` repeats daily while the terminal is open, in your computer's local timezone. Stop with Ctrl+C. It cannot wake a sleeping/off computer. For unattended checks, use Windows Task Scheduler to run the environment's Python with arguments `-m muj_study run --notify` and this project as **Start in**. Schedule is not installed automatically. Telegram setup needs your own bot token and chat ID; send your bot `/start` first. Delivery occurs only with `--notify`, and unchanged successful checks stay quiet. It shares summaries/topics/video links with Telegram. Email is not implemented.

Quota failures fall back to expired cached API responses where available and queue the request for `retry-queue`/the next scheduled run. Empty failures are not cached as good recommendations. `data/activity.log` records cache use, video filtering and download failures without API keys or LMS cookies. API errors are sanitized. Files and analysis stay under `data/`; delete it to reset study history. `logout` deletes only the local saved session; it does not revoke sessions on the LMS server.

## Verification and scope

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m muj_study doctor
```

Offline tests cover binary PDF chunking, cache/context invalidation, quota enforcement, cached feedback, filters, host checks, nesting and quota fallback. They do not establish live Gemini quality, YouTube results or MUJ compatibility. See [feature status](docs/FEATURE_STATUS.md) for implemented behavior and advanced features still pending. Use this only for your own permitted course materials, keep it local, and follow your university's acceptable-use rules.
