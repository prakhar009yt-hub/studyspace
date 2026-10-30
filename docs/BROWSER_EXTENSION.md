# Browser test edition

The static Vercel website can now work with a Chrome/Edge Manifest V3 extension and a local JSON file. The Python dashboard and Windows companion remain separate supported options; they are not required for this browser workflow.

## Install and use

1. Download `Studyspace-Extension-Test.zip` from the homepage and extract it to a permanent folder.
2. Open `chrome://extensions` or `edge://extensions`, enable Developer mode, select Load unpacked, and choose the `Studyspace-Extension` folder containing `manifest.json`.
3. Click the extension action. Sign into MUJ in the same browser profile, then Find my subjects. Grant access only to the listed MUJ and Google hosts as needed.
4. Choose a semester. Explicit labels such as `Sem_III` and semester-parent relationships are recognized. Assign unresolved subjects manually; previous semesters are not automatically fetched. Names ending in Lab are excluded.
5. Enter your own Gemini key and available model ID. Accept transmission of the chosen notes to Google and Fetch & analyze semester. Keep this tab open.
6. Optionally save originals to Downloads. Otherwise original bytes are transient, and only analyzed content is saved.
7. Save study JSON after the queue finishes or you stop it. Open it in `/study.html` for summaries, searchable notes, topic progress, quizzes, flashcards and an exam-date plan.
8. Enter a YouTube key and Find topic videos to search actual YouTube candidates and rank their metadata with Gemini. Up to three suitable videos are retained per topic. Save the updated JSON.
9. On another visit, import the saved JSON into the extension before reconnecting and syncing. Matching document hash and model reuse prior analysis; downloads still check source bytes for changes. Changing semesters starts a separate study file after confirmation.

The viewer stores changes in tab memory. Save a new JSON after edits; it does not overwrite the original file automatically. Keys are excluded by an export allowlist and are never saved in extension storage. See `/privacy.html` for data flows.

## Keys

Get Gemini keys from [Google AI Studio](https://aistudio.google.com/apikey). Enter a model available to your project; an unavailable model produces a visible error rather than a silent substitution.

For YouTube: create/select a Google Cloud project, enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com), open APIs & Services → Credentials → Create credentials → API key, and restrict that key to YouTube Data API v3. Website-referrer-only restrictions can reject extension-origin requests; use separate appropriately restricted development keys. Do not publish real keys in source or screenshots.

There is no Studyspace artificial daily request cap. Two workers and request pacing limit simultaneous analysis. Provider authentication/quota errors pause further analysis and appear in Activity & errors. Video lookup stops on provider errors and can be resumed after quota/access is restored. These controls do not combine keys to bypass Google limits. API billing and quotas remain your responsibility.

## Test scope and limitations

- This is an unpacked test extension, not a store listing. No live MUJ login or paid Google request is claimed by automated tests. The user must test authenticated access in their browser.
- A valid login does not guarantee direct API access. MUJ may require an approved OAuth/API integration. A 401/403 is reported; no access controls are bypassed.
- PDF, PPTX, DOCX, TXT and MD up to 50 MB are supported. DOC/PPT and web-page-only lessons require PDF export. Office extraction can omit vector diagrams/layout. PDF gives better fidelity.
- Large PDFs use Google's Files API with best-effort deletion after analysis. Google automatically expires uploads; a failed cleanup is reported.
- The file can include private academic material. Keep backups and do not distribute notes without permission. Keys stay in memory; users must re-enter them after closing the tab.
- The lightweight viewer includes study essentials, not every Python dashboard feature. It does not yet migrate old SQLite workspaces or support note-grounded follow-up chat or syllabus gap analysis.

## Build and distribute

```sh
python scripts/package_extension.py
node --test extension/tests/browser.test.mjs web/build.test.mjs
node web/build.mjs
```

The packager uses an explicit source allowlist, writes a deterministic test ZIP, and copies the shared viewer schema/style/privacy assets into `web/`. Commit those generated assets; Vercel can build from `web/` without accessing the repository parent. The website and extension bundle no user keys or notes. The download ZIP excludes test fixtures.

For wider distribution, create an Edge Add-ons or Chrome Web Store listing with screenshots, a privacy policy, narrowly scoped permission explanations and reviewer test instructions. Store publication/review and developer-account registration are separate manual steps. Do not ask general users to enable Developer mode as the permanent production distribution method.
