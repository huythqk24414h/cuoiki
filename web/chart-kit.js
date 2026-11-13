/* Pinned local Lightweight Charts 5.2.0 + ECharts 6.0.0. Financial calculations stay server-side. */
(function(){
 const charts=new Map();let priceType='candlestick';
 const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
 const number=v=>v==null||v===''?null:Number(v);
 function destroy(target){const old=charts.get(target);if(old){old.remove?.();old.dispose?.();charts.delete(target);}target.replaceChildren();}
 function render(target,rows,field,label,unit,options={}){
  destroy(target);if(!rows.length){target.textContent='Không có dữ liệu hợp lệ trong khoảng.';return;}
  const caption=document.createElement('p');caption.className='helper';caption.textContent=`${rows[0].symbol||''} · ${label} (${unit}) · ${options.source||'SSI FastConnect V3'} · ${rows[0].date}–${rows.at(-1).date}`;
  const tools=document.createElement('div');tools.className='chart-tools';
  const reset=document.createElement('button');reset.className='button secondary';reset.type='button';reset.textContent='Đặt lại';tools.append(reset);
  const plot=document.createElement('div');plot.className=options.main?'professional-chart main-price':'professional-chart';plot.tabIndex=0;plot.setAttribute('role','group');plot.setAttribute('aria-label',caption.textContent+'; phím trái/phải dịch thời gian, Home đặt lại');
  target.append(tools,plot,caption);
  const color=css('--color-text')||'#172235',bg=css('--color-surface')||'#fff',bid=css('--color-positive')||'#067858',ask=css('--color-negative')||'#c63150',axis=css('--color-axis')||'#64748b';
  if(options.main){
   const choose=document.createElement('select');choose.setAttribute('aria-label','Loại biểu đồ giá');
   for(const [value,text] of [['candlestick','Nến'],['hollow','Nến rỗng'],['bar','OHLC'],['line','Đường'],['area','Vùng'],['baseline','Baseline']]){const o=document.createElement('option');o.value=value;o.textContent=text;choose.append(o);}choose.value=priceType;tools.prepend(choose);
   const L=window.LightweightCharts,chart=L.createChart(plot,{autoSize:true,height:520,layout:{background:{type:'solid',color:bg},textColor:color,fontSize:16,attributionLogo:true},grid:{vertLines:{color:css('--color-border')},horzLines:{color:css('--color-border')}},crosshair:{mode:0},rightPriceScale:{borderColor:axis},timeScale:{borderColor:axis,timeVisible:false},handleScroll:true,handleScale:true});
   const Type={candlestick:L.CandlestickSeries,hollow:L.CandlestickSeries,bar:L.BarSeries,line:L.LineSeries,area:L.AreaSeries,baseline:L.BaselineSeries}[priceType];
   const settings={upColor:priceType==='hollow'?bg:bid,downColor:ask,borderUpColor:bid,borderDownColor:ask,wickUpColor:bid,wickDownColor:ask,color:bid,lineColor:bid,lineWidth:2,pointMarkersVisible:false,lastValueVisible:true};
   if(priceType==='baseline')settings.baseValue={type:'price',price:Number(rows[0].close_vnd)};
   const series=chart.addSeries(Type,settings);
   const candle=['candlestick','hollow','bar'].includes(priceType);
   series.setData(rows.map(r=>candle?{time:r.date,open:Number(r.open_vnd),high:Number(r.high_vnd),low:Number(r.low_vnd),close:Number(r.close_vnd)}:{time:r.date,value:Number(r.close_vnd)}));
   series.applyOptions({visible:options.price!==false});
   const volume=chart.addSeries(L.HistogramSeries,{color:bid,priceFormat:{type:'volume'},priceScaleId:'right'},1);
   volume.setData(rows.map(r=>({time:r.date,value:Number(r.volume_shares),color:Number(r.close_vnd)>=Number(r.open_vnd)?bid:ask})));volume.applyOptions({visible:options.volume!==false});
   chart.panes()[0].setHeight(380);chart.panes()[1].setHeight(140);chart.timeScale().fitContent();charts.set(target,chart);
   const tip=document.createElement('p');tip.className='chart-tooltip';tip.setAttribute('aria-live','polite');target.append(tip);
   chart.subscribeCrosshairMove(param=>{const data=param.seriesData.get(series);tip.textContent=data?`${param.time} · ${rows[0].symbol} · ${candle?`O ${data.open} / H ${data.high} / L ${data.low} / C ${data.close}`:data.value} ${unit}`:'Di chuột/chạm để đọc giá; khối lượng ở pane dưới.';});
   reset.onclick=()=>chart.timeScale().fitContent();choose.onchange=()=>{priceType=choose.value;render(target,rows,field,label,unit,options);};
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
 window.ChartKit={render,destroy};
 window.addEventListener('resize',()=>charts.forEach(c=>{if(c.getOption)c.resize();}));
 new MutationObserver(()=>window.dispatchEvent(new CustomEvent('chart-theme-change'))).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
})();
