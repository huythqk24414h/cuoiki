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
  '<main id="main" tabindex="-1"><p class="helper">Dữ liệu minh họa: Tổng quan, Phân tích và chỉ số dùng chuỗi mô phỏng. Bảng giá tại Sổ lệnh ghi rõ nguồn. Thu sổ lệnh SSI trực tiếp chạy riêng.</p>',
));
const eod = new URL('eod-ui.js', output);
const display = (await readFile(eod, 'utf8'))
  .replaceAll('Historical EOD · SSI', 'EOD mô phỏng')
  .replaceAll('SSI FastConnect V3', 'Dữ liệu mô phỏng')
  .replaceAll('Proxy SSI value', 'Giá trị giao dịch')
  .replaceAll(' · SHA-256 khớp', '')
  .replaceAll(' · kiểm chứng lại tại mỗi lần đọc API', '')
  .replaceAll('✓ CSV khớp SHA-256 trong manifest', 'Chuỗi được tạo để minh họa')
  .replaceAll('✓ OHLC và ngày chốt hợp lệ; đơn vị nguồn mở rộng chưa xác minh', 'OHLC và khối lượng mô phỏng')
  .replaceAll('Đối chiếu nguồn khác: xem Phương pháp', 'Phương pháp mô tả cách tính chỉ số');
await writeFile(eod, display);

const app = new URL('app.js', output);
const source = await readFile(app, 'utf8');
await writeFile(app, source.replace(
  '  const target=new URL(url,location.href);',
  '  const target=new URL(url,location.href);\n  return window.StaticLiquidity.request(target, options);',
));
