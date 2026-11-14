import { cp, copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';

const output = new URL('../public-demo/', import.meta.url);
await mkdir(output, { recursive: true });
await cp(new URL('../web/', import.meta.url), output, { recursive: true });
for (const file of ['static-api.js', 'prices.json']) {
  await copyFile(new URL('../demo/' + file, import.meta.url), new URL(file, output));
}
const page = new URL('index.html', output);
const html = (await readFile(page, 'utf8')).replace(
  '<script src="/app.js"',
  '<script src="/static-api.js" defer></script><script src="/app.js"',
);
await writeFile(page, html.replace(
  '<main id="main" tabindex="-1">',
  '<main id="main" tabindex="-1"><p class="helper">Xem nguồn và thời điểm cập nhật tại biểu đồ và bảng giá. Dữ liệu mô phỏng có nhãn riêng.</p>',
));
const eod = new URL('eod-ui.js', output);
const display = (await readFile(eod, 'utf8'))
  .replaceAll('Historical EOD · SSI', 'Lịch sử EOD')
  .replaceAll("options.source||'SSI FastConnect V3'", "options.source||state.meta?.manifest?.upstream_sources?.[0]?.name||'EOD'")
  .replaceAll('Proxy SSI value', 'Giá trị giao dịch')
  .replaceAll(' · SHA-256 khớp', '')
  .replaceAll(' · kiểm chứng lại tại mỗi lần đọc API', '')
  .replaceAll('✓ CSV khớp SHA-256 trong manifest', 'Chuỗi được tạo để minh họa')
  .replaceAll('✓ OHLC và ngày chốt hợp lệ; đơn vị nguồn mở rộng chưa xác minh', 'OHLC và khối lượng mô phỏng')
  .replaceAll('Đối chiếu nguồn khác: xem Phương pháp', 'Phương pháp mô tả cách tính chỉ số');
await writeFile(eod, display);
const intra = new URL('intraday-ui.js', output);
const intraSource = (await readFile(intra, 'utf8'))
  .replace('Tự kiểm tra local mỗi 5 giây; tải SSI tối đa mỗi 60 giây theo mã. Nến đang hình thành có thể đổi. 4H tách nghỉ trưa nên có thể thiếu kỳ. Giá/KL giữ đơn vị nguồn. Không dùng nến để dựng sổ lệnh.', 'Kiểm tra bản tin mới mỗi 5 giây. Nến tạm được dựng từ mẫu giá khớp đã nhận và có thể thiếu giao dịch. Giá giữ đơn vị SSI.');
await writeFile(intra, intraSource);

const app = new URL('app.js', output);
const source = await readFile(app, 'utf8');
await writeFile(app, source.replace(
  '  const target=new URL(url,location.href);',
  '  const target=new URL(url,location.href);\n  return window.StaticLiquidity.request(target, options);',
));
