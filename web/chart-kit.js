/* ECharts rendering for SSI market data. */
(function(){
 const charts=new Map(), priceTypes=new WeakMap();
 const types=[['candlestick','Nến'],['hollow','Nến rỗng'],['bar','Thanh OHLC'],['line','Đường'],['area','Vùng'],['baseline','Đường cơ sở']];
 const frames=[['15m','M15 · 15 phút'],['30m','M30 · 30 phút'],['1h','H1 · 1 giờ'],
  ['2h','H2 · 2 giờ'],['4h','H4 · 4 giờ'],['1D','D · Ngày'],['1W','W · Tuần'],
  ['1M','M · Tháng'],['1Q','Q · Quý'],['1Y','Y · Năm']];
 const intradayFrame=frame=>['15m','30m','1h','2h','4h'].includes(frame);
 function filteredCandles(rows,{range,from,to}){
  const day=row=>row.date.slice(0,10);
  const days=[...new Set(rows.map(day))];
  if(range==='CUSTOM')return rows.filter(row=>(!from||day(row)>=from)&&(!to||day(row)<=to));
  const sessions={'1D':1,'5D':5,'1W':5,'1M':22,'3M':66,'6M':132,'1Y':264,'3Y':792,'5Y':1320}[range];
  if(sessions){const start=days.at(-sessions)||days[0];return rows.filter(row=>day(row)>=start);}
  if(range==='YTD'&&days.length)return rows.filter(row=>day(row).slice(0,4)===days.at(-1).slice(0,4));
  return rows;
 }
 function filterLabel({range,from,to}){
  return range==='CUSTOM'?[from||'đầu chuỗi',to||'mới nhất'].join(' → '):range||'MAX';
 }
 function frameSelect(){
  const select=document.createElement('select');
  select.setAttribute('aria-label','Khung thời gian biểu đồ');
  for(const [value,label] of frames){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);}
  return select;
 }
 const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
 const number=v=>v==null||v===''?null:Number(v);
 const positive=v=>Number.isFinite(number(v))&&number(v)>0;
 const hasOHLC=row=>[row.open_vnd,row.high_vnd,row.low_vnd,row.close_vnd].every(positive)&&
  Number(row.low_vnd)<=Math.min(row.open_vnd,row.close_vnd)&&Number(row.high_vnd)>=Math.max(row.open_vnd,row.close_vnd);
 function rollup(rows,keyFor){
  const groups=new Map();
  for(const row of rows){
   const key=keyFor(row);
   const group=groups.get(key)||[];
   group.push(row);groups.set(key,group);
  }
  return [...groups.values()].map(group=>{
   const first=group[0],last=group.at(-1);
   const full=group.every(hasOHLC);
   const volumes=group.map(row=>number(row.volume_shares));
   return {...last,open_vnd:full?number(first.open_vnd):null,
    high_vnd:full?Math.max(...group.map(r=>number(r.high_vnd))):null,
    low_vnd:full?Math.min(...group.map(r=>number(r.low_vnd))):null,
    volume_shares:volumes.every(Number.isFinite)?volumes.reduce((sum,value)=>sum+value,0):null};
  });
 }
 function dailyRows(rows,frame){
  if(frame==='1D')return rows;
  return rollup(rows,row=>{
   const month=Number(row.date.slice(5,7)),year=row.date.slice(0,4);
   if(frame==='1Y')return year;
   if(frame==='1Q')return year+'-'+Math.floor((month-1)/3);
   if(frame==='1M')return row.date.slice(0,7);
   const day=new Date(row.date+'T00:00:00Z');day.setUTCDate(day.getUTCDate()-(day.getUTCDay()+6)%7);
   return day.toISOString().slice(0,10);
  });
 }
 function withOpenDay(history,minutes,symbol,through,today=new Date(Date.now()+7*3600000).toISOString().slice(0,10)){
  if((through&&through<today)||history.at(-1)?.date>=today)return history;
  const observed=intradayRows(minutes,'15m',symbol).filter(row=>row.date.startsWith(today)&&row.closed_at?.startsWith(today));
  if(!observed.length)return history;
  const [daily]=rollup(observed,()=>today);
  return [...history,{...daily,date:today,provisional:true}];
 }
 function intradayRows(rows,frame,symbol){
  const source=rows.map(row=>({date:row.timestamp,symbol,closed_at:row.closed_at,session:row.session,
   open_vnd:row.open,high_vnd:row.high,low_vnd:row.low,close_vnd:row.close,volume_shares:row.volume}));
  const length={'30m':30,'1h':60,'2h':120,'4h':240}[frame];
  if(!length)return source;
  const opening=['HNXINDEX','UPCOMINDEX'].includes(symbol)?540:555;
  const closing=symbol==='UPCOMINDEX'?900:885;
  const groups=new Map();
  for(const row of source){
   const minute=Number(row.date.slice(11,13))*60+Number(row.date.slice(14,16));
   if(minute<opening||minute>=closing)continue;
   const anchor=frame==='4h'?opening:minute<690?opening:780;
   const sessionEnd=frame==='4h'?closing:minute<690?690:closing;
   const start=anchor+Math.floor((minute-anchor)/length)*length;
   const key=row.date.slice(0,10)+':'+start;
   if(!groups.has(key))groups.set(key,{rows:[],start,end:Math.min(start+length,sessionEnd)});
   groups.get(key).rows.push(row);
  }
  const now=Date.now();
  return [...groups.values()].map(group=>{
   const bars=group.rows.sort((a,b)=>a.date.localeCompare(b.date));
   const [bar]=rollup(bars,()=>0),day=bars[0].date.slice(0,10);
   const start=day+'T'+String(Math.floor(group.start/60)).padStart(2,'0')+':'+String(group.start%60).padStart(2,'0')+':00+07:00';
   const end=day+'T'+String(Math.floor(group.end/60)).padStart(2,'0')+':'+String(group.end%60).padStart(2,'0')+':00+07:00';
   const expected=[];
   for(let minute=group.start;minute<group.end;minute+=15){
    if(minute<690||minute>=780)expected.push(minute);
   }
   const incomplete=bars.length<expected.length;
   return {...bar,date:start,period_end:end,provisional:Date.parse(end)>now,incomplete,session:undefined};
  }).sort((a,b)=>a.date.localeCompare(b.date));
 }

 function destroy(target){const old=charts.get(target);if(old){old.remove?.();old.dispose?.();charts.delete(target);}target.replaceChildren();}
 const displayNumber=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:4});
 const ohlcTypes=['candlestick','hollow','bar'];
 function drawFinancial(chart,rows,{type='candlestick',unit='Giá nguồn',volumePane=true,price=true,volume=true,zoom}={}){
  const green='#08764C',red='#BA2540',blue='#236ba7';
  const stacked=volumePane&&volume&&rows.some(row=>Number.isFinite(number(row.volume_shares)));
  const labels=rows.map(row=>String(row.date?.includes('T')?row.date:row.closed_at||row.date).slice(0,16).replace('T',' '));
  const quotes=rows.map(row=>hasOHLC(row)?[row.open_vnd,row.close_vnd,row.low_vnd,row.high_vnd].map(Number):[null,null,null,null]);
  const first=number(rows.find(row=>positive(row.close_vnd))?.close_vnd);
  const series=[];
  if(price&&type==='bar'){
   series.push({type:'custom',name:'OHLC',clip:true,encode:{x:0,y:[3,4]},
    data:quotes.map((bar,i)=>[i,...bar]),renderItem:(_,api)=>{
     const open=api.value(1),close=api.value(2),low=api.value(3),high=api.value(4);
     if(!positive(low)||!positive(high))return;
     const [x,top]=api.coord([api.value(0),high]);
     const bottom=api.coord([api.value(0),low])[1];
     const opening=api.coord([api.value(0),open])[1],closing=api.coord([api.value(0),close])[1];
     const w=Math.min(6,api.size([1,0])[0]*.3),stroke=close>=open?green:red;
     const line=(x1,y1,x2,y2)=>({type:'line',shape:{x1,y1,x2,y2},style:{stroke,lineWidth:1.2}});
     return {type:'group',children:[line(x,top,x,bottom),line(x-w,opening,x,opening),line(x,closing,x+w,closing)]};
    }});
  }else if(price&&ohlcTypes.includes(type)){
   const data=type==='hollow'?quotes.map((bar,i)=>{
    const [open,close]=bar;
    if(open==null)return bar;
    const prior=number(rows[i-1]?.close_vnd)??open;
    const color=close>=prior?green:red,fill=close>=open?'transparent':color;
    return {value:bar,itemStyle:{color:fill,color0:fill,borderColor:color,borderColor0:color,borderWidth:1}};
   }):quotes;
   series.push({type:'candlestick',name:'OHLC',data,itemStyle:{color:green,color0:red,borderColor:green,borderColor0:red}});
  }else if(price){
   series.push({type:'line',name:'Đóng cửa',data:rows.map(row=>number(row.close_vnd)),showSymbol:rows.length===1,
    symbolSize:6,lineStyle:{color:blue,width:1.7},itemStyle:{color:blue},
    ...(type==='area'?{areaStyle:{color:'rgba(35,107,167,.18)'}}:{}),
    ...(type==='baseline'&&first!=null?{markLine:{silent:true,symbol:'none',label:{show:false},data:[{yAxis:first}]}}:{})});
  }
  if(stacked)series.push({type:'bar',name:'Khối lượng',xAxisIndex:1,yAxisIndex:1,
   data:rows.map(row=>number(row.volume_shares)),itemStyle:{color:blue}});
  const category={type:'category',data:labels,axisLabel:{hideOverlap:true},axisTick:{show:false}};
  const axes=stacked?[0,1]:[0];
  const grid={left:75,right:25,top:30,bottom:stacked?'44%':64};
  const format=value=>Number.isFinite(number(value))?displayNumber.format(Number(value)):'—';
  chart.setOption({animation:false,aria:{enabled:true},
   tooltip:{trigger:'axis',renderMode:'richText',confine:true,axisPointer:{type:'line'},
    formatter:items=>{
     const row=rows[items[0]?.dataIndex];
     if(!row)return '';
     const lines=[row.symbol+' · '+labels[items[0].dataIndex]];
     if(row.session==='closing_auction'&&row.date.includes('T'))lines.push('ATC · Mốc đóng cửa SSI');
     if(row.incomplete&&!row.provisional)lines.push('Kỳ thiếu dữ liệu nguồn');
     if(row.period_end)lines.push('Kết thúc kỳ '+row.period_end.slice(11,16)+' · Dữ liệu đến '+String(row.closed_at||row.date).slice(11,16));
     if(row.provisional)lines.push('Kỳ đang mở');
     for(const [name,key] of [['Mở cửa','open_vnd'],['Cao nhất','high_vnd'],['Thấp nhất','low_vnd'],['Đóng cửa','close_vnd'],['Khối lượng','volume_shares']])
      lines.push(name+'  '+format(row[key]));
     return lines.join('\n');
    }},
   axisPointer:{link:[{xAxisIndex:'all'}]},
   grid:stacked?[grid,{left:75,right:25,top:'63%',bottom:58}]:grid,
   xAxis:stacked?[{...category,axisLabel:{show:false}},{...category,gridIndex:1}]:category,
   yAxis:stacked?[{type:'value',scale:true,name:unit},{type:'value',gridIndex:1,name:'Khối lượng'}]:
    {type:'value',scale:true,name:unit},
   dataZoom:[{type:'inside',xAxisIndex:axes,...zoom},{type:'slider',xAxisIndex:axes,bottom:9,height:25,...zoom}],
   series,
  },true);
  chart.resize();
 }
 function financialZoom(chart){
  const saved=chart?.getOption()?.dataZoom?.[0];
  return saved?{start:saved.start,end:saved.end}:undefined;
 }
 function render(target,rows,field,label,unit,options={}){
  const zoom=options.main||options.financial?financialZoom(charts.get(target)):undefined;
  destroy(target);if(!rows.length){target.textContent='Không có dữ liệu hợp lệ trong khoảng.';return;}
  const caption=document.createElement('p');caption.className='helper';caption.textContent=`${rows[0].symbol||''} · ${label} (${unit}) · ${options.source||'SSI FastConnect V3'} · ${rows[0].date}–${rows.at(-1).date}`;
  const tools=document.createElement('div');tools.className='chart-tools';
  const reset=document.createElement('button');reset.className='button secondary';reset.type='button';reset.textContent='Đặt lại';tools.append(reset);
  const plot=document.createElement('div');plot.className=options.main||options.financial?'intraday-chart':'professional-chart';plot.tabIndex=0;plot.setAttribute('role','group');plot.setAttribute('aria-label',caption.textContent+'; phím trái/phải xem từng nến, Home đặt lại');
  target.append(tools,plot,caption);
  const color=css('--color-text')||'#172235',bg=css('--color-surface')||'#fff',bid=css('--color-positive')||'#067858',ask=css('--color-negative')||'#c63150',axis=css('--color-axis')||'#64748b';
  if(options.main||options.financial){
   const complete=rows.filter(hasOHLC).length;
   const requested=priceTypes.get(target)||options.defaultType||'candlestick';
   const priceType=!complete&&ohlcTypes.includes(requested)?'line':requested;
   const choose=document.createElement('select');choose.setAttribute('aria-label','Loại biểu đồ giá');
   for(const [value,text] of types){const o=document.createElement('option');o.value=value;o.textContent=text;o.disabled=!complete&&ohlcTypes.includes(value);choose.append(o);}
   choose.value=priceType;tools.prepend(choose);
   if(complete<rows.length)caption.textContent+=` · Có OHLC ${complete}/${rows.length} kỳ`;
   const chart=echarts.init(plot,null,{renderer:'canvas'});
   charts.set(target,chart);
   drawFinancial(chart,rows,{...options,type:priceType,unit:options.main?'Giá nguồn':unit,zoom});
   reset.onclick=()=>chart.dispatchAction({type:'dataZoom',start:0,end:100});
   choose.onchange=()=>{priceTypes.set(target,choose.value);drawFinancial(chart,rows,{...options,type:choose.value,unit:options.main?'Giá nguồn':unit,zoom:financialZoom(chart)});};
   let cursor;
   plot.addEventListener('keydown',e=>{
    if(e.key==='Home'){e.preventDefault();reset.click();cursor=undefined;return;}
    if(!['ArrowLeft','ArrowRight'].includes(e.key))return;
    e.preventDefault();
    const zoom=financialZoom(chart),max=rows.length-1;
    const first=Math.ceil(max*(zoom?.start??0)/100),last=Math.max(first,Math.floor(max*(zoom?.end??100)/100));
    cursor=Math.max(first,Math.min(last,cursor==null?last:cursor+(e.key==='ArrowLeft'?-1:1)));
    chart.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:cursor});
   });
  }else{
   const chart=echarts.init(plot,null,{renderer:'canvas'});charts.set(target,chart);
   const compact=value=>new Intl.NumberFormat('vi-VN',{notation:'compact',maximumFractionDigits:1}).format(value);
   const narrow=plot.clientWidth<560;
   const actualLabel='Khối lượng phiên',baselineLabel='TB20 phiên ngày trước';
   const series=options.volumeComparison?[
    {name:actualLabel,type:'bar',showSymbol:false,itemStyle:{color:bid},data:rows.map(r=>number(r.volume_shares))},
    {name:baselineLabel,type:'line',showSymbol:false,connectNulls:false,smooth:false,lineStyle:{width:2},itemStyle:{color:axis},data:rows.map(r=>number(r.volume_avg20_previous))}
   ]:[{name:label,type:options.bars?'bar':'line',showSymbol:false,connectNulls:false,smooth:false,lineStyle:{width:2},itemStyle:{color:bid},data:rows.map(r=>number(r[field]))}];
   chart.setOption({backgroundColor:bg,textStyle:{fontSize:16,color},animation:false,aria:{enabled:true},tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:bg,textStyle:{color,fontSize:16},valueFormatter:value=>value==null?'Thiếu dữ liệu':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:4}).format(value)},legend:{top:0,data:series.map(s=>s.name),textStyle:{color,fontSize:16}},grid:{left:narrow?12:26,right:18,containLabel:true,top:64,bottom:94},xAxis:{type:'category',data:rows.map(r=>r.provisional?r.date+" *":r.date),axisLabel:{color,fontSize:16,hideOverlap:true,formatter:value=>narrow?value.slice(5):value}},yAxis:{type:'value',min:field==='index_value'?undefined:0,scale:field==='index_value',name:unit,nameTextStyle:{fontSize:16},axisLabel:{color,fontSize:16,formatter:compact}},dataZoom:[{type:'inside'},{type:'slider',showDataShadow:false,height:22,bottom:16,brushSelect:false,textStyle:{fontSize:16}}],series});
   reset.onclick=()=>chart.dispatchAction({type:'dataZoom',start:0,end:100});
   plot.addEventListener('keydown',e=>{if(e.key==='Home')reset.click();});
  }
 }
 window.ChartKit={render,destroy,frameSelect,intradayFrame,intradayRows,dailyRows,withOpenDay,drawFinancial,financialZoom,filteredCandles,filterLabel,
  refreshMs:()=>window.StaticLiquidity?60000:5000,
  sourceFrame:frame=>intradayFrame(frame)?'15m':frame};
 window.addEventListener('resize',()=>charts.forEach(c=>{if(c.getOption)c.resize();}));
 new MutationObserver(()=>window.dispatchEvent(new CustomEvent('chart-theme-change'))).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
})();
