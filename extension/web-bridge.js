// Studyspace Web Bridge - connects website pages with extension storage & features
(function () {
  'use strict';

  document.documentElement.dataset.studyspaceExtension = 'true';
  window.__STUDYSPACE_EXTENSION_ACTIVE__ = true;

  window.addEventListener('message', async (event) => {
    if (event.source !== window || !event.data || !event.data.type?.startsWith('STUDYSPACE_')) return;

    if (event.data.type === 'STUDYSPACE_PING') {
      window.postMessage({ type: 'STUDYSPACE_PONG', version: '0.1.2' }, '*');
    } else if (event.data.type === 'STUDYSPACE_GET_DATA') {
      try {
        const result = await chrome.storage.local.get(['studyspace_study', 'muj_logged_in', 'muj_last_seen']);
        window.postMessage({ type: 'STUDYSPACE_DATA_RESPONSE', payload: result }, '*');
      } catch (err) {
        window.postMessage({ type: 'STUDYSPACE_DATA_RESPONSE', error: err.message }, '*');
      }
    } else if (event.data.type === 'STUDYSPACE_SAVE_DATA') {
      try {
        await chrome.storage.local.set({ studyspace_study: event.data.payload });
        window.postMessage({ type: 'STUDYSPACE_SAVE_RESPONSE', ok: true }, '*');
      } catch (err) {
        window.postMessage({ type: 'STUDYSPACE_SAVE_RESPONSE', error: err.message }, '*');
      }
    }
  });

  window.postMessage({ type: 'STUDYSPACE_EXTENSION_READY', version: '0.1.2' }, '*');
})();

