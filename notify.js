/* 自選股與通知設定。
   自選股：存在這台裝置（localStorage）；開了通知的話也一起存到 Supabase，推播時才知道要列哪些。
   通知：右上角鈴鐺 → 開啟通知 → 瀏覽器訂閱推播 → 存到 Supabase（push_save），GitHub 排程依設定傳通知。 */
(function(){
  var SB = {url:'https://yydcsmxnqudluancdowo.supabase.co', key:'sb_publishable_XgJSPBpQXcNdTCDT4pvA3w_NXpbkCn6'};
  var VAPID = 'BNUZB1N8x1Uq6LVZx7TVEAht49iFsl1iWOXonjJRjRWxo8klTSuPWoVBO6kVaahRlFkPJU9Sa2h1GIPnDqgP2qc';
  var KW = 'stock-rank-watch', KP = 'stock-rank-push';

  function lsGet(k, d){ try{ var v = JSON.parse(localStorage.getItem(k)); return v==null ? d : v; }catch(e){ return d; } }
  function lsSet(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
  function esc(t){ return String(t==null?'':t).replace(/[&<>"]/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function rpc(fn, body){
    return fetch(SB.url+'/rest/v1/rpc/'+fn, {method:'POST', headers:{apikey:SB.key, 'Content-Type':'application/json'}, body:JSON.stringify(body), cache:'no-store'})
      .then(function(r){ if(!r.ok) throw new Error(r.status); return r.text(); }).then(function(t){ return t ? JSON.parse(t) : null; });
  }

  /* ---------- 自選股 ---------- */
  var listeners = [];
  function fire(){ listeners.forEach(function(f){ try{ f(); }catch(e){} }); }
  function saveLocal(l){ lsSet(KW, l); sync(); fire(); }

  window.Watch = {
    list: function(){ return lsGet(KW, []); },
    has: function(code){ return this.list().some(function(x){ return x[0]===code; }); },
    toggle: function(code, name){
      var l = this.list(), i = -1;
      l.forEach(function(x,k){ if(x[0]===code) i = k; });
      if(i>=0) l.splice(i,1); else l.push([code, name||code]);
      saveLocal(l);
      return i<0;
    },
    move: function(code, d){
      var l = this.list(), i = -1;
      l.forEach(function(x,k){ if(x[0]===code) i = k; });
      var j = i + d; if(i<0 || j<0 || j>=l.length) return;
      var t = l[i]; l[i] = l[j]; l[j] = t; saveLocal(l);
    },
    onChange: function(f){ listeners.push(f); },
  };

  /* ---------- 推播訂閱 ---------- */
  var ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform==='MacIntel' && navigator.maxTouchPoints>1);
  var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone===true;
  var supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  function prefs(){ var p = lsGet(KP, {}); return {close: p.close!==false, signals: p.signals!==false, intraday: p.intraday!==false, watch: window.Watch.list().map(function(x){ return x[0]; })}; }
  function b64(s){ s = s.replace(/-/g,'+').replace(/_/g,'/'); s += '===='.slice(s.length%4 || 4); var r = atob(s), a = new Uint8Array(r.length); for(var i=0;i<r.length;i++) a[i] = r.charCodeAt(i); return a; }
  function reg(){ return navigator.serviceWorker.register('sw.js').then(function(){ return navigator.serviceWorker.ready; }); }
  function current(){ return supported ? reg().then(function(r){ return r.pushManager.getSubscription(); }) : Promise.resolve(null); }
  function sync(){
    return current().then(function(s){ if(s) return rpc('push_save', {sub: s.toJSON(), prefs: prefs()}); }).catch(function(){});
  }
  function enable(){
    return Notification.requestPermission().then(function(p){
      if(p!=='granted') throw new Error('denied');
      return reg();
    }).then(function(r){
      return r.pushManager.getSubscription().then(function(s){ return s || r.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:b64(VAPID)}); });
    }).then(function(s){ return rpc('push_save', {sub: s.toJSON(), prefs: prefs()}); });
  }
  function disable(){
    return current().then(function(s){ if(!s) return; var ep = s.endpoint; return s.unsubscribe().then(function(){ return rpc('push_remove', {ep: ep}); }); });
  }

  /* ---------- 介面 ---------- */
  var css = ''
  + '.ntbtn{position:relative}'
  + '.ntbtn.on::after{content:"";position:absolute;top:7px;right:8px;width:8px;height:8px;border-radius:50%;background:var(--seal);box-shadow:0 0 0 2px var(--tint)}'
  + '.nt-scrim{position:fixed;inset:0;background:rgba(0,0,0,.36);opacity:0;pointer-events:none;transition:opacity .25s;z-index:68}'
  + '.nt-sheet{position:fixed;z-index:69;background:var(--paper);color:var(--ink);overflow-y:auto;overscroll-behavior:contain;box-shadow:0 0 40px rgba(0,0,0,.25);transition:transform .4s cubic-bezier(.2,.9,.25,1.05)}'
  + '@media (min-width:760px){.nt-sheet{top:0;right:0;bottom:0;width:420px;max-width:100vw;transform:translateX(105%)}}'
  + '@media (max-width:759px){.nt-sheet{left:0;right:0;bottom:0;max-height:88vh;border-radius:20px 20px 0 0;transform:translateY(105%);padding-bottom:env(safe-area-inset-bottom,0px)}}'
  + 'body.nt-open .nt-scrim{opacity:1;pointer-events:auto}body.nt-open .nt-sheet{transform:none}body.nt-open{overflow:hidden}'
  + '.nt-in{padding:18px 20px 28px}'
  + '.nt-in h2{font-family:var(--serif);font-weight:900;font-size:24px;margin:0;display:flex;justify-content:space-between;align-items:center}'
  + '.nt-x{border:0;background:var(--tint);color:var(--ink);width:34px;height:34px;border-radius:50%;font-size:18px;cursor:pointer}'
  + '.nt-st{margin:14px 0;padding:12px 14px;border-radius:12px;background:var(--tint);font-size:14px;line-height:1.6}'
  + '.nt-st b{display:block;font-size:15px}'
  + '.nt-main{width:100%;padding:12px;border:0;border-radius:12px;background:var(--accent);color:var(--paper);font:inherit;font-weight:700;font-size:16px;cursor:pointer}'
  + '.nt-main.off{background:var(--tint);color:var(--ink);border:1px solid var(--rule)}'
  + '.nt-main:disabled{opacity:.45;cursor:default}'
  + '.nt-sec{margin-top:22px}.nt-sec h3{font-size:15px;margin:0 0 8px}'
  + '.nt-opt{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--rule);cursor:pointer}'
  + '.nt-opt input{width:20px;height:20px;margin:2px 0 0;accent-color:var(--accent);flex:none}'
  + '.nt-opt span{font-size:15px}.nt-opt small{display:block;font-size:13px;color:var(--muted);margin-top:2px}'
  + '.nt-add{display:flex;gap:8px}'
  + '.nt-add input{flex:1;min-width:0;padding:10px 12px;border-radius:10px;border:1px solid var(--rule);background:var(--sheet);color:var(--ink);font:inherit;font-size:16px}'
  + '.nt-add button{padding:0 16px;border-radius:10px;border:1px solid var(--rule);background:var(--soft);color:var(--accent);font:inherit;font-weight:700;cursor:pointer}'
  + '.nt-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}'
  + '.nt-chips span{display:inline-flex;align-items:center;gap:6px;padding:6px 6px 6px 12px;border-radius:999px;background:var(--tint);border:1px solid var(--rule);font-size:14px}'
  + '.nt-chips span b{font-weight:700;cursor:pointer}.nt-chips small{color:var(--muted)}'
  + '.nt-chips button{border:0;background:none;color:var(--muted);font-size:16px;cursor:pointer;width:24px;height:24px;border-radius:50%;padding:0}'
  + '.nt-chips button:hover{background:var(--soft)}'
  + '.nt-msg{font-size:13px;color:var(--muted);margin-top:8px;min-height:1em}'
  + '.nt-fine{font-size:12px;color:var(--muted);margin-top:18px;line-height:1.6}'
  + '.nt-test{margin-top:10px;border:0;background:none;color:var(--accent);font:inherit;font-size:14px;cursor:pointer;padding:4px 0}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var scrim = document.createElement('div'); scrim.className = 'nt-scrim';
  var sheet = document.createElement('aside'); sheet.className = 'nt-sheet'; sheet.setAttribute('role','dialog'); sheet.setAttribute('aria-modal','true'); sheet.setAttribute('aria-label','通知');
  sheet.innerHTML = '<div class="nt-in" id="ntIn"></div>';
  document.body.appendChild(scrim); document.body.appendChild(sheet);
  var IN = sheet.querySelector('#ntIn');

  var btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'refbtn ntbtn'; btn.title = '通知'; btn.setAttribute('aria-label', '通知');
  btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  function place(){
    var rb = document.getElementById('refreshBtn');
    if(rb && rb.parentNode){ rb.parentNode.insertBefore(btn, rb); return true; }
    var h = document.querySelector('header.top .right'); if(h){ h.insertBefore(btn, h.firstChild); return true; }
    return false;
  }
  if(!place()) document.addEventListener('DOMContentLoaded', place);

  var on = false, busy = false, msg = '';
  function refreshState(){ return current().then(function(s){ on = !!s && Notification.permission==='granted'; btn.classList.toggle('on', on); }, function(){}); }
  refreshState();

  function render(){
    var p = prefs(), state, can = supported;
    if(!supported && ios && !standalone){ state = '<b>先把網站加到主畫面</b>iPhone 只有從主畫面的圖示打開，才能收通知：在 Safari 按分享 →「加入主畫面」，再從那個圖示打開這裡。'; can = false; }
    else if(!supported){ state = '<b>這個瀏覽器不支援通知</b>請改用 Chrome、Edge，或 iPhone 上加到主畫面的版本。'; }
    else if(Notification.permission==='denied'){ state = '<b>通知被擋住了</b>'+(ios ? '請到 iPhone「設定 → 通知 → Tide」打開允許通知。' : '請點網址列左邊的圖示，把「通知」改成允許。'); can = false; }
    else if(on){ state = '<b>通知已開啟</b>這台裝置會收到你勾選的通知。'; }
    else { state = '<b>通知還沒開</b>開啟後，收盤和盤後會把重點直接推到這台裝置。'; }
    IN.innerHTML = '<h2>通知<button class="nt-x" aria-label="關閉">×</button></h2>'
      + '<div class="nt-st">'+state+'</div>'
      + '<button class="nt-main'+(on?' off':'')+'" '+(can && !busy ? '' : 'disabled')+'>'+(busy ? '處理中…' : on ? '關閉這台裝置的通知' : '開啟通知')+'</button>'
      + (on ? '<button class="nt-test">在這台裝置顯示一則測試通知</button>' : '')
      + '<div class="nt-msg" role="status">'+esc(msg)+'</div>'
      + '<div class="nt-sec"><h3>要收哪些</h3>'
      +   '<label class="nt-opt"><input type="checkbox" data-k="close" '+(p.close?'checked':'')+'><span>收盤摘要<small>約 13:35：加權指數、資金最熱的產業、漲跌家數，加上自選股今天的漲跌</small></span></label>'
      +   '<label class="nt-opt"><input type="checkbox" data-k="intraday" '+(p.intraday?'checked':'')+'><span>盤中自選股提醒<small>盤中自選股大漲大跌（±5%、漲跌停）、5 分鐘內大量資金流入或流出、出現在「還沒漲的」名單時馬上通知；同一檔同一種狀況一天只通知一次</small></span></label>'
      +   '<label class="nt-opt"><input type="checkbox" data-k="signals" '+(p.signals?'checked':'')+'><span>盤後訊號<small>約晚上 9:40：今天新上榜的連續訊號、借券賣出暴增；自選股出現在任何名單會優先列出</small></span></label></div>'
      + '<p class="nt-fine">自選股在「<a href="watch.html">我的自選</a>」頁管理，推播會列出它們的狀況。</p>';
  }
  function open(){ msg = ''; render(); document.body.classList.add('nt-open'); refreshState().then(render); }
  function close(){ document.body.classList.remove('nt-open'); }
  btn.addEventListener('click', open);
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && document.body.classList.contains('nt-open')) close(); });
  window.openNotify = open;

  IN.addEventListener('click', function(e){
    if(e.target.closest('.nt-x')) return close();
    if(e.target.closest('.nt-test')){
      navigator.serviceWorker.ready.then(function(r){ r.showNotification('通知測試', {body:'看到這則就代表這台裝置可以收到通知。', icon:'icons/icon-192.png', tag:'local-test'}); });
      return;
    }
    if(e.target.closest('.nt-main') && !busy){
      busy = true; msg = ''; render();
      (on ? disable() : enable()).then(function(){ msg = on ? '已關閉通知。' : '已開啟通知！'; }, function(err){
        msg = String(err && err.message)==='denied' ? '沒有允許通知。' : '沒有成功，請稍後再試一次。';
      }).then(refreshState).then(function(){ busy = false; render(); });
    }
  });
  IN.addEventListener('change', function(e){
    var k = e.target.dataset && e.target.dataset.k; if(!k) return;
    var p = lsGet(KP, {}); p[k] = e.target.checked; lsSet(KP, p); sync();
  });
  window.Watch.onChange(function(){ if(document.body.classList.contains('nt-open')) render(); });
})();
