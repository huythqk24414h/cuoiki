/* SSI-specific status, historical alerts and explicitly manual book fallback. */
(function(){
  'use strict';
  const q=selector=>document.querySelector(selector);
  request('/api/market/research').then(r=>{const n=q('#research-readiness');if(n)n.textContent=`${r.status} · H1: ${r.h1} · ${r.recorded_days.length} ngày raw, ${r.counts.quote||0} quote / ${r.counts.trade||0} trade. Chưa đủ dữ liệu và hợp đồng đơn vị để đánh giá M0/M1/M2.`;}).catch(()=>{});
  const fmt=(value,digits=2)=>value==null?'—':calculator.formatDecimal(String(value),digits);
  const el=(tag,value)=>{const n=document.createElement(tag);if(value!=null)n.textContent=value;return n;};
  let manualMode=false;
  let manual=null, alerts=[], page=1, bookRevision=0, alertRevision=0, alertSummary='Chưa đánh giá',alertHash=null;
  const quality=el('details');quality.className='data-quality';const qualityTitle=el('summary','Chất lượng dữ liệu & kết nối');quality.append(qualityTitle);
  for(const id of ['global-source','global-context','universe-note','coverage-badge','header-source-time']){const item=q('#'+id);if(item)quality.append(item);}
  q('.global-market').append(quality);
  let evidenceRevision=0,evidenceTrigger=null;
  const drawer=q('#alert-evidence-panel');drawer.setAttribute('role','region');drawer.setAttribute('aria-label','Giải thích sự kiện thanh khoản');drawer.tabIndex=-1;
  const close=el('button','Đóng bằng chứng ×');close.type='button';close.className='button secondary';drawer.prepend(close);
  close.onclick=()=>{++evidenceRevision;drawer.hidden=true;window.ChartKit.destroy(eventChart);evidenceTrigger?.focus();};
  drawer.addEventListener('keydown',e=>{if(e.key==='Escape')close.click();});
  const advanced=el('details');advanced.append(el('summary','Kỹ thuật nâng cao · JSON sự kiện & phương pháp'));advanced.append(q('#alert-evidence'));drawer.append(advanced);
  const explanation=el('div'),eventChart=el('div');eventChart.className='chart-stage';drawer.insertBefore(explanation,advanced);drawer.insertBefore(eventChart,advanced);
  async function showEvidence(row,button){
    const ticket=++evidenceRevision;evidenceTrigger=button;drawer.hidden=false;drawer.focus();explanation.replaceChildren(el('p','Đang kiểm chứng bằng chứng…'));window.ChartKit.destroy(eventChart);q('#alert-evidence').textContent=JSON.stringify(row,null,2);
    try{
      const sheet=await request('/api/market/event-evidence?'+new URLSearchParams({symbol:row.symbol,date:row.timestamp}));if(ticket!==evidenceRevision)return;
      const matches=sheet.event_date_exact&&sheet.facts?.symbol===row.symbol&&sheet.facts?.date===row.timestamp&&String(sheet.facts?.rv20)===String(row.value);
      const validContext=Array.isArray(sheet.context)&&sheet.context.length>0&&sheet.context.every(r=>r.symbol===row.symbol&&r.date<=row.timestamp);
      if(!matches||!validContext){explanation.replaceChildren(el('h3','Bằng chứng chưa khớp sự kiện'),el('p','Ngày, mã, RV20 hoặc cửa sổ quan sát không khớp bản cảnh báo đang mở. Hãy đọc lại đánh giá; không diễn giải hoặc vẽ dữ liệu thay thế.'));return;}
      explanation.replaceChildren(el('h3',`${row.symbol} · ${row.timestamp} · RV20 ${fmt(row.value)} lần`));
      explanation.append(el('p',`Cảnh báo xuất hiện vì khối lượng ${fmt(row.volume,0)} / trung bình 20 quan sát trước ${fmt(row.baseline,2)} = ${fmt(row.value,4)} ≥ ${row.threshold}. Ưu tiên ${row.priority==='cao'?'cao (≥3 lần)':'theo dõi (≥2 lần)'}.`));
      explanation.append(el('p',`Đối chiếu máy tính: khớp mã, ngày và RV20. Nguồn quan sát: SSI EOD; đây là cảnh báo do Liquidity Lab tính, không phải cảnh báo phát hành bởi SSI. Cửa sổ hình gồm tối đa 30 quan sát kết thúc tại sự kiện, không có dữ liệu tương lai.`));
      q('#alert-evidence').textContent=JSON.stringify({event:row,facts:sheet.facts,method:sheet.method,verification:{date_symbol_ratio_match:true,no_future_context:true}},null,2);
      sheet.paragraphs.forEach(p=>explanation.append(el('p',p)));
      window.ChartKit.render(eventChart,sheet.context,'volume_shares','Khối lượng đến ngày sự kiện','đơn vị KL nguồn',{bars:true});
    }catch(error){if(ticket===evidenceRevision)explanation.replaceChildren(el('p','Không đọc được bằng chứng: '+error.message));}
  }
  function blankBook(message){
    for(const key of ['bid','ask','spread','imbalance'])q('#book-'+key).textContent='—';
    q('#book-levels').replaceChildren();
    for(let i=1;i<=3;i++){const row=el('tr');[i,'—','—','—','—'].forEach(v=>row.append(el('td',v)));q('#book-levels').append(row);}
    q('#book-evidence').replaceChildren();q('#book-chart')._disposeDepth?.();q('#book-chart').replaceChildren(el('p',message));
    q('#book-status').textContent=message;q('#book-caption').textContent='SSI DATA · Sổ lệnh chưa khả dụng';
  }
  async function loadBook(){
    manualMode=false;
    const id=++bookRevision;
    q('#book-refresh').disabled=true;
    blankBook('Đang kiểm tra trạng thái SSI DATA…');
    try{
      const data=await request('/api/market/book?symbol='+encodeURIComponent(q('#book-symbol').value));
      if(id!==bookRevision)return;
      if(data.available){drawBook({payload:data,result:data},'SSI DATA · LIVE');}
      else{
        blankBook(data.reason || 'Chưa có snapshot SSI DATA đủ điều kiện.');q('#book-caption').textContent=`${data.symbol} · ${data.status} · không phải LIVE`;
        if(data.unverified_levels){
          q('#book-caption').textContent=`SSI DATA · ${data.symbol} · ${data.status} · số theo SDK, chưa xác minh đơn vị giá/KL`;
          q('#book-bid-label').textContent='Giá mua (nguồn)';q('#book-ask-label').textContent='Giá bán (nguồn)';
          q('#book-bid-qty').textContent='KL mua (nguồn)';q('#book-ask-qty').textContent='KL bán (nguồn)';
          q('#book-levels').replaceChildren();
          for(let i=0;i<3;i++){
            const bid=data.unverified_levels.bids[i],ask=data.unverified_levels.asks[i],tr=el('tr');
            [i+1,bid?.[0]??'—',bid?.[1]??'—',ask?.[0]??'—',ask?.[1]??'—'].forEach(v=>tr.append(el('td',v)));q('#book-levels').append(tr);
          }
          for(const [key,value] of [['Nguồn','SSI DATA · chưa chuẩn hóa'],['Event time',data.event_time],['Received at',data.received_at],['Độ trễ quan sát',(data.latency_ms??'—')+' ms'],['Phiên nguồn',data.session||'Chưa nhận cờ phiên'],['Parser',data.unverified_levels.parser]]){
            const div=el('div');div.append(el('dt',key),el('dd',value));q('#book-evidence').append(div);
          }
        }
      }
    }catch(error){if(id===bookRevision)blankBook('Không đọc được server local: '+error.message);}
    finally{if(id===bookRevision)q('#book-refresh').disabled=false;}
  }
  function drawBook(view,label){
    manualMode=label==='MANUAL';
    ++bookRevision;q('#book-refresh').disabled=false;
    const {payload,result}=view;
    q('#book-bid-label').textContent='Giá mua (VND)';q('#book-ask-label').textContent='Giá bán (VND)';
    q('#book-bid-qty').textContent='KL mua (cp)';q('#book-ask-qty').textContent='KL bán (cp)';
    q('#book-status').textContent=`${label} · ${payload.symbol} · ${label==='MANUAL'?'Đầu vào người dùng, không phải SSI/live.':'Quote đủ điều kiện tính chỉ báo.'}`;
    q('#book-caption').textContent=`${label} · giá VND/cp · khối lượng cp`;
    q('#book-status').textContent+=` Spread ${fmt(result.spread_bps,2)} bps đo khoảng chênh giá tốt nhất; độ sâu chỉ gồm ba mức. Imbalance ${fmt(result.imbalance,4)} thể hiện giá trị lệnh chờ nghiêng ${Number(result.imbalance)>0?'phía mua':Number(result.imbalance)<0?'phía bán':'cân bằng'}. Lệnh có thể bị hủy; không dự báo chắc hướng giá hoặc khả năng khớp lệnh lớn.`;
    for(const [id,key] of [['bid','bid_depth_vnd'],['ask','ask_depth_vnd'],['spread','spread_bps'],['imbalance','imbalance']])q('#book-'+id).textContent=fmt(result[key],id==='imbalance'?6:4);
    const body=q('#book-levels');body.replaceChildren();
    for(let i=0;i<3;i++){
      const tr=el('tr'), bid=payload.bids[i],ask=payload.asks[i];
      [i+1,bid?fmt(bid.price):'—',bid?fmt(bid.quantity,0):'—',ask?fmt(ask.price):'—',ask?fmt(ask.quantity,0):'—'].forEach(v=>tr.append(el('td',v)));body.append(tr);
    }
    const details=q('#book-evidence');details.replaceChildren();
    const latency=Date.parse(payload.received_at)-Date.parse(payload.event_time);
    for(const [key,value] of [['Nguồn',label],['Thời gian sổ lệnh',payload.event_time],['Thời gian nhận',payload.received_at],['Độ trễ nguồn / nhập tay',latency+' ms'],['Phiên nguồn / khai báo',payload.session],['Input hash',result.input_hash],['Engine',result.engine_version]]){
      const group=el('div');group.append(el('dt',key),el('dd',value));details.append(group);
    }
    window.LiquidityDepthChart.render(q('#book-chart'),payload,label);
  }
  window.addEventListener('manual-book-updated',event=>{
    manual=event.detail?structuredClone(event.detail):null;
    q('#book-manual').disabled=!manual;
    if(!manual){manualMode=false;blankBook('Bản nhập tay đã thay đổi hoặc bị xóa. Tính lại để xem snapshot MANUAL mới.');}
  });
  q('#book-manual').addEventListener('click',()=>{if(manual)drawBook(manual,'MANUAL');});
  q('#book-symbol').addEventListener('change',loadBook);q('#book-refresh').addEventListener('click',loadBook);
  window.addEventListener('hashchange',()=>{if(location.hash==='#book'){if(manualMode&&manual)drawBook(manual,'MANUAL');else loadBook();}});
  function renderAlerts(){
    const symbol=q('#alert-symbol').value,priority=q('#alert-priority').value,first=q('#alert-from').value,last=q('#alert-to').value;
    const body=q('#alert-rows');body.replaceChildren();
    if(first&&last&&first>last){q('#alert-status').textContent='Ngày bắt đầu phải không sau ngày kết thúc.';q('#alert-page').textContent='Khoảng ngày không hợp lệ';q('#alert-prev').disabled=q('#alert-next').disabled=true;return;}
    q('#alert-status').textContent=alertSummary;
    const selected=alerts.filter(r=>(symbol==='ALL'||r.symbol===symbol)&&(priority==='ALL'||r.priority===priority)&&(!first||r.timestamp>=first)&&(!last||r.timestamp<=last));
    const total=Math.ceil(selected.length/10);page=Math.max(1,Math.min(page,total||1));
    selected.slice((page-1)*10,page*10).forEach(row=>{
      const tr=el('tr');[row.symbol,row.timestamp,fmt(row.value)+' lần','≥'+row.threshold,row.priority==='cao'?'Cao':'Theo dõi'].forEach(v=>tr.append(el('td',v)));
      const td=el('td'),button=el('button','Xem bằng chứng');button.className='button secondary';button.type='button';button.addEventListener('click',()=>showEvidence(row,button));td.append(button);tr.append(td);body.append(tr);
    });
    if(!selected.length){const td=el('td','Không có sự kiện khớp bộ lọc; không có nghĩa thị trường an toàn.');td.colSpan=6;const tr=el('tr');tr.append(td);body.append(tr);}
    q('#alert-page').textContent=`${selected.length} sự kiện · trang ${total?page:0}/${total}`;
    q('#alert-prev').disabled=page<=1;q('#alert-next').disabled=page>=total;
  }
  async function loadAlerts(){
    q('#alert-evidence-panel').hidden=true;
    const id=++alertRevision;q('#alert-refresh').disabled=true;q('#alert-status').textContent='Đang đánh giá snapshot local…';
    try{
      const data=await request('/api/market/alerts?'+new URLSearchParams({symbol:window.MarketState.value.symbol||document.querySelector('#symbol-filter').value,from:window.MarketState.value.range==='CUSTOM'&&window.MarketState.value.from?window.MarketState.value.from:(window.HistoricalRange?.start||'2026-01-01'),to:window.MarketState.value.to||'2026-11-04'}));if(id!==alertRevision)return;
      alerts=data.rows||[];page=1;
      alertHash=data.snapshot_sha256||null;
      const message=data.status==='evaluated'?`${data.evaluated_observations} quan sát đủ cửa sổ · ${alerts.length} sự kiện RV20≥2 · chỉ mã được chọn trong toolbar · đến ${window.MarketState.value.to||'ngày đã chọn'}.`:'Chưa đánh giá: thiếu snapshot SSI đã kiểm chứng.';
      alertSummary=message;
      q('#alert-status').textContent=message;q('#overview-alert-state').textContent=message;
      renderAlerts();
    }catch(error){if(id!==alertRevision)return;alerts=[];alertSummary='Chưa đánh giá: '+error.message;renderAlerts();q('#overview-alert-state').textContent='Chưa đánh giá · server local không phản hồi.';}
    finally{if(id===alertRevision)q('#alert-refresh').disabled=false;}
  }
  ['alert-symbol','alert-priority','alert-from','alert-to'].forEach(id=>q('#'+id).addEventListener('change',()=>{page=1;q('#alert-evidence-panel').hidden=true;renderAlerts();}));
  q('#alert-prev').addEventListener('click',()=>{page--;renderAlerts();});q('#alert-next').addEventListener('click',()=>{page++;renderAlerts();});q('#alert-refresh').addEventListener('click',loadAlerts);
  window.addEventListener('historical-snapshot-unavailable',()=>{
    ++alertRevision;alerts=[];alertHash=null;alertSummary='Chưa đánh giá: snapshot SSI hiện tại không khả dụng.';
    q('#alert-refresh').disabled=false;q('#alert-evidence-panel').hidden=true;renderAlerts();q('#overview-alert-state').textContent=alertSummary;
  });
  window.addEventListener('eod-updated',event=>{
    const hash=event.detail.meta?.manifest?.file_sha256?.['ohlcv_daily.csv'];if(hash&&hash!==alertHash)loadAlerts();
  });
  function updateStatus(){return request('/api/market/status').then(data=>{
    const badge=q('.connection-details .status-badge');
    const stateLabels={connecting:'Đang xác thực',reconnecting:'Đang tự kết nối lại',connected_no_ticks:'Đã kết nối · chờ mã/bản tin',connected_unverified:'Đang nhận báo giá',connected_scope_rejected:'DATA từ chối quyền',disconnected:data.disabled_reason?'Chưa bật kết nối':'Kết nối gián đoạn',stale:'Báo giá đã cũ',live:'LIVE · đã kiểm chứng'};
    badge.lastChild.textContent='SSI DATA · '+(stateLabels[data.status]||data.status);
    badge.dataset.connection=data.status;
    const time=data.last_event_at||data.probe_at;
    q('#header-source-time').textContent=`EOD ${data.snapshot_asof||'chưa có'} · ${data.last_event_at?'DATA nhận':'Probe'}: ${time?new Date(time).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa có'} UTC+7`;
    const steps=data.historical_probe||[];const auth=steps.find(r=>r.step==='auth');const ws=steps.find(r=>r.step==='DATA_quote_websocket');
    q('#ssi-connection-detail').textContent=`${data.disabled_reason||''} Kết nối: ${stateLabels[data.status]||data.status}. Đã nhận ${data.quote_events||0} quote, lưu ${data.persisted_snapshots||0} snapshot. ${data.measurement_reason||''} ${data.next_retry_at?'Tự thử lại: '+data.next_retry_at:''}${data.safe_error?` Lỗi: ${data.safe_error.error_type}, HTTP ${data.safe_error.http_status??'chưa có'}, mã ${data.safe_error.code||'—'}.`:''}`;
  }).catch(()=>{q('#ssi-connection-detail').textContent='Không đọc được trạng thái local. SSI không được gắn nhãn LIVE.';});}
  window.addEventListener('market-state-change',loadAlerts);
  loadBook();updateStatus();
  setInterval(()=>{if(!document.hidden){updateStatus();if(location.hash==='#book'&&!manualMode)loadBook();}},5000);
}());
