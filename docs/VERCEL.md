# Vercel website with a persistent Studyspace backend

## What this deploys

The user-facing website lives on Vercel. The existing Streamlit application, SQLite, documents, keys, worker pool, exam plans and LMS session live on **one persistent backend**. The website opens the full app inside a viewport-sized frame, with an **Open directly** link for browsers or login gateways that block embedded sign-in. This preserves existing features without moving private state into a disposable serverless filesystem.

There is no rewrite of your study engine and no new cloud database dependency. The Vercel website is not a standalone replacement for the backend. It must have a reachable backend to work. Its header theme is a separate local preference from the backend's saved theme.

Current Vercel documentation supports [container functions](https://vercel.com/docs/functions/runtimes/container) and [WebSockets](https://vercel.com/docs/functions/websockets). The deciding constraint here is [durable storage](https://vercel.com/i/serverless-container-storage): this app relies on filesystem semantics and local SQLite. Vercel does not mount the Compose volumes. Its WebSockets also have a function-duration lifecycle. Keeping the stream and worker execution on the persistent backend avoids those lifecycle limits for this deployment.

## 1. Run the persistent backend

Use a Linux server with Docker and Compose and a domain such as `study.your-domain.example`. Keep one app replica with all three persistent volumes from [DEPLOYMENT.md](DEPLOYMENT.md). Imports, AI analysis, recommended videos and exam plans work in hosted mode. Manual MUJ sign-in still needs the desktop workflow; a server owner may provision their valid saved session privately, subject to MUJ accepting it from that machine.

The optional Caddy gateway gives the backend automatic HTTPS and password protection. Point the backend domain's DNS to your server and allow inbound TCP 80/443. Do **not** expose port 8501 publicly.

Generate your own hashed gateway password interactively:

```sh
docker run --rm -it caddy:2-alpine caddy hash-password
```

Save the following in an owner-readable `.env` **on the backend server**, using your actual values. This file is ignored by Git. Single quotes protect the dollar characters in the password hash from Compose interpolation.

```dotenv
STUDYSPACE_BACKEND_DOMAIN=study.your-domain.example
STUDYSPACE_FRONTEND_ORIGIN=https://your-vercel-project.vercel.app
STUDYSPACE_LOGIN=your-workspace-login
STUDYSPACE_PASSWORD_HASH='paste-your-generated-bcrypt-hash-here'
```

`STUDYSPACE_FRONTEND_ORIGIN` must be the exact HTTPS origin, with no trailing slash or path. The gateway permits framing from that origin only. The workspace login is a separate gateway credential, not your MUJ password. Never put a plaintext password or credentials into a URL.

Start and validate:

```sh
docker compose -f compose.yaml -f compose.gateway.yaml config --quiet
docker compose -f compose.yaml -f compose.gateway.yaml up -d --build
docker compose -f compose.yaml -f compose.gateway.yaml ps
```

Open the backend's HTTPS URL directly. It must ask for your gateway credentials before showing Studyspace. The gateway protects HTTP, downloads and WebSocket upgrades. Supply Gemini/YouTube keys in backend Settings or the server's secret environment. Provider keys belong **only on the backend**.

If you already have an authenticated HTTPS gateway, use it instead of Caddy. It must support WebSockets, allow framing only from your frontend origin, keep private responses uncached, and preserve Streamlit's CORS and XSRF protections. Do not disable those protections to fix an iframe problem.

## 2. Deploy the Vercel website

1. Push the source repository to GitHub. GitHub authentication is still required if it has not been connected yet.
2. In Vercel, create/import a project from that repository.
3. Set **Root Directory** to **`web`**. This is essential: the repository root is the Python/Docker backend.
4. Choose **Other** as the Framework Preset, with Node.js **24.x**.
5. Add **`STUDYSPACE_BACKEND_URL`** = your protected backend root URL, for example `https://study.your-domain.example`.
6. Build Command: `npm run build`. Output Directory: `dist`. The included `web/vercel.json` declares these.
7. Deploy. Update the backend's `STUDYSPACE_FRONTEND_ORIGIN` to match the exact resulting Vercel origin, then reload/recreate the gateway.
8. Open your Vercel URL and select **Open my workspace**. If sign-in does not display inside the frame, choose **Open directly**, sign in in that tab, and continue there or reload the frame.

For CLI users, run the Vercel CLI from `web/`, not the repository root. Set the same public backend environment variable before building. No project linking or paid hosting is performed by this repository automatically.

Only the validated backend root URL is embedded into `config.js`. It is public, not a secret. A missing, non-HTTPS, credential-bearing, localhost or non-root URL fails a production build with an actionable message. Do not put `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, LMS cookies or worker keys into the `web` project. The build never reads or copies those variables. Changing the backend URL requires redeploying the static website.

### Preview deployments and embedded login

Preview deployments have different origins. The supplied gateway allows only your configured production origin. Use **Open directly** in previews, or deliberately add a specific preview origin to your gateway policy. Do not use a wildcard frame allowlist for a private workspace.

Browsers can restrict third-party cookies or cross-origin Basic Authentication. The launcher cannot inspect a cross-origin frame's contents or reliably determine whether login succeeded. It does not claim that an iframe load means the backend is healthy. The direct link is always available. Vercel Deployment Protection protects the launcher only; it does not secure the backend's separate URL, so the backend gateway remains necessary.

## Local verification

With the current local backend still at port 8503, PowerShell users can preview without modifying or exposing it:

```powershell
$env:STUDYSPACE_BACKEND_URL = 'http://127.0.0.1:8503'
node web/build.mjs --allow-local
.\.venv\Scripts\python.exe -m http.server 8510 --bind 127.0.0.1 --directory web/dist
```

Open `http://127.0.0.1:8510`. HTTP localhost is accepted only with `--allow-local`, and the flag is ignored under `VERCEL=1`. Never configure localhost in the deployed site: it refers to the visitor's computer, not your backend server. Preview output is ignored by Git.

Checks:

```sh
node --test web/build.test.mjs
node --check web/app.js
python -m unittest discover -s tests -v
```

The GitHub workflow checks the static build and authenticating gateway syntax in addition to backend tests. A real Vercel deployment and domain/login/WebSocket check still require your hosting accounts, backend domain and credentials. Docker/Caddy cannot be executed on a machine without Docker installed.
