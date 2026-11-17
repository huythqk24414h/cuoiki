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
  snapshot=null;
  await assert.rejects(read,/tạm thời không truy cập/);
});
