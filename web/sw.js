const CACHE_NAME = 'studyspace-offline-v1';
const ASSETS = [
  '/',
  '/index.html',
  '/study.html',
  '/companion.html',
  '/privacy.html',
  '/workspace.css',
  '/site.css',
  '/styles.css',
  '/theme.mjs',
  '/study.mjs',
  '/study-core.mjs',
  '/onboarding.mjs',
  '/demo.mjs',
  '/app.js',
  '/favicon.svg',
  '/manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // Never cache loopback companion requests
  if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response && response.status === 200 && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => caches.match('/study.html'));
    })
  );
});

