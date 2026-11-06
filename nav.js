/* 選單：兩個頁面共用，任何時候都看得到。
   電腦（寬 900px 以上）：左邊固定一欄，按 ☰ 可以收成只剩圖示，收合狀態記在這台裝置。
   平板（600～899px）：左邊固定一條只有圖示的窄欄。
   手機（600px 以下）：畫面最下面固定一排分頁按鈕，跟一般 App 一樣。
   頁面只要在 header.top 裡放品牌名稱，載入這支程式就好；頁面裡的連結要點到哪一頁由這裡決定。 */
(function(){
  var ITEMS = [
    {id:'live', short:'盤中資金', label:'盤中資金', sub:'板塊資金流向、熱力圖', href:'index.html',
     icon:'<path d="M3 17l5-6 4 3 6-8 3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="18" cy="6" r="1.6" fill="currentColor"/>'},
    {id:'rank', short:'成交值', label:'成交值排行', sub:'台股成交值、放大倍數', href:'rank.html',
     icon:'<path d="M5 20V11M12 20V5M19 20v-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'},
    {id:'chips', short:'法人籌碼', label:'法人籌碼', sub:'三大法人買賣超', href:'rank.html#chips',
     icon:'<circle cx="8" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.9"/><circle cx="16.5" cy="9.5" r="2.6" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M2.8 19c.6-3.4 2.7-5.2 5.2-5.2s4.6 1.8 5.2 5.2M13.6 15.2c.9-.9 1.9-1.3 2.9-1.3 2.1 0 3.8 1.6 4.3 4.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>'},
    {id:'us', short:'美股', label:'美股', sub:'美股成交值排行', href:'rank.html#us',
     icon:'<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M3.5 12h17M12 3.5c2.6 2.4 2.6 14.6 0 17M12 3.5c-2.6 2.4-2.6 14.6 0 17" fill="none" stroke="currentColor" stroke-width="1.6"/>'}
  ];

  /* 分支預覽（htmlpreview）底下，頁面之間的連結要換成預覽網址 */
  function pageUrl(file){
    var g = /(https:\/\/github\.com\/[^/]+\/[^/]+\/blob\/[^/]+\/)/.exec(location.search);
    if(location.hostname==='htmlpreview.github.io' && g) return 'https://htmlpreview.github.io/?'+g[1]+file;
    return file==='index.html' ? './' : file;
  }
  window.pageUrl = pageUrl;

  var css = ''
  + ':root{--side-w:232px;--side-mini:68px}'
  + '.side{position:fixed;z-index:40;top:0;bottom:0;left:0;width:var(--side-w);background:var(--sheet);border-right:1px solid var(--rule);display:flex;flex-direction:column;transition:width .22s ease,transform .22s ease;overflow:hidden}'
  + '.side .sb{display:flex;align-items:center;gap:10px;height:68px;padding:0 14px 0 16px;flex:none}'
  + '.side .sb b{font-family:var(--serif);font-weight:900;font-size:19px;color:var(--accent);white-space:nowrap}'
  + '.side nav{display:flex;flex-direction:column;gap:4px;padding:6px 10px}'
  + '.side nav a{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:12px;color:var(--ink);text-decoration:none;white-space:nowrap}'
  + '.side nav a svg{flex:none;width:22px;height:22px;color:var(--muted)}'
  + '.side nav a span{display:flex;flex-direction:column;line-height:1.3;min-width:0}'
  + '.side nav a span b{font-size:15px;font-weight:700}'
  + '.side nav a span small{font-size:12px;color:var(--muted)}'
  + '.side nav a:hover{background:var(--tint)}'
  + '.side nav{position:relative}'
  + '.side nav a{position:relative;z-index:1;transition:color .25s}'
  + '.side nav a[aria-current]{color:var(--on-fill)}'
  + '.side nav a[aria-current]:hover{background:transparent}'
  + '.sthumb{position:absolute;left:10px;right:10px;top:0;height:0;border-radius:12px;background:var(--fill);box-shadow:0 1px 3px rgba(0,0,0,.15);transition:transform .32s cubic-bezier(.4,0,.2,1),height .32s cubic-bezier(.4,0,.2,1)}'
  + '.tthumb{position:absolute;top:0;left:0;width:52px;height:26px;border-radius:999px;background:var(--fill);transition:transform .32s cubic-bezier(.4,0,.2,1)}'
  + '.still .sthumb,.still .tthumb{transition:none !important}'
  /* 換頁時整頁淡入淡出，選單本身不動（支援的瀏覽器才有） */
  + '@view-transition{navigation:auto}'
  + '.tabbar{view-transition-name:tabbar}.side{view-transition-name:side}'
  + '::view-transition-old(root),::view-transition-new(root){animation-duration:.22s}'
  + '.side nav a[aria-current] svg,.side nav a[aria-current] small{color:var(--on-fill)}'
  + '.side .foot{margin-top:auto;padding:14px 18px 18px;font-size:12px;line-height:1.6;color:var(--muted);white-space:normal}'
  + '.menubtn{flex:none;width:40px;height:40px;display:grid;place-items:center;border-radius:12px;border:1px solid var(--rule);background:var(--tint);color:var(--ink);cursor:pointer;padding:0}'
  + '.menubtn svg{width:20px;height:20px}'
  + '.side .menubtn{background:transparent;border-color:transparent}'
  + '.side .menubtn:hover{background:var(--tint)}'
  + 'header.top .lead-in{display:flex;align-items:center;gap:12px}'
  + '.scrim{position:fixed;inset:0;z-index:39;background:rgba(0,0,0,.38);opacity:0;pointer-events:none;transition:opacity .2s}'
  /* 電腦：常駐在左邊，可以收成只剩圖示 */
  + '@media (min-width:900px){'
  +   'body{padding-left:var(--side-w);transition:padding-left .22s ease}'
  +   'body.side-mini{padding-left:var(--side-mini)}'
  +   'body.side-mini .side{width:var(--side-mini)}'
  +   'body.side-mini .side .sb b,body.side-mini .side nav a span,body.side-mini .side .foot{display:none}'
  +   'body.side-mini .side nav a{justify-content:center;padding:10px 0}'
  +   'body.side-mini .side .sb{justify-content:center;padding:0}'
  +   'header.top .menubtn,header.top .lead-in .brand{display:none}'
  + '}'
  /* 平板：常駐一條只有圖示的窄欄 */
  + '@media (min-width:600px) and (max-width:899px){'
  +   'body{padding-left:var(--side-mini)}'
  +   '.side{width:var(--side-mini)}'
  +   '.side .sb,.side nav a span,.side .foot{display:none}'
  +   '.side nav{padding-top:14px}'
  +   '.side nav a{justify-content:center;padding:10px 0}'
  +   'header.top .menubtn{display:none}'
  + '}'
  /* 手機：最下面一排分頁按鈕 */
  + '.tabbar{display:none}'
  + '@media (max-width:599px){'
  +   '.side,.scrim,header.top .menubtn{display:none !important}'
  +   'body{padding-bottom:calc(64px + env(safe-area-inset-bottom,0px))}'
  +   '.tabbar{display:flex;position:fixed;z-index:40;left:0;right:0;bottom:0;background:var(--sheet);border-top:1px solid var(--rule);padding:4px 4px calc(4px + env(safe-area-inset-bottom,0px));box-shadow:0 -4px 16px rgba(0,0,0,.06)}'
  +   '.tabbar a{position:relative;z-index:1;flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 0;border-radius:12px;color:var(--muted);text-decoration:none;font-size:11px;font-weight:500;transition:color .25s}'
  +   '.tabbar a svg{width:52px;height:26px;padding:2px 14px;box-sizing:border-box;transition:color .25s}'
  +   '.tabbar a[aria-current]{color:var(--accent);font-weight:700}'
  +   '.tabbar a[aria-current] svg{color:var(--on-fill)}'
  + '}'
  + '@media (prefers-reduced-motion: reduce){.side,.scrim,body{transition:none !important}}'
  /* ===== 果凍效果：滑塊的前緣先跑、後緣晚一點跟上（移動時被拉長），到定點用彈簧曲線微微彈一下；按住時稍微壓扁 ===== */
  + '@property --l{syntax:"<length>";inherits:false;initial-value:0px}'
  + '@property --r{syntax:"<length>";inherits:false;initial-value:0px}'
  + ':root{--spring:linear(0,.16 5%,.52 12%,.84 20%,1.02 28%,1.07 34%,1.06 40%,1.02 50%,.995 62%,.99 72%,1)}'
  + '.seg .thumb,.tthumb{left:var(--l) !important;width:calc(var(--r) - var(--l)) !important;transform:none}'
  + '.tthumb{top:var(--tt,0px)}'
  + '.seg .thumb,.tthumb,.sthumb{transition:--l .5s var(--spring),--r .5s var(--spring),--t .5s var(--spring),--b .5s var(--spring),scale .25s var(--spring)}'
  + '.seg.press .thumb,.tabbar.press .tthumb,.side nav.press .sthumb{scale:.94}'
  + '.theme i{transition:transform .55s var(--spring) !important}'
  + '@property --t{syntax:"<length>";inherits:false;initial-value:0px}'
  + '@property --b{syntax:"<length>";inherits:false;initial-value:0px}'
  + '.sthumb{top:var(--t) !important;height:calc(var(--b) - var(--t)) !important;transform:none !important}'
  /* 底部分頁列：半透明毛玻璃，後面的內容隱約透出來 */
  + '@media (max-width:599px){.tabbar{background:color-mix(in srgb,var(--sheet) 72%,transparent) !important;-webkit-backdrop-filter:blur(22px) saturate(1.7);backdrop-filter:blur(22px) saturate(1.7)}'
  +   '.tthumb{box-shadow:0 1px 4px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.35)}}'
  + '@media (prefers-reduced-motion: reduce){.seg .thumb,.tthumb,.sthumb{transition-timing-function:ease !important;transition-delay:0s !important}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  /* 把滑塊的兩個邊移到 a～b。往哪邊走，那一邊先動、另一邊晚 70ms 才跟上，看起來就像果凍被拉長再彈回去 */
  var LAG = 55;
  function edges(el, a, b, still, vert){
    var A = vert ? '--t' : '--l', B = vert ? '--b' : '--r';
    var a0 = parseFloat(el.style.getPropertyValue(A)), b0 = parseFloat(el.style.getPropertyValue(B));
    if(Math.abs(a0-a)<0.5 && Math.abs(b0-b)<0.5) return;   /* 已經在往這裡走（或已經到了），不要打斷正在跑的動畫 */
    if(still || isNaN(a0)){
      el.style.transitionProperty = 'none';
      el.style.setProperty(A, a+'px'); el.style.setProperty(B, b+'px');
      void el.offsetWidth; el.style.transitionProperty = '';
      return;
    }
    var fwd = a > a0;                                 /* 往右（或往下）走 */
    el.style.transitionDelay = vert
      ? (fwd ? '0s,0s,'+LAG+'ms,0s,0s' : '0s,0s,0s,'+LAG+'ms,0s')
      : (fwd ? LAG+'ms,0s,0s,0s,0s' : '0s,'+LAG+'ms,0s,0s,0s');
    el.style.setProperty(A, a+'px'); el.style.setProperty(B, b+'px');
  }
  window.jelly = edges;
  /* 按住按鈕時滑塊稍微壓扁 */
  function pressable(root, sel){
    root.addEventListener('pointerdown', function(e){ var g = e.target.closest(sel); if(g) g.classList.add('press'); });
    ['pointerup','pointercancel','pointerleave'].forEach(function(t){ root.addEventListener(t, function(){ document.querySelectorAll('.press').forEach(function(x){ x.classList.remove('press'); }); }, true); });
  }
  pressable(document, '.seg');

  var burger = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var side = document.createElement('aside');
  side.className = 'side'; side.id = 'appSide'; side.setAttribute('aria-label', '主選單');
  side.innerHTML = '<div class="sb"><button type="button" class="menubtn" id="sideToggle" aria-label="收合選單" title="收合／展開選單">'+burger+'</button><b>股市動能排行</b></div>'
    + '<nav><i class="sthumb" aria-hidden="true"></i>'+ITEMS.map(function(it){
        return '<a id="nav-'+it.id+'" href="'+pageUrl(it.href)+'" title="'+it.label+'"><svg viewBox="0 0 24 24" aria-hidden="true">'+it.icon+'</svg><span><b>'+it.label+'</b><small>'+it.sub+'</small></span></a>';
      }).join('')+'</nav>'
    + '<div class="foot">資料來源：證交所、櫃買中心、永豐金證券、Polygon。僅供參考，不構成投資建議。</div>';
  var tabs = document.createElement('nav');
  tabs.className = 'tabbar'; tabs.setAttribute('aria-label', '主選單');
  tabs.innerHTML = '<i class="tthumb" aria-hidden="true"></i>'+ITEMS.map(function(it){
    return '<a id="tab-'+it.id+'" href="'+pageUrl(it.href)+'"><svg viewBox="0 0 24 24" aria-hidden="true">'+it.icon+'</svg>'+it.short+'</a>';
  }).join('');
  document.body.appendChild(tabs);
  var scrim = document.createElement('div'); scrim.className = 'scrim';
  document.body.insertBefore(scrim, document.body.firstChild);
  document.body.insertBefore(side, document.body.firstChild);

  /* 頁首左邊放 ☰（手機用）；品牌名稱在電腦版改由左側選單顯示 */
  var head = document.querySelector('header.top'), brand = head && head.querySelector('.brand');
  if(head && brand){
    var wrap = document.createElement('div'); wrap.className = 'lead-in';
    head.insertBefore(wrap, brand);
    wrap.innerHTML = '<button type="button" class="menubtn" id="menuOpen" aria-label="打開選單" aria-controls="appSide" aria-expanded="false">'+burger+'</button>';
    wrap.appendChild(brand);
    brand.href = pageUrl('index.html');
  }

  function wide(){ return window.matchMedia('(min-width:900px)').matches; }
  try{ if(localStorage.getItem('stock-rank-side')==='mini') document.body.classList.add('side-mini'); }catch(e){}
  function setOpen(on){
    document.body.classList.toggle('side-open', on);
    var b = document.getElementById('menuOpen'); if(b) b.setAttribute('aria-expanded', on ? 'true' : 'false');
  }
  document.getElementById('sideToggle').addEventListener('click', function(){
    if(!wide()){ setOpen(false); return; }
    var mini = document.body.classList.toggle('side-mini');
    try{ localStorage.setItem('stock-rank-side', mini ? 'mini' : 'full'); }catch(e){}
    setTimeout(function(){ window.dispatchEvent(new Event('resize')); }, 240);   /* 讓按鈕滑塊、熱力圖重新量寬度 */
  });
  var ob = document.getElementById('menuOpen'); if(ob) ob.addEventListener('click', function(){ setOpen(true); });
  scrim.addEventListener('click', function(){ setOpen(false); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && document.body.classList.contains('side-open')) setOpen(false); });
  side.addEventListener('click', function(e){ if(e.target.closest('nav a') && !wide()) setOpen(false); });

  /* 目前在哪一頁：頁面可以呼叫 navMark('rank'|'us'|'live') 改亮起來的項目 */
  var CUR = null;
  function placeThumbs(still){                       /* 把滑塊移到目前的項目，跟頁面上的滑動切換鈕同一種動畫 */
    var t = document.getElementById('tab-'+CUR), tt = tabs.querySelector('.tthumb');
    var a = document.getElementById('nav-'+CUR), st = side.querySelector('.sthumb');
    [tabs, side].forEach(function(el){ if(still) el.classList.add('still'); });
    if(t && t.offsetWidth){
      var r = t.querySelector('svg').getBoundingClientRect(), base = tabs.getBoundingClientRect();
      tt.style.setProperty('--tt', (r.top-base.top)+'px');
      edges(tt, r.left-base.left, r.right-base.left, still);
    }
    if(a && a.offsetHeight) edges(st, a.offsetTop, a.offsetTop+a.offsetHeight, still, true);
    if(still){ void tabs.offsetWidth; void side.offsetWidth; requestAnimationFrame(function(){ tabs.classList.remove('still'); side.classList.remove('still'); }); }
  }
  window.navMark = function(id, still){
    CUR = id;
    ITEMS.forEach(function(it){ ['nav-','tab-'].forEach(function(pre){
      var a = document.getElementById(pre+it.id); if(!a) return;
      if(it.id===id) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
    }); });
    placeThumbs(still);
  };
  window.addEventListener('resize', function(){ placeThumbs(true); });
  /* 點選單：同一頁裡切換（成交值、籌碼、美股）直接換；要換到另一頁時，先讓滑塊滑過去再換頁 */
  function onNav(e){
    var a = e.target.closest('a[id^="nav-"],a[id^="tab-"]');
    if(!a || e.defaultPrevented || e.button!==0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var id = a.id.replace(/^(nav|tab)-/, '');
    if(id===CUR){ e.preventDefault(); window.scrollTo({top:0, behavior:'smooth'}); return; }
    var sameDoc = isRank && id!=='live';
    if(sameDoc) return;                               /* 交給網址的 # 切換，頁面自己會換內容 */
    e.preventDefault();
    window.navMark(id);
    var href = a.href;
    setTimeout(function(){ location.href = href; }, 260);
  }
  tabs.addEventListener('click', onNav); side.addEventListener('click', onNav);
  pressable(tabs, '.tabbar'); pressable(side, '.side nav');
  var isRank = /rank\.html/.test(location.pathname + location.search);
  window.navMark(isRank ? ({'#us':'us', '#chips':'chips'}[location.hash] || 'rank') : 'live', true);
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ placeThumbs(true); });
})();
