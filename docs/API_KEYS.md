# Obtain and insert API keys

## Gemini

1. Sign in at [Google AI Studio API keys](https://aistudio.google.com/api-keys).
2. Create/select a project and use **Create API key**, or copy the key shown for your project.
3. Run `.\.venv\Scripts\python.exe -m muj_study setup` and paste it at the hidden `GEMINI_API_KEY` prompt.
4. Select a model your project can access in `config.json` or dashboard Settings. The default is `gemini-3.1-flash-lite`, which passed a live structured-analysis check; both analysis and ranking models are configurable.
5. Test with a small note using `analyze`. `doctor` only verifies that a key is present.

API access, free usage and billing depend on your project/model. A Gemini web-app subscription does not itself configure an API key or this project's billing. Check [Gemini API setup](https://ai.google.dev/gemini-api/docs/get-started), [models](https://ai.google.dev/gemini-api/docs/models), and your project's limits before bulk processing.

## YouTube Data API v3

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Open **APIs & Services → Library**, search **YouTube Data API v3**, and click **Enable**. [Direct API library page](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
3. Open **APIs & Services → Credentials → Create credentials → API key**. [Credentials page](https://console.cloud.google.com/apis/credentials).
4. Edit the new key. Under **API restrictions**, choose **Restrict key → YouTube Data API v3**. Use a separate key from Gemini. For this local Python application, browser HTTP-referrer restrictions will fail; an IP restriction is practical only if you have a stable public outbound IP.
5. Run `setup` and paste it at the hidden `YOUTUBE_API_KEY` prompt. Existing Gemini key can be retained by pressing Enter.
6. Analyze a note, then run `recommend NOTE_ID`. View actual quotas under the API's **Quotas & System Limits** in Cloud Console.

Public video search/metadata uses an API key and needs no YouTube account OAuth. Account operations require OAuth and appropriate scopes. This app does not implement Watch Later insertion; YouTube restricts operations on special system playlists. Use the video link and YouTube's own Save button, or a normal custom playlist in a future OAuth integration.

Quota documentation checked during implementation describes separate daily search-call and other-endpoint quotas. Do not assume an older 100-unit search cost applies to your current quota model. The app conservatively tracks search requests and metadata requests separately; it cannot see use by other apps. See [getting started](https://developers.google.com/youtube/v3/getting-started), [quota costs](https://developers.google.com/youtube/data/determine_quota_cost), [search reference](https://developers.google.com/youtube/data/reference/rest/v3/search/list), and [captions permissions](https://developers.google.com/youtube/data/reference/rest/v3/captions/download).

Keys can also be supplied as `GEMINI_API_KEY` and `YOUTUBE_API_KEY` environment variables. Environment variables override the private key file. Never place actual keys in `config.example.json` or commit them. Rotate a key in the provider console if it is exposed.
