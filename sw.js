/* 離線備援：一律先上網拿最新的，拿不到（沒網路、太慢）才用上次存下來的。
   行情資料（Supabase）不存，避免把舊的盤中數字當成最新的。 */
var CACHE = 'stock-rank-v1';
var SHELL = ['./', 'index.html', 'signals.html', 'rank.html', 'manifest.webmanifest', 'icons/icon-192.png'];
self.addEventListener('install', function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL); }).catch(function(){}).then(function(){ return self.skipWaiting(); }));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(ks){ return Promise.all(ks.filter(function(k){ return k!==CACHE; }).map(function(k){ return caches.delete(k); })); })
    .then(function(){ return self.clients.claim(); }));
});
self.addEventListener('fetch', function(e){
  var req = e.request, url = new URL(req.url);
  if(req.method!=='GET' || /supabase\.co$/.test(url.hostname)) return;
  var mine = url.origin===location.origin || url.hostname==='raw.githubusercontent.com' || /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  if(!mine) return;
  var key = url.hostname==='raw.githubusercontent.com' ? url.origin+url.pathname : req;   /* 資料網址後面的 ?t= 不影響快取 */
  e.respondWith(
    fetch(req).then(function(res){
      if(res && (res.ok || res.type==='opaque')){ var copy = res.clone(); caches.open(CACHE).then(function(c){ c.put(key, copy); }); }
      return res;
    }).catch(function(){
      return caches.match(key, {ignoreSearch: url.origin===location.origin}).then(function(r){ return r || caches.match('index.html'); });
    })
  );
});
