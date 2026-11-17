const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const handle = require('../api/market-data.js');

test('catalog pagination, coverage, missing symbol, and Redis failure', async (t) => {
  const directory = Array.from({length:85}, (_,n)=>({symbol:'X'+n,board:n<80?'HOSE':'HNX'}));
  const db = {
    catalog:{securities:directory,index_memberships:{VN30:['X1']}},
    history:{indexes:[],symbols:{X1:{last:'2026-11-13'}}},
    'intraday-coverage':{symbols:{X1:{last:'2026-11-13T14:30:00+07:00'}}},
    'intraday:X1':{candles:{'15m':[]}},
  };
  const oldUrl = process.env.UPSTASH_REDIS_REST_URL, oldToken = process.env.UPSTASH_REDIS_REST_TOKEN;
  process.env.UPSTASH_REDIS_REST_URL = 'https://redis.test';
  process.env.UPSTASH_REDIS_REST_TOKEN = 'test';
  t.after(() => {
    if (oldUrl === undefined) delete process.env.UPSTASH_REDIS_REST_URL;
    else process.env.UPSTASH_REDIS_REST_URL = oldUrl;
    if (oldToken === undefined) delete process.env.UPSTASH_REDIS_REST_TOKEN;
    else process.env.UPSTASH_REDIS_REST_TOKEN = oldToken;
  });
  const store = t.mock.method(globalThis,'fetch', async (_, opts)=>{
    const key = JSON.parse(opts.body)[1].slice('liquiditylab:'.length);
    return {ok:true,json:async()=>({result:db[key] ? JSON.stringify(db[key]) : null})};
  });
  async function get(query) {
    const res = {setHeader(){},status(code){this.code=code;return this;},
      json(body){return [this.code,body];}};
    return handle({method:'GET',query},res);
  }
  const [code, page] = await get({kind:'catalog',board:'HOSE',page:'2',size:'25'});
  assert.equal(code,200);
  assert.equal(page.total,80);
  assert.equal(page.securities[0].symbol,'X25');
  const [,member] = await get({kind:'catalog',board:'VN30'});
  assert.equal(member.securities[0].daily_last,'2026-11-13');
  assert.ok(member.securities[0].intraday_last);
  assert.equal((await get({kind:'series',symbol:'X2'}))[0],404);
  assert.equal((await get({kind:'series',symbol:'X1'}))[0],502);
  assert.deepEqual(await get({kind:'intraday',symbol:'X1',resolution:'15m'}),[200,{rows:[]}]);
  assert.equal((await get({kind:'catalog',size:'500'}))[0],400);
  const morningBook = {quote_time:'2026-11-16T11:29:00+07:00',bids:[[30,100]],asks:[[31,120]]};
  db['book-morning'] = {last_books:{X1:morningBook}};
  db.live = {updated_at:new Date().toISOString(),rows:[{symbol:'X1',status:'no_quote'}]};
  const [, withMorning] = await get({kind:'live',symbol:'X1'});
  assert.deepEqual(withMorning.last_books.X1,morningBook);
  assert.equal(withMorning.rows[0].status,'no_quote');
  const afternoonBook = {...morningBook,quote_time:'2026-11-16T14:29:00+07:00'};
  db['book-afternoon'] = {last_books:{X1:afternoonBook}};
  db.live.updated_at = '2026-11-16T14:30:00+07:00';
  const [, withAfternoon] = await get({kind:'live',symbol:'X1'});
  assert.deepEqual(withAfternoon.last_books.X1,afternoonBook);
  store.mock.mockImplementation(async (_,opts)=>{
    const key=JSON.parse(opts.body)[1];
    return key==='liquiditylab:live'?{ok:false}:
      {ok:true,json:async()=>({result:key.endsWith('book-afternoon')?JSON.stringify(db['book-afternoon']):null})};
  });
  const [archiveCode, archived] = await get({kind:'live'});
  assert.equal(archiveCode,200);
  assert.deepEqual(archived.last_books.X1,afternoonBook);
  store.mock.mockImplementation(async()=>({ok:false}));
  assert.equal((await get({kind:'catalog'}))[0],502);
});

