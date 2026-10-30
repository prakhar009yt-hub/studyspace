# MUJ Brightspace connection

The supplied URL identifies the Brightspace `/d2l/` platform. Its default adapter uses a browser session from manual login and attempts read-only Brightspace endpoints for API versions, your enrollments, and each tracked course's table of contents. It negotiates the advertised LP/LE API versions. Nested modules become local course/module folders. External links and videos are cataloged in SQLite, not downloaded. HTML pages are recorded as links; they are not automatically sent to Gemini.

These API routes are documented by D2L, but whether browser-session authentication is sufficient depends on university configuration. Some deployments require registered application OAuth or disallow student API access. An access-denied result is not evidence of an expired login. No OAuth app or university approval is invented here. The connector needs an authenticated MUJ test to confirm access. References: [enrollments](https://docs.valence.desire2learn.com/res/enroll.html), [content](https://docs.valence.desire2learn.com/res/content.html), [API versions](https://docs.valence.desire2learn.com/res/apiprop.html).

## Manual login

Run `python -m muj_study login`, sign in in the visible Chromium browser and complete SSO/OTP yourself. Navigate to the LMS home screen before pressing Enter in the terminal. Authentication storage is saved only after a configured logged-in element is visible. The tool never asks for an LMS password. If it reports expiry immediately after a successful login, inspect the home screen and set `lms.logged_in_selector` to an element that is shown only when logged in. A session-storage-only SSO deployment may require renewed manual login; Playwright storage state does not preserve every browser mechanism.

## Selector fallback

Change `lms.adapter` from `brightspace` to `selectors` in `config.json`. Inspect your own logged-in content pages using browser developer tools. Set:

- `logged_in_selector`: a visible authenticated navigation/name element.
- `course_selector`: anchor elements linking to enrolled courses.
- `module_selector`: anchor elements linking to modules/content listing pages.
- `file_selector`: anchor elements linking to attachments or external resources.
- `unit_selector`: optional heading containing current unit title.
- `next_selector`: optional pagination anchor.

Selectors must match anchors with actual `href` values. Playwright locators traverse open shadow roots but not cross-origin iframes or closed shadow roots. If MUJ renders its tree using JS-only controls, a dedicated adapter extension may be needed. Keep fixes in `muj_study/lms.py`; do not scatter page selectors throughout the app. Missing content matches produce visible errors.

Configure `allowed_hosts` only for trusted attachment hosts you recognize. Redirects outside the allowlist are rejected before following them. Downloads use conditional ETag/Last-Modified requests when available, compare hashes otherwise, retry transient failures three times, and continue after an individual attachment failure. Servers without validators require fetching bytes to detect changes. The current 100 MB size check happens after buffering the response; this is not a streaming memory cap.

Saved cookies are sensitive. Default location is `%LOCALAPPDATA%\MUJStudyAssistant\session.json`; use `MUJ_PRIVATE_DIR` to override only to another private non-shared folder. Repository/shared-path checks reject common unsafe locations but cannot identify every sync service. `logout` deletes the local session. Data files remain local under `data/`.
