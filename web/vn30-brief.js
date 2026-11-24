
(async () => {
  const status = document.querySelector('#review-session');
  if (!status) return;
  if (typeof window.StaticLiquidity === 'undefined' && document.querySelector('#vn30-review')) {
    status.textContent = 'Bản tin tổng hợp VN30 dùng dữ liệu công bố trên phiên bản web.';
    document.querySelector('#review-export').disabled = true;
    return;
  }
  status.textContent = 'Đang đọc dữ liệu SSI…';
  const control = document.querySelector('#review-export');
  control.disabled = true;
  const get = async query => {
    const res = await fetch('/api/market-data?' + query, {signal: AbortSignal.timeout(15000)});
    if (!res.ok) throw Error(String(res.status));
    return res.json();
  };
  const bookStatus = document.querySelector('#review-book');
  const make=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node;};
  const digest=make('section');digest.className='card liquidity-panel';
  const digestSource=make('p','Đang kiểm tra mốc SSI…'), digestEod=make('p','Đang đọc độ phủ EOD…');
  const digestDepth=make('p','Đang đọc sổ lệnh…');
  digest.append(make('h2','Bản tin thanh khoản 30 giây'),digestSource,digestEod,digestDepth);
  const flags=make('section');flags.className='card liquidity-panel';
  const flagStatus=make('p','Đang kiểm tra các tín hiệu SSI…'),flagList=make('ul'),flagTime=make('p');
  flagTime.className='helper';
  const previousFlags=make('details'),previousTitle=make('summary','Lần ghi nhận trước'),previousList=make('ul');
  previousFlags.append(previousTitle,previousList);previousFlags.hidden=true;
  const flagMethod=make('p','Spread mở rộng khi tăng ít nhất 50% và 5 bps so với báo giá hợp lệ trước đó trong lượt xem này. Độ sâu dựa trên cửa sổ 60 giây.');
  flagMethod.className='helper';
  flags.append(make('h2','Bảng cờ đỏ thanh khoản'),flagStatus,flagTime,flagList,previousFlags,flagMethod);
  status.closest('section').before(digest,flags);
  const lastSpreads=new Map(),wideSpreads=new Map();
  const flagKey='liquiditylab:last-flags:v1';
  let remembered={};
  try {
    const saved=JSON.parse(localStorage.getItem(flagKey)||'{}');
    if(saved&&typeof saved==='object'&&!Array.isArray(saved))remembered=saved;
  } catch {}
  let quoteFlags=[],eodFlags=[],observedDepthFlags=[];
  const vietnamTime=new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'medium'});
  const stamp=value=>value!=null&&Number.isFinite(new Date(value).getTime())?vietnamTime.format(new Date(value)):'chưa có mốc';
  function ticker(symbol){
    if(!window.SymbolDossier)return make('span',symbol);
    const button=make('button',symbol);button.type='button';button.className='rank-symbol';
    button.setAttribute('aria-label','Mở hồ sơ '+symbol);
    button.onclick=()=>window.SymbolDossier.open(symbol);return button;
  }
  let flagVersion, lastLive, bookMissing=false;
  const todayIct=()=>new Date(Date.now()+7*3600000).toISOString().slice(0,10);
  function renderSources(){
    const candles=data?.evaluationTime?'Nến SSI đến '+stamp(data.evaluationTime):'Đang đọc nến SSI';
    const books=lastLive?.updated_at?'Sổ lệnh ghi nhận cuối '+stamp(lastLive.updated_at):'Đang đọc sổ lệnh';
    digestSource.textContent=candles+' · '+books+'.';
    flagTime.textContent=candles+' · EOD chính thức '+(data?.lastEod||'đang đọc')+'.';
  }
  const eventKey=entry=>entry.kind+':'+(entry.symbol||'VN30');
  function flagRow(entry,previous=false){
    const item=make('li');if(entry.symbol)item.append(ticker(entry.symbol),' · ');
    item.append(entry.text+' · '+(previous?'Lần ghi nhận trước: ':'')+entry.source);return item;
  }
  function drawFlags(){
    const entries=[...quoteFlags,...eodFlags];
    let dirty=false;
    for(const entry of [...entries,...observedDepthFlags]){
      if(!entry.kind||!entry.observedAt)continue;
      const key=eventKey(entry);
      if(!remembered[key]||entry.observedAt>remembered[key].observedAt){
        remembered[key]=entry;dirty=true;
      }
    }
    if(dirty){
      remembered=Object.fromEntries(Object.entries(remembered).sort((a,b)=>b[1].observedAt-a[1].observedAt).slice(0,120));
      try{localStorage.setItem(flagKey,JSON.stringify(remembered));}catch {}
    }
    const active=new Set(entries.map(eventKey));
    const old=Object.values(remembered).filter(entry=>entry?.observedAt&&!active.has(eventKey(entry)))
      .sort((a,b)=>b.observedAt-a.observedAt);
    const version=JSON.stringify([entries,old,bookMissing]);
    if(version===flagVersion)return;
    flagVersion=version;
    flagList.replaceChildren(...entries.map(entry=>flagRow(entry)));
    previousList.replaceChildren(...old.map(entry=>flagRow(entry,true)));
    previousFlags.hidden=!old.length;
    if(!old.length||!entries.length)previousFlags.open=Boolean(old.length);
    previousTitle.textContent='Lần ghi nhận trước ('+old.length+')';
    flagStatus.textContent=entries.length?entries.length+' dấu hiệu theo quy tắc đang theo dõi.':
      bookMissing?'Chưa có sổ lệnh của ngày hôm nay. Đang hiển thị các lần ghi nhận đã lưu.':'Chưa thấy dấu hiệu đạt ngưỡng trong dữ liệu hiện có.';
  }
  function refreshFlags(live,fresh,recent){
    const now=Date.now();
    const ict=new Date(now+7*3600000), minute=ict.getUTCHours()*60+ict.getUTCMinutes();
    const trading=ict.getUTCDay()>0&&ict.getUTCDay()<6&&((minute>=555&&minute<690)||(minute>=780&&minute<870));
    quoteFlags=[];
    if(trading&&!recent(live.updated_at)){
      quoteFlags.push({kind:'gap',text:'Gián đoạn dữ liệu sổ lệnh',source:'Mốc bộ thu '+stamp(live.updated_at),observedAt:Date.parse(live.updated_at)});
    }else if(trading&&fresh.length===0){
      quoteFlags.push({kind:'no-quotes',text:'Chưa có báo giá hai phía đủ mới',source:'Mốc bộ thu '+stamp(live.updated_at),observedAt:Date.parse(live.updated_at)});
    }
    for(const row of fresh){
      const bid=Number(row.bids[0]?.[0]),ask=Number(row.asks[0]?.[0]),time=Date.parse(row.quote_time);
      if(!(ask>bid&&bid>0))continue;
      const bps=(ask-bid)/((ask+bid)/2)*10000,previous=lastSpreads.get(row.symbol);
      if(previous&&time>previous.time&&time-previous.time<=120000&&bps>=previous.bps*1.5&&bps-previous.bps>=5)
        wideSpreads.set(row.symbol,{bps,before:previous.bps,time});
      if(!previous||time>previous.time)lastSpreads.set(row.symbol,{bps,time});
    }
    for(const [symbol,wide] of wideSpreads){
      if(now-wide.time>60000){wideSpreads.delete(symbol);continue;}
      quoteFlags.push({kind:'spread',symbol,text:'Spread mở rộng '+fmt(wide.before,2)+' → '+fmt(wide.bps,2)+' bps',source:'SSI '+stamp(wide.time),observedAt:wide.time});
    }
    observedDepthFlags=Object.entries(live.depth_windows||{}).filter(([,depth])=>depth.state==='OBSERVED_LOW_DEPTH')
      .map(([symbol,depth])=>{
        const time=depth.observed_until||depth.updated_at;
        return {kind:'depth',symbol,text:'Đã quan sát đợt độ sâu mua thấp trong cửa sổ 60 giây',source:'SSI '+stamp(time),observedAt:Date.parse(time)};
      });
    quoteFlags.push(...observedDepthFlags.filter(entry=>now-entry.observedAt>=0&&now-entry.observedAt<=30000));
    drawFlags();
  }
  let checkingBook = false;
  async function refreshBook() {
    if (checkingBook || document.hidden || !['', '#monitor'].includes(location.hash)) return;
    checkingBook = true;
    try {
      const live = await get('kind=live');
      lastLive=live;
      bookMissing=live.updated_at?.slice(0,10)!==todayIct();
      const isRecent = value => {
        const age = Date.now() - Date.parse(value);
        return age >= 0 && age <= 30000;
      };
      const fresh = isRecent(live.updated_at) ? (live.rows || []).filter(row =>
        isRecent(row.quote_time) && row.bids?.length && row.asks?.length) : [];
      const saved = Object.keys(live.last_books || {}).length;
      const trades = isRecent(live.updated_at) ? (live.rows || []).filter(row =>
        row.trade_time?.slice(0, 10) === live.updated_at.slice(0, 10) && row.total_volume != null) : [];
      bookStatus.textContent = 'SSI trong phiên · ' +
        (fresh.length ? fresh.length + ' mã có báo giá mua/bán mới' :
          saved ? saved + ' mã có bản chụp sổ lệnh đã lưu' : 'Đang chờ báo giá mua/bán') +
        (trades.length ? ' · ' + trades.length + ' mã có khối lượng khớp lũy kế' : '') +
        '. Xem giờ nguồn trong tab Sổ lệnh.';
      renderSources();
      digestDepth.textContent=(bookMissing?'Chưa có sổ lệnh ngày '+todayIct()+' · ':'')+fresh.length+' mã có báo giá hai phía trong 30 giây · '+saved+' mã có bản chụp lưu.';
      refreshFlags(live,fresh,isRecent);
    } catch (error) {
      bookStatus.textContent = error.message === '404' ? 'Chưa có sổ lệnh SSI được công bố.' :
        'Chưa kiểm tra được trạng thái sổ lệnh SSI.';
      digestDepth.textContent=bookStatus.textContent;
      quoteFlags=[{text:'Không đọc được trạng thái sổ lệnh',source:'Đang thử lại'}];drawFlags();
    } finally {
      checkingBook = false;
    }
  }
  let data;
  drawFlags();
  refreshBook();
  setInterval(refreshBook, 15000);
  let checkingEod = false;
  const seriesCache = new Map();
  async function refreshEod(){
    if(checkingEod || document.hidden || !['', '#monitor'].includes(location.hash))return;
    checkingEod = true;
    try{
      const [history,coverage]=await Promise.all([get('kind=history'),get('kind=intraday').catch(()=>null)]);
      const members=data?.members || [...new Set((await get('kind=catalog&board=VN30&size=30')).index_memberships?.VN30 || [])];
      const lastEod=members.map(symbol=>history.symbols[symbol]?.last).filter(Boolean).sort().at(-1);
      const covered=coverage?.coverage||coverage?.symbols||{};
      const latest=members.map(symbol=>covered[symbol]?.last).filter(Boolean).sort().at(-1);
      const session=latest?.slice(0,10)>lastEod?latest.slice(0,10):lastEod;
      const refreshKey=JSON.stringify([session,coverage?.updated_at,history.updated_at]);
      if(!session)throw Error('Missing session');
      const pending=members.filter(symbol=>{
        const entry=history.symbols[symbol];
        return entry && seriesCache.get(symbol)?.revision!==(entry.revision || entry.last);
      });
      if(data?.refreshKey===refreshKey && !pending.length){
        renderBrief();
        return;
      }
      let next=0;
      await Promise.all(Array.from({length:Math.min(5,pending.length)},async()=>{
        while(next<pending.length){
          const symbol=pending[next++];
          const entry=history.symbols[symbol];
          try{
            const rows=await get('kind=series&tail=21&symbol='+encodeURIComponent(symbol)+
              '&revision='+encodeURIComponent(entry.revision || entry.last));
            if(Array.isArray(rows)&&rows.at(-1)?.date===entry.last)
              seriesCache.set(symbol,{revision:entry.revision || entry.last,rows});
          }catch {}
        }
      }));
      const upcoming=members.map(symbol=>{
        const rows=seriesCache.get(symbol)?.rows||[], intraday=covered[symbol];
        const volume=Number(intraday?.session_volume);
        const current=rows.at(-1)?.date<session && intraday?.last?.slice(0,10)===session &&
          intraday.session_volume!=null && Number.isFinite(volume) && volume>=0;
        const latest=current?{symbol,date:session,volume_shares:volume,provisional:true,closed_at:intraday.last}:null;
        return evaluate(symbol,latest?[...rows,latest]:rows,session);
      });
      if(!upcoming.some(row=>row.latest))throw Error('No confirmed EOD rows');
      data={members,session,lastEod,evaluationTime:latest,refreshKey,provisional:upcoming.some(row=>row.latest?.provisional)};
      records=upcoming;
      control.disabled=false;
      renderBrief();
    }catch{
      status.textContent=data ? 'SSI EOD · Phiên '+data.session+' · Đang thử lại cập nhật' :
        'Chưa đọc được bản tin SSI EOD. Trang sẽ tự thử lại.';
    }finally{checkingEod=false;}
  }
  const root = document.querySelector('#vn30-review');
  const body = root.querySelector('tbody');
  const detail = root.querySelector('dialog');
  const fmt = (value, digits = 0) => Number.isFinite(value)
    ? value.toLocaleString('vi-VN', {maximumFractionDigits: digits}) : '—';
  let records = [], selected = null;
  function cell(row, value) {
    const td = document.createElement('td');
    td.textContent = value;
    row.append(td);
    return td;
  }
  function draw() {
    const filtered = records.filter(r => r.symbol.includes(root.querySelector('input').value.trim().toUpperCase()));
    const sorted = filtered.sort((a,b) => (b.rv ?? -1) - (a.rv ?? -1) || a.symbol.localeCompare(b.symbol));
    body.replaceChildren();
    for (const r of sorted.slice(0, root.querySelector('select').value === '5' ? 5 : sorted.length)) {
      const tr = body.insertRow();
      cell(tr, '').append(ticker(r.symbol));
      cell(tr, r.latest?.date ?? '—');
      cell(tr, fmt(r.latest ? Number(r.latest.volume_shares) : NaN));
      cell(tr, fmt(r.rv, 4));
      cell(tr, r.rv == null ? 'Chưa đủ dữ liệu' : r.rv >= 3 ? 'Ưu tiên cao' : r.rv >= 2 ? 'Theo dõi' : 'Dưới ngưỡng');
      if(r.latest?.provisional)tr.lastChild.textContent+=' · Tạm tính';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button secondary';
      button.textContent = 'Xem bằng chứng';
      button.addEventListener('click', () => open(r));
      cell(tr, '').append(button);
    }
    root.querySelector('#review-matches').textContent = body.rows.length + '/' + sorted.length + ' mã khớp';
  }
  function open(r) {
    selected = r;
    const fields = {
      '#review-symbol': r.symbol + ' · Bằng chứng RV20',
      '#review-reason': r.rv == null ? 'Chưa đủ quan sát hợp lệ để tính RV20.' :
        'RV20 = ' + fmt(+r.latest.volume_shares) + ' / ' + fmt(r.avg,2) + ' = ' + fmt(r.rv,4) + ' lần.',
      '#review-source': (r.latest?.provisional?'SSI trong phiên, khối lượng tích lũy đến '+stamp(r.latest.closed_at)+'. Phiên đánh giá ':'Nguồn SSI EOD. Phiên đánh giá ') + (r.latest?.date || '—') +
        '. Ngưỡng theo dõi ≥ 2 lần, ưu tiên cao ≥ 3 lần.',
    };
    for (const [selector, value] of Object.entries(fields)) detail.querySelector(selector).textContent = value;
    const tbody = detail.querySelector('tbody');
    tbody.replaceChildren();
    for (const row of [...r.prior, ...(r.latest ? [r.latest] : [])]) {
      const tr = tbody.insertRow();
      cell(tr, row.date);
      cell(tr, fmt(+row.volume_shares));
      cell(tr, row === r.latest ? 'Phiên đánh giá' : 'Cửa sổ tham chiếu');
    }
    detail.showModal();
  }
  root.querySelector('input').addEventListener('input',draw);
  root.querySelector('select').addEventListener('change',draw);
  detail.querySelector('#review-chart').addEventListener('click', () => {
    if (!selected) return;
    const select = document.querySelector('#symbol-filter');
    if (select && [...select.options].some(o=>o.value === selected.symbol)){
      select.value = selected.symbol;
      select.dispatchEvent(new Event('change',{bubbles:true}));
    } else {
      window.MarketState.set({symbol:selected.symbol});
    }
    detail.close();
    location.hash = '#analysis';
  });
  root.querySelector('#review-export').addEventListener('click', () => {
    const csv = ['symbol,session,volume_source,mean_previous_20,rv20,provisional,source_time',
      ...records.map(r => [r.symbol,r.latest?.date ?? '',r.latest?.volume_shares ?? '',r.avg ?? '',r.rv ?? '',Boolean(r.latest?.provisional),r.latest?.closed_at||r.latest?.date||''].join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));
    const link = document.createElement('a');
    link.href=url; link.download='liquiditylab-vn30-'+data.session+'.csv'; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  function evaluate(symbol, rows, session) {
    const index = rows.findIndex(r => r.date === session);
    const latest = rows[index];
    const prior = index >= 0 ? rows.slice(Math.max(0,index-20),index) : [];
    const valid = row => row?.volume_shares != null && row.volume_shares !== '' &&
      Number.isFinite(Number(row.volume_shares)) && Number(row.volume_shares) >= 0;
    const avg = prior.length === 20 && prior.every(valid)
      ? prior.reduce((sum,r)=>sum+Number(r.volume_shares),0)/20 : null;
    const rv = avg > 0 && valid(latest) ? Number(latest.volume_shares)/avg : null;
    return {symbol,latest,prior,avg,rv};
  }

  function renderBrief(){
  const eligible = records.filter(r=>r.rv!=null);
  const alerts = eligible.filter(r=>r.rv>=2).sort((a,b)=>b.rv-a.rv||a.symbol.localeCompare(b.symbol));
  digestEod.textContent=`${data.provisional?'Trong phiên · RV20 tạm tính':'EOD'} ${data.session} · ${eligible.length}/${data.members.length} mã tính được RV20 · ${alerts.length} mã đạt ≥2`+
    (alerts.length?' · Cao nhất '+alerts.slice(0,3).map(r=>r.symbol+' '+fmt(r.rv,2)+'×').join(', '):'')+'.';
  eodFlags=alerts.map(r=>({kind:'rv20',symbol:r.symbol,text:(r.rv>=3?'RV20 ưu tiên cao ':'RV20 theo dõi ')+fmt(r.rv,2)+' lần'+(r.latest.provisional?' · tạm tính':''),
    source:r.latest.provisional?'SSI đến '+stamp(r.latest.closed_at):'SSI EOD '+r.latest.date,
    observedAt:Date.parse(r.latest.closed_at||r.latest.date+'T00:00:00+07:00')}));
  drawFlags();
  root.querySelector('#review-session').textContent = data.provisional?
    'SSI trong phiên · '+data.session+' · Tạm tính đến '+stamp(data.evaluationTime)+' · EOD chính thức '+data.lastEod:
    'SSI EOD · Phiên '+data.session;
  renderSources();
  root.querySelector('#review-coverage').textContent = records.filter(r=>r.latest).length+'/'+data.members.length+
    ' mã có dữ liệu phiên này. '+eligible.length+' mã đủ điều kiện tính RV20.';
  root.querySelector('#review-alerts').textContent = eligible.length
    ? alerts.length+'/'+eligible.length+' mã đạt ngưỡng RV20 ≥ 2'+(alerts.length ? '. Cao nhất: '+alerts.slice(0,3).map(r=>r.symbol+' '+fmt(r.rv,2)+'×').join(', ')+'.' : '.')
    : 'Chưa đủ dữ liệu để đánh giá RV20.';
  draw();
  }
  refreshEod();
  window.addEventListener('hashchange',()=>{refreshEod();refreshBook();});
  document.addEventListener('visibilitychange',()=>{refreshEod();refreshBook();});
  setInterval(refreshEod,60000);
})();
