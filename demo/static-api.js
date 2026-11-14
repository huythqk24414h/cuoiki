'use strict';
window.StaticLiquidity = (() => {
  const snapshot = fetch('/prices.json', {cache:'no-cache'}).then(response => {
    if (!response.ok) throw Error('Không tải được bảng giá.');
    return response.json();
  });
  const unavailable = 'Tính năng này cần dữ liệu SSI trong ứng dụng chạy trên máy.';
  function simulatedRows(symbol) {
    const rows = [];
    let close = 24500;
    const changes = [120,-80,190,-230,50,140,-110];
    for (let day = new Date('2026-08-03T00:00:00Z'); rows.length < 75; day.setUTCDate(day.getUTCDate()+1)) {
      if ([0,6].includes(day.getUTCDay())) continue;
      const i = rows.length;
      const open = close;
      close += changes[(i+Math.floor(i/7))%changes.length];
      const volume = 90000 + (i*7919)%42000 + (i%17===0 ? 190000 : 0);
      const history = rows.slice(-20);
      const average = history.length===20 ? history.reduce((sum,row)=>sum+row.volume_shares,0)/20 : null;
      const change = i ? (close/open-1)*100 : null;
      const returns = [...rows.slice(-19).map(row=>row.return_pct),change];
      const mean = returns.reduce((sum,value)=>sum+value,0)/20;
      const volatility = i>=20 ? Math.sqrt(returns.reduce((sum,value)=>sum+(value-mean)**2,0)/19) : null;
      rows.push({symbol,date:day.toISOString().slice(0,10),open_vnd:open,close_vnd:close,
        high_vnd:Math.max(open,close)+120,low_vnd:Math.min(open,close)-100,
        volume_shares:volume,relative_volume20:average && volume/average,
        volume_avg20_previous:average,volatility20_pct:volatility,return_pct:change,
        price_adjustment:'simulation',upstream_source:'Dữ liệu mô phỏng'});
    }
    return rows;
  }
  const history = simulatedRows('DEMO');
  const first = history[0].date, last = history.at(-1).date;
  const range = {start:first,end:last,actual_first:first,actual_last:last};
  function historicalRows(q) {
    let rows = history.filter(row=>row.date <= (q.get('to') || last) && row.date >= (q.get('from') || first));
    const periods = {'1D':1,'5D':5,'1W':5,'1M':22,'3M':66};
    const size = periods[q.get('range')];
    if (size) rows = rows.slice(-size);
    return rows;
  }
  function aggregate(rows, resolution) {
    if (resolution === '1D') return rows;
    const periods = new Map();
    for (const row of rows) {
      const day = new Date(row.date+'T00:00:00Z');
      day.setUTCDate(day.getUTCDate()-(day.getUTCDay()+6)%7);
      const key = resolution==='1W' ? day.toISOString().slice(0,10) : row.date.slice(0,7);
      const previous = periods.get(key);
      periods.set(key, previous ? {...row, open_vnd:previous.open_vnd,
        high_vnd:Math.max(previous.high_vnd,row.high_vnd),low_vnd:Math.min(previous.low_vnd,row.low_vnd),
        volume_shares:Number(previous.volume_shares)+Number(row.volume_shares)} : row);
    }
    return [...periods.values()];
  }

  let catalogTime = 0, catalogPromise;
  const series = new Map();
  async function load(kind, symbol) {
    const q = new URLSearchParams({kind,...(symbol ? {symbol} : {})});
    const response = await fetch('/api/market-data?'+q,{cache:'no-store'});
    return response.ok ? response.json() : null;
  }
  function catalog() {
    if (!catalogPromise || Date.now()-catalogTime>60000) {
      catalogTime = Date.now();
      catalogPromise = load('history').catch(()=>null);
    }
    return catalogPromise;
  }
  async function historyResponse(path, q, data) {
    const symbols = Object.keys(data.symbols);
    const equities = symbols.filter(s=>!data.indexes.includes(s));
    const last = symbols.map(s=>data.symbols[s].last).sort().at(-1);
    const first = symbols.map(s=>data.symbols[s].first).sort()[0];
    if(path==='meta') return {available:true,status:'SSI FastConnect',asof_date:last,last_available_session:last,
      loaded_symbols:equities,issues:[],historical_range:{start:data.query_start,end:last,actual_first:first,actual_last:last},
      manifest:{upstream_sources:[{name:'SSI FastConnect V3'}],adjustment_policy:'unknown',
        retrieved_at_utc:data.updated_at,row_count:symbols.reduce((n,s)=>n+data.symbols[s].count,0)}};
    if(path==='catalog') return {securities:equities.map(symbol=>({symbol,board:'HOSE',stockType:'Stock'})),
      indexes:symbols.filter(s=>data.indexes.includes(s)).map(index=>({index})),index_memberships:{}};
    if(path==='insights') return {paragraphs:['Dữ liệu ngày từ SSI FastConnect. Giá giữ đơn vị nguồn.']};
    const symbol=q.get('symbol');
    let rows=[];
    if(data.symbols[symbol]) {
      const cached=series.get(symbol);
      if(cached?.version!==data.updated_at)
        series.set(symbol,{version:data.updated_at,rows:load('series',symbol).catch(()=>null)});
      rows=await series.get(symbol).rows;
      if(!rows){series.delete(symbol);throw Error('Chuỗi SSI tạm thời chưa tải được.');}
    }
    rows=rows.filter(row=>row.date<=(q.get('to')||last)&&row.date>=(q.get('from')||first));
    const filter=q.get('range');
    const count={'1D':1,'5D':5,'1W':5,'1M':22,'3M':66,'6M':132,'1Y':264,'3Y':792,'5Y':1320}[filter];
    if(count) rows=rows.slice(-count);
    if(filter==='YTD'&&rows.length) rows=rows.filter(row=>row.date.slice(0,4)===rows.at(-1).date.slice(0,4));
    if(path==='index') return {source:'SSI FastConnect V3',rows:rows.map(row=>({
      tradingDate:row.date,indexValue:row.close_vnd,indexChangePercentage:row.return_pct}))};
    const resolution=q.get('resolution')||'1D', summary=rows.at(-1);
    return {available:true,rows:aggregate(rows,resolution),summary,resolution,
      last_available_session:summary?.date,unit_status:'Đơn vị nguồn SSI'};
  }
  async function liveBoard(q) {
    const data=await load('live').catch(()=>null);
    const age=Date.now()-Date.parse(data?.updated_at);
    const active=age>=0&&age<=15000;
    const matching=(data?.rows||[]).filter(row=>row.symbol.includes((q.get('search')||'').trim().toUpperCase()));
    const size=Number(q.get('size'))||30,pages=Math.max(1,Math.ceil(matching.length/size));
    const page=Math.min(pages,Number(q.get('page'))||1);
    const levels=side=>side.map(([price,quantity])=>({price,quantity}));
    const rows=matching.slice((page-1)*size,page*size).map(row=>({...row,bids:levels(row.bids),asks:levels(row.asks),
      status:active&&row.status==='fresh_two_sided_quote'?'receiving':'stale',trade_status:'stale',
      received_at:data.updated_at}));
    return {mode:'DATA',rows,page,pages,total:matching.length,catalog_total:data?.rows?.length||0,
      display_note:active?'SSI DATA · Snapshot '+data.updated_at:data?'Snapshot SSI cũ · '+data.updated_at:'Chưa có snapshot SSI trong phiên.',
      units_note:'Giữ đơn vị nguồn SSI.',view_note:'Danh sách mã do collector theo dõi.'};
  }

  async function request(target, options) {
    const path = target.pathname;
    const q = target.searchParams;
    if (path === '/api/calculate') {
      const data = JSON.parse(options.body);
      const now = data.received_at;
      if (data.source !== 'manual' || data.price_unit !== 'VND' ||
          data.quantity_unit !== 'share' || data.session !== 'continuous' ||
          data.contract_version !== '1.0' || !Number.isFinite(Date.parse(data.event_time)) ||
          Date.parse(data.event_time) > Date.parse(now)) throw Error('Kiểm tra hợp đồng dữ liệu nhập tay và thời gian.');
      const book = window.LiquidityCalculator.buildManualPayload({
        symbol:data.symbol, bids:data.bids, asks:data.asks
      }, now);
      const stats = window.LiquidityCalculator.calculateManual(book);
      const bid = stats['Độ sâu mua (VND)'], ask = stats['Độ sâu bán (VND)'];
      const places = Math.max(bid.split('.')[1]?.length || 0, ask.split('.')[1]?.length || 0);
      const units = value => {
        const [whole, fraction = ''] = value.split('.');
        return BigInt(whole + fraction.padEnd(places,'0'));
      };
      const total = String(units(bid) + units(ask)).padStart(places+1,'0');
      return {bid_depth_vnd:bid, ask_depth_vnd:ask,
        total_depth_vnd:places ? total.slice(0,-places)+'.'+total.slice(-places) : total,
        spread_bps:stats['Spread (bps)'], imbalance:stats.Imbalance,
        levels:{bid:book.bids.length,ask:book.asks.length}};
    }
    const endpoint=path.split('/').at(-1);
    if(endpoint==='board'&&q.get('mode')==='DATA') return liveBoard(q);
    if(endpoint==='intraday') {
      const live=await load('live').catch(()=>null);
      const points=live?.recent_trades?.[q.get('symbol')]||[];
      const span={'15m':15,'1h':60,'4h':240}[q.get('resolution')]||15;
      const candles=new Map();
      for (const [time,price] of points) {
        const date=new Date(time);
        const session=date.getUTCHours()>=6 ? 6 : 2;
        const anchor=new Date(time.slice(0,10)+'T00:00:00Z').getTime()+session*3600000;
        const bucket=anchor+Math.floor((date-anchor)/(span*60000))*span*60000;
        const timestamp=new Date(bucket+7*3600000).toISOString().slice(0,19)+'+07:00';
        const value=Number(price), candle=candles.get(timestamp);
        if(candle){candle.high=Math.max(candle.high,value);candle.low=Math.min(candle.low,value);candle.close=value;}
        else candles.set(timestamp,{timestamp,open:value,high:value,low:value,close:value});
      }
      const current=Date.now()-Date.parse(live?.updated_at);
      return {rows:[...candles.values()],last_source_time:points.at(-1)?.[0],retrieved_at:live?.updated_at,
        status:points.length?(current>=0&&current<=15000?'SSI · Nến tạm từ bản tin khớp nhận được':'SSI · Dữ liệu đã lưu'):'Chờ bản tin SSI'};
    }
    const published=await catalog();
    if(published&&['meta','catalog','series','index','insights'].includes(endpoint))
      return historyResponse(endpoint,q,published);
    const data = await snapshot;
    const real = data.source === 'SSI FastConnect';
    const closing=published ? Object.entries(published.symbols)
      .filter(([symbol])=>!published.indexes.includes(symbol)).map(([,entry])=>entry.close) : data.rows;
    const latest=published||real ? closing.map(row=>row.date).sort().at(-1) : null;
    if (path === '/api/market/status') return {
      status:'Bản web EOD', snapshot_asof:latest,
      disabled_reason:'Bản web sử dụng bảng giá đóng cửa do GitHub Actions cập nhật.',
      measurement_reason:'Dữ liệu sổ lệnh trong phiên xem trên ứng dụng chạy trên máy.'
    };
    const rows = historicalRows(q);
    if (path === '/api/market/meta') return {
      available:true,status:'MÔ PHỎNG',asof_date:last,last_available_session:last,
      loaded_symbols:['DEMO'],historical_range:range,issues:[],
      manifest:{dataset_type:'simulation',row_count:history.length,
        adjustment_policy:'simulation',upstream_sources:[{name:'Dữ liệu mô phỏng'}]}
    };
    if (path === '/api/market/catalog') return {
      securities:[{symbol:'DEMO',symbolNameVi:'Cổ phiếu mô phỏng',board:'HOSE',stockType:'Stock'}],
      indexes:[{index:'DEMO-INDEX',indexName:'Chỉ số mô phỏng'}],
      index_memberships:{'DEMO-INDEX':['DEMO']}
    };
    if (path === '/api/market/series') {
      const resolution=q.get('resolution') || '1D';
      return {available:true,rows:aggregate(rows,resolution),summary:rows.at(-1),
        last_available_session:rows.at(-1)?.date,resolution,unit_status:'Mô phỏng'};
    }
    if (path === '/api/market/index') return {source:'Dữ liệu mô phỏng',rows:rows.map(row=>({
      tradingDate:row.date,indexValue:row.close_vnd/20,indexChange:(row.close_vnd-row.open_vnd)/20,
      indexChangePercentage:row.return_pct
    }))};
    if (path === '/api/market/insights') return {paragraphs:['Biểu đồ và chỉ số sử dụng chuỗi giá mô phỏng để minh họa cách tính.']};
    if (path === '/api/market/coverage' || path === '/api/market/rankings')
      throw Error('Bản mô phỏng có một mã minh họa. Độ phủ và xếp hạng cần dữ liệu thị trường.');

    if (path === '/api/market/alerts') return {status:'unavailable',rows:[]};
    if (path === '/api/market/research') return {status:'Chờ kiểm chứng',h1:'NOT_TESTED',recorded_days:[],counts:{}};
    if (path === '/api/market/board') {
      const matching = closing.filter(row=>row.symbol.includes((q.get('search') || '').trim().toUpperCase()));
      const size = Number(q.get('size')) || 30;
      const pages = Math.max(1,Math.ceil(matching.length / size));
      const page = Math.min(pages,Number(q.get('page')) || 1);
      const boardRows = matching.slice((page-1)*size,page*size).map(row=>({
        symbol:row.symbol, bids:[], asks:[], last_price:row.close, high:row.high,low:row.low,
        total_volume:row.volume, session:real || published ? 'EOD '+row.date : 'Mô phỏng', status:'eod', trade_status:'eod'
      }));
      return {mode:'EOD',rows:boardRows,page,pages,total:matching.length,catalog_total:closing.length,
        units_note:real || published ? 'Giá và khối lượng theo đơn vị nguồn SSI.' : 'Dữ liệu mô phỏng.',
        view_note:'Bản web hiển thị các mã có trong snapshot.',
        display_note:real || published ? 'Giá đóng cửa SSI · Ngày ghi ở mỗi mã.' : 'Dữ liệu mô phỏng · Minh họa bảng giá.'};
    }
    throw Error(unavailable);
  }
  return {request};
})();
