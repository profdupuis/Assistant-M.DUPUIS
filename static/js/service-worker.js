const CACHE_NAME = 'assistant-cache-v1';
const URLS_TO_CACHE = [
  '/', // utile si tu rediriges après login
  '/static/css/style.css',
  '/static/js/ia_interface.js',
  '/static/img/icon_libre_512.png',
  '/static/img/icon_send.png',
  '/static/img/icon_burger.png',
  '/static/img/icon_home.png',
  '/offline.html'
];

// Installation du service worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(URLS_TO_CACHE);
    })
  );
});

// Activation (nettoyage des anciens caches si besoin)
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
    )
  );
});

// Gestion des requêtes
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request).then(response => {
      return response || caches.match('/offline.html');
    }))
  );
});
