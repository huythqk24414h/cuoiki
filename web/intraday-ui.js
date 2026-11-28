/* Intraday candles and observed 60s outcomes are separate from predictive H1. */
(function(){
 const section=document.querySelector('#analysis'),alerts=document.querySelector('#alerts');
 const card=document.createElement('article');card.className='card';
 const title=document.createElement('h2');title.textContent='Theo dõi trong ngày · SSI';
 const select=ChartKit.frameSelect();select.setAttribute('aria-label','Khung nến nội ngày');

 const status=document.createElement('p'),plot=document.createElement('div');plot.className='intraday-chart';
 const note=document.createElement('p');note.textContent='Tự kiểm tra local mỗi 5 giây; tải SSI tối đa mỗi 60 giây theo mã. Nến đang hình thành có thể đổi. 4H tách nghỉ trưa nên có thể thiếu kỳ. Giá/KL giữ đơn vị nguồn. Không dùng nến để dựng sổ lệnh.';
 const dateNote=document.createElement('p');dateNote.className='helper';dateNote.textContent='Nến nội phiên theo mã, khung nến và bộ lọc ngày phía trên.';
 card.append(title,select,status,dateNote,plot,note);section.insertBefore(card,section.children[1]);
 const warning=document.createElement('article');warning.className='card';warning.id='depth-observation';
 const wt=document.createElement('h2');wt.textContent='Độ sâu bên mua · quan sát 60 giây';
 const ws=document.createElement('p');ws.setAttribute('role','status');ws.textContent='Đang đọc mẫu SSI…';
 const evidenceData=document.createElement('dl');evidenceData.className='source-list depth-window-facts';evidenceData.hidden=true;
 const wn=document.createElement('p');wn.className='helper';
 wn.textContent='Quy tắc quan sát dùng phân vị 10% của tối thiểu 100 mẫu trước cửa sổ và yêu cầu độ sâu thấp kéo dài ít nhất 15 giây. H1 chưa được kiểm định ngoài mẫu.';
 const bookLink=document.createElement('a');bookLink.href='#book';bookLink.textContent='Xem sổ lệnh SSI của mã';
 warning.append(wt,ws,evidenceData,wn,bookLink);alerts.insertBefore(warning,alerts.children[1]);
 let warningKey;
 let chart=null,busy=false;const vn=d=>d?new Date(d).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa có';
 const dailyPlot=document.querySelector('#price-chart');
 const dailyCard=dailyPlot.closest('.history-card');
 const toolbar=document.createElement('label');toolbar.textContent='Khung biểu đồ ';
 const overviewSelect=ChartKit.frameSelect();
 overviewSelect.value=window.MarketState.value.resolution;
 toolbar.append(overviewSelect);dailyCard.querySelector('.card-heading').append(toolbar);
 const overviewPane=document.createElement('div');overviewPane.hidden=true;
 const overviewStatus=document.createElement('p');overviewStatus.className='helper';overviewStatus.setAttribute('role','status');
 const overviewPlot=document.createElement('div');overviewPlot.className='chart-stage';
 overviewPane.append(overviewStatus,overviewPlot);dailyPlot.after(overviewPane);
 const overviewNote=document.createElement('p');overviewNote.className='helper';
 overviewNote.textContent='Biểu đồ dùng bộ lọc ngày phía trên. OHLC và khối lượng gộp đúng khung đã chọn; kỳ đang mở cập nhật theo nến SSI M15 mới.';
 overviewPane.append(overviewNote);
 const sessionStamp=document.createElement('p');sessionStamp.className='helper';
 document.querySelector('.snapshot-banner').after(sessionStamp);
 const eodParts=[dailyPlot,dailyCard.querySelector('.legend'),dailyCard.querySelector('.chart-foot'),
   dailyCard.querySelector('#chart-caption'),dailyCard.querySelector(':scope > p.helper'),
   dailyPlot.previousElementSibling?.matches('p.helper')?dailyPlot.previousElementSibling:null].filter(Boolean);
 let overviewKey, overviewVersion=0, overviewBusy=false, overviewRevision;
 async function refreshOverview(force=false){
   if(document.hidden||document.body.classList.contains('guest')||!['','#monitor'].includes(location.hash))return;
   const resolution=overviewSelect.value;
   if(overviewBusy&&!force)return;
   const symbol=window.MarketState.value.symbol||'SSI';
   const intraday=ChartKit.intradayFrame(resolution);
   const market=window.MarketState.value;
   const query=new URLSearchParams(intraday?{symbol,resolution:ChartKit.sourceFrame(resolution)}:
     {symbol,resolution:'1D',range:market.range,period:market.period,to:market.to,
      ...(market.range==='CUSTOM'&&market.from?{from:market.from}:{})});
   const rangeLabel=ChartKit.filterLabel(market);
   const key=resolution+':'+query+':'+rangeLabel,ticket=++overviewVersion;
   const changed=key!==overviewKey;overviewKey=key;overviewBusy=true;
   if(changed){ChartKit.destroy(overviewPlot);overviewRevision=undefined;overviewStatus.textContent=`Đang tải nến ${symbol}…`;sessionStamp.textContent=overviewStatus.textContent;}
   try{
     const through=market.range==='CUSTOM'?market.to:null;
     const [data,minutes]=await Promise.all([
       request('/api/market/'+(intraday?'intraday':'series')+'?'+query),
       !intraday&&window.StaticLiquidity?request('/api/market/intraday?'+new URLSearchParams({symbol,resolution:'15m'})):null,
     ]);
     if(ticket!==overviewVersion||overviewSelect.value!==resolution)return;
     const rows=intraday?ChartKit.filteredCandles(ChartKit.intradayRows(data.rows||[],resolution,symbol),market):ChartKit.dailyRows(
       ChartKit.withOpenDay(data.rows||[],minutes?.rows||[],symbol,through),resolution);
     const last=rows.at(-1);
     const asOf=last&&(intraday?vn(last.closed_at||last.date):last.date);
     const label=intraday?'SSI trong phiên':last?.provisional?'SSI EOD và kỳ đang mở':'SSI EOD';
     const stamp=last?.provisional?`${asOf} · Đang mở, tạm tính đến ${vn(last.closed_at)}`:asOf;
     sessionStamp.textContent=last?`${label} · ${symbol} · ${stamp}`:`${label} · ${symbol} · chưa có dữ liệu`;
     const retrieved=(intraday?data:minutes)?.retrieved_at;
     overviewStatus.textContent=last?`${symbol} · ${rows.length} kỳ · ${stamp} · Bộ lọc ${rangeLabel}${retrieved?' · Lần tải '+vn(retrieved):''}`:
       `${symbol} · ${rangeLabel} · Không có nến SSI trong khoảng này. Thử khung D nếu đang xem lịch sử xa.`;
     if(!rows.length){ChartKit.destroy(overviewPlot);overviewRevision=undefined;return;}
     const revision=[key,rows.length,last.date,last.close_vnd,last.volume_shares,last.closed_at,data.retrieved_at,data.revision].join(':');
     if(revision===overviewRevision)return;
     ChartKit.render(overviewPlot,rows,'close_vnd','Giá và khối lượng','đơn vị nguồn',{main:true,intraday,source:label});
     overviewRevision=revision;
   }catch(error){
     if(ticket===overviewVersion){
       overviewStatus.textContent='Chưa cập nhật được nến: '+error.message;
       if(changed)sessionStamp.textContent=overviewStatus.textContent;
     }
   }finally{if(ticket===overviewVersion)overviewBusy=false;}
 }
 function switchOverview(){
   const intraday=ChartKit.intradayFrame(overviewSelect.value);
   overviewPane.hidden=false;
   eodParts.forEach(part=>part.hidden=true);
   dailyCard.querySelector('h2').textContent=intraday?'Giá & khối lượng · SSI trong phiên':'Giá & khối lượng · Lịch sử và kỳ đang mở';
   refreshOverview(true);
 }
 overviewSelect.addEventListener('change',switchOverview);
 let globalResolution=window.MarketState.value.resolution;
 window.addEventListener('market-state-change',()=>{
   const resolution=window.MarketState.value.resolution;
   if(resolution!==globalResolution){globalResolution=resolution;overviewSelect.value=resolution;switchOverview();}
   else refreshOverview(true);
 });
 window.addEventListener('hashchange',()=>refreshOverview(true));
 document.addEventListener('visibilitychange',()=>refreshOverview());
 setInterval(refreshOverview,ChartKit.refreshMs());
 switchOverview();
 async function update(){
  if(busy||document.hidden||document.body.classList.contains('guest'))return;
  const page=location.hash.slice(1);if(!['analysis','alerts'].includes(page))return;
  busy=true;const symbol=window.MarketState.value.symbol||'SSI',resolution=select.value;
  try{
   if(page==='analysis'){
    const r=await request('/api/market/intraday?'+new URLSearchParams({symbol,resolution:'15m'}));
    if(symbol!==(window.MarketState.value.symbol||'SSI')||resolution!==select.value)return;
    const market=window.MarketState.value;
    let rows;
    if(ChartKit.intradayFrame(resolution))rows=ChartKit.filteredCandles(ChartKit.intradayRows(r.rows,resolution,symbol),market);
    else {
      const daily=await request('/api/market/series?'+new URLSearchParams({symbol,resolution:'1D',range:market.range,to:market.to,...(market.range==='CUSTOM'&&market.from?{from:market.from}:{})}));
      if(resolution!==select.value||symbol!==window.MarketState.value.symbol)return;
      rows=ChartKit.dailyRows(ChartKit.withOpenDay(daily.rows||[],r.rows||[],symbol,market.range==='CUSTOM'?market.to:null),resolution);
    }
    status.textContent=`${symbol} · ${rows.length} nến · Bộ lọc ${ChartKit.filterLabel(market)} · Nến cuối trong khoảng ${vn(rows.at(-1)?.closed_at||rows.at(-1)?.date)} · Lần tải ${vn(r.retrieved_at)}`;
    if(!chart)chart=echarts.init(plot);
    ChartKit.drawFinancial(chart,rows,{zoom:ChartKit.financialZoom(chart)});
   }else{
    const r=await request('/api/market/depth-warning?'+new URLSearchParams({symbol}));
    if(symbol!==(window.MarketState.value.symbol||'SSI')||location.hash!=='#alerts')return;
    const unit=r.unit||'';
    const amount=value=>value==null?'—':Number(value).toLocaleString('vi-VN');
    const mode=r.preview?(r.stale?'Dữ liệu đã lưu':'Mẫu vừa nhận'):'SSI DATA';
    const headline=[symbol,mode,r.state,r.reason].filter(Boolean).join(' · ');
    const fields=[
      ['Cửa sổ quan sát',r.anchor_time&&r.observed_until?vn(r.anchor_time)+' → '+vn(r.observed_until)+' ICT':'Chưa hình thành dải đánh giá'],
      ['Mẫu đạt kiểm tra',r.valid_60s!=null&&r.samples?`${r.valid_60s}/${Math.min(r.samples,60)} mẫu gần nhất`:r.samples?`${r.valid_samples}/${r.samples} mẫu`:'Chưa có mẫu để chấm'],
      ['Độ sâu mua ở mẫu cuối',r.bid_depth!=null?`${amount(r.bid_depth)} · ${unit}`:'—'],
      ['Ngưỡng quan sát',r.threshold!=null?`${amount(r.threshold)} · ${unit} · ${r.baseline_n} mẫu cơ sở`:'Chưa đủ mẫu cơ sở'],
      ['Mốc bộ thu SSI',r.snapshot_at||r.updated_at?vn(r.snapshot_at||r.updated_at)+' ICT':'Chưa có'],
    ];
    const key=JSON.stringify([headline,fields]);
    if(warningKey===key)return;
    warningKey=key;
    ws.textContent=headline;
    evidenceData.hidden=false;
    evidenceData.replaceChildren(...fields.map(([key,value])=>{
      const group=document.createElement('div'),label=document.createElement('dt'),content=document.createElement('dd');
      label.textContent=key;content.textContent=value;group.append(label,content);return group;
    }));
   }
  }catch(e){
    if(location.hash!=='#'+page||symbol!==(window.MarketState.value.symbol||'SSI'))return;
    (page==='analysis'?status:ws).textContent='Chưa đọc được dữ liệu SSI: '+e.message;
    if(page==='alerts'){warningKey=null;evidenceData.hidden=true;}
  }finally{busy=false;}
 }
 select.addEventListener('change',update);window.addEventListener('hashchange',update);window.addEventListener('market-state-change',update);window.addEventListener('resize',()=>chart?.resize());setInterval(update,ChartKit.refreshMs());update();
 if(window.StaticLiquidity)setInterval(()=>{if(location.hash==='#alerts')update();},5000);
 document.addEventListener('visibilitychange',update);
})();
