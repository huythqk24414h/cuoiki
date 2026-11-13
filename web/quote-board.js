/* Real SSI DATA snapshots served locally; no browser credentials and no EOD substitution. */
(function(){
 'use strict';
 const q=s=>document.querySelector(s),body=q('#board-rows');if(!body)return;
 const state={page:1,size:30,scope:'INDEX:VN30',search:'',sort:'symbol',direction:1,rows:[]};
 let mode='DATA';
 const modeLabel=document.createElement('label');modeLabel.textContent='Nguồn xem';const modeSelect=document.createElement('select');modeSelect.innerHTML='<option value="DATA">SSI DATA · nhận theo sự kiện</option><option value="EOD">Giá đóng cửa đã lưu · không realtime</option>';modeLabel.append(modeSelect);q('#board-search').parentElement.parentElement.prepend(modeLabel);modeSelect.addEventListener('change',()=>{mode=modeSelect.value;load(true);});
 let revision=0,busy=false,timer=null,searchTimer=null,paint=null,stream=null,streamKey='',streamReady=false,lastGlobalScope=window.MarketState.value.scope;
 function scheduleRender(){if(paint==null)paint=requestAnimationFrame(()=>{paint=null;render();});}
 const rowNodes=new Map(),lastValues=new Map();
 const fmt=v=>v==null||v===''?'—':/^(ATO|ATC)$/.test(String(v))?v:window.LiquidityCalculator.formatDecimal(String(v),4).replace(/([.,]0+)$/,'');
 const time=v=>v?new Date(v).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour12:false}):'—';
 const labels={eod:'EOD đã lưu · không live',receiving:'Đang nhận',stale:'Dữ liệu cũ',waiting:'Chờ dữ liệu',offline:'Mất kết nối',invalid_time:'Sai thời gian'};
 function el(tag,value,className){const n=document.createElement(tag);if(value!=null)n.textContent=value;if(className)n.className=className;return n;}
 function field(row,key){if(key==='volume')return row.total_volume;if(key==='price')return row.last_price;return row.symbol;}
 function render(){
  const ordered=[...state.rows].sort((a,b)=>{
   if(state.sort==='symbol')return state.direction*a.symbol.localeCompare(b.symbol);
   const x=Number(field(a,state.sort)),y=Number(field(b,state.sort));
   const ax=field(a,state.sort)!=null&&Number.isFinite(x),by=field(b,state.sort)!=null&&Number.isFinite(y);
   return ax!==by?(ax?-1:1):state.direction*(x-y||a.symbol.localeCompare(b.symbol));
  });
  const retained=new Set(ordered.map(r=>r.symbol));
  for(const [symbol,node] of rowNodes)if(!retained.has(symbol)){node.remove();rowNodes.delete(symbol);lastValues.delete(symbol);}
  body.querySelectorAll('tr[data-empty]').forEach(n=>n.remove());
  for(const [rowIndex,row] of ordered.entries()){
   let tr=rowNodes.get(row.symbol);
   if(!tr){tr=el('tr');tr.append(el('td'));const button=el('button',row.symbol,'rank-symbol');button.type='button';button.onclick=()=>window.MarketState.set({symbol:row.symbol});tr.firstChild.append(button);for(let i=1;i<29;i++)tr.append(el('td'));rowNodes.set(row.symbol,tr);}
   tr.dataset.state=row.status;tr.firstChild.firstChild.title=`${row.name} · ${row.board} · loại SSI: ${row.stock_type}`;
   const bs=[...row.bids].reverse(),as=row.asks;
   const fields=[row.symbol,row.ceiling,row.floor,row.reference,row.session||'Chưa nhận cờ',...bs.flatMap(r=>[r.price,r.quantity]),row.last_price,row.last_quantity,row.change,row.change_pct,...as.flatMap(r=>[r.price,r.quantity]),row.total_volume,row.high,row.low,row.foreign_buy,row.foreign_sell,row.foreign_room,time(row.received_at),row.topic_supported?(labels[row.status]||row.status):'Topic không hỗ trợ'];
   const colors={1:'market-ceiling',2:'market-floor',3:'market-reference',11:row.colors?.last};
   [...(row.colors?.bids||[])].reverse().forEach((c,i)=>colors[5+i*2]=c);(row.colors?.asks||[]).forEach((c,i)=>colors[15+i*2]=c);
   const previous=lastValues.get(row.symbol);
   fields.forEach((value,i)=>{if(!i)return;const cell=tr.children[i],text=i===4||i>=27?String(value):fmt(value);
    if(cell.textContent!==text)cell.textContent=text;
    if(previous&&previous[i]!==value&&value!=null&&i!==4&&i<27&&Number.isFinite(Number(value))&&Number.isFinite(Number(previous[i]))&&previous[i]!=null){const direction=Number(value)>Number(previous[i])?'flash-up':'flash-down';cell.classList.remove('flash-up','flash-down');cell.classList.add(direction);setTimeout(()=>cell.classList.remove(direction),300);}
    for(const c of ['market-up','market-down','market-reference','market-ceiling','market-floor'])cell.classList.toggle(c,colors[i]===c&&value!=null);
    cell.classList.toggle('price-missing',value==null);
    cell.title=i===4?`Cờ SSI: ${row.session_time||'chưa nhận'}; không suy ra phiên từ giờ máy`:i>=11&&i<=14?`Khớp: ${labels[row.trade_status]||row.trade_status} · ${row.trade_time||'chưa nhận'}. ${i>=13?row.change_reason:''}`:i>=24&&i<=26?'Chưa có dữ liệu khối ngoại/room được kiểm chứng cho bảng này.':row.reason||'';
   });
   lastValues.set(row.symbol,fields);if(body.children[rowIndex]!==tr)body.insertBefore(tr,body.children[rowIndex]||null);
  }
  if(!ordered.length){const tr=el('tr'),td=el('td','Không có mã khớp bộ lọc.');tr.dataset.empty='true';td.colSpan=29;tr.append(td);body.append(tr);}
 }
 function syncScope(){const value=state.scope;state.scope=value;const select=q('#board-scope');if(![...select.options].some(o=>o.value===value)){const option=el('option',value.startsWith('INDEX:')?'Chỉ số '+value.slice(6):value);option.value=value;select.append(option);}select.value=value;}
 function accept(result){
   const group=body.closest('table').querySelector('th[colspan="4"]');if(group)group.textContent=result.mode==='EOD'?'Cuối ngày (EOD)':'Khớp lệnh';
   state.rows=result.rows;state.page=result.page;scheduleRender();
   q('#board-page-status').textContent=`Trang ${result.page}/${result.pages} · ${result.rows.length}/${result.total} mục khớp · ${result.catalog_total} mục danh mục SSI`;
   q('#board-page-prev').disabled=result.page<=1;q('#board-page-next').disabled=result.page>=result.pages;
   q('#board-status').title=result.units_note+' '+result.view_note;
   q('#board-status').textContent=result.mode==='EOD'?'Giá đóng cửa SSI đã lưu; ngày ghi ở từng mã. Không phải realtime; không có bid/ask lịch sử.':`${result.fresh_rows}/${result.rows.length} mã mới · ${result.received_rows} mã đã nhận. ${result.received_rows===0?'SSI chưa gửi bản tin; có thể chọn Giá đóng cửa đã lưu.':'Xem thời gian và trạng thái riêng từng mã.'}`;
 }
 function closeStream(){++revision;if(stream)stream.close();stream=null;streamKey='';streamReady=false;}
 function connectStream(){
  if(!window.EventSource||mode==='EOD'){closeStream();return;}
  const key=new URLSearchParams({scope:state.scope,search:state.search,page:String(state.page),size:String(state.size)}).toString();
  if(key===streamKey&&stream)return;
  closeStream();streamKey=key;const current=++revision;
  stream=new EventSource('/api/market/board-stream?'+key);
  stream.addEventListener('board',event=>{if(current!==revision)return;try{const result=JSON.parse(event.data);if(!Array.isArray(result.rows))throw Error();streamReady=true;accept(result);}catch(_){streamReady=false;}});
  stream.addEventListener('cycle',()=>{if(current!==revision)return;closeStream();if(location.hash==='#book'&&!document.hidden)connectStream();});
  stream.onerror=()=>{if(current!==revision)return;streamReady=false;q('#board-status').textContent='Luồng local đang kết nối lại; HTTP dự phòng giữ trạng thái và thời gian nguồn, không coi dữ liệu cũ là mới.';};
 }
 async function load(force=false){
  if(document.hidden||location.hash!=='#book'){closeStream();return;}
  if(force)closeStream();
  if(busy&&!force)return;
  connectStream();if(streamReady&&!force)return;
  if(mode==='EOD'&&!force&&state.rows.some(r=>r.status==='eod'))return;
  busy=true;const ticket=revision;
  try{const result=await request('/api/market/board?'+new URLSearchParams({scope:state.scope,search:state.search,page:String(state.page),size:String(state.size),mode}));if(ticket===revision)accept(result);}
  catch(error){if(ticket!==revision)return;q('#board-status').textContent=error.message+' · Các giá đang hiển thị không phải dữ liệu mới.';for(const tr of rowNodes.values()){tr.dataset.state='offline';tr.lastChild.textContent='Không cập nhật';}}
  finally{busy=false;}
 }

 const table=body.closest('table');
 for(const [index,key,title] of [[0,'symbol','Mã'],[11,'price','Giá khớp'],[21,'volume','Tổng KL']]){
  const headers=[...table.querySelectorAll('thead tr:last-child th')];
  // Header groups differ from flat data columns: attach safe page-sort controls above the table.
  const controls=q('#quote-board .board-toolbar')||q('#quote-board');
  const button=el('button',title+' ↕ (trang này)','button secondary');button.type='button';button.onclick=()=>{state.direction=state.sort===key?-state.direction:1;state.sort=key;scheduleRender();};controls.append(button);
 }
 q('#board-search').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.search=e.target.value;state.page=1;rowNodes.forEach(n=>n.remove());rowNodes.clear();lastValues.clear();load(true);},250);});
 q('#board-scope').addEventListener('change',e=>{state.page=1;state.scope=e.target.value;window.MarketState.set({scope:e.target.value});load(true);});
 q('#board-page-prev').onclick=()=>{state.page--;load(true);};q('#board-page-next').onclick=()=>{state.page++;load(true);};
 window.addEventListener('market-state-change',()=>{const next=window.MarketState.value.scope;if(next===lastGlobalScope)return;lastGlobalScope=next;state.scope=next||'INDEX:VN30';syncScope();state.page=1;if(location.hash==='#book')load(true);});
 window.addEventListener('hashchange',()=>{if(location.hash==='#book'){syncScope();load();}else closeStream();});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)closeStream();else load();});
 syncScope();load();timer=setInterval(load,1000);
})();
