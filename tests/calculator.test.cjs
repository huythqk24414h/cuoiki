'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {buildManualPayload,formatDecimal,cumulativeLevels,describeResult} = require('../web/calculator-core.js');
const now='2026-11-04T03:30:00.000Z';
const form = () => ({symbol:' TEST ',time:'2026-11-04T10:00',
  bids:[{price:'100',quantity:'20'},{price:'99',quantity:'10'},{price:'',quantity:''}],
  asks:[{price:'102',quantity:'10'},{price:'103',quantity:'20'},{price:'',quantity:''}]});

test('manual contract preserves decimal strings, metadata, Vietnam time and original input',()=>{
  const input=form(), original=JSON.stringify(input), payload=buildManualPayload(input,now);
  assert.equal(payload.symbol,'TEST');assert.equal(payload.event_time,'2026-11-04T10:00:00+07:00');
  assert.equal(payload.received_at,now);assert.equal(payload.source,'manual');
  assert.equal(payload.contract_version,'1.0');assert.equal(payload.price_unit,'VND');
  assert.deepEqual(payload.bids,[{price:'100',quantity:'20'},{price:'99',quantity:'10'}]);
  assert.equal(JSON.stringify(input),original);
  input.time='';assert.equal(buildManualPayload(input,now).event_time,now);
});

test('rejects partial rows, gaps and missing first level',()=>{
  for (const bids of [[{price:'100',quantity:''}], [{price:'',quantity:''}],
    [{price:'100',quantity:'20'},{price:'',quantity:''},{price:'99',quantity:'2'}]]) {
    assert.throws(()=>buildManualPayload({...form(),bids},now));
  }
});

test('explicit received time uses UTC+7 and rejects receive before event',()=>{
  const input={...form(),receivedTime:'2026-11-04T10:00:01'};
  assert.equal(buildManualPayload(input,now).received_at,'2026-11-04T10:00:01+07:00');
  assert.equal(buildManualPayload({...input,time:''},now).event_time,'2026-11-04T10:00:01+07:00');
  assert.throws(()=>buildManualPayload({...input,receivedTime:'2026-11-04T09:59'},now),/sau thời gian nhận/);
  assert.throws(()=>buildManualPayload({...input,receivedTime:'2026-02-29T10:00'},now),/không tồn tại/);
});

test('rejects ambiguous numbers, commas, negatives, zero and noninteger volumes',()=>{
  for (const value of ['1,000','-1','0','NaN','Infinity','1e3','abc','1000000000000000.1']) {
    const input=form();input.bids[0].price=value;
    assert.throws(()=>buildManualPayload(input,now),value);
  }
  const input=form();input.asks[0].quantity='1.1';assert.throws(()=>buildManualPayload(input,now));
  input.asks[0].quantity=' 002.00 ';assert.equal(buildManualPayload(input,now).asks[0].quantity,'2');
});

test('validates clock, leap day, future date and symbol',()=>{
  for (const time of ['2026-02-29T10:00','2026-11-04T25:00','2026-11-04T10:31','2026-11-04']) {
    assert.throws(()=>buildManualPayload({...form(),time},now));
  }
  assert.throws(()=>buildManualPayload(form(),'no-time'));
  assert.throws(()=>buildManualPayload({...form(),symbol:''},now));
});

test('formats decimal/exponent outputs with grouping and no Number precision loss',()=>{
  for (const [value, digits, expected] of [
    ['123456789012345678901234567890',4,'123.456.789.012.345.678.901.234.567.890'],
    ['1.234567890123456789e+20',4,'123.456.789.012.345.678.900'],
    ['-1.482701812191103789126853377E-2',6,'-0,014827'],
    ['1e-8',10,'0,00000001'],['-0.0000',4,'0'],['999.99995',4,'1.000'],
    ['2.5',0,'3'],['-2.5',0,'-3'],['0',4,'0'],['0.000049',4,'0'],
    ['NaN',4,'—'],['1,000',4,'—']]) {
    assert.equal(formatDecimal(value,digits),expected,value);
  }
});

test('cumulative graph values increase and match hand-computed input',()=>{
  const payload=buildManualPayload(form(),now), series=cumulativeLevels(payload);
  assert.deepEqual(series.bids.map(x=>x.cumulativeValue),[2000,2990]);
  assert.deepEqual(series.asks.map(x=>x.cumulativeValue),[1020,3080]);
  assert.equal(series.bids[1].price,99);
});

test('rule explanations use exact depth comparison and distinguish tiny sign from zero',()=>{
  const result={bid_depth_vnd:'100000000000000000000001',ask_depth_vnd:'100000000000000000000000',imbalance:'1e-40',spread_bps:'1.123456'};
  const descriptions=describeResult(result);
  assert.match(descriptions[0],/bên mua lớn hơn/);assert.match(descriptions[1],/dương/);
  assert.match(descriptions[2],/1,1235 bps/);assert.match(descriptions[3],/không bảo đảm khớp lệnh/);
  result.ask_depth_vnd=result.bid_depth_vnd;result.imbalance='0E-20';
  assert.match(describeResult(result)[0],/bằng nhau/);
  assert.match(describeResult(result)[1],/bằng 0/);
});
