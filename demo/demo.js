'use strict';
const calculator = window.LiquidityCalculator;
const levels = document.querySelector('#levels');
for (const [side, title, initialPrice] of [['bids', 'Bên mua', 24950], ['asks', 'Bên bán', 25000]]) {
  const group = document.createElement('fieldset');
  group.innerHTML = '<legend>' + title + '</legend>';
  for (let index = 1; index <= 3; index++) {
    const row = document.createElement('div');
    row.className = 'level';
    const price = index === 1 ? initialPrice : '';
    const quantity = index === 1 ? 1000 : '';
    row.innerHTML = `<label>Giá ${index}<input name="${side}-p${index}" inputmode="decimal" value="${price}"></label>
      <label>KL ${index}<input name="${side}-q${index}" inputmode="numeric" value="${quantity}"></label>`;
    group.append(row);
  }
  levels.append(group);
}

function renderPrices(snapshot) {
  const rows = snapshot.rows.map(row => {
    const tr = document.createElement('tr');
    for (const value of [row.symbol, row.date, ...['close', 'high', 'low', 'volume'].map(key => calculator.formatDecimal(row[key], 4))]) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.append(td);
    }
    return tr;
  });
  document.querySelector('#prices-body').replaceChildren(...rows);
  document.querySelector('#price-status').textContent = snapshot.source === 'SSI FastConnect'
    ? 'SSI FastConnect · Giá/khối lượng theo đơn vị nguồn · Cập nhật ' + new Date(snapshot.updated_at).toLocaleString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'}) + ' (UTC+7)'
    : 'Dữ liệu mô phỏng · Minh họa giao diện và không phản ánh giá thị trường.';
}
fetch('./prices.json', {cache:'no-cache'}).then(response => {
  if (!response.ok) throw Error('Snapshot unavailable');
  return response.json();
}).then(renderPrices).catch(() => {
  document.querySelector('#price-status').textContent = 'Chưa tải được bản giá. Hãy tải lại trang.';
});

document.querySelector('#book-form').addEventListener('submit', event => {
  event.preventDefault();
  const fields = new FormData(event.currentTarget);
  const result = document.querySelector('#results');
  const error = document.querySelector('#book-error');
  result.replaceChildren();
  error.textContent = '';
  try {
    const form = {symbol: fields.get('symbol')};
    for (const side of ['bids', 'asks']) {
      form[side] = [1, 2, 3].map(i => ({price: fields.get(side + '-p' + i), quantity: fields.get(side + '-q' + i)}));
    }
    const data = calculator.buildManualPayload(form, new Date().toISOString());
    const stats = calculator.calculateManual(data);
    for (const [label, value] of Object.entries(stats)) {
      const item = document.createElement('div');
      const term = document.createElement('dt');
      const definition = document.createElement('dd');
      term.textContent = label;
      definition.textContent = calculator.formatDecimal(value, 4);
      item.append(term, definition);
      result.append(item);
    }
  } catch (problem) {
    error.textContent = problem.message;
  }
});
