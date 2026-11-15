/* Historical EOD presentation only. Every market value comes from validated local APIs. */
(function () {
  'use strict';
  const q = selector => document.querySelector(selector);
  const fmt = (value, digits = 2) => value == null ? '—' : calculator.formatDecimal(String(value), digits);
  const dateVN = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? value.split('-').reverse().join('/') : '—';
  const state = {meta:null, rows:[], summary:null, symbol:'', range:'1M', search:'', sort:'date', descending:true, page:1, price:true, volume:true};
  Object.assign(state,window.MarketState.value);
  let catalog=[], hasCoverage=false;
  let memberships={};
  function params(){const s=window.MarketState.value;return new URLSearchParams({symbol:state.symbol,range:state.range,scope:s.scope,resolution:s.resolution,to:s.to,...(s.range==='CUSTOM'&&s.from?{from:s.from}:{})});}
  function syncToolbar(){
    const s=window.MarketState.value;
    for(const [id,key] of [['market-scope','scope'],['market-type','type'],['market-from','from'],['market-to','to'],['market-resolution','resolution']])q('#'+id).value=s[key];
    document.querySelectorAll('[data-range]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.range===s.range)));
    const page=location.hash.slice(1)||'monitor';
    text('#global-context',['book','calculator'].includes(page)?'Snapshot / nhập thủ công: khoảng lịch sử không dựng lại sổ lệnh; mã theo bộ lọc chung.':'Bộ lọc chung áp dụng dữ liệu lịch sử. RV20 và volatility20 luôn tính trên nến ngày trước khi tổng hợp tuần/tháng.');
  }
  function filterCatalog(){
    const s=window.MarketState.value,needle=q('#market-search').value.trim().toLocaleLowerCase('vi');
    const members=catalog.filter(r=>(s.scope==='ALL'||r.board===s.scope||(s.scope.startsWith('INDEX:')&&(memberships[s.scope.slice(6)]||[]).includes(r.symbol)))&&(s.type==='ALL'||r.stockType===s.type)&&(!needle||[r.symbol,r.symbolNameVi,r.symbolNameEn].some(v=>String(v||'').toLocaleLowerCase('vi').includes(needle))));
    const select=q('#symbol-filter');select.replaceChildren();
    const ordered=hasCoverage ? [...members].sort((a,b)=>
      Number(b.symbol.toLowerCase()===needle)-Number(a.symbol.toLowerCase()===needle) ||
      Number(Boolean(b.daily_last))-Number(Boolean(a.daily_last))) : members;
    const visible=ordered;
    for(const row of visible){const option=node('option',`${row.symbol} · ${row.symbolNameVi||row.board} · ${row.stockType||'chưa phân loại'}${hasCoverage ? ' · '+(row.daily_last?'có EOD':'chưa có EOD')+(row.intraday_last?' · có nội ngày':'')+(row.status==='absent'||row.status==='ended'?' · ngoài danh mục hiện hành':'') : ''}`);option.value=row.symbol;select.append(option);}
    if(members.some(r=>r.symbol===state.symbol))select.value=state.symbol;
    else if(members.length){window.MarketState.set({symbol:ordered[0].symbol});}
    select.disabled=!members.length;
    text('#universe-note',`${members.length}/${catalog.length} mã khớp. ${visible.length<members.length?'Nhập mã hoặc tên để tìm trong toàn bộ danh mục.':'Danh mục SSI hiện tại.'}`);
  }
  async function loadCoverage(){
    const s=window.MarketState.value;
    try{const data=await request('/api/market/coverage?'+new URLSearchParams({scope:s.scope,to:s.to}));if(s.scope!==window.MarketState.value.scope||s.to!==window.MarketState.value.to)return;
      const note=`${data.gate.status} · ${data.gate.n}/${data.gate.denominator} mục có nến ${data.date} · ${data.loaded_symbols} có lịch sử trong khoảng · ${data.gate.reason||''}`;
      text('#coverage-badge',note);text('#universe-note',`Danh mục ${data.scope}: ${data.catalog_count} mục SSI; ngưỡng 95% / một phần 80%; mẫu số lịch sử chưa xác minh.`);
      q('#quality-list').replaceChildren(node('li',note),node('li','Dữ liệu từng mã được đối chiếu raw có SHA-256. Metadata sáu mã cũ chỉ là snapshot tham chiếu trước mở rộng.'));
      q('#method-provenance').replaceChildren(node('dt','Phạm vi SSI hiện tại'),node('dd',`${data.scope}: ${data.catalog_count} mục, ${data.loaded_symbols} có lịch sử; ${data.sessions} phiên, ${data.first}–${data.last}`),node('dt','Độ phủ theo phiên'),node('dd',note),node('dt','Đơn vị / điều chỉnh'),node('dd','Source native; đơn vị mở rộng và chính sách điều chỉnh chưa xác minh đầy đủ. Không xuất turnover thực.'));
    }catch(e){text('#coverage-badge','BLOCKED · Không kiểm chứng được độ phủ: '+e.message);}
  }
  async function loadIndex(){
    try{
      const s=window.MarketState.value,code=q('#index-select').value;if(!code)return;
      const data=await request('/api/market/index?'+new URLSearchParams({symbol:code,range:s.range,to:s.to,...(s.range==='CUSTOM'&&s.from?{from:s.from}:{})}));
      text('#index-status',`${code} · ${data.rows.length} phiên chính thức · ${data.source||'SSI indexSummary'} · ${data.rows.at(-1)?.tradingDate||'chưa có dữ liệu'}`);
      const valid=data.rows.filter(r=>r.indexValue!=null&&Number.isFinite(Number(r.indexValue))&&Number(r.indexValue)>0);
      const target=q('#index-chart');target.replaceChildren();
      if(!valid.length){target.append(node('p',data.reason||'Không có giá trị chỉ số đã kiểm chứng trong khoảng.'));return;}
      const last=valid.at(-1);text('#index-status',`${code}: ${fmt(last.indexValue)} điểm · thay đổi ${fmt(last.indexChange)} điểm / ${fmt(last.indexChangePercentage)}% · ${last.tradingDate} · ${data.source||'SSI indexSummary'}`);
      chart('#index-chart','index_value',code,'điểm',{data:valid.map(r=>({date:r.tradingDate.slice(0,10).replaceAll('/','-'),symbol:code,index_value:r.indexValue,volume_shares:null})),source:data.source||'SSI indexSummary'});
    }catch(e){text('#index-status','BLOCKED · '+e.message);q('#index-chart').replaceChildren();}
  }
  window.addEventListener('hashchange',syncToolbar);
  window.addEventListener('market-state-change',()=>{
    Object.assign(state,window.MarketState.value);syncToolbar();
    if(state.meta?.available){filterCatalog();loadSeries();loadRankings();loadCoverage();loadIndex();}
    const book=q('#book-symbol');
    if(book && [...book.options].some(o=>o.value===state.symbol)){
      book.value=state.symbol;book.dispatchEvent(new Event('change'));
    }
  });
  let revision = 0;
  let rankingRevision = 0;
  const pageSize = 10;
  const columns = ['symbol','date','open_vnd','high_vnd','low_vnd','close_vnd','volume_shares','turnover_vnd','source_value_vnd','price_adjustment','upstream_source','source_url'];
  function text(selector, value) { q(selector).textContent = value; }
  function node(tag, content, className) {
    const element = document.createElement(tag);
    if (content != null) element.textContent = content;
    if (className) element.className = className;
    return element;
  }
  function emptyChart(selector, message) {
    const target = q(selector);
    target.replaceChildren(node('p', message, 'small-empty'));
    target.setAttribute('aria-busy','false');
  }
  function clearData(message) {
    state.rows = []; state.summary = null;
    for (const id of ['return','volume','relative','volatility']) {
      text(`#metric-${id}`,'—'); text(`#detail-${id}`,message); q(`#metric-${id}`).removeAttribute('title');
    }
    for (const selector of ['#price-chart','#volume-trend-chart','#relative-chart','#volatility-chart','#value-chart']) emptyChart(selector,message);
    text('#eod-insight',message); text('#analysis-insight',message); text('#analysis-context',message);
    text('#chart-caption',message); text('#chart-count','0 phiên'); text('#source-last','—');
    text('#table-caption','Chưa có dòng EOD đã kiểm chứng.');
    q('#export-eod').disabled = true;
    renderTable();
  }
  function showError(message) { text('#eod-error',message); q('#eod-error').hidden = false; }
  function invalidateProvenance(message) {
    ++rankingRevision;
    q('#ranking-body').replaceChildren();
    text('#ranking-empty','Xếp hạng không khả dụng vì snapshot chưa được kiểm chứng.');q('#ranking-empty').hidden=false;
    text('#ranking-scope','Chưa có phạm vi dữ liệu hợp lệ.');text('#ranking-unit','—');
    state.meta={available:false,status:'BLOCKED',issues:[message],loaded_symbols:[],coverage_by_symbol:{},manifest:{}};
    provenance(state.meta);
  }
  function setBusy(busy) {
    q('#symbol-filter').disabled = busy || !state.meta?.available;
    q('#refresh').disabled = busy;
    q('#refresh').textContent = busy ? 'Đang đọc local…' : 'Đọc lại snapshot';
    q('#price-chart').setAttribute('aria-busy',String(busy));
    q('#monitor').setAttribute('aria-busy',String(busy));
  }
  function provenance(meta) {
    if(!meta.available)window.dispatchEvent(new CustomEvent('historical-snapshot-unavailable'));
    const manifest = meta.manifest || {};
    const sources = manifest.upstream_sources || [];
    const vd=manifest.value_diagnostics;
    const valueNote=vd?`${vd.equal_close_times_volume}/${vd.observations} dòng SSI value bằng close × volume; giữ làm proxy nguồn, turnover thực chưa xác minh và để trống.`:'Chưa có bằng chứng GTGD thực. Không coi giá trị proxy là turnover.';
    text('#value-chart-note',valueNote);text('#value-quality-note',valueNote);
    const name = sources.map(s => s.name || s.id).join(', ') || 'Chưa có nguồn hợp lệ';
    text('#source-name',name); text('#source-quality',meta.available ? `${meta.status} · SHA-256 khớp` : 'BLOCKED');
    text('#universe-note',meta.available ? `Mẫu ${meta.loaded_symbols.length} mã · không phải toàn HOSE` : 'Chưa có snapshot hợp lệ');
    const list = q('#quality-list'); list.replaceChildren();
    const checks = meta.available ? [manifest.dataset_type==='ssi_history_revision'?'✓ JSON chuẩn hóa đối chiếu raw và SHA-256':'✓ CSV khớp SHA-256 trong manifest','✓ OHLC và ngày chốt hợp lệ; đơn vị nguồn mở rộng chưa xác minh',`✓ ${manifest.row_count} dòng · ${meta.loaded_symbols.length} mã trong mẫu`,'Đối chiếu nguồn khác: xem Phương pháp'] : ['Snapshot chưa qua kiểm chứng',...(meta.issues || [])];
    checks.forEach(item => list.append(node('li',item)));
    text('#manifest-json',JSON.stringify(manifest,null,2));
    const dl = q('#method-provenance'); dl.replaceChildren();
    const coverage = Object.entries(meta.coverage_by_symbol || {}).map(([s,c]) => `${s}: ${c.rows} phiên, ${dateVN(c.first_available_session)}–${dateVN(c.last_available_session)}`).join('; ');
    const entries = [['Nguồn upstream',name],['Ngày khóa tối đa',dateVN(meta.asof_date)],['Phiên cuối thực tế',dateVN(meta.last_available_session)],['Múi giờ',meta.timezone || 'Asia/Ho_Chi_Minh'],['Lần truy xuất (UTC)',manifest.retrieved_at_utc || '—'],['Đơn vị','Giá: đơn vị giá nguồn; khối lượng: cp; turnover: VND (nullable)'],['Điều chỉnh',manifest.adjustment_policy==='unknown'?'Chưa xác định (SSI)':manifest.adjustment_policy || '—'],['Độ phủ',coverage || 'Không có'],['Chất lượng',meta.available ? `${meta.status} · kiểm chứng lại tại mỗi lần đọc API` : 'BLOCKED']];
    entries.forEach(([key,value]) => { const div=node('div'); div.append(node('dt',key),node('dd',value)); dl.append(div); });
    const links=q('#method-links'); links.replaceChildren();
    sources.forEach(source => {
      const p=node('p');
      for (const [label,key] of [[source.id==='ssi_v3'?'Endpoint (cần token)':'Trang nguồn','source_url'],['Tài liệu','documentation_url'],['Điều khoản','terms_url']]) {
        if (typeof source[key] !== 'string' || !/^https?:\/\//.test(source[key])) continue;
        const a=node('a',`${label} ↗ `,'text-link'); a.href=source[key]; a.target='_blank'; a.rel='noopener noreferrer'; p.append(a);
      }
      links.append(p);
    });
  }
  function renderSummary(payload) {
    const s=payload.summary;
    if (!s) { clearData(payload.message||'Khoảng đã chọn không có dòng EOD hợp lệ.'); return; }
    const metrics = [['return','return_pct','%',2,'Lợi suất đóng cửa so phiên trước'],['volume','volume_shares',' KL nguồn',0,`Phiên ${dateVN(s.date)}`],['relative','relative_volume20',' lần',2,'Khối lượng / TB20 trước, loại phiên hiện tại'],['volatility','volatility20_pct','%',2,'Độ lệch chuẩn mẫu · không năm hóa']];
    metrics.forEach(([id,key,unit,digits,description]) => {
      text(`#metric-${id}`,s[key] == null ? '—' : key==='turnover_vnd' ? `${fmt(Number(s[key])/1e9,2)} tỷ VND` : `${key === 'return_pct' && Number(s[key]) > 0 ? '+' : ''}${fmt(s[key],digits)}${unit}`);
      text(`#detail-${id}`,s[key] == null ? (s.missing_reasons?.[key] || 'Chưa có dữ liệu.') : description);
      q(`#metric-${id}`).title=s[key] == null ? (s.missing_reasons?.[key] || 'Thiếu dữ liệu') : `${s[key]}${unit}`;
    });
    const source=(state.meta.manifest.upstream_sources || []).map(item=>item.name || item.id).join(', ');
    const adjustment=state.meta.manifest.adjustment_policy==='provider_adjusted'?'giá đã điều chỉnh':state.meta.manifest.adjustment_policy==='unadjusted'?'giá chưa điều chỉnh':'điều chỉnh giá chưa xác định';
    text('#snapshot-state',`Phiên cuối thực tế: ${dateVN(payload.last_available_session)} · ${source} · Asia/Ho_Chi_Minh`);
    text('#source-last',dateVN(payload.last_available_session));
    text('#chart-caption',`${state.symbol} · ${dateVN(state.rows[0]?.date)}–${dateVN(s.date)} · ${adjustment}`);
    text('#chart-count',`${state.rows.length} phiên trong khoảng`);
    const explanation=`${state.symbol} đóng cửa ${fmt(s.close_vnd,2)} đơn vị giá nguồn ngày ${dateVN(s.date)}. Khối lượng ${fmt(s.volume_shares,0)} KL nguồn${s.relative_volume20 == null ? '; chưa đủ dữ liệu so TB20.' : `, bằng ${fmt(s.relative_volume20,2)} lần TB20 phiên trước.`}`;
    window.dispatchEvent(new CustomEvent('eod-updated',{detail:{rows:state.rows,summary:s,meta:state.meta}}));
    text('#eod-insight',explanation); text('#analysis-insight',explanation);
    const selectedSymbol=state.symbol,selectedDate=s.date;request('/api/market/insights?'+new URLSearchParams({symbol:selectedSymbol,date:selectedDate})).then(sheet=>{if(state.symbol!==selectedSymbol||state.summary?.date!==selectedDate)return;text('#eod-insight',sheet.paragraphs.join(' '));text('#analysis-insight',sheet.paragraphs.join(' '));}).catch(()=>{});
    text('#analysis-context',`${state.symbol} · ${dateVN(state.rows[0]?.date)}–${dateVN(s.date)} · ${state.rows.length} phiên · cùng bộ lọc Tổng quan. KPI là phiên cuối; đổi độ dài khoảng không đổi phiên cuối.`);
    text('#table-caption',`${state.symbol} · đơn vị giá nguồn · volume: đơn vị nguồn · ${state.meta.manifest.adjustment_policy}`);
  }
  const svgNS='http://www.w3.org/2000/svg';
  function svg(tag,attributes,content) {
    const element=document.createElementNS(svgNS,tag);
    Object.entries(attributes || {}).forEach(([key,value]) => element.setAttribute(key,String(value)));
    if (content != null) element.textContent=content;
    return element;
  }
  function chart(selector, field, label, unit, options = {}) {
    const target=q(selector);if(window.ChartKit){window.ChartKit.render(target,options.data||state.rows,field,label,unit,{...options,price:state.price,volume:state.volume});return;}const full=options.data||state.rows;const zoom=target._zoom;const rows=zoom?full.slice(zoom[0],zoom[1]):full;
    target.replaceChildren(); target.setAttribute('aria-busy','false');
    if (!rows.length) { emptyChart(selector,'Chưa có snapshot đã kiểm chứng. Xem Phương pháp & nguồn.'); return; }
    const hasLine = options.main ? state.price : true;
    const hasBars = options.main ? state.volume : !!options.bars;
    const values=rows.map(r => r[field] == null ? null : Number(r[field])/(options.divisor||1));
    const finite=values.filter(v => v != null && Number.isFinite(v));
    if ((!hasLine || !finite.length) && !hasBars) {
      emptyChart(selector,options.main ? 'Đã ẩn cả hai chuỗi. Bật Giá đóng cửa hoặc Khối lượng để xem lại.' : `Chưa đủ mẫu: ${rows.at(-1).missing_reasons?.[field] || 'Không có chỉ số hợp lệ trong khoảng này.'}`); return;
    }
    // Match viewBox to rendered width so SVG labels stay 14–16px on narrow cards.
    const width=Math.max(300,Math.round(target.clientWidth || 640)), left=70, right=18, plotWidth=width-left-right;
    const lineTop=34, lineBottom=options.main?300:236, barTop=336, barBottom=412;
    const height=options.main?450:hasBars?450:278;
    const frame=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'chart-frame',role:'img','aria-label':`${state.symbol}: ${label} (${unit}), ${rows.length} phiên; bảng dữ liệu ở Tổng quan.`});
    frame.append(svg('title',{},`${state.symbol} · ${label} (${unit})`));
    let min=finite.length ? Math.min(...finite) : 0, max=finite.length ? Math.max(...finite) : 1;
    if (field !== 'close_vnd') min=Math.min(0,min);
    const padding=(max-min)*0.09 || Math.abs(max)*0.03 || 1;
    min=field==='close_vnd'||field==='index_value'?min-padding:Math.max(0,min-padding); max+=padding;
    const x=i => left+(rows.length === 1 ? plotWidth/2 : i*plotWidth/(rows.length-1));
    const y=value => lineBottom-(value-min)/(max-min)*(lineBottom-lineTop);
    if (hasLine && finite.length) {
      const millions=field==='volume_avg20_previous' && max>=1000000;
      frame.append(svg('text',{x:left,y:18,class:'eod-axis'},millions ? 'TB20 trước · triệu cp' : `${label} · ${unit}`));
      for(let i=0;i<4;i++) {
        const value=min+(max-min)*i/3, yy=y(value);
        frame.append(svg('line',{x1:left,y1:yy,x2:width-right,y2:yy,class:'eod-gridline'}));
        frame.append(svg('text',{x:left-8,y:yy+5,'text-anchor':'end',class:'eod-axis'},fmt(millions ? value/1000000 : value,millions ? 1 : field==='close_vnd' ? 0 : 2)));
      }
      let path='', broken=true;
      values.forEach((value,i) => { if(value == null || !Number.isFinite(value)) { broken=true; return; } if(i && state.resolution==='1D' && (Date.parse(rows[i].date)-Date.parse(rows[i-1].date))/86400000>7)broken=true; path+=`${broken ? 'M' : 'L'}${x(i).toFixed(2)},${y(value).toFixed(2)} `; broken=false; });
      frame.append(svg('path',{d:path,class:'eod-line'}));
    }
    const volumeBars=[];
    if (hasBars) {
      const volumes=rows.map(r => Number(r.volume_shares));
      const volumeMax=Math.max(...volumes,1);
      frame.append(svg('text',{x:left,y:barTop-9,class:'eod-axis'},`KL · max ${fmt(volumeMax/1000000,2)} triệu đơn vị KL nguồn`));
      volumes.forEach((v,i) => {
        const h=v/volumeMax*(barBottom-barTop);
        const bar=svg('rect',{x:x(i)-Math.min(9,plotWidth/rows.length*0.65)/2,y:barBottom-h,width:Math.min(9,plotWidth/rows.length*0.65),height:h,class:'eod-volume',tabindex:0,role:'button'});
        volumeBars.push(bar);frame.append(bar);
      });
    }
    for(const i of [...new Set(width<480 ? [0,rows.length-1] : [0,Math.floor((rows.length-1)/2),rows.length-1])]) {
      frame.append(svg('text',{x:x(i),y:height-7,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle',class:'eod-axis'},dateVN(rows[i].date)));
    }
    const tooltip=node('p','Chọn một ngày để xem số liệu.','chart-tooltip'); tooltip.setAttribute('aria-live','polite');
    const crossV=svg('line',{class:'chart-crosshair',y1:lineTop,y2:hasBars?barBottom:lineBottom,visibility:'hidden'});
    const crossH=svg('line',{class:'chart-crosshair',x1:left,x2:width-right,visibility:'hidden'});
    const point=svg('circle',{r:5,class:'eod-point',visibility:'hidden'});frame.append(crossV,crossH,point);
    let cursor=0,drag=null;
    function inspect(i){
      cursor=Math.max(0,Math.min(rows.length-1,i));const row=rows[cursor],value=values[cursor];
      const yy=value==null?lineBottom:y(value);
      for(const [line,attrs] of [[crossV,{x1:x(cursor),x2:x(cursor)}],[crossH,{y1:yy,y2:yy}],[point,{cx:x(cursor),cy:yy}]]){Object.entries(attrs).forEach(([k,v])=>line.setAttribute(k,v));line.setAttribute('visibility',value==null?'hidden':'visible');}
      tooltip.textContent=`${row.date} · ${row.symbol} · ${label}: ${value==null?'thiếu dữ liệu':fmt(value)} ${unit} · KL ${fmt(row.volume_shares,0)} đơn vị nguồn · ${options.source||'SSI FastConnect V3'}`;
    }
    const localX=e=>(e.clientX-frame.getBoundingClientRect().left)/frame.getBoundingClientRect().width*width;
    frame.setAttribute('tabindex','0');frame.setAttribute('role','group');
    frame.addEventListener('pointermove',e=>{
      const px=localX(e);inspect(Math.round((px-left)/plotWidth*(rows.length-1)));
      if(drag){const shift=Math.round((drag.x-px)/plotWidth*rows.length),n=drag.end-drag.start,start=Math.max(0,Math.min(full.length-n,drag.start+shift));target._zoom=[start,start+n];}
    });
    frame.addEventListener('pointerdown',e=>{frame.setPointerCapture(e.pointerId);drag={x:localX(e),start:zoom?.[0]||0,end:zoom?.[1]||full.length};});
    frame.addEventListener('pointerup',()=>{if(drag&&target._zoom)chart(selector,field,label,unit,options);drag=null;});
    frame.addEventListener('pointerleave',()=>{if(!drag)[crossV,crossH,point].forEach(n=>n.setAttribute('visibility','hidden'));});
    function resize(factor){const start=zoom?.[0]||0,end=zoom?.[1]||full.length,n=Math.min(full.length,Math.max(2,Math.round((end-start)*factor))),center=start+cursor;const next=Math.max(0,Math.min(full.length-n,center-Math.floor(n/2)));target._zoom=[next,next+n];chart(selector,field,label,unit,options);}
    frame.addEventListener('wheel',e=>{e.preventDefault();resize(e.deltaY<0?.7:1.4);},{passive:false});
    frame.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','+','-'].includes(e.key))e.preventDefault();if(e.key==='ArrowLeft')inspect(cursor-1);if(e.key==='ArrowRight')inspect(cursor+1);if(e.key==='+')resize(.7);if(e.key==='-')resize(1.4);if(e.key==='Home'){delete target._zoom;chart(selector,field,label,unit,options);}});
    const reset=node('button','Đặt lại zoom','button secondary');reset.type='button';reset.addEventListener('click',()=>{delete target._zoom;chart(selector,field,label,unit,options);});
    target.append(reset);
    target.append(frame,tooltip,node('p',`${rows[0]?.symbol||state.symbol} · ${label} (${unit}) · ${options.source||'SSI FastConnect V3'} · ${rows[0]?.date||'—'}–${rows.at(-1)?.date||'—'}`,'helper'));
  }
  function renderCharts() {
    chart('#price-chart','close_vnd','Giá đóng cửa','đơn vị giá nguồn',{main:true});
    chart('#volume-trend-chart','volume_shares',state.resolution==='1D'?'Khối lượng phiên & TB20 trước':'Khối lượng tổng hợp (không so với TB20 ngày)','đơn vị KL nguồn',{bars:true,volumeComparison:state.resolution==='1D'});
    chart('#relative-chart','relative_volume20','Khối lượng tương đối','lần');
    chart('#volatility-chart','volatility20_pct','Volatility20','%');
    chart('#value-chart','source_value_vnd','Proxy SSI value','đơn vị nguồn');
  }
  function filteredRows() {
    const query=state.search.trim().toUpperCase();
    const rows=state.rows.filter(row => !query || row.date.includes(query) || row.symbol.includes(query));
    return rows.sort((a,b) => {
      const comparison=state.sort==='date' ? a.date.localeCompare(b.date) : Number(a[state.sort])-Number(b[state.sort]);
      return state.descending ? -comparison : comparison;
    });
  }
  function renderTable() {
    const rows=filteredRows(), pages=Math.ceil(rows.length/pageSize);
    state.page=Math.max(1,Math.min(state.page,pages || 1));
    const body=q('#eod-table-body'); body.replaceChildren();
    rows.slice((state.page-1)*pageSize,state.page*pageSize).forEach(row => {
      const tr=node('tr');
      for(const field of ['date','open_vnd','high_vnd','low_vnd','close_vnd','volume_shares','source_value_vnd']) tr.append(node('td',field==='date'?dateVN(row.date):fmt(row[field],field==='volume_shares'?0:2)));
      body.append(tr);
    });
    if (!rows.length) { const td=node('td',state.rows.length?'Không có ngày khớp bộ lọc. Thử xóa nội dung tìm kiếm.':'Không có dòng EOD đã kiểm chứng.'); td.colSpan=7; const tr=node('tr');tr.append(td);body.append(tr); }
    text('#table-count',`${rows.length} / ${state.rows.length} dòng khớp · ${state.symbol || '—'}`);
    text('#eod-table-caption',`${state.symbol || '—'} · ${rows.length} dòng khớp · giá đơn vị giá nguồn; khối lượng nguồn`);
    text('#page-status',`Trang ${pages ? state.page : 0} / ${pages}`);
    q('#page-prev').disabled=state.page<=1;
    q('#page-next').disabled=state.page>=pages;
    q('#export-eod').disabled=!rows.length;
    document.querySelectorAll('[data-sort]').forEach(button => {
      if(button.dataset.sort===state.sort) button.parentElement.setAttribute('aria-sort',state.descending?'descending':'ascending');
      else button.parentElement.removeAttribute('aria-sort');
    });
  }
  async function loadRankings() {
    const ticket=++rankingRevision;
    const metric=q('#ranking-metric').value;
    try {
      const result=await request(`/api/market/rankings?${params()}&metric=${encodeURIComponent(metric)}`);
      if(ticket!==rankingRevision) return;
      q('#ranking-body').replaceChildren();
      if(!result.available || result.rows.length<2) {
        text('#ranking-empty',result.message||'Không đủ độ bao phủ để xếp hạng.');text('#ranking-scope',`${result.coverage?.gate.n??0}/${result.coverage?.gate.denominator??'—'} · ${result.coverage?.date||'—'}`);q('#ranking-empty').hidden=false;return;
      }
      q('#ranking-empty').hidden=true;
      const field=metric==='volume'?'volume_shares':metric;
      const unit=metric==='volume'?'KL nguồn':metric==='return_pct'?'%':'lần';
      text('#ranking-unit',unit);text('#ranking-scope',`${result.rows.length} mã được tải · phiên cuối từng mã · giảm dần`);
      result.rows.forEach(row => {
        const tr=node('tr'), td=node('td'), button=node('button',row.symbol,'rank-symbol');
        button.type='button'; button.setAttribute('aria-label',`Xem ${row.symbol}`);
        button.addEventListener('click',() => {q('#symbol-filter').value=row.symbol;state.symbol=row.symbol;loadSeries();});
        td.append(button);tr.append(td,node('td',`${fmt(row[field],metric==='volume'?0:2)} ${unit}`));q('#ranking-body').append(tr);
      });
    } catch(error) {
      if(ticket!==rankingRevision) return;
      q('#ranking-body').replaceChildren();text('#ranking-empty',`Không đọc được xếp hạng local: ${error.message}`);q('#ranking-empty').hidden=false;
    }
  }
  async function loadSeries() {
    const ticket=++revision;
    setBusy(true);q('#eod-error').hidden=true;
    clearData('Đang đọc dữ liệu local…');
    try {
      const payload=await request(`/api/market/series?${params()}`);
      if(ticket!==revision) return;
      if(!payload.available) throw new Error((payload.issues || []).join(' · ') || 'Chưa có snapshot đã kiểm chứng.');
      state.rows=payload.rows;state.summary=payload.summary;state.page=1;document.querySelectorAll('.chart-stage').forEach(n=>delete n._zoom);
      renderSummary(payload);renderCharts();renderTable();text('#global-source',`Historical EOD · SSI · ${state.symbol} · nến ${payload.resolution} · cập nhật hợp lệ ${payload.last_available_session||'chưa có'} · ${payload.unit_status}`);return true;
    } catch(error) {
      if(ticket!==revision) return;
      const message=`Không thể dùng snapshot: ${error.message}. Kiểm tra file bằng scripts/validate_demo_eod.py; mở Phương pháp để xem giới hạn.`;
      clearData(message);showError(message);text('#snapshot-state','Khoảng/mã chưa khả dụng · sửa bộ lọc hoặc đọc lại snapshot');return false;
    } finally { if(ticket===revision) setBusy(false); }
  }
  async function loadSnapshot() {
    ++revision; ++rankingRevision;
    setBusy(true);q('#eod-error').hidden=true;
    q('#ranking-body').replaceChildren();
    try {
      const meta=await request('/api/market/meta');state.meta=meta;
      if(meta.historical_range){
        const range=meta.historical_range;window.HistoricalRange=range;
        for(const id of ['market-from','market-to','alert-from','alert-to']){const input=q('#'+id);if(input){input.min=range.start;input.max=range.end;}}
        document.querySelectorAll('[data-range="3Y"],[data-range="5Y"]').forEach(button=>{button.disabled=false;button.title='Xem phần lịch sử SSI đã có từ '+range.start+' đến '+range.actual_last;});
        text('#global-source',`Historical EOD · SSI · ${range.actual_first}–${range.actual_last}`);
        text('#sidebar-history-date',`Đến ${dateVN(range.actual_last)}`);text('#history-banner-title',`Historical EOD · Đến ${dateVN(range.actual_last)}`);
      }

      provenance(meta);
      const select=q('#symbol-filter');select.replaceChildren();
      if(!meta.available) {
        const message=`Chưa có snapshot đã kiểm chứng. ${(meta.issues || []).join(' · ')} Chạy fetch_ssi_history.py hoặc kiểm tra snapshot SSI local.`;
        select.append(node('option','Chưa có dữ liệu'));clearData(message);showError(message);text('#snapshot-state','BLOCKED · Chưa có snapshot đã kiểm chứng');return;
      }
      const directory=await request('/api/market/catalog');catalog=directory.securities;hasCoverage=Boolean(directory.coverage_available);memberships=directory.index_memberships||{};
      q('#market-scope').querySelectorAll('[data-index-scope]').forEach(o=>o.remove());directory.indexes.forEach(r=>{const o=node('option',`Chỉ số: ${r.index}`);o.value='INDEX:'+r.index;o.dataset.indexScope='true';o.disabled=!memberships[r.index];if(o.disabled)o.title='Chưa có membership SSI đã kiểm chứng; chọn sàn hoặc chỉ số riêng bên dưới';q('#market-scope').append(o);});
      if(!catalog.length)catalog=meta.loaded_symbols.map(symbol=>({symbol,board:'unknown'}));
      const types=q('#market-type');types.replaceChildren(node('option','Tất cả loại'));types.options[0].value='ALL';
      [...new Set(catalog.map(r=>r.stockType).filter(Boolean))].sort().forEach(type=>{const o=node('option',type);o.value=type;types.append(o);});
      const indices=q('#index-select');indices.replaceChildren();directory.indexes.forEach(r=>{const o=node('option',r.indexName||r.index);o.value=r.index;indices.append(o);});if(directory.indexes.some(r=>r.index==='VNINDEX'))indices.value='VNINDEX';
      const book=q('#book-symbol');book.replaceChildren();catalog.filter(r=>!window.StaticLiquidity||memberships.VN30?.includes(r.symbol)).forEach(r=>{const o=node('option',r.symbol);o.value=r.symbol;book.append(o);});
      syncToolbar();filterCatalog();if(meta.historical_range&&state.range!=='CUSTOM'&&(!state.to||state.to==='2026-11-04')){window.MarketState.set({to:meta.historical_range.actual_last});}if([...book.options].some(o=>o.value===state.symbol))book.value=state.symbol;book.dispatchEvent(new Event('change'));
      await Promise.all([loadSeries(),loadRankings(),loadCoverage(),loadIndex()]);
    } catch(error) {
      const message=`Không kết nối được ứng dụng local: ${error.message}. Kiểm tra chương trình đang chạy rồi chọn Đọc lại snapshot.`;
      clearData(message);showError(message);invalidateProvenance(message);text('#snapshot-state','Không đọc được server local');
    } finally {setBusy(false);}
  }
  q('#symbol-filter').addEventListener('change',event => window.MarketState.set({symbol:event.target.value}));
  q('#book-symbol').addEventListener('change',event=>window.MarketState.set({symbol:event.target.value}));
  for(const [id,key] of [['market-scope','scope'],['market-type','type'],['market-from','from'],['market-to','to'],['market-resolution','resolution']])q('#'+id).addEventListener('change',e=>window.MarketState.set({[key]:e.target.value,...((key==='from'||key==='to')?{range:'CUSTOM'}:{})}));
  q('#market-search').addEventListener('input',filterCatalog);
  q('#index-select').addEventListener('change',loadIndex);
  document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click',() => {
    window.MarketState.set({range:button.dataset.range});
    document.querySelectorAll('[data-range]').forEach(other => other.setAttribute('aria-pressed',String(button===other)));
  }));
  document.querySelectorAll('[data-series]').forEach(button => button.addEventListener('click',() => {
    const series=button.dataset.series;state[series]=!state[series];button.setAttribute('aria-pressed',String(state[series]));renderCharts();
  }));
  q('#refresh').addEventListener('click',async () => {await loadSnapshot();toast(state.meta?.available?'Đã đọc và kiểm chứng lại snapshot local. Không gọi nguồn internet.':'Snapshot chưa khả dụng. Xem thông báo và kiểm tra file local.');});
  q('#ranking-metric').addEventListener('change',loadRankings);
  q('#table-search').addEventListener('input',event => {state.search=event.target.value;state.page=1;renderTable();});
  document.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click',() => {
    if(state.sort===button.dataset.sort) state.descending=!state.descending;
    else {state.sort=button.dataset.sort;state.descending=state.sort==='date';}
    state.page=1;renderTable();
  }));
  q('#page-prev').addEventListener('click',() => {state.page--;renderTable();});
  q('#page-next').addEventListener('click',() => {state.page++;renderTable();});
  q('#export-eod').addEventListener('click',() => {
    const rows=filteredRows();if(!rows.length) return;
    const csvCell=(value,key) => {
      let content=String(value ?? '');
      if(key==='upstream_source' && /^[\s]*[=+@-]/.test(content)) content="'"+content;
      return `"${content.replace(/"/g,'""')}"`;
    };
    const source=(state.meta?.manifest?.upstream_sources || []).map(s=>s.name).join('; ').replace(/[\r\n]/g,' ');
    const lines=[`# Historical EOD; source=${source}; asof=${state.meta.asof_date}; timezone=Asia/Ho_Chi_Minh`, `# symbol=${state.symbol}; range=${state.range}; search=${state.search.replace(/[\r\n]/g,' ')}; rows=${rows.length}; price=source_native_unverified; volume=source_native_unverified; turnover=unavailable; source_value=SSI_proxy_unverified`,columns.join(','),...rows.map(row=>columns.map(key=>csvCell(row[key],key)).join(','))];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const link=node('a');link.href=url;link.download=`eod-${state.symbol}-${state.range}-filtered.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast(`Đã xuất ${rows.length} dòng khớp bộ lọc, gồm nguồn và ngày chốt. Số thập phân giữ nguyên từ CSV.`);
  });
  window.addEventListener('chart-theme-change',()=>{if(state.rows.length)renderCharts();loadIndex();});
  window.addEventListener('hashchange',() => {if(state.rows.length) renderCharts();loadIndex();});
  let resizeTimer;
  window.addEventListener('resize',() => {clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(state.rows.length) renderCharts();},150);});
  loadSnapshot();
}());
