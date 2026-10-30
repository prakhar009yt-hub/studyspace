# Efficient analysis and Gemini agents

**Google quota mode:** Settings → **Use Google quota directly (no local Gemini cap)** disables local Gemini caps across agents. Request counts are still recorded. Google quota/access errors and project cooldowns remain enforced. This mode does not reveal Google's remaining allowance or enforce a spending cap; provider billing applies. Turn the checkbox off to restore the saved local caps. YouTube's separate local budget is unchanged.

Open **Settings → Analysis agents and efficiency**.

1. Enter a worker name and Gemini API key in the password field.
2. Enter the Google project label. Use `primary` for the existing Gemini key’s project. For other keys, use their actual Google project ID. Identical projects must have identical labels.
3. Set the project’s local daily request budget and click **Add analysis agent**. Agents with the same label share the smaller configured budget. Adding another key for that project does not reset its counter.
4. Set **Parallel analysis workers** (1–8). Concurrency is also limited by the number of keys. Each key has one request in flight, and separate files share a queue rather than all agents analyzing the same source.
5. In **Notes**, click **Analyze downloaded notes**, or fetch the current semester. Settings apply to the next job. Lab subjects remain excluded.

Keys are stored in `analysis_agents.json` inside the app’s existing private directory, outside the repository. Primary Gemini and YouTube keys remain in their existing private store. Keys are never shown in tables or token reports. Removing an extra agent removes its saved credential; in-flight jobs use the configuration they already loaded.

## Efficiency

- Efficient mode omits generated video queries from the AI response. Three contextual search phrases are built locally for every topic.
- Readable PDF chunks with no detected image/form/vector/shading content use extracted text and original page numbers. Scans, diagrams and mixed chunks retain the original PDF. PowerPoint images remain included.
- Existing completed analyses and cached generation responses are reused. Concurrent copies of the same content in the same course/unit share analysis through a content lock and cache.
- Duplicate topic names across chunks merge locally; concepts, definitions, prerequisites and page citations are retained. No extra AI merge call is needed.
- The prompt asks for complete topic coverage with concise explanations. **Maximum output tokens per request** controls the output ceiling, not a guaranteed output length. Truncated responses are rejected rather than saved as complete analyses.
- Provider-reported input, output, thinking and cached tokens are recorded per response. Settings displays recorded totals and per-agent usage. Cache hits make no new API request. Failed requests that return no usage metadata cannot be measured locally.

Text extraction and shorter responses can reduce token use, but savings depend on each source and response. More detailed output consumes more output tokens. No fixed reduction percentage or provider cost reduction has been measured or promised.

## Quotas and failures

Google applies rate limits per project, not per API key: [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Extra keys from one project do not add provider quota. Project labels are supplied by you; this app cannot discover the owning project from a key alone. Use workers only within the access and quota authorized for their projects.

- The existing primary project keeps its `gemini_calls` counter and configured budget. Additional project groups get separate local daily counters. Counters are not reset when agents are added or removed.
- A quota/rate-limit error pauses all configured keys sharing that project for five minutes. Invalid-key/access errors pause that key for an hour; other errors pause that key for one minute. These are cooldowns, not a guarantee that a provider quota has reset.
- Retries consume local request budget. Other available agents can continue the queue after an agent fails; the failed file remains pending for a later analysis run.
- If every agent is exhausted or unavailable, pending files remain saved. Provider quota and billing settings remain authoritative.

To use a provider other than Gemini would require another adapter; these worker key fields accept Gemini API keys only.
