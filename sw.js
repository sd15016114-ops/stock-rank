/* 離線備援：一律先上網拿最新的，拿不到（沒網路、太慢）才用上次存下來的。
   行情資料（Supabase）不存，避免把舊的盤中數字當成最新的。 */
var CACHE = 'stock-rank-v4';
var SHELL = ['./', 'index.html', 'signals.html', 'rank.html', 'watch.html', 'manifest.webmanifest', 'icons/icon-192.png'];
self.addEventListener('install', function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL); }).catch(function(){}).then(function(){ return self.skipWaiting(); }));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(ks){ return Promise.all(ks.filter(function(k){ return k!==CACHE && k!=='stock-rank-badge'; }).map(function(k){ return caches.delete(k); })); })
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

/* 主畫面圖示上的數字：推播帶 badge 就累加，打開 App 時由頁面清掉（數字存在快取裡，Service Worker 隨時會被系統關掉） */
function addBadge(n){
  if(!self.navigator || !self.navigator.setAppBadge) return null;
  return caches.open('stock-rank-badge').then(function(c){
    return c.match('n').then(function(r){ return r ? r.text() : '0'; }).then(function(t){
      var v = (parseInt(t, 10) || 0) + n;
      return c.put('n', new Response(String(v))).then(function(){ return self.navigator.setAppBadge(v); });
    });
  }).catch(function(){});
}
self.addEventListener('message', function(e){
  if(e.data==='clear-badge') e.waitUntil(caches.open('stock-rank-badge').then(function(c){ return c.delete('n'); }));
});

/* 推播：收到就顯示，點了打開對應的頁面 */
self.addEventListener('push', function(e){
  var d = {};
  try{ d = e.data ? e.data.json() : {}; }catch(err){ d = {title: 'Tide', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(Promise.all([
    self.registration.showNotification(d.title || 'Tide', {
      body: d.body || '', icon: 'icons/icon-192.png', badge: 'icons/icon-192.png', tag: d.tag, data: {url: d.url || './'}
    }),
    d.badge ? addBadge(d.badge) : null
  ]));
});
self.addEventListener('notificationclick', function(e){
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || './';
  e.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(function(list){
    for(var i = 0; i < list.length; i++){ if('focus' in list[i]){ list[i].navigate(url).catch(function(){}); return list[i].focus(); } }
    return clients.openWindow(url);
  }));
});
