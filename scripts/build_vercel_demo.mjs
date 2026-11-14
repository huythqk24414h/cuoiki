import { cp, copyFile, mkdir } from 'node:fs/promises';

const output = new URL('../public-demo/', import.meta.url);
await mkdir(output, { recursive: true });
await cp(new URL('../demo/', import.meta.url), output, { recursive: true });
await copyFile(new URL('../web/calculator-core.js', import.meta.url), new URL('calculator-core.js', output));
