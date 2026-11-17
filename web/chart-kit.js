/* Pinned local Lightweight Charts 5.2.0 + ECharts 6.0.0. Financial calculations stay server-side. */
(function(){
 const charts=new Map(), priceTypes=new WeakMap();
 const types=[['candlestick','Nến'],['hollow','Nến rỗng'],['bar','Thanh OHLC'],['line','Đường'],['area','Vùng'],['baseline','Đường cơ sở']];
 const frames=[['15m','M15 · 15 phút'],['30m','M30 · 30 phút'],['1h','H1 · 1 giờ'],
  ['2h','H2 · 2 giờ'],['4h','H4 · theo buổi'],['1D','D · Ngày'],['1W','W · Tuần'],
  ['1M','M · Tháng'],['1Q','Q · Quý'],['1Y','Y · Năm']];
 const intradayFrame=frame=>['15m','30m','1h','2h','4h'].includes(frame);
 const historyRange=(range,frame)=>{
  if(frame==='1D'||['CUSTOM','MAX'].includes(range))return range;
  const ranges=['1D','5D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX'];
  const minimum={'1W':'1Y','1M':'3Y','1Q':'3Y','1Y':'MAX'}[frame];
  return ranges.indexOf(range)>=ranges.indexOf(minimum)?range:minimum;
 };
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
  const source=rows.map(row=>({date:row.timestamp,symbol,closed_at:row.closed_at,
   open_vnd:row.open,high_vnd:row.high,low_vnd:row.low,close_vnd:row.close,volume_shares:row.volume}));
  const length=frame==='30m'?30:frame==='2h'?120:0;
  if(!length)return source;
  // A grouped candle must start on the exchange's session grid and finish at
  // its own boundary, including shorter buckets immediately before lunch or close.
  const morning=['HNXINDEX','UPCOMINDEX'].includes(symbol)?540:555;
  const close=symbol==='UPCOMINDEX'?900:870;
  const groups=new Map();
  for(const row of source){
   const minute=Number(row.date.slice(11,13))*60+Number(row.date.slice(14,16));
   const anchor=minute<690?morning:780, end=minute<690?690:close;
   if(minute<anchor||minute>=end)continue;
   const start=anchor+Math.floor((minute-anchor)/length)*length;
   const day=row.date.slice(0,10),key=day+':'+start;
   if(!groups.has(key))groups.set(key,{rows:[],start,end:Math.min(start+length,end)});
   groups.get(key).rows.push({row,minute});
  }
  const result=[];
  for(const group of groups.values()){
   const expected=(group.end-group.start)/15;
   if(group.rows.length!==expected||!group.rows.every(({minute},i)=>minute===group.start+i*15))continue;
   const bars=group.rows.map(({row})=>row);
   const [bar]=rollup(bars,()=>0);
   result.push({...bar,date:bars[0].date});
  }
  return result;
 }
 function destroy(target){const old=charts.get(target);if(old){old.remove?.();old.dispose?.();charts.delete(target);}target.replaceChildren();}
 function render(target,rows,field,label,unit,options={}){
  destroy(target);if(!rows.length){target.textContent='Không có dữ liệu hợp lệ trong khoảng.';return;}
  const caption=document.createElement('p');caption.className='helper';caption.textContent=`${rows[0].symbol||''} · ${label} (${unit}) · ${options.source||'SSI FastConnect V3'} · ${rows[0].date}–${rows.at(-1).date}`;
  const tools=document.createElement('div');tools.className='chart-tools';
  const reset=document.createElement('button');reset.className='button secondary';reset.type='button';reset.textContent='Đặt lại';tools.append(reset);
  const plot=document.createElement('div');plot.className=options.main?'professional-chart main-price':'professional-chart';plot.tabIndex=0;plot.setAttribute('role','group');plot.setAttribute('aria-label',caption.textContent+'; phím trái/phải dịch thời gian, Home đặt lại');
  target.append(tools,plot,caption);
  const color=css('--color-text')||'#172235',bg=css('--color-surface')||'#fff',bid=css('--color-positive')||'#067858',ask=css('--color-negative')||'#c63150',axis=css('--color-axis')||'#64748b';
  if(options.main||options.financial){
   const ohlcTypes=['candlestick','hollow','bar'];
   const complete=rows.filter(hasOHLC).length;
   const requested=priceTypes.get(target)||options.defaultType||'candlestick';
   const priceType=!complete&&ohlcTypes.includes(requested)?'line':requested;
   const hasVolume=options.volumePane!==false&&rows.some(row=>Number.isFinite(number(row.volume_shares)));
   const choose=document.createElement('select');choose.setAttribute('aria-label','Loại biểu đồ giá');
   for(const [value,text] of types){const o=document.createElement('option');o.value=value;o.textContent=text;o.disabled=!complete&&ohlcTypes.includes(value);choose.append(o);}
   choose.value=priceType;tools.prepend(choose);
   if(complete<rows.length)caption.textContent+=` · Có OHLC ${complete}/${rows.length} kỳ`;
   const L=window.LightweightCharts;
   const dateTime=new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
   const timeLabel=time=>typeof time==='number'?dateTime.format(time*1000):String(time);
   const tickLabel=(time,type)=>{
    const parts=Object.fromEntries(dateTime.formatToParts(time*1000).map(({type,value})=>[type,value]));
    return type===L.TickMarkType.Time?`${parts.hour}:${parts.minute}`:`${parts.day}/${parts.month}`;
   };
   const chart=L.createChart(plot,{autoSize:true,layout:{background:{type:'solid',color:bg},textColor:color,fontSize:15,attributionLogo:true},
    localization:{timeFormatter:timeLabel},grid:{vertLines:{color:css('--color-border')},horzLines:{color:css('--color-border')}},
    crosshair:{mode:0},rightPriceScale:{borderColor:axis},
    timeScale:{borderColor:axis,timeVisible:Boolean(options.intraday),secondsVisible:false,
     ...(options.intraday?{tickMarkFormatter:tickLabel}:{})},handleScroll:true,handleScale:true});
   const Type={candlestick:L.CandlestickSeries,hollow:L.CandlestickSeries,bar:L.BarSeries,line:L.LineSeries,area:L.AreaSeries,baseline:L.BaselineSeries}[priceType];
   const settings={upColor:priceType==='hollow'?bg:bid,downColor:ask,borderUpColor:bid,borderDownColor:ask,wickUpColor:bid,wickDownColor:ask,color:bid,lineColor:bid,lineWidth:2,pointMarkersVisible:false,lastValueVisible:true};
   if(priceType==='baseline')settings.baseValue={type:'price',price:Number(rows.find(row=>positive(row.close_vnd))?.close_vnd||0)};
   const series=chart.addSeries(Type,settings);
   const candle=ohlcTypes.includes(priceType);
   const timeOf=r=>options.intraday?Date.parse(r.date)/1000:r.date;
   series.setData(rows.map((r,i)=>{
    const time=timeOf(r);
    if(candle){
     if(!hasOHLC(r))return {time};
     const bar={time,open:Number(r.open_vnd),high:Number(r.high_vnd),low:Number(r.low_vnd),close:Number(r.close_vnd)};
     if(priceType==='hollow'){
      const prior=rows[i-1]?.close_vnd;
      const direction=bar.close>=(positive(prior)?Number(prior):bar.open)?bid:ask;
      Object.assign(bar,{color:bar.close>=bar.open?bg:direction,borderColor:direction,wickColor:direction});
     }
     return bar;
    }
    return positive(r.close_vnd)?{time,value:Number(r.close_vnd)}:{time};
   }));
   series.applyOptions({visible:options.price!==false});
   if(hasVolume){
    const volume=chart.addSeries(L.HistogramSeries,{title:'Khối lượng',color:bid,priceFormat:{type:'volume'},priceScaleId:'right'},1);
    volume.setData(rows.map(r=>Number.isFinite(number(r.volume_shares))?
     {time:timeOf(r),value:number(r.volume_shares),color:!positive(r.open_vnd)||Number(r.close_vnd)>=Number(r.open_vnd)?bid:ask}:{time:timeOf(r)}));
    volume.applyOptions({visible:options.volume!==false});
    chart.panes()[1].setHeight(125);
   }
   chart.timeScale().fitContent();charts.set(target,chart);
   const tip=document.createElement('p');tip.className='chart-tooltip';tip.setAttribute('aria-live','polite');target.append(tip);
   chart.subscribeCrosshairMove(param=>{const data=param.seriesData.get(series);tip.textContent=data?`${timeLabel(param.time)} · ${rows[0].symbol} · ${candle?`O ${data.open} / H ${data.high} / L ${data.low} / C ${data.close}`:data.value} ${unit}`:'Di chuột hoặc chạm để xem số liệu.';});
   reset.onclick=()=>chart.timeScale().fitContent();choose.onchange=()=>{priceTypes.set(target,choose.value);render(target,rows,field,label,unit,options);target.querySelector('.chart-tools select')?.focus();};
   plot.addEventListener('keydown',e=>{if(e.key==='Home'){e.preventDefault();chart.timeScale().fitContent();}if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();chart.timeScale().scrollToPosition(chart.timeScale().scrollPosition()+(e.key==='ArrowLeft'?-5:5),false);}});
  }else{
   const chart=echarts.init(plot,null,{renderer:'canvas'});charts.set(target,chart);
   const compact=value=>new Intl.NumberFormat('vi-VN',{notation:'compact',maximumFractionDigits:1}).format(value);
   const narrow=plot.clientWidth<560;
   const actualLabel='Khối lượng phiên',baselineLabel='TB20 phiên ngày trước';
   const series=options.volumeComparison?[
    {name:actualLabel,type:'bar',showSymbol:false,itemStyle:{color:bid},data:rows.map(r=>number(r.volume_shares))},
    {name:baselineLabel,type:'line',showSymbol:false,connectNulls:false,smooth:false,lineStyle:{width:2},itemStyle:{color:axis},data:rows.map(r=>number(r.volume_avg20_previous))}
   ]:[{name:label,type:options.bars?'bar':'line',showSymbol:false,connectNulls:false,smooth:false,lineStyle:{width:2},itemStyle:{color:bid},data:rows.map(r=>number(r[field]))}];
   chart.setOption({backgroundColor:bg,textStyle:{fontSize:16,color},animation:false,aria:{enabled:true},tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:bg,textStyle:{color,fontSize:16},valueFormatter:value=>value==null?'Thiếu dữ liệu':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:4}).format(value)},legend:{top:0,data:series.map(s=>s.name),textStyle:{color,fontSize:16}},grid:{left:narrow?12:26,right:18,containLabel:true,top:64,bottom:94},xAxis:{type:'category',data:rows.map(r=>r.date),axisLabel:{color,fontSize:16,hideOverlap:true,formatter:value=>narrow?value.slice(5):value}},yAxis:{type:'value',min:field==='index_value'?undefined:0,scale:field==='index_value',name:unit,nameTextStyle:{fontSize:16},axisLabel:{color,fontSize:16,formatter:compact}},dataZoom:[{type:'inside'},{type:'slider',showDataShadow:false,height:22,bottom:16,brushSelect:false,textStyle:{fontSize:16}}],series});
   reset.onclick=()=>chart.dispatchAction({type:'dataZoom',start:0,end:100});
   plot.addEventListener('keydown',e=>{if(e.key==='Home')reset.click();});
  }
 }
 window.ChartKit={render,destroy,frameSelect,intradayFrame,intradayRows,dailyRows,historyRange,withOpenDay,
  sourceFrame:frame=>frame==='30m'||frame==='2h'?'15m':frame};
 window.addEventListener('resize',()=>charts.forEach(c=>{if(c.getOption)c.resize();}));
 new MutationObserver(()=>window.dispatchEvent(new CustomEvent('chart-theme-change'))).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
})();
