"use strict";

const CACHE_PREFIX = "frontier-pulse-";
const CACHE_NAME = `${CACHE_PREFIX}v1.5`;
const APP_SHELL = [
  "./",
  "./index.html",
  "./assets/styles.css",
  "./assets/app.js",
  "./favicon.svg",
  "./og-card.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => Promise.allSettled(APP_SHELL.map((path) => cache.add(path))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME).map((key) => caches.delete(key))
  )).then(() => self.clients.claim()));
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request, { ignoreSearch: false });
    if (cached) return cached;
    throw error;
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request, { ignoreSearch: false });
  const update = fetch(request).then(async (response) => {
    if (response.ok) await cache.put(request, response.clone());
    return response;
  });
  return cached || update;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.searchParams.has("t") || request.cache === "no-store") {
    event.respondWith(fetch(request));
    return;
  }
  const isData = url.pathname.includes("/data/") || url.pathname.endsWith("/feed.xml");
  event.respondWith(isData ? networkFirst(request) : staleWhileRevalidate(request));
});