test('production board keeps the last two-sided quote across missing and older snapshots', async () => {
  const time = new Date().toISOString();
  const original = {symbol:'ACB',quote_time:time,bids:[[20,100],[19,100],[18,100]],asks:[[21,200],[22,200],[23,200]]};
  let snapshot = {updated_at:time,rows:[original]};
  const window = {};
  runInNewContext(readFileSync(require.resolve('../demo/static-api.js'),'utf8'),{
    window, URLSearchParams, fetch:async url=>({
      ok:snapshot!==null, status:snapshot===null?502:200,
      json:async()=>url.includes('kind=live')?snapshot:{},
    }),
  });
  const read=()=>window.StaticLiquidity.request(new URL('https://example.test/api/market/board?mode=DATA'));
  assert.equal((await read()).rows[0].bids[0].price,20);
  snapshot={updated_at:time,rows:[{...original,bids:[[20,999],[19,100]]}],last_books:{
    ACB:{...original,quote_time:'2026-11-16T11:00:00+07:00',bids:[[19,90]]},
  }};
  const saved=(await read()).rows[0];
  assert.equal(saved.bids[0].price,20);
  assert.equal(saved.status,'Bản chụp đã lưu');
  assert.equal(saved.received_at,time);
  const detail=await window.StaticLiquidity.request(new URL('https://example.test/api/market/book?symbol=ACB'));
  assert.equal(detail.snapshot_metrics.bid,5700);
  assert.equal(detail.snapshot_metrics.ask,13200);
  assert.equal(detail.available,false);
  snapshot=null;
  await assert.rejects(read,/tạm thời không truy cập/);
});

test('chart frames aggregate genuine candles without bridging lunch or filling gaps', () => {
  const window={addEventListener(){}};
  runInNewContext(readFileSync(require.resolve('../web/chart-kit.js'),'utf8'),{
    window, document:{documentElement:{}}, MutationObserver:class{observe(){}},
  });
  const kit=window.ChartKit;
  const bar=(time,open=10,close=12)=>({
    timestamp:`2026-11-17T${time}:00+07:00`,open,high:13,low:9,close,volume:100,
  });
  const rows=[bar('09:15'),bar('09:30',12,11),bar('10:00'),bar('11:15'),bar('13:00'),bar('13:15')];
  const grouped=kit.intradayRows(rows,'30m','VNINDEX');
  assert.equal(grouped.length,3);
  assert.equal(grouped[0].date,'2026-11-17T09:15:00+07:00');
  assert.equal(grouped[0].close_vnd,11);
  assert.equal(grouped[0].volume_shares,200);
  assert.equal(grouped[1].date,'2026-11-17T11:15:00+07:00');
  assert.equal(grouped[1].volume_shares,100);
  assert.equal(grouped[2].date,'2026-11-17T13:00:00+07:00');
  assert.equal(kit.intradayRows(rows,'2h','VNINDEX').length,1);
  const year=kit.dailyRows([{date:'2026-10-31',close_vnd:'10'},{date:'2026-11-17',close_vnd:'11'}],'1Y');
  assert.equal(year[0].close_vnd,'11');
  assert.equal(year[0].open_vnd,null);
  assert.equal(year[0].volume_shares,null);
  const past=[{date:'2026-11-16',open_vnd:8,high_vnd:12,low_vnd:7,close_vnd:10,volume_shares:400}];
  const minuteBars=[{...bar('09:15'),closed_at:'2026-11-17T09:30:00+07:00'},
    {...bar('09:30',12,11),closed_at:'2026-11-17T09:45:00+07:00'}];
  const provisional=kit.withOpenDay(past,minuteBars,'VNINDEX',null,'2026-11-17');
  assert.equal(provisional[1].date,'2026-11-17');
  assert.equal(provisional[1].provisional,true);
  assert.equal(provisional[1].volume_shares,200);
  const week=kit.dailyRows(provisional,'1W');
  assert.equal(week.length,1);
  assert.equal(week[0].open_vnd,8);
  assert.equal(week[0].close_vnd,11);
  assert.equal(week[0].volume_shares,600);
  assert.equal(week[0].provisional,true);
  assert.equal(kit.withOpenDay(past,minuteBars,'VNINDEX','2026-11-16','2026-11-17').length,1);
  assert.equal(kit.withOpenDay(provisional,minuteBars,'VNINDEX',null,'2026-11-17').length,2);
});

