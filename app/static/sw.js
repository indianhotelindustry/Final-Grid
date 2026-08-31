/**
 * FinalGrid Service Worker — Offline-First
 *
 * Strategy:
 *  - HTML pages  → Network-first (never cache; each page carries a CSP nonce
 *                  that changes per request — caching HTML would cause nonce
 *                  mismatch and break all inline scripts).
 *  - Static assets (CSS / JS / fonts from /static/) → Cache-first,
 *                  fallback to network.
 *  - API GET requests → Network-first, cache fallback for read-only data.
 */

const CACHE_NAME = 'pms-static-v5';
const API_CACHE  = 'pms-api-v1';

// Only cache truly static, immutable assets — never HTML
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/vendor/bootstrap/css/bootstrap.min.css',
    '/static/vendor/bootstrap/js/bootstrap.bundle.min.js',
    '/static/vendor/bootstrap-icons/font/bootstrap-icons.css',
    '/static/vendor/bootstrap-icons/font/fonts/bootstrap-icons.woff2',
    '/static/vendor/chartjs/chart.umd.min.js',
];

// Styled offline fallback page
const OFFLINE_PAGE = `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline</title>
<link href="/static/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="/static/vendor/bootstrap-icons/font/bootstrap-icons.css">
</head><body class="bg-light">
<div class="container py-5 text-center" style="max-width:520px">
  <div class="card shadow-sm p-5 rounded-4">
    <div style="font-size:3rem" class="text-warning mb-3"><i class="bi bi-wifi-off"></i></div>
    <h3 class="mb-3">You are offline</h3>
    <p class="text-muted mb-4">The server is not reachable right now. Your data is safe — the PMS
    will resume normal operation as soon as the network connection is restored.</p>
    <button class="btn btn-primary" onclick="location.reload()">
      <i class="bi bi-arrow-clockwise me-1"></i> Retry
    </button>
  </div>
</div></body></html>`;

// Install: pre-cache static assets only
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// Activate: remove old caches
self.addEventListener('activate', event => {
    const keep = new Set([CACHE_NAME, API_CACHE]);
    event.waitUntil(
        caches.keys().then(names =>
            Promise.all(
                names.filter(n => !keep.has(n)).map(n => caches.delete(n))
            )
        ).then(() => self.clients.claim())
    );
});

// Fetch: strategy depends on request type
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    const isHTML = event.request.headers.get('accept')?.includes('text/html');
    const isNavigation = event.request.mode === 'navigate';
    const isAPIGet = url.pathname.startsWith('/api/') && event.request.method === 'GET';

    // HTML / navigation requests: always go to network (preserves CSP nonce)
    if (isHTML || isNavigation) {
        event.respondWith(
            fetch(event.request).catch(() =>
                new Response(OFFLINE_PAGE, {
                    headers: { 'Content-Type': 'text/html' }
                })
            )
        );
        return;
    }

    // API GET requests: network-first with cache fallback for read-only data
    if (isAPIGet) {
        event.respondWith(
            fetch(event.request).then(response => {
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(API_CACHE).then(c => c.put(event.request, clone));
                }
                return response;
            }).catch(() => caches.match(event.request))
        );
        return;
    }

    // Static assets: cache-first, network fallback
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;
            return fetch(event.request).then(response => {
                // Cache successful static asset responses
                if (response.ok && url.pathname.startsWith('/static/')) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            });
        })
    );
});
