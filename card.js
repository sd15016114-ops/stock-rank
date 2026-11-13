/* 個股卡片：任何頁面呼叫 openStockCard('2330') 就會打開。
   電腦從右邊滑出、手機從下面滑上來；資料從 Supabase 的 stock_hist 表讀（每天盤後更新全市場最近 60 個交易日）。 */
(function(){
  var SB = {url:'https://yydcsmxnqudluancdowo.supabase.co', key:'sb_publishable_XgJSPBpQXcNdTCDT4pvA3w_NXpbkCn6'};
  var css = ''
  + '.sc-scrim{position:fixed;inset:0;background:rgba(0,0,0,.36);opacity:0;pointer-events:none;transition:opacity .25s;z-index:70}'
  + '.sc-sheet{position:fixed;z-index:71;background:var(--paper);color:var(--ink);overflow-y:auto;overscroll-behavior:contain;box-shadow:0 0 40px rgba(0,0,0,.25);transition:transform .4s var(--spring,cubic-bezier(.2,.9,.25,1.05))}'
  + '@media (min-width:760px){.sc-sheet{top:0;right:0;bottom:0;width:560px;max-width:100vw;transform:translateX(105%)}}'
  + '@media (max-width:759px){.sc-sheet{left:0;right:0;bottom:0;max-height:88vh;border-radius:20px 20px 0 0;transform:translateY(105%)}.sc-sheet .sc-grab{display:block}}'
  + 'body.sc-open .sc-scrim{opacity:1;pointer-events:auto}body.sc-open .sc-sheet{transform:none}body.sc-open{overflow:hidden}'
  + '.sc-grab{display:none;width:44px;height:5px;border-radius:3px;background:var(--rule);margin:10px auto 0}'
  + '.sc-in{padding:16px 20px 28px}'
  + '.sc-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}'
  + '.sc-top h2{font-family:var(--serif);font-weight:900;font-size:28px;margin:0;line-height:1.2}'
  + '.sc-top h2 small{font-family:var(--sans);font-size:14px;font-weight:500;color:var(--muted);margin-left:8px}'
  + '.sc-px{text-align:right}.sc-px b{font-size:24px;font-weight:700;display:block;line-height:1.2}'
  + '.sc-close{border:0;background:var(--tint);color:var(--ink);width:34px;height:34px;border-radius:50%;font-size:18px;cursor:pointer;flex:none}'
  + '.sc-keys{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}'
  + '.sc-keys span{font-size:13px;font-weight:700;border-radius:10px;padding:6px 10px;background:var(--tint);border:1px solid var(--rule)}'
  + '.sc-sec{margin-top:20px}'
  + '.sc-sec h3{font-size:15px;margin:0 0 2px;display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}'
  + '.sc-sec h3 small{font-weight:400;font-size:12px;color:var(--muted)}'
  + '.sc-sec svg{display:block;width:100%;height:auto;overflow:visible}'
  + '.sc-legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--muted);margin-top:4px}'
  + '.sc-legend i{display:inline-block;width:12px;height:3px;border-radius:2px;vertical-align:3px;margin-right:4px}'
  + 'table.sc-t{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}'
  + 'table.sc-t th,table.sc-t td{padding:6px 3px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}'
  + 'table.sc-t th{font-weight:400;color:var(--muted)}'
  + 'table.sc-t th:first-child,table.sc-t td:first-child{text-align:left}'
  + '@media (max-width:759px){table.sc-t .r{display:none}table.sc-t{font-size:12px}}'
  + '.sc-msg{padding:40px 0;text-align:center;color:var(--muted)}'
  + '.sc-fine{font-size:12px;color:var(--muted);margin-top:14px}'
  + '.sc-sheet .up{color:var(--up)}.sc-sheet .down{color:var(--down)}'
  + '.sc-star{margin-top:8px;border:1px solid var(--rule);background:var(--tint);color:var(--ink);font:inherit;font-size:13px;font-weight:700;border-radius:999px;padding:5px 12px;cursor:pointer}'
  + '.sc-star.on{background:var(--soft);color:var(--accent);border-color:var(--fill)}'
  + '.stocklink{cursor:pointer}.stocklink:hover td{background:var(--tint)}'
  + '.histbtn{display:block;width:100%;margin-top:12px;padding:10px 14px;border-radius:12px;border:1px solid var(--rule);background:var(--soft);color:var(--accent);font:inherit;font-size:14px;font-weight:700;cursor:pointer;text-align:center}'
  + '.histbtn:hover{border-color:var(--fill)}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  var scrim = document.createElement('div'); scrim.className = 'sc-scrim';
  var sheet = document.createElement('aside'); sheet.className = 'sc-sheet'; sheet.setAttribute('role','dialog'); sheet.setAttribute('aria-modal','true'); sheet.setAttribute('aria-label','個股資金歷史');
  sheet.innerHTML = '<div class="sc-grab"></div><div class="sc-in" id="scIn"></div>';
  document.body.appendChild(scrim); document.body.appendChild(sheet);
  var IN = sheet.querySelector('#scIn'), CACHE = {}, lastFocus = null;

  function fix(n,d){ return n.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d}); }
  function yi(m){ var v=Math.abs(m)/100; return fix(v, v>=100?0:v>=10?1:2); }        /* 百萬元 → 億元 */
  function lots(n){ return (n>0?'+':n<0?'−':'')+Math.abs(n).toLocaleString('zh-TW'); }
  function pct(p){ return p==null?'—':(p>0?'▲ ':p<0?'▼ ':'')+fix(Math.abs(p),2)+'%'; }
  function cls(n){ return n>0?'up':n<0?'down':''; }
  function md(s){ return (+s.slice(5,7))+'/'+(+s.slice(8)); }
  function esc(t){ return String(t==null?'':t).replace(/[&<>"]/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function cv(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  /* 比例尺用第 95 百分位，不讓單一天的極端值把其他天壓扁 */
  function robust(arr){ var a = arr.filter(function(x){ return x!=null; }).map(Math.abs).sort(function(x,y){ return x-y; }); return a.length ? (a[Math.floor(a.length*0.95)] || a[a.length-1]) : 1; }

  function close(){
    document.body.classList.remove('sc-open');
    if(lastFocus && lastFocus.focus) try{ lastFocus.focus({preventScroll:true}); }catch(e){}
  }
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && document.body.classList.contains('sc-open')) close(); });
  /* 手機：在面板最上面往下拉就關掉 */
  var y0 = null;
  sheet.addEventListener('touchstart', function(e){ y0 = sheet.scrollTop<=0 ? e.touches[0].clientY : null; }, {passive:true});
  sheet.addEventListener('touchmove', function(e){ if(y0!=null && e.touches[0].clientY - y0 > 90){ y0 = null; close(); } }, {passive:true});
  IN.addEventListener('click', function(e){
    if(e.target.closest('.sc-close')) close();
    var sb = e.target.closest('.sc-star');
    if(sb && window.Watch){ var now = window.Watch.toggle(sb.dataset.code, sb.dataset.name); sb.outerHTML = star(sb.dataset.code, sb.dataset.name); }
  });
  /* 自選股按鈕（有載入 notify.js 才顯示） */
  function star(code, name){
    if(!window.Watch) return '';
    var on = window.Watch.has(code);
    return '<button type="button" class="sc-star'+(on?' on':'')+'" data-code="'+esc(code)+'" data-name="'+esc(name)+'" aria-pressed="'+on+'">'+(on?'★ 自選中':'☆ 自選')+'</button>';
  }

  function fetchStock(code){
    if(CACHE[code]) return CACHE[code];
    CACHE[code] = fetch(SB.url+'/rest/v1/stock_hist?code=eq.'+encodeURIComponent(code)+'&select=data', {headers:{apikey:SB.key}})
      .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
      .then(function(j){ if(!j || !j[0]) throw new Error('none'); return j[0].data; })
      .catch(function(e){ delete CACHE[code]; throw e; });
    return CACHE[code];
  }

  window.openStockCard = function(code, hint){
    lastFocus = document.activeElement;
    IN.innerHTML = '<div class="sc-top"><div><h2>'+esc((hint&&hint.name)||code)+'<small>'+esc(code)+'</small></h2></div><button class="sc-close" aria-label="關閉">×</button></div><div class="sc-msg">資料載入中…</div>';
    document.body.classList.add('sc-open'); sheet.scrollTop = 0;
    fetchStock(code).then(function(c){ render(code, c); }, function(){
      IN.querySelector('.sc-msg').textContent = '找不到這檔的歷史資料（可能是剛上市，或今天的資料還在更新）。';
    });
  };
  /* 頁面上任何有 data-stock 的元素，點了就打開卡片 */
  document.addEventListener('keydown', function(e){
    var el = (e.key==='Enter' || e.key===' ') && e.target.closest && e.target.closest('tr[data-stock]');
    if(el){ e.preventDefault(); window.openStockCard(el.dataset.stock, {name: el.dataset.name}); }
  });
  document.addEventListener('click', function(e){
    var el = e.target.closest && e.target.closest('[data-stock]');
    if(!el || e.defaultPrevented) return;
    e.preventDefault(); e.stopPropagation();
    window.openStockCard(el.dataset.stock, {name: el.dataset.name});
  }, true);   /* 捕獲階段先處理，頁面本身「點列展開」的程式就不會被觸發 */

  function render(code, c){
    var n = c.dates.length, last = n-1, f = c.f||[], t = c.t||[];
    var v5 = c.value.slice(-5).filter(function(x){ return x!=null; });
    var r5 = v5.length && c.avg ? v5.reduce(function(a,b){ return a+b; },0)/v5.length/c.avg : null;
    function run(arr){ var s=0, dir=0; for(var i=last;i>=0;i--){ var x=arr[i]; if(x==null) break; var sg = x>0?1:x<0?-1:0; if(!dir) dir=sg; if(!sg || sg!==dir) break; s++; } return [dir,s]; }
    function sum(arr,d){ var s=0; for(var i=last;i>last-d && i>=0;i--) s += arr[i]||0; return s; }
    var fr = run(f), tr = run(t), keys = [];
    if(r5) keys.push('<span class="'+(r5>=1.3?'up':'')+'">近 5 日成交值是平常的 '+fix(r5,1)+' 倍</span>');
    if(fr[1]>=2) keys.push('<span class="'+cls(fr[0])+'">外資連 '+fr[1]+' '+(fr[0]>0?'買':'賣')+'</span>');
    if(tr[1]>=2) keys.push('<span class="'+cls(tr[0])+'">投信連 '+tr[1]+' '+(tr[0]>0?'買':'賣')+'</span>');
    if(f.some(function(x){ return x!=null; })){ var s20 = sum(f,20); keys.push('<span class="'+cls(s20)+'">外資近 20 日 '+lots(s20)+' 張</span>'); }
    var sb = c.sbl||[], dtr = c.dt||[];
    if(sb[last]){
      var pb = sb.slice(-21,-1).filter(function(x){ return x!=null; }), ab = pb.length ? pb.reduce(function(a,b){ return a+b; },0)/pb.length : 0;
      if(!ab || sb[last] >= ab*3) keys.push('<span class="down">借券賣出 '+sb[last].toLocaleString('zh-TW')+' 張'+(ab ? '，平常的 '+fix(sb[last]/ab,1)+' 倍' : '')+'</span>');
    }
    if(dtr[last]!=null && dtr[last] >= 50) keys.push('<span>當沖比例 '+fix(dtr[last],0)+'%</span>');
    var CF = cost(f, c.close), CT = cost(t, c.close), px0 = c.close[last];
    [['投信', CT], ['外資', CF]].forEach(function(z){
      var k = z[1]; if(!k.now || !px0 || k.pos <= 0) return;      /* 近 60 天整體是賣超的就不標，成本意義不大 */
      var g = (px0 / k.now - 1) * 100;
      keys.push('<span class="'+cls(g)+'">'+z[0]+'成本約 '+fix(k.now, k.now>=100?0:1)+'（現價'+(g>=0?'高':'低')+' '+fix(Math.abs(g),1)+'%）</span>');
    });
    var p = c.pct[last], px = c.close[last];
    IN.innerHTML =
      '<div class="sc-top"><div><h2>'+esc(c.name)+'<small>'+esc(code)+(c.ind?'・'+esc(c.ind):'')+'</small></h2>'+star(code, c.name)+'</div>'
      +'<div style="display:flex;gap:12px;align-items:flex-start"><div class="sc-px"><b>'+(px!=null?fix(px,2):'—')+'</b><span class="'+cls(p)+'">'+pct(p)+'</span></div><button class="sc-close" aria-label="關閉">×</button></div></div>'
      +'<div class="sc-keys">'+keys.join('')+'</div>'
      +'<div class="sc-sec"><h3>'+n+' 天成交值<small>長條紅漲綠跌・虛線是 60 日平均・折線是收盤價</small></h3>'+valueChart(c)+'</div>'
      +'<div class="sc-sec"><h3>法人成本<small>近 '+n+' 天買超的張數乘上當天收盤價，加權平均成買進均價（推估值）</small></h3>'+costChart(c, CF, CT)+'</div>'
      +'<div class="sc-sec"><h3>'+n+' 天法人買賣超<small>柱狀是每天買賣超（張）・折線是累計</small></h3>'+instChart(c)+'</div>'
      +'<div class="sc-sec"><h3>近 10 天明細</h3>'+table(c)+'</div>'
      +'<p class="sc-fine">資料每天盤後更新（法人資料晚上 9 點半左右齊全）。成交值單位億元，法人單位張。</p>';
  }
  /* 法人成本：近 60 天每次買超的張數 × 當天收盤價，加權平均成「買進均價」（賣超不影響均價）。
     法人在 60 天前就有的持股算不進來，所以這是近期進場的成本推估，不是真正的總持股成本。
     回傳每天累積到那天的均價、最後的均價、60 天合計買賣超張數 */
  function cost(net, close){
    var lots = 0, amt = 0, sum = 0, out = [];
    for(var i=0;i<net.length;i++){
      var x = net[i], p = close[i];
      if(x!=null){ sum += x; if(x > 0 && p){ lots += x; amt += x*p; } }
      out.push(lots ? amt/lots : null);
    }
    return {line: out, now: lots ? amt/lots : null, pos: sum};
  }
  function costChart(c, CF, CT){
    if(!(c.f||[]).some(function(x){ return x!=null; })) return '<div class="sc-msg" style="padding:16px 0">還沒有法人資料。</div>';
    var W=520, H=150, n=c.dates.length, bw=W/n, ac=cv('--accent'), mu=cv('--muted'), up=cv('--up');
    var vals = c.close.concat(CF.line, CT.line).filter(function(v){ return v!=null; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi-lo)*0.08 || hi*0.02; lo -= pad; hi += pad;
    function X(i){ return (i+.5)*bw; } function Y(v){ return 6 + (1-(v-lo)/(hi-lo))*(H-12); }
    function path(arr){ var d='', on=false; arr.forEach(function(v,i){ if(v==null){ on=false; return; } d += (on?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1); on=true; }); return d; }
    var s = '<svg viewBox="0 0 '+W+' '+(H+18)+'" role="img" aria-label="收盤價與法人成本">'
      + '<path d="'+path(c.close)+'" fill="none" stroke="'+up+'" stroke-width="2"/>'
      + '<path d="'+path(CF.line)+'" fill="none" stroke="'+ac+'" stroke-width="2" stroke-dasharray="6 4"/>'
      + '<path d="'+path(CT.line)+'" fill="none" stroke="'+mu+'" stroke-width="2" stroke-dasharray="2 4" stroke-linecap="round"/>'
      + '<text x="0" y="'+(H+14)+'" font-size="11" fill="'+mu+'">'+md(c.dates[0])+'</text><text x="'+W+'" y="'+(H+14)+'" font-size="11" text-anchor="end" fill="'+mu+'">'+md(c.dates[n-1])+'</text></svg>';
    var px = c.close[n-1];
    function line(name, k, col, dash){
      var t = k.now ? '約 '+fix(k.now, k.now>=100?1:2)+(px ? '，現價'+(px>=k.now?'高':'低')+' '+fix(Math.abs(px/k.now-1)*100,1)+'%' : '')+'（'+n+' 天合計'+(k.pos>=0?'買超 ':'賣超 ')+Math.abs(k.pos).toLocaleString('zh-TW')+' 張）' : '近 '+n+' 天沒有買超';
      return '<span><i style="background:'+col+(dash?';height:0;border-top:2px '+dash+' '+col:'')+'"></i>'+name+'成本 '+t+'</span>';
    }
    s += '<div class="sc-legend" style="flex-direction:column;gap:2px"><span><i style="background:'+up+'"></i>收盤價 '+(px!=null?fix(px,2):'—')+'</span>'
      + line('外資', CF, ac, 'dashed') + line('投信', CT, mu, 'dotted') + '</div>';
    return s;
  }
  function valueChart(c){
    var W=520,H=170,n=c.dates.length,bw=W/n, vals=c.value, mx=Math.max(robust(vals)*1.1, (c.avg||0)*1.2)||1;
    var cl=c.close.filter(function(x){return x!=null;}), lo=Math.min.apply(null,cl), hi=Math.max.apply(null,cl);
    var up=cv('--up'), dn=cv('--down'), ac=cv('--accent'), mu=cv('--muted');
    var s='<svg viewBox="0 0 '+W+' '+(H+18)+'" role="img" aria-label="成交值走勢">';
    vals.forEach(function(v,i){ if(v==null) return; var h=Math.min(v/mx,1)*(H-10);
      if(v>mx) s+='<path d="M'+(i*bw+bw/2)+' 0 l4 6 h-8z" fill="'+mu+'"/>';
      s+='<rect x="'+(i*bw+1)+'" y="'+(H-h)+'" width="'+Math.max(1,bw-2)+'" height="'+h+'" rx="1.5" fill="'+((c.pct[i]||0)>=0?up:dn)+'" opacity=".55"><title>'+c.dates[i]+'　'+yi(v)+' 億</title></rect>'; });
    if(c.avg){ var y=H-Math.min(c.avg/mx,1)*(H-10); s+='<line x1="0" x2="'+W+'" y1="'+y+'" y2="'+y+'" stroke="'+mu+'" stroke-dasharray="4 4"/><text x="'+W+'" y="'+(y-4)+'" font-size="11" text-anchor="end" fill="'+mu+'">60 日平均 '+yi(c.avg)+' 億</text>'; }
    var pts=c.close.map(function(v,i){ return v==null?null:[(i+.5)*bw, 8+(1-(v-lo)/((hi-lo)||1))*(H*0.55)]; }).filter(Boolean);
    s+='<polyline fill="none" stroke="'+ac+'" stroke-width="2" points="'+pts.map(function(p){return p.join(',');}).join(' ')+'"/>';
    s+='<text x="0" y="'+(H+14)+'" font-size="11" fill="'+mu+'">'+md(c.dates[0])+'</text><text x="'+W+'" y="'+(H+14)+'" font-size="11" text-anchor="end" fill="'+mu+'">'+md(c.dates[n-1])+'</text></svg>';
    return s;
  }
  function instChart(c){
    var f=(c.f||[]), t=(c.t||[]);
    if(!f.some(function(x){ return x!=null; })) return '<div class="sc-msg" style="padding:16px 0">還沒有法人資料。</div>';
    var W=520,H=150,n=c.dates.length,bw=W/n, mid=H/2, mx=robust(f.concat(t))*1.1||1, cf=0, ct=0;
    var cumF=f.map(function(v){ return cf+=(v||0); }), cumT=t.map(function(v){ return ct+=(v||0); });
    var cm=Math.max.apply(null,cumF.concat(cumT).map(Math.abs).concat(1));
    var up=cv('--up'), dn=cv('--down'), ac=cv('--accent'), mu=cv('--muted');
    var s='<svg viewBox="0 0 '+W+' '+(H+18)+'" role="img" aria-label="法人買賣超"><line x1="0" x2="'+W+'" y1="'+mid+'" y2="'+mid+'" stroke="'+cv('--rule')+'"/>';
    function bars(arr,off,op,who){ arr.forEach(function(v,i){ if(v==null) return; var h=Math.min(Math.abs(v)/mx,1)*(mid-6);
      s+='<rect x="'+(i*bw+off)+'" y="'+(v>=0?mid-h:mid)+'" width="'+Math.max(1,bw/2-1)+'" height="'+h+'" fill="'+(v>=0?up:dn)+'" opacity="'+op+'"><title>'+c.dates[i]+' '+who+' '+lots(v)+' 張</title></rect>'; }); }
    bars(f,1,.6,'外資'); bars(t,bw/2,.3,'投信');
    function line(arr,col,dash){ return '<polyline fill="none" stroke="'+col+'" stroke-width="2" '+(dash?'stroke-dasharray="5 3" ':'')+'points="'+arr.map(function(v,i){ return ((i+.5)*bw)+','+(mid-v/cm*(mid-6)); }).join(' ')+'"/>'; }
    s+=line(cumF,ac)+line(cumT,mu,true)+'</svg>';
    s+='<div class="sc-legend"><span><i style="background:'+ac+'"></i>外資累計 '+lots(cf)+' 張</span><span><i style="background:'+mu+'"></i>投信累計（虛線）'+lots(ct)+' 張</span><span>柱狀：左邊深色外資、右邊淺色投信</span></div>';
    return s;
  }
  function table(c){
    var n=c.dates.length, rows='', f=c.f||[], t=c.t||[], sb=c.sbl||[], dtr=c.dt||[];
    var hasX = sb.some(function(x){ return x!=null; }) || dtr.some(function(x){ return x!=null; });
    for(var i=n-1;i>=Math.max(0,n-10);i--){
      rows+='<tr><td>'+md(c.dates[i])+'</td><td>'+(c.close[i]!=null?fix(c.close[i],2):'—')+'</td><td class="'+cls(c.pct[i])+'">'+pct(c.pct[i])+'</td><td>'+(c.value[i]!=null?yi(c.value[i]):'—')+'</td><td class="r">'+(c.ratio[i]!=null?fix(c.ratio[i],1)+'×':'—')+'</td><td class="'+cls(f[i])+'">'+(f[i]!=null?lots(f[i]):'—')+'</td><td class="'+cls(t[i])+'">'+(t[i]!=null?lots(t[i]):'—')+'</td>'
        +(hasX?'<td class="r">'+(sb[i]!=null?sb[i].toLocaleString('zh-TW'):'—')+'</td><td class="r">'+(dtr[i]!=null?fix(dtr[i],0)+'%':'—')+'</td>':'')+'</tr>'; }
    return '<table class="sc-t"><tr><th>日期</th><th>收盤</th><th>漲跌</th><th>成交值（億）</th><th class="r">放大</th><th>外資（張）</th><th>投信（張）</th>'+(hasX?'<th class="r">借券賣出</th><th class="r">當沖</th>':'')+'</tr>'+rows+'</table>';
  }
})();
