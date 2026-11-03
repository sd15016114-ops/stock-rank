/* 左側收放選單：兩個頁面共用。
   電腦（寬 900px 以上）：左邊固定一欄，按 ☰ 可以收成只剩圖示，收合狀態記在這台裝置。
   手機：平常收起來，按 ☰ 從左邊滑出，點旁邊或按 Esc 關掉。
   頁面只要在 header.top 裡放品牌名稱，載入這支程式就好；頁面裡的連結要點到哪一頁由這裡決定。 */
(function(){
  var ITEMS = [
    {id:'live', label:'盤中資金', sub:'板塊資金流向、熱力圖', href:'index.html',
     icon:'<path d="M3 17l5-6 4 3 6-8 3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="18" cy="6" r="1.6" fill="currentColor"/>'},
    {id:'rank', label:'排行與籌碼', sub:'台股成交值、法人買賣超', href:'rank.html',
     icon:'<path d="M5 20V11M12 20V5M19 20v-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'},
    {id:'us', label:'美股', sub:'美股成交值排行', href:'rank.html#us',
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
  + '.side nav a[aria-current]{background:var(--fill);color:var(--on-fill)}'
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
  /* 手機：從左邊滑出 */
  + '@media (max-width:899px){'
  +   '.side{transform:translateX(-102%);visibility:hidden;transition:transform .22s ease,visibility 0s .22s}'
  +   'body.side-open .side{visibility:visible;box-shadow:0 0 30px rgba(0,0,0,.25);transition:transform .22s ease}'
  +   'body.side-open .side{transform:none}'
  +   'body.side-open .scrim{opacity:1;pointer-events:auto}'
  +   'body.side-open{overflow:hidden}'
  + '}'
  + '@media (prefers-reduced-motion: reduce){.side,.scrim,body{transition:none !important}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var burger = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var side = document.createElement('aside');
  side.className = 'side'; side.id = 'appSide'; side.setAttribute('aria-label', '主選單');
  side.innerHTML = '<div class="sb"><button type="button" class="menubtn" id="sideToggle" aria-label="收合選單" title="收合／展開選單">'+burger+'</button><b>股市動能排行</b></div>'
    + '<nav>'+ITEMS.map(function(it){
        return '<a id="nav-'+it.id+'" href="'+pageUrl(it.href)+'" title="'+it.label+'"><svg viewBox="0 0 24 24" aria-hidden="true">'+it.icon+'</svg><span><b>'+it.label+'</b><small>'+it.sub+'</small></span></a>';
      }).join('')+'</nav>'
    + '<div class="foot">資料來源：證交所、櫃買中心、永豐金證券、Polygon。僅供參考，不構成投資建議。</div>';
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
  window.navMark = function(id){
    ITEMS.forEach(function(it){ var a = document.getElementById('nav-'+it.id); if(it.id===id) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current'); });
  };
  var isRank = /rank\.html/.test(location.pathname + location.search);
  window.navMark(isRank ? (location.hash==='#us' ? 'us' : 'rank') : 'live');
})();
