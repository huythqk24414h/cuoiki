/* Public SSI evidence for a single symbol. */
(() => {
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};
  const dialog=el('dialog');dialog.className='card';dialog.style.width='min(960px, 94vw)';
  const form=el('form');form.method='dialog';
  const close=el('button','Đóng hồ sơ');close.className='button secondary';form.append(close);
  const title=el('h2');title.id='symbol-dossier-title';dialog.setAttribute('aria-labelledby',title.id);
  const status=el('p');status.setAttribute('role','status');
  const chart=el('div');chart.className='chart-stage';
  const evidence=el('details'),summary=el('summary','20 phiên tham chiếu RV20');
  const table=el('table'),header=table.createTHead().insertRow(),body=table.createTBody();
  for(const label of ['Ngày','Khối lượng SSI'])header.append(el('th',label));
  evidence.append(summary,table);
  const bookTitle=el('h3','Sổ lệnh gần nhất'),bookTime=el('p'),book=el('table');
  const bookHeader=book.createTHead().insertRow(),bookBody=book.createTBody();
  for(const label of ['Mức','Giá mua','KL mua','Giá bán','KL bán'])bookHeader.append(el('th',label));
  const analysis=el('a','Mở Phân tích của mã');analysis.className='button secondary';analysis.href='#analysis';
  dialog.append(form,title,status,chart,evidence,bookTitle,bookTime,book,analysis);
  document.body.append(dialog);
  let revision=0,active;
  const num=(n,digits=0)=>n==null||n===''||!Number.isFinite(Number(n))?'—':
    Number(n).toLocaleString('vi-VN',{maximumFractionDigits:digits});
  function row(target,values){const tr=target.insertRow();for(const value of values)tr.append(el('td',value));}
  dialog.addEventListener('close',()=>{revision++;ChartKit.destroy(chart);});
  analysis.addEventListener('click',()=>{if(active)window.MarketState.set({symbol:active});dialog.close();});
  async function open(symbol){
    if(!/^[A-Z0-9]{1,12}$/.test(symbol))return;
    const ticket=++revision;
    active=symbol;title.textContent='Hồ sơ '+symbol;status.textContent='Đang đọc dữ liệu SSI…';
    bookTime.textContent='Đang đọc báo giá SSI…';evidence.open=false;
    ChartKit.destroy(chart);body.replaceChildren();bookBody.replaceChildren();
    if(!dialog.open)dialog.showModal();
    const [daily,quote]=await Promise.allSettled([
      fetch('/api/market-data?'+new URLSearchParams({kind:'series',symbol,tail:'21'}),{signal:AbortSignal.timeout(10000)})
        .then(response=>{if(!response.ok)throw Error('SSI EOD chưa khả dụng');return response.json();}),
      request('/api/market/book?'+new URLSearchParams({symbol})),
    ]);
    if(ticket!==revision)return;
    const rows=daily.status==='fulfilled'?daily.value:[];
    const latest=rows.at(-1),prior=rows.slice(0,-1);
    status.textContent=latest?`SSI EOD · ${latest.date} · Khối lượng ${num(latest.volume_shares)} · TB20 ${num(latest.volume_avg20_previous,2)} · RV20 ${num(latest.relative_volume20,3)} lần.`:
      'Chưa đọc được lịch sử EOD của mã này.';
    for(const point of prior)row(body,[point.date,num(point.volume_shares)]);
    if(rows.length)ChartKit.render(chart,rows,'close_vnd','Giá và khối lượng','đơn vị nguồn',{financial:true});
    const snapshot=quote.status==='fulfilled'?quote.value:null;
    const bids=snapshot?.unverified_levels?.bids||snapshot?.bids?.map(r=>[r.price,r.quantity]);
    const asks=snapshot?.unverified_levels?.asks||snapshot?.asks?.map(r=>[r.price,r.quantity]);
    bookTime.textContent=bids?.length&&asks?.length?
      `SSI DATA · ${snapshot.status||'Bản chụp'} · ${snapshot.event_time||'chưa có giờ nguồn'}`:'Chưa đọc được báo giá SSI hai phía.';
    for(let i=0;i<3;i++)row(bookBody,[i+1,num(bids?.[i]?.[0],4),num(bids?.[i]?.[1]),num(asks?.[i]?.[0],4),num(asks?.[i]?.[1])]);
  }
  window.SymbolDossier={open};
})();
