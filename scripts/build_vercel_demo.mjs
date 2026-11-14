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
await writeFile(page, html);

const app = new URL('app.js', output);
const source = await readFile(app, 'utf8');
await writeFile(app, source.replace(
  '  const target=new URL(url,location.href);',
  '  const target=new URL(url,location.href);\n  return window.StaticLiquidity.request(target, options);',
));
