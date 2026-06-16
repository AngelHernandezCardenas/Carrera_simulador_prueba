const CACHE_NAME = 'gps-tracker-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Para esta app, siempre intentamos ir a la red primero porque los datos (el mapa, los scripts)
  // necesitan estar frescos, especialmente los websockets y las peticiones POST.
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
