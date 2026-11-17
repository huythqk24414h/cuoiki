
(async () => {
  const status = document.querySelector('#review-session');
  if (!status) return;
  status.textContent = 'Đang đọc dữ liệu SSI…';
  const control = document.querySelector('#review-export');
  control.disabled = true;
  const get = async query => {
    const res = await fetch('/api/market-data?' + query, {signal: AbortSignal.timeout(15000)});
    if (!res.ok) throw Error(String(res.status));
    return res.json();
  };
  const bookStatus = document.querySelector('#review-book');
  let checkingBook = false;
  async function refreshBook() {
    if (checkingBook || document.hidden || !['', '#monitor'].includes(location.hash)) return;
    checkingBook = true;
    try {
      const live = await get('kind=live');
      const isRecent = value => {
        const age = Date.now() - Date.parse(value);
        return age >= 0 && age <= 30000;
      };
      const fresh = isRecent(live.updated_at) ? (live.rows || []).filter(row =>
        isRecent(row.quote_time) && row.bids?.length && row.asks?.length) : [];
      const saved = Object.keys(live.last_books || {}).length;
      const trades = isRecent(live.updated_at) ? (live.rows || []).filter(row =>
        row.trade_time?.slice(0, 10) === live.updated_at.slice(0, 10) && row.total_volume != null) : [];
      bookStatus.textContent = 'SSI trong phiên · ' +
        (fresh.length ? fresh.length + ' mã có báo giá mua/bán mới' :
          saved ? saved + ' mã có bản chụp sổ lệnh đã lưu' : 'Đang chờ báo giá mua/bán') +
        (trades.length ? ' · ' + trades.length + ' mã có khối lượng khớp lũy kế' : '') +
        '. Xem giờ nguồn trong tab Sổ lệnh.';
    } catch (error) {
      bookStatus.textContent = error.message === '404' ? 'Chưa có sổ lệnh SSI được công bố.' :
        'Chưa kiểm tra được trạng thái sổ lệnh SSI.';
    } finally {
      checkingBook = false;
    }
  }
  refreshBook();
  setInterval(refreshBook, 15000);
  let data;
  try {
    const [catalog,history] = await Promise.all([get('kind=catalog'),get('kind=history')]);
    const members = [...new Set(catalog.index_memberships?.VN30 || [])];
    const session = members.map(s=>history.symbols[s]?.last).filter(Boolean).sort().at(-1);
    if (!session) throw Error('Missing session');
    const recent = {};
    let next = 0;
    await Promise.all(Array.from({length:5},async()=>{
      while(next<members.length){
        const symbol=members[next++];
        try { recent[symbol]=await get('kind=series&tail=21&symbol='+encodeURIComponent(symbol)); }
        catch { recent[symbol]=[]; }
      }
    }));
    data={members,session,recent};
    control.disabled=false;
  } catch {
    status.textContent='Chưa tải được bản tin SSI. Hãy tải lại trang để thử lại.';
    return;
  }
  const root = document.querySelector('#vn30-review');
  const body = root.querySelector('tbody');
  const detail = root.querySelector('dialog');
  const fmt = (value, digits = 0) => Number.isFinite(value)
    ? value.toLocaleString('vi-VN', {maximumFractionDigits: digits}) : '—';
  let records = [], selected = null;
  function cell(row, value) {
    const td = document.createElement('td');
    td.textContent = value;
    row.append(td);
    return td;
  }
  function draw() {
    const filtered = records.filter(r => r.symbol.includes(root.querySelector('input').value.trim().toUpperCase()));
    const sorted = filtered.sort((a,b) => (b.rv ?? -1) - (a.rv ?? -1) || a.symbol.localeCompare(b.symbol));
    body.replaceChildren();
    for (const r of sorted.slice(0, root.querySelector('select').value === '5' ? 5 : sorted.length)) {
      const tr = body.insertRow();
      cell(tr, r.symbol);
      cell(tr, r.latest?.date ?? '—');
      cell(tr, fmt(r.latest ? Number(r.latest.volume_shares) : NaN));
      cell(tr, fmt(r.rv, 4));
      cell(tr, r.rv == null ? 'Chưa đủ dữ liệu' : r.rv >= 3 ? 'Ưu tiên cao' : r.rv >= 2 ? 'Theo dõi' : 'Dưới ngưỡng');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button secondary';
      button.textContent = 'Xem bằng chứng';
      button.addEventListener('click', () => open(r));
      cell(tr, '').append(button);
    }
    root.querySelector('#review-matches').textContent = body.rows.length + '/' + sorted.length + ' mã khớp';
  }
  function open(r) {
    selected = r;
    const fields = {
      '#review-symbol': r.symbol + ' · Bằng chứng RV20',
      '#review-reason': r.rv == null ? 'Chưa đủ quan sát hợp lệ để tính RV20.' :
        'RV20 = ' + fmt(+r.latest.volume_shares) + ' / ' + fmt(r.avg,2) + ' = ' + fmt(r.rv,4) + ' lần.',
      '#review-source': 'Nguồn SSI EOD từ production. Phiên đánh giá ' + (data.session || '—') +
        '. Ngưỡng theo dõi ≥ 2 lần, ưu tiên cao ≥ 3 lần.',
    };
    for (const [selector, value] of Object.entries(fields)) detail.querySelector(selector).textContent = value;
    const tbody = detail.querySelector('tbody');
    tbody.replaceChildren();
    for (const row of [...r.prior, ...(r.latest ? [r.latest] : [])]) {
      const tr = tbody.insertRow();
      cell(tr, row.date);
      cell(tr, fmt(+row.volume_shares));
      cell(tr, row === r.latest ? 'Phiên đánh giá' : 'Cửa sổ tham chiếu');
    }
    detail.showModal();
  }
  root.querySelector('input').addEventListener('input',draw);
  root.querySelector('select').addEventListener('change',draw);
  detail.querySelector('#review-chart').addEventListener('click', () => {
    if (!selected) return;
    const select = document.querySelector('#symbol-filter');
    if (select && [...select.options].some(o=>o.value === selected.symbol)){
      select.value = selected.symbol;
      select.dispatchEvent(new Event('change',{bubbles:true}));
    } else {
      window.MarketState.set({symbol:selected.symbol});
    }
    detail.close();
    location.hash = '#analysis';
  });
  root.querySelector('#review-export').addEventListener('click', () => {
    const csv = ['symbol,session,volume_source,mean_previous_20,rv20',
      ...records.map(r => [r.symbol,r.latest?.date ?? '',r.latest?.volume_shares ?? '',r.avg ?? '',r.rv ?? ''].join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));
    const link = document.createElement('a');
    link.href=url; link.download='liquiditylab-vn30-'+data.session+'.csv'; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  function evaluate(symbol, rows, session) {
    const index = rows.findIndex(r => r.date === session);
    const latest = rows[index];
    const prior = index >= 0 ? rows.slice(Math.max(0,index-20),index) : [];
    const valid = row => row?.volume_shares != null && row.volume_shares !== '' &&
      Number.isFinite(Number(row.volume_shares)) && Number(row.volume_shares) >= 0;
    const avg = prior.length === 20 && prior.every(valid)
      ? prior.reduce((sum,r)=>sum+Number(r.volume_shares),0)/20 : null;
    const rv = avg > 0 && valid(latest) ? Number(latest.volume_shares)/avg : null;
    return {symbol,latest,prior,avg,rv};
  }

  records = data.members.map(symbol=>evaluate(symbol,data.recent[symbol]||[],data.session));
  const eligible = records.filter(r=>r.rv!=null);
  const alerts = eligible.filter(r=>r.rv>=2).sort((a,b)=>b.rv-a.rv||a.symbol.localeCompare(b.symbol));
  root.querySelector('#review-session').textContent = 'SSI EOD · Phiên '+data.session;
  root.querySelector('#review-coverage').textContent = records.filter(r=>r.latest).length+'/'+data.members.length+
    ' mã có dữ liệu phiên này. '+eligible.length+' mã đủ điều kiện tính RV20.';
  root.querySelector('#review-alerts').textContent = eligible.length
    ? alerts.length+'/'+eligible.length+' mã đạt ngưỡng RV20 ≥ 2'+(alerts.length ? '. Cao nhất: '+alerts.slice(0,3).map(r=>r.symbol+' '+fmt(r.rv,2)+'×').join(', ')+'.' : '.')
    : 'Chưa đủ dữ liệu để đánh giá RV20.';
  draw();
})();
