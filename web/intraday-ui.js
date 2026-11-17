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
 const warning=document.createElement('article');warning.className='card';const wt=document.createElement('h2');wt.textContent='Độ sâu bên mua · cửa sổ quan sát 60 giây';const ws=document.createElement('p');const wn=document.createElement('p');wn.textContent='Ghi mẫu mỗi giây khi quy ước SSI đã xác minh. Xác nhận sau 60 giây liệu độ sâu thấp kéo dài 15 giây; đây là kết quả đã quan sát, chưa phải dự báo M0/M1/M2. Nến 15m/1h/4h không thay dữ liệu sổ lệnh.';warning.append(wt,ws,wn);alerts.insertBefore(warning,alerts.children[1]);
 let chart=null,busy=false;const vn=d=>d?new Date(d).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'chưa có';
 const dailyPlot=document.querySelector('#price-chart');
 const dailyCard=dailyPlot.closest('.history-card');
 const toolbar=document.createElement('label');toolbar.textContent='Khung biểu đồ ';
 const overviewSelect=document.createElement('select');
 for(const [value,label] of [['15m','M15'],['1h','H1'],['4h','H4 · theo buổi'],['eod','Theo bộ lọc EOD']]){
   const option=document.createElement('option');option.value=value;option.textContent=label;overviewSelect.append(option);
 }
 toolbar.append(overviewSelect);dailyCard.querySelector('.card-heading').append(toolbar);
 const overviewPane=document.createElement('div');overviewPane.hidden=true;
 const overviewStatus=document.createElement('p');overviewStatus.className='helper';overviewStatus.setAttribute('role','status');
 const overviewPlot=document.createElement('div');overviewPlot.className='intraday-chart';
 overviewPane.append(overviewStatus,overviewPlot);dailyPlot.after(overviewPane);
 const overviewNote=document.createElement('p');overviewNote.className='helper';
 overviewNote.textContent='Giờ Việt Nam. H4 gộp theo buổi để tách nghỉ trưa. Giá và khối lượng theo đơn vị nguồn SSI.';
 overviewPane.append(overviewNote);
 const sessionStamp=document.createElement('p');sessionStamp.className='helper';
 document.querySelector('.snapshot-banner').after(sessionStamp);
 const eodParts=[dailyPlot,dailyCard.querySelector('.legend'),dailyCard.querySelector('.chart-foot'),
   dailyCard.querySelector('#chart-caption'),dailyCard.querySelector(':scope > p.helper'),
   dailyPlot.previousElementSibling?.matches('p.helper')?dailyPlot.previousElementSibling:null].filter(Boolean);
 let overviewChart, overviewKey, overviewVersion=0, overviewBusy=false;
 async function refreshOverview(force=false){
   if(document.hidden||document.body.classList.contains('guest')||!['','#monitor'].includes(location.hash))return;
   const resolution=overviewSelect.value;
   if(resolution==='eod'||overviewBusy&&!force)return;
   const symbol=window.MarketState.value.symbol||'SSI';
   const key=symbol+':'+resolution,ticket=++overviewVersion;
   const changed=key!==overviewKey;overviewKey=key;overviewBusy=true;
   if(changed){overviewChart?.clear();overviewStatus.textContent=`Đang tải nến ${symbol}…`;sessionStamp.textContent=overviewStatus.textContent;}
   try{
     const data=await request('/api/market/intraday?'+new URLSearchParams({symbol,resolution}));
     if(ticket!==overviewVersion||overviewSelect.value!==resolution)return;
     const rows=data.rows||[];
     sessionStamp.textContent=rows.length?`SSI trong phiên · ${symbol} · nến cuối đóng ${vn(data.last_source_time)}`:`SSI trong phiên · ${symbol} · chưa có nến`;
     overviewStatus.textContent=`${symbol} · ${rows.length} nến · Mốc nguồn cuối ${vn(data.last_source_time)} · Lần tải ${vn(data.retrieved_at)}`;
     if(!rows.length){overviewChart?.clear();overviewStatus.textContent+=` · ${data.status||'Chưa có dữ liệu SSI'}`;return;}
     overviewChart??=echarts.init(overviewPlot);
     const labels=rows.map(candleLabel);
     overviewChart.setOption({
       animation:false,tooltip:{trigger:'axis'},axisPointer:{link:[{xAxisIndex:'all'}]},
       grid:[{left:68,right:18,top:18,bottom:'44%'},{left:68,right:18,top:'63%',bottom:58}],
       xAxis:[{type:'category',data:labels,axisLabel:{show:false}},{type:'category',gridIndex:1,data:labels}],
       yAxis:[{scale:true,name:'Giá'},{gridIndex:1,name:'Khối lượng'}],
       dataZoom:[{type:'inside',xAxisIndex:[0,1]},{type:'slider',xAxisIndex:[0,1]}],
       series:[
         {type:'candlestick',name:'OHLC',data:rows.map(r=>[r.open,r.close,r.low,r.high].map(Number)),
           itemStyle:{color:'#08764C',color0:'#BA2540',borderColor:'#08764C',borderColor0:'#BA2540'}},
         {type:'bar',name:'Khối lượng',xAxisIndex:1,yAxisIndex:1,data:rows.map(r=>Number(r.volume)),itemStyle:{color:'#236ba7'}}
       ]},changed);
     overviewChart.resize();
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
   const intraday=overviewSelect.value!=='eod';
   if(!intraday){overviewVersion++;overviewBusy=false;sessionStamp.textContent='Đang xem biểu đồ EOD.';}
   overviewPane.hidden=!intraday;
   eodParts.forEach(part=>part.hidden=intraday);
   dailyCard.querySelector('h2').textContent=intraday?'Giá & khối lượng · SSI trong phiên':'Giá & khối lượng · SSI EOD';
   refreshOverview(true);
 }
 overviewSelect.addEventListener('change',switchOverview);
 window.addEventListener('market-state-change',()=>refreshOverview(true));
 window.addEventListener('hashchange',()=>refreshOverview(true));
 window.addEventListener('resize',()=>{if(!overviewPane.hidden)overviewChart?.resize();});
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
    ws.textContent=`${r.symbol} · ${r.state} · ${r.valid_samples}/${r.samples} mẫu hợp lệ · ${r.reason||r.method||'Đang chờ mẫu SSI thật'}${r.anchor_time?' · thời điểm gốc '+vn(r.anchor_time):''}${r.label!=null?' · kết quả quan sát '+r.label:''}`;
   }
  }catch(e){(page==='analysis'?status:ws).textContent='Chưa đọc được dữ liệu: '+e.message;}finally{busy=false;}
 }
 select.addEventListener('change',update);window.addEventListener('hashchange',update);window.addEventListener('market-state-change',update);window.addEventListener('resize',()=>chart?.resize());setInterval(update,window.StaticLiquidity?60000:5000);update();
})();
