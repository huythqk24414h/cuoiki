// Read published SSI market data using the server-side Redis token.
const symbolPattern = /^[A-Z0-9]{1,12}$/;
const resolutions = ['15m', '1h', '4h'];

module.exports = async function (req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET') return res.status(405).json({error:'Method not allowed'});
  const {kind, symbol, resolution, board, q, page, size} = req.query;
  if (!['history','series','live','intraday','catalog','market-delta'].includes(kind))
    return res.status(400).json({error:'Unknown dataset'});
  if ((kind === 'series' || kind === 'market-delta' || (kind === 'intraday' && symbol !== undefined)) &&
      (typeof symbol !== 'string' || !symbolPattern.test(symbol)))
    return res.status(400).json({error:'Invalid symbol'});
  if (kind === 'intraday' && resolution !== undefined &&
      (!symbol || !resolutions.includes(resolution)))
    return res.status(400).json({error:'Invalid resolution'});
  const paged = kind === 'catalog' && [page, size, board, q].some(value => value !== undefined);
  const pageNumber = page === undefined ? 1 : Number(page);
  const pageSize = size === undefined ? 60 : Number(size);
  if (paged && ((board !== undefined && !['HOSE','HNX','UPCOM','VN30'].includes(board)) ||
      (q !== undefined && (typeof q !== 'string' || q.length > 100)) ||
      [page,size].some(value => value !== undefined && (typeof value !== 'string' || !/^\d+$/.test(value))) ||
      !Number.isSafeInteger(pageNumber) || pageNumber < 1 || pageSize < 1 || pageSize > 200))
    return res.status(400).json({error:'Invalid catalog filters'});
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_READ_ONLY_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return res.status(503).json({error:'Market data store not configured'});

  async function read(key, field) {
    const response = await fetch(url, {
      method:'POST', signal:AbortSignal.timeout(5000),
      headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
      body:JSON.stringify(field ? ['HGET','liquiditylab:'+key,field] : ['GET','liquiditylab:'+key]),
    });
    if (!response.ok) throw Error('Store request failed');
    const {result, error} = await response.json();
    if (error) throw Error('Store read failed');
    return result === null ? null : JSON.parse(result);
  }
  try {
    let data;
    if (kind === 'market-delta') {
      data = await read('market-eod-updates', symbol);
    } else if (kind === 'series') {
      const history = await read('history');
      const entry = history?.symbols?.[symbol];
      data = entry ? await read(entry.key.replace(/^liquiditylab:/,'')) : null;
      if (entry && !data) throw Error('Missing stored series');
    } else if (kind === 'history') {
      data = await read(kind);
      if (data) for (const entry of Object.values(data.symbols)) delete entry.key;
    } else if (kind === 'intraday' && symbol) {
      data = await read('intraday:'+symbol);
      if (!data) {
        const legacy = await read('intraday');
        if (legacy?.symbols?.[symbol])
          data = {source:legacy.source, updated_at:legacy.updated_at, candles:legacy.symbols[symbol]};
      }
      if (data && resolution) {
        const {candles,...metadata} = data;
        data = {...metadata, rows:candles[resolution]};
      }
    } else if (kind === 'intraday') {
      const [legacy, coverage] = await Promise.all([read(kind), read('intraday-coverage')]);
      if (coverage) {
        data = {...legacy, ...coverage, symbols:{...coverage.symbols,...legacy?.symbols}, coverage:coverage.symbols};
      } else data = legacy;
    } else if (kind === 'catalog') {
      const [catalog, history, intraday, legacy] = await Promise.all([
        read('catalog'), read('history'), read('intraday-coverage'), read('intraday'),
      ]);
      if (catalog) {
        const directory = new Map(catalog.securities.map(row=>[row.symbol,row]));
        for (const code of Object.keys(history?.symbols || {})) {
          if (!history.indexes.includes(code) && !directory.has(code))
            directory.set(code,{symbol:code,board:null,status:'absent',stockType:'Stock'});
        }
        const needle = (q || '').trim().toLocaleLowerCase('vi');
        const matching = [...directory.values()].filter(row=>
          (!board || row.board === board || (board === 'VN30' && catalog.index_memberships.VN30.includes(row.symbol))) &&
          (!needle || [row.symbol,row.symbolNameVi,row.symbolNameEn].some(value=>
            String(value || '').toLocaleLowerCase('vi').includes(needle))));
        const selected = paged ? matching.slice((pageNumber-1)*pageSize,pageNumber*pageSize) : matching;
        data = {...catalog, securities:selected.map(row=>({...row,
          daily_last:history?.symbols?.[row.symbol]?.last || null,
          intraday_last:intraday?.symbols?.[row.symbol]?.last ||
            legacy?.symbols?.[row.symbol]?.['15m']?.at(-1)?.closed_at || null,
        })), total:matching.length, ...(paged ? {page:pageNumber,size:pageSize} : {})};
      }
    } else data = await read(kind);
    if (!data) return res.status(404).json({error:'No published data yet'});
    if (['catalog','history','series','intraday'].includes(kind))
      res.setHeader('Cache-Control','public, max-age=0, s-maxage=30');
    return res.status(200).json(data);
  } catch {
    return res.status(502).json({error:'Market data temporarily unavailable'});
  }
};
