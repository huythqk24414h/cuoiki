/* Shared step-depth view. Geometry only; authoritative values remain backend Decimal. */
(function(){
  'use strict';
  function render(container,payload,source,{sourceUnits=false}={}){
    const priceUnit=sourceUnits?'đơn vị giá SSI':'VND/cp';
    const depthUnit=sourceUnits?'giá nguồn × KL nguồn':'VND';
    const quantityUnit=sourceUnits?'đơn vị KL nguồn':'cp';
    if(window.echarts&&container.clientWidth>0){
      container._disposeDepth?.();
      echarts.getInstanceByDom(container)?.dispose();
      container.replaceChildren();
      const series=window.LiquidityCalculator.cumulativeLevels(payload),style=getComputedStyle(document.documentElement),color=style.getPropertyValue('--color-text').trim();
      const plot=document.createElement('div');plot.className='professional-chart';plot.style.height='380px';plot.style.minWidth='0';plot.tabIndex=0;plot.setAttribute('aria-label',`${source} · ${payload.symbol} · độ sâu ba mức · ${depthUnit}`);container.append(plot);
      const chart=echarts.init(plot,null,{renderer:'canvas'});
      const narrow=(container.clientWidth||plot.clientWidth)<560;
      const midpoint=(series.bids[0].price+series.asks[0].price)/2;
      const maximum=Math.max(series.bids.at(-1).cumulativeValue,series.asks.at(-1).cumulativeValue);
      const divisor=maximum>=1000000?1000000:maximum>=1000?1000:1;
      const magnitude=(divisor===1000000?'triệu ':divisor===1000?'nghìn ':'')+(sourceUnits?'đơn vị nguồn':'VND');
      const priceDivisor=sourceUnits?1:1000;
      const format=(value,digits=2)=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:digits}).format(value);
      chart.setOption({animation:false,aria:{enabled:true},textStyle:{fontSize:16,color},tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:style.getPropertyValue('--color-surface').trim(),textStyle:{color,fontSize:16},formatter:points=>(Array.isArray(points)?points:[points]).map(p=>`${p.seriesName}<br>Giá: ${format(p.value[0])} ${priceUnit}<br>Độ sâu lũy kế: ${format(p.value[1])} ${depthUnit}`).join('<br>')},legend:{top:0,data:['Mua','Bán'],textStyle:{fontSize:16,color}},grid:{left:12,right:32,containLabel:true,bottom:58,top:62},xAxis:{type:'value',scale:true,name:sourceUnits?'Giá · đơn vị nguồn':'Giá · nghìn VND/cp',nameLocation:'middle',nameGap:36,nameTextStyle:{fontSize:16},min:series.bids.at(-1).price,max:series.asks.at(-1).price,splitNumber:narrow?3:5,axisLabel:{fontSize:16,hideOverlap:true,formatter:v=>format(v/priceDivisor)}},yAxis:{type:'value',min:0,name:'Lũy kế · '+magnitude,nameTextStyle:{fontSize:16,align:'left'},splitNumber:narrow?4:5,axisLabel:{fontSize:16,formatter:v=>format(v/divisor,1)}},series:[{name:'Mua',type:'line',step:'start',showSymbol:false,lineStyle:{width:2,color:style.getPropertyValue('--color-positive').trim()},itemStyle:{color:style.getPropertyValue('--color-positive').trim()},data:[...series.bids].reverse().map(p=>[p.price,p.cumulativeValue]).concat([[midpoint,0]])},{name:'Bán',type:'line',step:'end',showSymbol:false,lineStyle:{width:2,color:style.getPropertyValue('--color-negative').trim()},itemStyle:{color:style.getPropertyValue('--color-negative').trim()},data:[[midpoint,0],...series.asks.map(p=>[p.price,p.cumulativeValue])]}]});
      const note=document.createElement('p');note.className='helper';note.textContent=`${source} · ${payload.symbol} · ${payload.event_time}. Giá theo ${priceUnit}. Trục độ sâu theo ${magnitude}, từ tối đa ba mức mỗi phía.`;container.append(note);
      const observer=new ResizeObserver(()=>chart.resize());observer.observe(plot);
      container._disposeDepth=()=>{observer.disconnect();chart.dispose();delete container._disposeDepth;};
      return;
    }
    container._disposeDepth?.();
    container.replaceChildren();
    const series=window.LiquidityCalculator.cumulativeLevels(payload);
    const bids=series.bids,asks=series.asks;
    const min=bids.at(-1).price,max=asks.at(-1).price,mid=(bids[0].price+asks[0].price)/2;
    const ceiling=Math.max(bids.at(-1).cumulativeValue,asks.at(-1).cumulativeValue);
    if(!Number.isFinite(ceiling)||!(max>min)||!(ceiling>0)){
      container.textContent='Không vẽ được trong giới hạn hình học; xem số chính xác từ engine.';return;
    }
    const width=Math.max(300,container.clientWidth||450),height=250,left=64,right=16,top=26,bottom=206;
    const x=price=>left+(price-min)/(max-min)*(width-left-right);
    const y=value=>bottom-value/ceiling*(bottom-top);
    const ns='http://www.w3.org/2000/svg';
    const svg=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text!=null)n.textContent=text;return n;};
    const chart=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'chart-frame',role:'img','aria-label':`${source} · độ sâu lũy kế theo giá, ${depthUnit}`});
    chart.append(svg('title',{},`${source} · độ sâu theo ${depthUnit}`));
    const axis=value=>Math.abs(value)>=1e6?value.toExponential(1):window.LiquidityCalculator.formatDecimal(String(value),0);
    chart.append(svg('text',{x:left,y:16,class:'eod-axis'},'Lũy kế · '+depthUnit));
    for(let i=0;i<3;i++){
      const value=ceiling*i/2,yy=y(value);
      chart.append(svg('line',{x1:left,y1:yy,x2:width-right,y2:yy,class:'eod-gridline'}));
      chart.append(svg('text',{x:left-6,y:yy+5,'text-anchor':'end',class:'eod-axis'},axis(value)));
    }
    chart.append(svg('line',{x1:x(mid),y1:top,x2:x(mid),y2:bottom,class:'depth-midline'}));
    const caption=document.createElement('p');caption.className='chart-tooltip';caption.textContent=`${source} · Chọn mức giá để xem chi tiết. Hình học gần đúng.`;
    for(const side of ['bids','asks']){
      const points=side==='bids'?[...bids].reverse().concat([{price:mid,cumulativeValue:0}]):[{price:mid,cumulativeValue:0},...asks];
      let d=`M${x(points[0].price)},${y(points[0].cumulativeValue)}`;
      points.slice(1).forEach(point=>{d+=`H${x(point.price)}V${y(point.cumulativeValue)}`;});
      chart.append(svg('path',{d,class:side==='bids'?'depth-bid-line':'depth-ask-line'}));
      series[side].forEach((point,i)=>{
        const text=`${source} · ${side==='bids'?'Mua':'Bán'} mức ${i+1}: giá ${window.LiquidityCalculator.formatDecimal(point.price)} ${priceUnit}, KL ${window.LiquidityCalculator.formatDecimal(point.quantity,0)} ${quantityUnit}, lũy kế ≈${window.LiquidityCalculator.formatDecimal(point.cumulativeValue)} ${depthUnit}`;
        const circle=svg('circle',{cx:x(point.price),cy:y(point.cumulativeValue),r:6,class:side==='bids'?'depth-bid-point':'depth-ask-point',tabindex:0,role:'button','aria-label':text});
        circle.append(svg('title',{},text));
        const select=()=>{caption.textContent=text;};
        ['pointerenter','focus','click'].forEach(event=>circle.addEventListener(event,select));
        circle.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();select();}});
        chart.append(circle);
      });
    }
    for(const price of [min,mid,max])chart.append(svg('text',{x:x(price),y:height-22,'text-anchor':price===min?'start':price===max?'end':'middle',class:'eod-axis'},axis(price)));
    chart.append(svg('text',{x:width-right,y:height-3,'text-anchor':'end',class:'eod-axis'},'Giá · '+priceUnit));
    container.append(chart,caption);
  }
  window.LiquidityDepthChart=Object.freeze({render});
}());
