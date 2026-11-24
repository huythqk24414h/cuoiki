const test = require('node:test');
const assert = require('node:assert/strict');
const {simulateSweep} = require('../web/calculator-core.js');
const book = {
  bids: [{price:'100', quantity:'20'}, {price:'99', quantity:'10'}, {price:'98', quantity:'1'}],
  asks: [{price:'102', quantity:'10'}, {price:'103', quantity:'20'}, {price:'104', quantity:'1'}],
};

test('sweep uses the opposite side and consumes best prices first', () => {
  const buy = simulateSweep(book, 'buy', 15);
  assert.equal(buy.vwap, 1535 / 15);
  assert.equal(buy.slippageBps, (1535 / 15 - 101) / 101 * 10000);
  assert.equal(buy.fillRatio, 1);
  const sell = simulateSweep(book, 'sell', 25);
  assert.equal(sell.vwap, 2495 / 25);
  assert.equal(sell.slippageBps, (101 - 2495 / 25) / 101 * 10000);
});

test('shortfall preserves the filled fraction and suppresses full-order slippage', () => {
  const result = simulateSweep(book, 'buy', 40);
  assert.deepEqual(result, {requested:40, filled:31, remaining:9, vwap:3184/31, slippageBps:null, fillRatio:31/40});
  assert.throws(() => simulateSweep(book, 'buy', .5));
});
