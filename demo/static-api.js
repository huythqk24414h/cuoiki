'use strict';
window.StaticLiquidity = (() => {
  const snapshot = fetch('/prices.json', {cache:'no-cache'}).then(response => {
    if (!response.ok) throw Error('Không tải được bảng giá.');
    return response.json();
  });
  const unavailable = 'Tính năng này cần dữ liệu SSI trong ứng dụng chạy trên máy.';
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
    const data = await snapshot;
    const real = data.source === 'SSI FastConnect';
    const latest = real ? data.rows.map(row=>row.date).sort().at(-1) : null;
    if (path === '/api/market/status') return {
      status:'Bản web EOD', snapshot_asof:latest,
      disabled_reason:'Bản web sử dụng bảng giá đóng cửa do GitHub Actions cập nhật.',
      measurement_reason:'Dữ liệu sổ lệnh trong phiên xem trên ứng dụng chạy trên máy.'
    };
    if (path === '/api/market/meta') return {available:false,issues:['Bản web có bảng giá đóng cửa tại tab Sổ lệnh. Chuỗi lịch sử và chỉ số thị trường nằm trong ứng dụng chạy trên máy.']};
    if (path === '/api/market/alerts') return {status:'unavailable',rows:[]};
    if (path === '/api/market/research') return {status:'Chờ kiểm chứng',h1:'NOT_TESTED',recorded_days:[],counts:{}};
    if (path === '/api/market/board') {
      const matching = data.rows.filter(row=>row.symbol.includes((q.get('search') || '').trim().toUpperCase()));
      const size = Number(q.get('size')) || 30;
      const pages = Math.max(1,Math.ceil(matching.length / size));
      const page = Math.min(pages,Number(q.get('page')) || 1);
      const rows = matching.slice((page-1)*size,page*size).map(row=>({
        symbol:row.symbol, bids:[], asks:[], last_price:row.close, high:row.high,low:row.low,
        total_volume:row.volume, session:real ? 'EOD '+row.date : 'Mô phỏng', status:'eod', trade_status:'eod'
      }));
      return {mode:'EOD',rows,page,pages,total:matching.length,catalog_total:data.rows.length,
        units_note:real ? 'Giá và khối lượng theo đơn vị nguồn SSI.' : 'Dữ liệu mô phỏng.',
        view_note:'Bản web hiển thị các mã có trong snapshot.',
        display_note:real ? 'Giá đóng cửa SSI · Ngày ghi ở mỗi mã.' : 'Dữ liệu mô phỏng · Minh họa bảng giá.'};
    }
    throw Error(unavailable);
  }
  return {request};
})();
