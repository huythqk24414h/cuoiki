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
    chart.setOption({animation:false,tooltip:{trigger:'axis'},grid:{left:80,right:24,bottom:65},xAxis:{type:'category',data:r.rows.map(x=>x.timestamp.slice(0,16).replace('T',' '))},yAxis:{scale:true,name:'Giá nguồn'},dataZoom:zoom?.length?zoom:[{type:'inside'},{type:'slider'}],series:[{type:'candlestick',data:r.rows.map(x=>[x.open,x.close,x.low,x.high].map(Number)),itemStyle:{color:'#08764C',color0:'#BA2540',borderColor:'#08764C',borderColor0:'#BA2540'}}]},true);chart.resize();
   }else{
    const r=await request('/api/market/depth-warning?'+new URLSearchParams({symbol}));
    ws.textContent=`${r.symbol} · ${r.state} · ${r.valid_samples}/${r.samples} mẫu hợp lệ · ${r.reason||r.method||'Đang chờ mẫu SSI thật'}${r.anchor_time?' · thời điểm gốc '+vn(r.anchor_time):''}${r.label!=null?' · kết quả quan sát '+r.label:''}`;
   }
  }catch(e){(page==='analysis'?status:ws).textContent='Chưa đọc được dữ liệu: '+e.message;}finally{busy=false;}
 }
 select.addEventListener('change',update);window.addEventListener('hashchange',update);window.addEventListener('market-state-change',update);window.addEventListener('resize',()=>chart?.resize());setInterval(update,5000);update();
})();
