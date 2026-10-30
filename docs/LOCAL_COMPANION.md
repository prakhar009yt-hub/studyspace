# Vercel website, local downloads and analysis

## How it works

Vercel serves the public website and Windows companion ZIP. After installation, each visitor runs their own local Studyspace process, bound only to `127.0.0.1:8765`. The website's **Open local workspace** button opens that local app in a new browser tab. One person's localhost is unrelated to another person's localhost: there is no shared database, session or set of API keys.

| Vercel | Each user's Windows computer |
| --- | --- |
| Static launcher, theme, setup instructions | Full Streamlit dashboard and sidebar |
| Downloadable companion source package | MUJ manual login, browser automation and downloads |
| No provider keys or private runtime data | Gemini/YouTube calls using that user's keys |
| No Python worker execution | Notes, analysis results, quizzes, feedback and exam plans |

AI processing still sends analyzed documents to Gemini and video requests to Google; local execution does not mean offline AI. The website does not access the files directly. Local credentials live in that user's Windows profile outside the extracted project; documents and study state are under `data/` in their extracted folder.

## First use

1. Open the deployed Vercel website on your **Windows PC**.
2. Download the Windows companion ZIP and extract **all files** to a permanent folder such as `Documents\Studyspace`. Do not run it from inside the ZIP.
3. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/) if not installed.
4. Double-click **Setup.cmd** once. It creates a local virtual environment, installs the app's declared Python dependencies and downloads Playwright Chromium. This needs internet access and may take several minutes.
5. Double-click **Studyspace.cmd**. It starts the local app hidden and opens `http://127.0.0.1:8765/` in your normal browser.
6. In local **Settings**, add your own Gemini/YouTube keys. In **LMS**, connect and sign in manually on this computer. Downloads and analysis run here, not on Vercel or the site owner's computer.

Later, run `Studyspace.cmd` and use the local tab or the Vercel launch button. Keep the PC awake while jobs run. The setup does not install a Windows service, scheduled startup task, VPN, public tunnel, firewall exception or custom protocol handler.

The companion uses a separate port (8765), so the existing development dashboard on 8503 is unchanged. A fresh extracted companion starts with its own empty library. It does not copy the developer's notes, existing databases or credentials. Repeated launches reuse the companion's own verified process; an unrelated process on the port is never adopted or killed. If startup fails, inspect `data/companion.log`.

## Deployment settings

Import GitHub repository `prakhar009yt-hub/studyspace` into Vercel. Choose Root Directory **web**, Framework **Other**, Build Command **npm run build**, Output Directory **dist**, Node.js **24.x**, and `STUDYSPACE_MODE=local`. Do not add provider keys or an external backend URL to Vercel. GitHub contains the companion source and the generated source-only ZIP; CI regenerates the ZIP and checks that it matches the reviewed sources.

## Updating

Back up `data/` and your user-profile credential store privately. To update code, close that extracted companion's dashboard process, extract a new bundle into the same folder without deleting `data/` or credentials, then rerun Setup.cmd and Studyspace.cmd. Downloading an update alone does not replace a running Python process. Existing user data is not part of the download.

## Browser and platform limits

A normal website cannot silently install or run Python. Users must install/start the companion themselves. Public websites connecting to localhost may encounter local-network permission or browser navigation policies. Use the direct localhost tab; do not disable browser protections or CORS/XSRF to work around a blocked embed. The launcher never scans local ports or fetches private file content.

The provided installer is for Windows. Phones/tablets cannot execute the Windows companion. Use the separate optional Tailscale route if you need to reach your own Windows PC from a phone, or a future cross-platform companion must be developed.

## Cost

This mode needs no paid backend hosting. Vercel usage remains subject to its selected plan and limits. You supply your own computer, internet and electricity, and your own Google API keys. It does not provide API credits or bypass quotas/billing.
