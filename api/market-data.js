// Read published market data from a private Redis store.
module.exports = async function (req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET') return res.status(405).json({error:'Method not allowed'});
  const kind = req.query.kind;
  if (!['history','series','live'].includes(kind)) return res.status(400).json({error:'Unknown dataset'});
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_READ_ONLY_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return res.status(503).json({error:'Market data store not configured'});
  try {
    async function read(key) {
      const response = await fetch(url, {
      method:'POST', signal:AbortSignal.timeout(5000),
      headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
      body:JSON.stringify(['GET',key]),
    });
    if (!response.ok) throw Error('Store request failed');
    const {result, error} = await response.json();
    if (error) throw Error('Store read failed');
      return result ? JSON.parse(result) : null;
    }
    let data = await read('liquiditylab:'+(kind === 'live' ? 'live' : 'history'));
    if (kind === 'series') {
      const symbol = req.query.symbol;
      if (typeof symbol !== 'string' || !/^[A-Z0-9]{1,12}$/.test(symbol))
        return res.status(400).json({error:'Invalid symbol'});
      const entry = data?.symbols?.[symbol];
      data = entry ? await read(entry.key) : null;
    } else if (kind === 'history' && data) {
      for (const entry of Object.values(data.symbols)) delete entry.key;
    }
    if (!data) return res.status(404).json({error:'No published data yet'});
    return res.status(200).json(data);
  } catch {
    return res.status(502).json({error:'Market data temporarily unavailable'});
  }
};
