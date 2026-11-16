import { gunzipSync } from 'node:zlib';
import { existsSync } from 'node:fs';
import { cp, copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const output = new URL('../public-demo/', import.meta.url);
await mkdir(output, { recursive: true });
await cp(new URL('../web/', import.meta.url), output, { recursive: true });
for (const file of ['static-api.js']) {
  await copyFile(new URL('../demo/' + file, import.meta.url), new URL(file, output));
}
const archive = new URL('../demo/eod-archive.ndjson.gz', import.meta.url);
if (existsSync(archive)) {
  const target = new URL('eod-archive/', output);
  await mkdir(target, {recursive:true});
  for (const line of gunzipSync(await readFile(archive)).toString('utf8').trimEnd().split('\n')) {
    const [name, rows] = JSON.parse(line);
    if (!/^(catalog|[A-Z0-9]{1,12})\.json$/.test(name)) throw Error('Invalid archive filename');
    await writeFile(new URL(name,target), JSON.stringify(rows));
  }
}
const page = new URL('index.html', output);
const html = (await readFile(page, 'utf8')).replace(
  '<script src="/app.js"',
  '<script src="/static-api.js" defer></script><script src="/app.js"',
);
await writeFile(page, html.replace(
  '<main id="main" tabindex="-1">',
  '<main id="main" tabindex="-1"><p class="helper">Xem nguồn và thời điểm cập nhật tại biểu đồ và bảng giá.</p>',
).replace('<div id="price-chart"', '<p class="helper">Do giới hạn dung lượng công bố, VN30 dùng lịch sử SSI từ phiên đầu nguồn có dữ liệu; các mã còn lại dùng từ 2022 đến nay.</p><div id="price-chart"'));
const eod = new URL('eod-ui.js', output);
const display = (await readFile(eod, 'utf8'))
  .replaceAll('Historical EOD · SSI', 'Lịch sử EOD')
  .replaceAll("options.source||'SSI FastConnect V3'", "options.source||state.meta?.manifest?.upstream_sources?.[0]?.name||'EOD'")
  .replaceAll('Proxy SSI value', 'Giá trị SSI theo nguồn')
  .replaceAll(' · SHA-256 khớp', '')
  .replaceAll(' · kiểm chứng lại tại mỗi lần đọc API', '')
  .replaceAll('✓ CSV khớp SHA-256 trong manifest', 'Chuỗi lấy từ API SSI')
  .replaceAll('✓ OHLC và ngày chốt hợp lệ; đơn vị nguồn mở rộng chưa xác minh', 'OHLC và khối lượng do SSI cung cấp')
  .replaceAll('Đối chiếu nguồn khác: xem Phương pháp', 'Phương pháp mô tả cách tính chỉ số');
await writeFile(eod, display);
const intra = new URL('intraday-ui.js', output);
const intraSource = (await readFile(intra, 'utf8'))
  .replace('Tự kiểm tra local mỗi 5 giây; tải SSI tối đa mỗi 60 giây theo mã. Nến đang hình thành có thể đổi. 4H tách nghỉ trưa nên có thể thiếu kỳ. Giá/KL giữ đơn vị nguồn. Không dùng nến để dựng sổ lệnh.', 'Đọc các nến đã đóng từ OHLCV 1 phút của SSI. HOSE · khớp lệnh liên tục. Khung theo buổi dài tối đa 135 phút sáng hoặc 90 phút chiều. Giá và khối lượng theo đơn vị nguồn SSI.');
await writeFile(intra, intraSource);

const app = new URL('app.js', output);
const source = await readFile(app, 'utf8');
await writeFile(app, source.replace(
  '  const target=new URL(url,location.href);',
  '  const target=new URL(url,location.href);\n  return window.StaticLiquidity.request(target, options);',
));

// New deployments must load the matching scripts even on a previously opened site.
let pageHtml = await readFile(page, 'utf8');
for (const name of ['static-api.js','app.js','eod-ui.js','market-ui.js','quote-board.js','intraday-ui.js']) {
  const version = createHash('sha256').update(await readFile(new URL(name, output))).digest('hex').slice(0,12);
  pageHtml = pageHtml.replace(`src="/${name}"`, `src="/${name}?v=${version}"`);
}
await writeFile(page, pageHtml);
