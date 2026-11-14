/* Pure manual-entry helpers; all authoritative finance calculations remain in Python. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LiquidityCalculator = factory();
}(typeof window !== 'undefined' ? window : this, function () {
  'use strict';
  function decimalParts(value) {
    const text = String(value).trim();
    const match = /^([+-]?)(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/.exec(text);
    if (!match || text.length > 2048) throw new Error('Số thập phân không hợp lệ.');
    const exponent = Number(match[3] || 0);
    if (!Number.isInteger(exponent) || Math.abs(exponent) > 1000) throw new Error('Số vượt giới hạn hiển thị.');
    const [whole, fraction = ''] = match[2].split('.');
    const digits = whole + fraction;
    const point = whole.length + exponent;
    let integer, decimals;
    if (point <= 0) { integer = '0'; decimals = '0'.repeat(-point) + digits; }
    else if (point >= digits.length) { integer = digits + '0'.repeat(point - digits.length); decimals = ''; }
    else { integer = digits.slice(0, point); decimals = digits.slice(point); }
    integer = integer.replace(/^0+(?=\d)/, '') || '0';
    decimals = decimals.replace(/0+$/, '');
    return {negative:match[1] === '-' && (integer !== '0' || decimals !== ''), integer, fraction:decimals};
  }

  function formatDecimal(value, maxDigits = 4) {
    if (!Number.isInteger(maxDigits) || maxDigits < 0 || maxDigits > 20) throw new Error('Số chữ số hiển thị phải từ 0 đến 20.');
    let parts;
    try { parts = decimalParts(value); } catch (_) { return '—'; }
    let {integer, fraction} = parts;
    if (fraction.length > maxDigits) {
      const scaled = integer + fraction.slice(0, maxDigits).padEnd(maxDigits, '0');
      let rounded = (BigInt(scaled) + (fraction[maxDigits] >= '5' ? 1n : 0n)).toString().padStart(maxDigits + 1, '0');
      integer = maxDigits ? rounded.slice(0, -maxDigits) : rounded;
      fraction = maxDigits ? rounded.slice(-maxDigits) : '';
    }
    fraction = fraction.replace(/0+$/, '');
    const sign = parts.negative && (integer !== '0' || fraction !== '') ? '-' : '';
    const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return sign + grouped + (fraction ? ',' + fraction : '');
  }

  function positiveInput(value, description, integerOnly = false) {
    const text = typeof value === 'string' ? value.trim() : typeof value === 'number' ? String(value) : '';
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) throw new Error(`${description}: dùng số dương, dấu chấm thập phân; không dùng dấu phẩy hoặc ký hiệu phân cách.`);
    const parts = decimalParts(text);
    if (parts.integer === '0' && !parts.fraction) throw new Error(`${description}: cần số lớn hơn 0.`);
    if (parts.integer.length > 16 || (parts.integer.length === 16 && (parts.integer > '1000000000000000' || parts.fraction))) throw new Error(`${description}: số không được vượt 10^15.`);
    if (integerOnly && parts.fraction) throw new Error(`${description}: khối lượng phải là số nguyên dương.`);
    return parts.integer + (parts.fraction ? '.' + parts.fraction : '');
  }

  function buildManualPayload(form, nowISO) {
    if (!form || typeof form !== 'object') throw new Error('Cần dữ liệu nhập tay.');
    const symbol = String(form.symbol || '').trim().toUpperCase();
    if (!symbol || symbol.length > 20) throw new Error('Nhập mã từ 1 đến 20 ký tự.');
    if (typeof nowISO !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(nowISO) || !Number.isFinite(Date.parse(nowISO))) throw new Error('Thời gian nhận chưa hợp lệ.');
    function vietnamTime(value, label) {
      const time = String(value || '').trim();
      if (!time) return null;
      const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(time);
      if (!match) throw new Error(`${label} phải là ngày giờ Việt Nam hợp lệ.`);
      const [year, month, day, hour, minute, second] = match.slice(1).map((v, i) => Number(v || (i === 5 ? 0 : v)));
      const checked = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
      if (checked.getUTCFullYear() !== year || checked.getUTCMonth() !== month - 1 || checked.getUTCDate() !== day || checked.getUTCHours() !== hour || checked.getUTCMinutes() !== minute || checked.getUTCSeconds() !== second) throw new Error(`${label}: ngày giờ không tồn tại.`);
      return `${time.length === 16 ? time + ':00' : time}+07:00`;
    }
    const receivedTime = vietnamTime(form.receivedTime, 'Thời gian nhận') || nowISO;
    const eventTime = vietnamTime(form.time, 'Thời gian nguồn') || receivedTime;
    if (Date.parse(eventTime) > Date.parse(receivedTime)) throw new Error('Thời gian nguồn không được sau thời gian nhận.');
    function side(name, label) {
      const rows = form[name];
      if (!Array.isArray(rows) || rows.length < 1 || rows.length > 3) throw new Error(`${label}: cần từ 1 đến 3 mức.`);
      const result = [];
      let ended = false;
      rows.forEach((row, index) => {
        const price = row && row.price != null ? String(row.price).trim() : '';
        const quantity = row && row.quantity != null ? String(row.quantity).trim() : '';
        if (!price && !quantity) { ended = true; return; }
        if (ended) throw new Error(`${label}: điền liên tục từ mức 1, không bỏ trống mức ở giữa.`);
        if (!price || !quantity) throw new Error(`${label}, mức ${index + 1}: điền đủ giá và khối lượng.`);
        result.push({price:positiveInput(price, `${label}, mức ${index + 1}, giá`),
          quantity:positiveInput(quantity, `${label}, mức ${index + 1}, khối lượng`, true)});
      });
      if (!result.length) throw new Error(`${label}: cần ít nhất mức 1.`);
      return result;
    }
    return {contract_version:'1.0', source:'manual', symbol, price_unit:'VND', quantity_unit:'share',
      session:'continuous', event_time:eventTime, received_at:receivedTime,
      bids:side('bids','Bên mua'), asks:side('asks','Bên bán')};
  }

  function cumulativeLevels(payload) {
    function side(entries) {
      let total = 0;
      return entries.map(level => {
        const price = Number(level.price), quantity = Number(level.quantity);
        total += price * quantity;
        if (!Number.isFinite(price) || !Number.isFinite(quantity) || !Number.isFinite(total)) throw new Error('Dữ liệu biểu đồ không hợp lệ.');
        return {price, quantity, cumulativeValue:total};
      });
    }
    // Approximation only for SVG geometry; displayed exact values come from the backend.
    return {bids:side(payload.bids), asks:side(payload.asks)};
  }

  function compareDecimal(left, right) {
    const a = decimalParts(left), b = decimalParts(right);
    if (a.negative !== b.negative) return a.negative ? -1 : 1;
    const scale = Math.max(a.fraction.length, b.fraction.length);
    const av = BigInt(a.integer + a.fraction.padEnd(scale,'0'));
    const bv = BigInt(b.integer + b.fraction.padEnd(scale,'0'));
    const comparison = av === bv ? 0 : av > bv ? 1 : -1;
    return a.negative ? -comparison : comparison;
  }

  function describeResult(result) {
    const comparison = compareDecimal(result.bid_depth_vnd, result.ask_depth_vnd);
    const depth = comparison === 0 ? 'Giá trị niêm yết hai phía bằng nhau trong các mức được nhập.' : comparison > 0 ? 'Giá trị niêm yết bên mua lớn hơn bên bán trong các mức được nhập.' : 'Giá trị niêm yết bên bán lớn hơn bên mua trong các mức được nhập.';
    const imbalance = compareDecimal(result.imbalance, '0');
    return [depth, imbalance === 0 ? 'Imbalance bằng 0: hai phía cân bằng theo giá trị niêm yết.' : `Imbalance ${imbalance > 0 ? 'dương' : 'âm'} theo giá trị niêm yết; không phải tín hiệu dự báo giá.`,
      `Spread ${formatDecimal(result.spread_bps,4)} bps, tính từ hai giá tốt nhất đã nhập.`,
      'Dữ liệu nhập tay chưa được xác minh với SSI. Lệnh chờ có thể bị sửa hoặc hủy; các chỉ số không bảo đảm khớp lệnh và không phải khuyến nghị đầu tư.'];
  }

  function calculateManual(payload) {
    const prices = [...payload.bids, ...payload.asks].map(row => decimalParts(row.price));
    const scale = Math.max(...prices.map(price => price.fraction.length));
    const scaled = price => BigInt(price.integer + price.fraction.padEnd(scale, '0'));
    const bids = prices.slice(0, payload.bids.length).map(scaled);
    const asks = prices.slice(payload.bids.length).map(scaled);
    if (bids.some((value, index) => index && value >= bids[index - 1]) ||
        asks.some((value, index) => index && value <= asks[index - 1]) || bids[0] >= asks[0]) {
      throw new Error('Giá mua phải giảm dần, giá bán phải tăng dần và giá mua tốt nhất phải thấp hơn giá bán tốt nhất.');
    }
    const depth = (rows, values) => rows.reduce((sum, row, index) => sum + values[index] * BigInt(row.quantity), 0n);
    const bid = depth(payload.bids, bids), ask = depth(payload.asks, asks);
    const bestSum = bids[0] + asks[0];
    const unit = 10n ** BigInt(scale);
    function decimal(value, digits) {
      const absolute = (value < 0n ? -value : value).toString().padStart(digits + 1, '0');
      const prefix = value < 0n ? '-' : '';
      return digits ? prefix + absolute.slice(0, -digits) + '.' + absolute.slice(-digits) : prefix + absolute;
    }
    function ratio(numerator, denominator) {
      const absolute = numerator < 0n ? -numerator : numerator;
      const rounded = (absolute * 10n ** 12n * 2n + denominator) / (denominator * 2n);
      return decimal(numerator < 0n ? -rounded : rounded, 12);
    }
    return {
      'Độ sâu mua (VND)': decimal(bid, scale),
      'Độ sâu bán (VND)': decimal(ask, scale),
      'Mid (VND/cổ phiếu)': decimal(bestSum * 5n, scale + 1),
      'Spread (VND/cổ phiếu)': decimal(asks[0] - bids[0], scale),
      'Spread (bps)': ratio((asks[0] - bids[0]) * 20000n, bestSum),
      'Imbalance': ratio(bid - ask, bid + ask),
    };
  }

  return Object.freeze({buildManualPayload,calculateManual,formatDecimal,cumulativeLevels,describeResult});
}));
