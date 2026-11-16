'use strict';
window.StaticLiquidity = (() => {
  const unavailable = 'Tính năng này cần dữ liệu SSI trong ứng dụng chạy trên máy.';
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

  function enrichArchive(rows) {
    const returns = [];
    return rows.map((row, i) => {
      const prior = Number(rows[i-1]?.close_vnd);
      const close = Number(row.close_vnd);
      const change = prior > 0 && close > 0 ? (close/prior-1)*100 : null;
      returns.push(change);
      const previous = rows.slice(Math.max(0,i-20),i).map(r=>Number(r.volume_shares));
      const average = previous.length===20 && previous.every(Number.isFinite)
        ? previous.reduce((sum,v)=>sum+v,0)/20 : null;
      const sample = returns.slice(-20);
      const mean = sample.length===20 && sample.every(Number.isFinite)
        ? sample.reduce((sum,v)=>sum+v,0)/20 : null;
      return {...row,return_pct:change,volume_avg20_previous:average,
        relative_volume20:average>0 ? Number(row.volume_shares)/average : null,
        volatility20_pct:mean===null ? null : Math.sqrt(sample.reduce((sum,v)=>sum+(v-mean)**2,0)/19),
        liquidation_days_100k_5pct:average>0 ? 100000/(0.05*average) : null};
    });
  }

  let catalogTime = 0, catalogPromise;
  const series = new Map();
  let archive;
  function archiveCatalog() {
    return archive ??= fetch('/eod-archive/catalog.json').then(response=>{
      if(response.status===404) return {};
      if(!response.ok) throw Error('Không đọc được kho lịch sử SSI.');
      if(!response.headers.get('content-type')?.includes('application/json')) return {};
      return response.json();
    }).catch(error=>{archive=undefined;throw error;});
  }
  async function load(kind, symbol, resolution) {
    const q = new URLSearchParams({kind,...(symbol ? {symbol} : {}),...(resolution ? {resolution} : {})});
    const response = await fetch('/api/market-data?'+q,{cache:'no-store'});
    if (response.status === 404) return null;
    if (!response.ok) throw Error('Kho dữ liệu SSI tạm thời không truy cập được.');
    return response.json();
  }
  function catalog() {
    if (!catalogPromise || Date.now()-catalogTime>60000) {
      catalogTime = Date.now();
      catalogPromise = load('history').catch(error=>{catalogPromise=undefined;throw error;});
    }
    return catalogPromise;
  }
  let directoryCache;
  function marketDirectory() {
    const now = Date.now();
    if (!directoryCache || now-directoryCache.time>=60000) {
      directoryCache={time:now,data:load('catalog').catch(error=>{directoryCache=undefined;throw error;})};
    }
    return directoryCache.data;
  }
  async function historyResponse(path, q, data) {
    const symbols = Object.keys(data.symbols);
    const equities = symbols.filter(s=>!data.indexes.includes(s));
    const last = symbols.map(s=>data.symbols[s].last).sort().at(-1);
    const first = symbols.map(s=>data.symbols[s].first).sort()[0];
    if(path==='meta') return {available:true,status:'SSI FastConnect',asof_date:last,last_available_session:last,
      loaded_symbols:equities,issues:[],historical_range:{start:first,end:last,actual_first:first,actual_last:last},
      manifest:{upstream_sources:[{name:'SSI FastConnect V3'}],adjustment_policy:'unknown',
        retrieved_at_utc:data.updated_at,row_count:symbols.reduce((n,s)=>n+data.symbols[s].count,0)}};
    if(path==='catalog') {
      const directory=await marketDirectory();
      const saved=await archiveCatalog();
      const combined=new Map(Object.values(saved).map(row=>[row.symbol,{...row,daily_last:row.last}]));
      for(const row of directory?.securities||equities.map(symbol=>({symbol,board:'HOSE',stockType:'Stock',daily_last:data.symbols[symbol].last}))) {
        combined.set(row.symbol,{...combined.get(row.symbol),...row,daily_last:row.daily_last||saved[row.symbol]?.last});
      }
      return {securities:[...combined.values()],
        indexes:symbols.filter(s=>data.indexes.includes(s)).map(index=>({index})),
        index_memberships:directory?.index_memberships||{}, coverage_available:true};
    }
    if(path==='insights') {
      const day=q.get('date');
      const payload=await historyResponse('series',new URLSearchParams({symbol:q.get('symbol')||'',range:'CUSTOM',from:day||'',to:day||''}),data);
      const value=payload.summary?.liquidation_days_100k_5pct;
      return {paragraphs:[value!=null&&Number.isFinite(Number(value))
        ? 'Ước lượng thoát 100.000 cổ phiếu ở mức tham gia 5% khối lượng bình quân 20 phiên trước: '+
          Number(value).toLocaleString('vi-VN',{maximumFractionDigits:2})+' phiên. Đây là kịch bản; thanh khoản, giá và khả năng khớp thực tế có thể thay đổi.'
        : 'Chưa đủ 20 phiên có dữ liệu và khối lượng bình quân dương để ước lượng số phiên thoát vị thế.']};
    }
    const symbol=q.get('symbol')?.trim().toUpperCase();
    let rows=[];
    const saved=path==='index' ? null : (await archiveCatalog())[symbol];
    const version=data.symbols[symbol]?.revision||data.updated_at;
    if(saved && !data.symbols[symbol]) {
      if(!series.has(symbol)) {
        if(series.size>=10) series.delete(series.keys().next().value);
        const request=fetch('/eod-archive/'+encodeURIComponent(symbol)+'.json').then(async response=>{
          if(!response.ok) throw Error('Không tải được chuỗi SSI từ kho lịch sử.');
          return (await response.json()).map(([date,open_vnd,high_vnd,low_vnd,close_vnd,volume_shares])=>
            ({symbol,date,open_vnd,high_vnd,low_vnd,close_vnd,volume_shares}));
        }).catch(error=>{series.delete(symbol);throw error;});
        series.set(symbol,{version,rows:request});
      }
      rows=await series.get(symbol).rows;
    }
    if(data.symbols[symbol]) {
      const cached=series.get(symbol);

      if(!cached || cached.version!==version) {
        if(series.size>=10) series.delete(series.keys().next().value);
        series.set(symbol,{version,rows:load('series',symbol).catch(()=>null)});
      }
      rows=await series.get(symbol).rows;
      if(!rows){series.delete(symbol);throw Error('Chuỗi SSI tạm thời chưa tải được.');}
    }
    if(path!=='index' && symbol && !data.symbols[symbol] && /^[A-Z0-9]{1,12}$/.test(symbol)) {
      const delta=await load('market-delta',symbol);
      if(delta?.rows?.length) {
        const merged=new Map(rows.map(row=>[row.date,row]));
        for(const [date,open_vnd,high_vnd,low_vnd,close_vnd,volume_shares] of delta.rows)
          merged.set(date,{symbol,date,open_vnd,high_vnd,low_vnd,close_vnd,volume_shares});
        rows=[...merged.values()].sort((a,b)=>a.date.localeCompare(b.date));
      }
    }
    if(path!=='index' && !data.symbols[symbol]) rows=enrichArchive(rows);
    const members=(await marketDirectory())?.index_memberships?.VN30||[];
    const lower=q.get('period')!=='recent'&&(symbol==='VN30'||members.includes(symbol)) ? '2000-07-28' : '2022-01-01';
    rows=rows.filter(row=>row.date>=lower);
    const filter=q.get('range');
    const end=filter==='CUSTOM' ? q.get('to') || last : rows.at(-1)?.date || last;
    rows=rows.filter(row=>row.date<=end&&row.date>=(filter==='CUSTOM' ? q.get('from') || first : first));
    const count={'1D':1,'5D':5,'1W':5,'1M':22,'3M':66,'6M':132,'1Y':264,'3Y':792,'5Y':1320}[filter];
    if(count) rows=rows.slice(-count);
    if(filter==='YTD'&&rows.length) rows=rows.filter(row=>row.date.slice(0,4)===rows.at(-1).date.slice(0,4));
    if(path==='index') return {source:'SSI FastConnect V3',rows:rows.map(row=>({
      tradingDate:row.date,indexValue:row.close_vnd,indexChangePercentage:row.return_pct}))};
    const resolution=q.get('resolution')||'1D', summary=rows.at(-1);
    const omitted=data.symbols[symbol]?.quarantined_dates?.length || 0;
    return {available:true,rows:aggregate(rows,resolution),summary,resolution,
      last_available_session:summary?.date,message:(data.symbols[symbol]||saved||summary)?null:'Mã này chưa có lịch sử SSI được nạp.',unit_status:'Đơn vị nguồn SSI'+(omitted ? ' · '+omitted+' phiên OHLCV bị cách ly' : '')};
  }
  function boardMatches(row, q, members) {
    const scope = 'INDEX:VN30';
    const search = (q.get('search') || '').trim().toLocaleLowerCase('vi');
    return (scope==='ALL' || row.board===scope || (scope.startsWith('INDEX:') && members[scope.slice(6)]?.includes(row.symbol)))
      && [row.symbol,row.symbolNameVi,row.symbolNameEn].some(value=>String(value||'').toLocaleLowerCase('vi').includes(search));
  }

  async function liveBoard(q) {
    const data=await load('live').catch(()=>null);
    const age=Date.now()-Date.parse(data?.updated_at);
    const active=age>=0&&age<=15000;
    const directory = await marketDirectory().catch(()=>null);
    const metadata = new Map((directory?.securities||[]).map(row=>[row.symbol,row]));
    const matching=(data?.rows||[]).map(row=>({...metadata.get(row.symbol), ...row}))
      .filter(row=>boardMatches(row,q,{VN30:data?.rows?.map(row=>row.symbol)||[]}));
    const size=Number(q.get('size'))||30,pages=Math.max(1,Math.ceil(matching.length/size));
    const page=Math.min(pages,Number(q.get('page'))||1);
    const levels=side=>side.map(([price,quantity])=>({price,quantity}));
    const rows=matching.slice((page-1)*size,page*size).map(row=>({...row,
      bids:active?levels(row.bids||[]):[],asks:active?levels(row.asks||[]):[],
      status:active&&row.status==='fresh_two_sided_quote'?'receiving':active&&row.status==='session_unverified'?'Chưa xác minh phiên':'stale',
      trade_status:freshTime(row.trade_time)?'receiving':'stale',
      received_at:data.updated_at}));
    return {mode:'DATA',rows,page,pages,total:matching.length,catalog_total:data?.rows?.length||0,
      display_note:active?'SSI DATA · Snapshot '+data.updated_at:data?'Snapshot SSI cũ · '+data.updated_at:'Chưa có snapshot SSI trong phiên.',
      units_note:'Giữ đơn vị nguồn SSI.',view_note:'Danh sách mã do collector theo dõi.'};
  }

  function freshTime(value) {
    const age=Date.now()-Date.parse(value);
    return age>=0&&age<=30000;
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
        spread_vnd_per_share:stats['Spread (VND/cổ phiếu)'], spread_bps:stats['Spread (bps)'], imbalance:stats.Imbalance,
        levels:{bid:book.bids.length,ask:book.asks.length}};
    }
    const endpoint=path.split('/').at(-1);
    if(endpoint==='book') {
      const symbol=q.get('symbol');
      const snapshot=await load('live',symbol);
      const row=snapshot?.rows?.find(row=>row.symbol===symbol);
      const current=freshTime(snapshot?.updated_at)&&freshTime(row?.quote_time)&&row?.bids?.length&&row?.asks?.length;
      if (current && row.status==='fresh_two_sided_quote' && row.metrics?.available) return row.metrics;
      const quote=current ? row : snapshot?.last_books?.[symbol];
      if (quote) {
        return {symbol, available:false, status:current?'Báo giá trong phiên':'Bản chụp đã lưu',
          reason:current?'Báo giá gốc SSI. Chỉ báo cần xác minh phiên và đơn vị.':`Bản chụp SSI ${quote.capture_session==='morning'?'phiên sáng':quote.capture_session==='afternoon'?'phiên chiều':'gần nhất'}. Xem thời gian nguồn bên dưới.`,
          unverified_levels:{bids:quote.bids,asks:quote.asks},event_time:quote.quote_time,
          received_at:quote.received_at||snapshot.updated_at,session:quote.session};
      }
      return {symbol, available:false,status:snapshot?'stale':'unavailable',
        reason:snapshot?'Chưa có báo giá SSI mới đủ điều kiện cho mã này.':'Chưa có snapshot sổ lệnh SSI được công bố.'};
    }
    if(endpoint==='rankings' && q.get('metric')==='volume' && ['ALL','HOSE','INDEX:VN30'].includes(q.get('scope'))) {
      const snapshot=await load('live');
      if (freshTime(snapshot?.updated_at)) {
        const day=snapshot.updated_at.slice(0,10);
        const rows=(snapshot.rows||[]).filter(row=>row.trade_time?.startsWith(day) &&
          row.total_volume!=null && row.total_volume!=='' && Number.isFinite(Number(row.total_volume)) && Number(row.total_volume)>=0)
          .sort((a,b)=>Number(b.total_volume)-Number(a.total_volume))
          .map(row=>({symbol:row.symbol,volume_shares:row.total_volume}));
        if(rows.length>=2) return {available:true,rows,asof:snapshot.updated_at,
          label:`SSI trong phiên · ${rows.length}/${snapshot.rows.length} mã VN30 · ${snapshot.updated_at.slice(0,19).replace('T',' ')} ICT`};
      }
      const [intraday,directory]=await Promise.all([load('intraday').catch(()=>null),marketDirectory().catch(()=>null)]);
      const members=directory?.index_memberships?.VN30||[];
      const covered=members.map(symbol=>({symbol,...intraday?.coverage?.[symbol]}))
        .filter(row=>row.last&&row.session_volume!=null && Number.isFinite(Number(row.session_volume)));
      const last=covered.map(row=>row.last).sort().at(-1);
      const rows=covered.filter(row=>row.last===last).sort((a,b)=>Number(b.session_volume)-Number(a.session_volume))
        .map(row=>({symbol:row.symbol,volume_shares:row.session_volume}));
      if(rows.length>=2) return {available:true,rows,asof:last,
        label:`SSI OHLCV nội phiên · ${rows.length}/${members.length} mã VN30 cùng mốc ${last.slice(0,16).replace('T',' ')} ICT · KL quan sát trong khớp liên tục`};
    }
    if(endpoint==='board'&&q.get('mode')==='DATA') return liveBoard(q);
    if(endpoint==='intraday') {
      const snapshot=await load('intraday',q.get('symbol'),q.get('resolution'));
      const rows=snapshot?.rows||[];
      return {rows,last_source_time:rows.at(-1)?.closed_at,retrieved_at:snapshot?.updated_at,
        status:rows.length?'SSI · Nến đã đóng':'Chưa có nến SSI cho mã này'};
    }
    const published=await catalog();
    if(published&&['meta','catalog','series','index','insights'].includes(endpoint))
      return historyResponse(endpoint,q,published);

    const closing=published ? Object.entries(published.symbols)
      .filter(([symbol])=>!published.indexes.includes(symbol)).map(([,entry])=>entry.close) : [];
    const latest=published ? closing.map(row=>row.date).sort().at(-1) : null;
    if(endpoint==='rankings'&&q.get('metric')==='volume'&&published&&['ALL','HOSE','INDEX:VN30'].includes(q.get('scope'))) {
      const directory=await marketDirectory();
      const members=new Set(directory?.index_memberships?.VN30||[]);
      const matching=closing.filter(row=>members.has(row.symbol)&&row.date===latest&&
        row.volume!=null&&Number.isFinite(Number(row.volume)));
      const rows=matching.sort((a,b)=>Number(b.volume)-Number(a.volume))
        .map(row=>({symbol:row.symbol,volume_shares:row.volume}));
      return {available:rows.length>=2,rows,
        label:`SSI EOD · ${rows.length}/${members.size} mã VN30 · phiên ${latest}`,
        message:'Chưa đủ mã VN30 cùng ngày để xếp hạng.'};
    }
    if (path === '/api/market/status') return {
      status:'SSI · Trong phiên và cuối ngày', snapshot_asof:latest,
      disabled_reason:'Ngày EOD là ngày có giá đóng cửa gần nhất.',
      measurement_reason:'Trang Sổ lệnh hiển thị báo giá SSI và thời gian nguồn.',
      last_snapshot_at:(await load('live').catch(()=>null))?.updated_at
    };
    if(endpoint==='meta') return {available:false,issues:['Chưa có lịch sử SSI được công bố.']};
    if(endpoint==='coverage'||endpoint==='rankings') throw Error('Chưa có phạm vi thị trường đã xác minh.');
    if (endpoint==='depth-warning') {
      const symbol=q.get('symbol');
      const live=await load('live');
      const row=live?.rows?.find(row=>row.symbol===symbol);
      return {symbol,state:'Chưa đánh giá',valid_samples:0,samples:0,reason:row
        ? 'Web có bản chụp sổ lệnh. Phép kiểm tra 60 giây cần chuỗi mẫu liên tục và đơn vị SSI đã xác minh.'
        : 'Chưa có mẫu sổ lệnh đã công bố cho mã này. Phép kiểm tra 60 giây cần chuỗi mẫu liên tục và đơn vị SSI đã xác minh.'};
    }
    if(published && ['alerts','event-evidence'].includes(endpoint)) {
      const symbol=q.get('symbol');
      if(!symbol) return {status:'unavailable',rows:[]};
      const date=q.get('date');
      const to=date||q.get('to')||latest;
      const params=new URLSearchParams({symbol,range:'CUSTOM',resolution:'1D',period:q.get('period')||'recent',to});
      const series=await historyResponse('series',params,published);
      const finite=row=>row.relative_volume20!=null&&Number.isFinite(Number(row.relative_volume20));
      if(endpoint==='event-evidence') {
        const row=series.rows.at(-1);
        if(row?.date!==date || !finite(row)) throw Error('Chưa có bằng chứng RV20 cho phiên đã chọn.');
        return {event_date_exact:true,facts:{symbol,date,rv20:row.relative_volume20},
          context:series.rows.slice(-30),method:'SSI EOD / TB20 phiên trước',
          paragraphs:['RV20 đo khối lượng tương đối của phiên.']};
      }
      let selected=series.rows.filter(row=>!q.get('from')||row.date>=q.get('from'));
      if(!q.get('from')&&!q.get('to')) selected=selected.slice(-22);
      const eligible=selected.filter(finite);
      return {status:'evaluated',evaluated_observations:eligible.length,
        first_session:selected[0]?.date,last_session:selected.at(-1)?.date,
        rows:eligible.filter(row=>Number(row.relative_volume20)>=2).reverse().map(row=>({
          symbol,timestamp:row.date,value:row.relative_volume20,volume:row.volume_shares,
          baseline:row.volume_avg20_previous,threshold:Number(row.relative_volume20)>=3?3:2,
          priority:Number(row.relative_volume20)>=3?'cao':'theo_doi'}))};
    }
    if(endpoint==='alerts') return {status:'unavailable',rows:[]};
    if (path === '/api/market/research') return {status:'Chờ kiểm chứng',h1:'NOT_TESTED',recorded_days:[],counts:{}};
    if (path === '/api/market/board') {
      const directory = published ? await historyResponse('catalog',q,published) : {securities:[],index_memberships:{}};
      const saved = await archiveCatalog();
      const prices = new Map(closing.map(row=>[row.symbol,row]));
      const matching = directory.securities.filter(row=>boardMatches(row,q,directory.index_memberships))
        .sort((a,b)=>a.symbol.localeCompare(b.symbol));
      const size = Math.min(50,Math.max(1,Number(q.get('size'))||30));
      const pages = Math.max(1,Math.ceil(matching.length / size));
      const page = Math.max(1,Math.min(pages,Number(q.get('page'))||1));
      const boardRows = await Promise.all(matching.slice((page-1)*size,page*size).map(async ({symbol,board,symbolNameVi,stockType})=>{
        let row = prices.get(symbol);
        if (!row) {
          const delta = await load('market-delta',symbol).catch(()=>null);
          let last = delta?.rows?.at(-1);
          if (!last && saved[symbol]) {
            const response = await fetch('/eod-archive/'+encodeURIComponent(symbol)+'.json');
            if(response.ok) last=(await response.json()).at(-1);
          }
          if(last) {
            const [date,,high,low,close,volume]=last;
            row={date,high,low,close,volume};
          }
        }
        return {symbol,board,name:symbolNameVi,stock_type:stockType,topic_supported:true,bids:[],asks:[],last_price:row?.close,high:row?.high,low:row?.low,
          total_volume:row?.volume,session:row?'EOD '+row.date:'Chưa có EOD',status:'eod',trade_status:'eod'};
      }));
      return {mode:'EOD',rows:boardRows,page,pages,total:matching.length,catalog_total:directory.securities.length,
        units_note:published ? 'Giá và khối lượng theo đơn vị nguồn SSI.' : 'Chưa có dữ liệu SSI.',
        view_note:'Bản web hiển thị các mã có trong snapshot.',
        display_note:published ? 'Giá đóng cửa SSI · Ngày ghi ở mỗi mã.' : 'Chưa có bảng giá SSI được công bố.'};
    }
    throw Error(unavailable);
  }
  return {request};
})();
