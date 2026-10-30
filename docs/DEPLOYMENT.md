# Deploy Studyspace

To avoid server hosting charges, use [the free personal PC hosting route](FREE_HOSTING.md). This preserves the desktop MUJ login workflow and uses private Tailscale access; your PC stays responsible for uptime and storage.

For the **Vercel website + persistent backend** option, follow [VERCEL.md](VERCEL.md). The `web/` folder is the Vercel project; the Python application continues to run on the persistent backend described below.

## Supported deployment

Studyspace is a Python/Streamlit server, not a static site. GitHub stores its source and runs checks; GitHub Pages cannot execute this application. The supplied Docker Compose setup is for one owner on Docker Desktop or a private Linux server. A hosting service must support a long-running Python process, WebSockets, child processes, and writable persistent disk.

This application shares one database, API-key store, LMS session, theme and configuration across visitors. It has **no built-in user authentication or account isolation**. The Compose port deliberately binds to `127.0.0.1`. Do not make it public without adding an authenticated gateway. Multiple users need a separate deployment and volumes per owner, or a future application-level authentication/isolation design.

## Start

Install Docker Engine with Compose on a server, or Docker Desktop on your computer. Clone this repository, enter its directory, then run:

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Open `http://127.0.0.1:8501`. For a remote server, connect privately:

```sh
ssh -L 8501:127.0.0.1:8501 your-user@your-server
```

Then open the same localhost URL on your computer. Keep the SSH connection open. Do not open port 8501 in the public firewall. The image runs as UID/GID 10001, drops Linux capabilities, and uses Chromium for permitted headless LMS work. The health check uses `/_stcore/health`.

The container entrypoint honors `PORT` (default 8501). Compose exposes that default port; change both mappings if you change it. `MUJ_CONFIG`, `MUJ_DATA_DIR`, and `MUJ_PRIVATE_DIR` specify persistent paths. `MUJ_DEPLOYED=1` prevents attempts to open an unavailable desktop sign-in window. Timezone defaults to Asia/Kolkata in Compose.

## Keys and storage

Use **Settings → API keys** through the private connection, or supply `GEMINI_API_KEY` and `YOUTUBE_API_KEY` through the server environment or your host's secret manager. Compose forwards these variables without baking them into the image. Do not write real keys into Compose, Dockerfiles, source files or committed `.env` files. Environment keys take precedence over values saved in Settings; remove an environment key to use the saved one.

Named volumes:

| Volume | Purpose | Container path |
| --- | --- | --- |
| `studyspace-config` | Preferences and native theme | `/state/config` |
| `studyspace-data` | Database, notes, jobs, exam plans, exports | `/state/data` |
| `studyspace-private` | Keys, optional LMS session, worker credentials | `/state/private` |

Compose prefixes volume names with the project directory name. Keep a stable Compose project name when moving directories. Back up all three volumes privately with the service stopped for a consistent database snapshot. Restore ownership to UID/GID 10001. Avoid `docker compose down -v`, which deletes persistent volumes. Normal `docker compose down` preserves them.

Fresh deployments start with automatic sync and automatic analysis disabled. Add keys, import notes, and enable automatic work deliberately in LMS settings. Existing preferences are preserved across restarts. Standard Linux runtimes do not provide Windows GDI+ metafile rendering; export documents with unsupported WMF/EMF drawings to PDF for best fidelity.

## MUJ login limitation

Manual university sign-in opens a visible browser on the machine running Python. A normal hosted container has no graphical session; clicking a website on your laptop cannot open that server-side browser locally. Therefore **Connect MUJ LMS is disabled in hosted mode**. Import, analysis, recommendations, progress, themes and exam planning remain available.

For the complete manual-login workflow, run the desktop version locally. An advanced server owner can provision their own existing `session.json` securely into `/state/private/session.json` using SSH/Docker's private administration tools and ensure owner-only access and UID 10001 ownership. Never commit or publicly upload that file. Headless discovery/downloads then require the university to accept that session from the server. SSO expiry, network restrictions or device binding may require signing in again locally; this approach is not guaranteed. Session expiry stops fetching and is reported in the UI. There is no password or OTP automation.

## Updates and validation

```sh
git pull --ff-only
docker compose up -d --build
docker compose logs --tail=100
```

The GitHub Actions workflow tests Python on Windows and Linux, checks tracked sources for common credential patterns, builds the image, and smoke-tests its health endpoint. It does not publish the container, deploy a host, or use real API credentials. Source tests and container-bootstrap tests can run locally:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/check_publish.py
```

The scanner detects common Google/GitHub keys and private runtime paths. It is a guard, not a guarantee against every possible secret; review staged files before pushing. `.gitignore` excludes keys, settings, local data, session files and personal screenshots. `.dockerignore` uses an allowlist of application sources.
