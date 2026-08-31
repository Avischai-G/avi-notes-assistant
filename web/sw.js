/* Minimal installability service worker.
   Network-first for everything so deploys always win when online (stale-asset
   caching already bit this app once); the cache only answers when the network
   is unreachable, giving the installed app a working shell offline. API and
   WebSocket traffic is never cached. */
const CACHE = "agentonomy-shell-v3";
const SHELL = ["/", "/app.css", "/app.js", "/live.js", "/live-fx.js", "/icon-192.png", "/icon-512.png", "/icon-192-maskable.png", "/icon-512-maskable.png", "/a-mark.svg", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  // cache: "no-cache" forces revalidation past the browser's heuristic
  // HTTP cache, so a deploy really wins on the next load.
  const network = fetch(event.request.url, { cache: "no-cache", credentials: "same-origin" })
    .then((response) => {
      if (response.ok && url.origin === location.origin) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      }
      return response;
    });
  const cached = () => caches.match(event.request, { ignoreSearch: url.pathname === "/" });
  event.respondWith((async () => {
    // On a slow connection the shell must not hang behind the revalidating
    // fetch: after 3s of network silence the cached copy answers, while the
    // fetch keeps running above to refresh the cache for the next load.
    const timer = new Promise((resolve) => setTimeout(resolve, 3000));
    const first = await Promise.race([network.catch(() => null), timer]);
    if (first instanceof Response) return first;
    const hit = await cached();
    if (hit) return hit;
    return network; // nothing cached yet: the network is the only answer
  })());
  event.waitUntil(network.catch(() => {}));
});

self.addEventListener("push", (event) => {
  let payload = { title: "⏰ Reminder", body: "" };
  try { payload = { ...payload, ...event.data.json() }; } catch {}
  const options = {
    body: payload.body,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    vibrate: [200, 100, 200],
    // A repeat of the same reminder replaces its notification and re-alerts
    // instead of stacking duplicates.
    renotify: Boolean(payload.tag),
  };
  if (payload.tag) options.tag = payload.tag;
  if (payload.data) options.data = payload.data;
  if (payload.actions) options.actions = payload.actions;
  event.waitUntil(self.registration.showNotification(payload.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  if (event.action === "done") return; // acknowledged: nothing else to do
  if (event.action === "snooze") {
    const data = event.notification.data || {};
    event.waitUntil(fetch("/api/reminders/snooze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: data.task_id, title: data.title, minutes: 10 }),
    }).catch(() => {}));
    return;
  }
  // A plain press on the reminder itself just opens the app.
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => "focus" in w);
      return open ? open.focus() : self.clients.openWindow("/");
    }),
  );
});
