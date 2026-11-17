/* Intraday candles and observed 60s outcomes are separate from predictive H1. */
(function(){
 const section=document.querySelector('#analysis'),alerts=document.querySelector('#alerts');
 const card=document.createElement('article');card.className='card';
 const title=document.createElement('h2');title.textContent='Theo dõi trong ngày · SSI';
 const select=document.createElement('select');select.setAttribute('aria-label','Khung nến nội ngày');
 for(const [v,t] of [['15m','15 phút'],['1h','1 giờ'],['4h','Theo buổi sáng/chiều']]){const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o);}
 const status=document.createElement('p'),plot=document.createElement('div');plot.className='intraday-chart';
 const note=document.createElement('p');note.textContent='Tự kiểm tra local mỗi 5 giây; tải SSI tối đa mỗi 60 giây theo mã. Nến đang hình thành có thể đổi. 4H tách nghỉ trưa nên có thể thiếu kỳ. Giá/KL giữ đơn vị nguồn. Không dùng nến để dựng sổ lệnh.';
 const dateNote=document.createElement('p');dateNote.className='helper';dateNote.textContent='Nến nội phiên đọc riêng theo mã và khung nến. Bộ lọc ngày EOD phía trên không giới hạn biểu đồ này.';
 card.append(title,select,status,dateNote,plot,note);section.insertBefore(card,section.children[1]);
 const warning=document.createElement('article');warning.className='card';const wt=document.createElement('h2');wt.textContent='Độ sâu bên mua · cửa sổ quan sát 60 giây';const ws=document.createElement('p');const wn=document.createElement('p');wn.textContent=window.StaticLiquidity?
  'Lấy mẫu sổ lệnh SSI mỗi giây. So độ sâu ba mức mua với phân vị 10% từ ít nhất 100 mẫu trước đó. Một đợt thấp cần kéo dài ít nhất 15 giây trong cửa sổ 60 giây. Kết quả chỉ dùng để quan sát, theo đơn vị nguồn.':
  'Ghi mẫu mỗi giây khi quy ước SSI đã xác minh. Xác nhận sau 60 giây liệu độ sâu thấp kéo dài 15 giây.';
 warning.append(wt,ws,wn);alerts.insertBefore(warning,alerts.children[1]);
 let chart=null,busy=false;const vn=d=>d?new Date(d).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa có';
 const dailyPlot=document.querySelector('#price-chart');
 const dailyCard=dailyPlot.closest('.history-card');
 const toolbar=document.createElement('label');toolbar.textContent='Khung biểu đồ ';
 const overviewSelect=ChartKit.frameSelect();
 toolbar.append(overviewSelect);dailyCard.querySelector('.card-heading').append(toolbar);
 const overviewPane=document.createElement('div');overviewPane.hidden=true;
 const overviewStatus=document.createElement('p');overviewStatus.className='helper';overviewStatus.setAttribute('role','status');
 const overviewPlot=document.createElement('div');overviewPlot.className='chart-stage';
 overviewPane.append(overviewStatus,overviewPlot);dailyPlot.after(overviewPane);
 const overviewNote=document.createElement('p');overviewNote.className='helper';
 overviewNote.textContent='H4 gộp theo buổi. Từ khung D trở lên, kỳ đang mở dùng các nến SSI M15 đã đóng. Khối lượng là phần đã quan sát trong khớp liên tục.';
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
     {symbol,resolution:'1D',range:ChartKit.historyRange(market.range,resolution),period:market.period,to:market.to,
      ...(market.range==='CUSTOM'&&market.from?{from:market.from}:{})});
   const key=resolution+':'+query,ticket=++overviewVersion;
   const changed=key!==overviewKey;overviewKey=key;overviewBusy=true;
   if(changed){ChartKit.destroy(overviewPlot);overviewRevision=undefined;overviewStatus.textContent=`Đang tải nến ${symbol}…`;sessionStamp.textContent=overviewStatus.textContent;}
   try{
     const through=market.range==='CUSTOM'?market.to:null;
     const [data,minutes]=await Promise.all([
       request('/api/market/'+(intraday?'intraday':'series')+'?'+query),
       !intraday&&window.StaticLiquidity?request('/api/market/intraday?'+new URLSearchParams({symbol,resolution:'15m'})):null,
     ]);
     if(ticket!==overviewVersion||overviewSelect.value!==resolution)return;
     const rows=intraday?ChartKit.intradayRows(data.rows||[],resolution,symbol):ChartKit.dailyRows(
       ChartKit.withOpenDay(data.rows||[],minutes?.rows||[],symbol,through),resolution);
     const last=rows.at(-1);
     const asOf=last&&(intraday?vn(last.closed_at||last.date):last.date);
     const label=intraday?'SSI trong phiên':last?.provisional?'SSI EOD và kỳ đang mở':'SSI EOD';
     const stamp=last?.provisional?`${asOf} · Đang mở, tạm tính đến ${vn(last.closed_at)}`:asOf;
     sessionStamp.textContent=last?`${label} · ${symbol} · ${stamp}`:`${label} · ${symbol} · chưa có dữ liệu`;
     overviewStatus.textContent=last?`${symbol} · ${rows.length} kỳ · ${stamp}`:
       `${symbol} · Chưa có nến cho khung này. Có thể chọn khung nhỏ hơn hoặc lịch sử EOD.`;
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
 function candleLabel(row){
   return String(row.closed_at||row.timestamp).slice(0,16).replace('T',' ');
 }
 function switchOverview(){
   const intraday=ChartKit.intradayFrame(overviewSelect.value);
   overviewPane.hidden=false;
   eodParts.forEach(part=>part.hidden=true);
   dailyCard.querySelector('h2').textContent=intraday?'Giá & khối lượng · SSI trong phiên':'Giá & khối lượng · Lịch sử và kỳ đang mở';
   refreshOverview(true);
 }
 overviewSelect.addEventListener('change',switchOverview);
 window.addEventListener('market-state-change',()=>refreshOverview(true));
 window.addEventListener('hashchange',()=>refreshOverview(true));
 document.addEventListener('visibilitychange',()=>refreshOverview());
 setInterval(refreshOverview,window.StaticLiquidity?60000:5000);
 switchOverview();
 async function update(){
  if(busy||document.hidden||document.body.classList.contains('guest'))return;
  const page=location.hash.slice(1);if(!['analysis','alerts'].includes(page))return;
  busy=true;const symbol=window.MarketState.value.symbol||'SSI',resolution=select.value;
  try{
   if(page==='analysis'){
    const r=await request('/api/market/intraday?'+new URLSearchParams({symbol,resolution}));
    if(symbol!==(window.MarketState.value.symbol||'SSI')||resolution!==select.value)return;
    status.textContent=`${symbol} · ${r.status} · ${r.rows.length} nến · nến nguồn cuối ${vn(r.last_source_time)} · lần tải ${vn(r.retrieved_at)}${r.error?' · '+JSON.stringify(r.error):''}${r.refreshing?' · đang tải SSI':''}`;
    if(!chart)chart=echarts.init(plot);
    const zoom=chart.getOption()?.dataZoom;
    const labels=r.rows.map(candleLabel);
    chart.setOption({animation:false,tooltip:{trigger:'axis'},axisPointer:{link:[{xAxisIndex:'all'}]},
      grid:[{left:80,right:24,top:18,bottom:'44%'},{left:80,right:24,top:'63%',bottom:58}],
      xAxis:[{type:'category',data:labels,axisLabel:{show:false}},{type:'category',gridIndex:1,data:labels}],
      yAxis:[{scale:true,name:'Giá nguồn'},{gridIndex:1,name:'Khối lượng'}],
      dataZoom:zoom?.length?zoom:[{type:'inside',xAxisIndex:[0,1]},{type:'slider',xAxisIndex:[0,1]}],
      series:[{type:'candlestick',name:'OHLC',data:r.rows.map(x=>[x.open,x.close,x.low,x.high].map(Number)),
        itemStyle:{color:'#08764C',color0:'#BA2540',borderColor:'#08764C',borderColor0:'#BA2540'}},
        {type:'bar',name:'Khối lượng',xAxisIndex:1,yAxisIndex:1,data:r.rows.map(x=>Number(x.volume)),itemStyle:{color:'#236ba7'}}]},true);
    chart.resize();
   }else{
    const r=await request('/api/market/depth-warning?'+new URLSearchParams({symbol}));
    if(symbol!==(window.MarketState.value.symbol||'SSI')||location.hash!=='#alerts')return;
    ws.textContent=r.preview?[
      symbol,r.state,`${r.valid_60s}/60 giây gần nhất có mẫu đạt kiểm tra`,
      r.bid_depth!=null?'Độ sâu mua '+Number(r.bid_depth).toLocaleString('vi-VN')+' ('+r.unit+')':null,
      r.threshold!=null?'Ngưỡng '+Number(r.threshold).toLocaleString('vi-VN'):null,
      r.stale?'Bản đo gần nhất '+vn(r.updated_at):'Cập nhật '+vn(r.updated_at),
      r.reason||null,
    ].filter(Boolean).join(' · '):
      `${r.symbol} · ${r.state} · ${r.valid_samples}/${r.samples} mẫu hợp lệ · ${r.reason||r.method||'Đang chờ mẫu SSI thật'}`;
   }
  }catch(e){(page==='analysis'?status:ws).textContent='Chưa đọc được dữ liệu: '+e.message;}finally{busy=false;}
 }
 select.addEventListener('change',update);window.addEventListener('hashchange',update);window.addEventListener('market-state-change',update);window.addEventListener('resize',()=>chart?.resize());setInterval(update,window.StaticLiquidity?60000:5000);update();
 if(window.StaticLiquidity)setInterval(()=>{if(location.hash==='#alerts')update();},5000);
})();