test('the financial chart tooltip keeps full SSI data in all display modes', () => {
  const window={addEventListener(){}};
  runInNewContext(readFileSync(require.resolve('../web/chart-kit.js'),'utf8'),{
    window, document:{documentElement:{}}, MutationObserver:class{observe(){}},
  });
  const rows=[{symbol:'LPB',date:'2026-11-17',closed_at:'2026-11-17T11:00:00+07:00',
    open_vnd:37200,high_vnd:37250,low_vnd:37150,close_vnd:37200,volume_shares:59100,provisional:true}];
  for(const type of ['candlestick','hollow','bar','line','area','baseline']){
    let options;
    const chart={setOption(value){options=value;},resize(){}};
    window.ChartKit.drawFinancial(chart,rows,{type,zoom:{start:25,end:100}});
    assert.equal(options.tooltip.trigger,'axis');
    const tooltip=options.tooltip.formatter([{dataIndex:0}]);
    assert.match(tooltip,/LPB · 2026-11-17 11:00/);
    assert.match(tooltip,/Kỳ đang mở/);
    for(const label of ['Mở cửa','Cao nhất','Thấp nhất','Đóng cửa','Khối lượng'])assert.ok(tooltip.includes(label));
    assert.equal(options.series[1].data[0],59100);
    assert.equal(options.dataZoom[1].start,25);
  }
});

test('analysis preview adds source value and partial metrics without changing official EOD', async () => {
  const day=offset=>new Date(Date.now()+7*3600000+offset*86400000).toISOString().slice(0,10);
  const history=Array.from({length:20},(_,i)=>({symbol:'LPB',date:day(i-20),close_vnd:100,volume_shares:50,source_value_vnd:5000}));
  const today=day(0);
  const bars=[0,1].map(i=>({timestamp:today+`T09:${i?'30':'15'}:00+07:00`,
    closed_at:today+`T09:${i?'45':'30'}:00+07:00`,open:100,high:111,low:98,close:110,volume:25,source_value:500}));
  const window={};
  runInNewContext(readFileSync(require.resolve('../demo/static-api.js'),'utf8'),{window,URLSearchParams,
    fetch:async path=>{
      const kind=new URL(path,'https://test.invalid').searchParams.get('kind');
      const data={history:{indexes:[],symbols:{LPB:{first:day(-20),last:day(-1)}}},series:history,
        catalog:{index_memberships:{VN30:['LPB']}},intraday:{rows:bars}}[kind]||{};
      return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data};
    }});
  const read=query=>window.StaticLiquidity.request(new URL('/api/market/series?symbol=LPB&range=1D&'+query,'https://test.invalid'));
  const official=await read('resolution=1D');
  const preview=await read('resolution=1D&preview=1');
  assert.equal(official.summary.date,day(-1));
  assert.equal(preview.rows.length,1);
  assert.equal(preview.open_session.date,today);
  assert.equal(preview.open_session.provisional,true);
  assert.equal(preview.open_session.relative_volume20,1);
  assert.equal(preview.open_session.source_value_vnd,1000);
  assert.ok(Math.abs(preview.open_session.volatility20_pct-Math.sqrt(5))<1e-12);
  delete bars[1].source_value;
  assert.equal((await read('resolution=1D&preview=1')).open_session.source_value_vnd,null);
});
