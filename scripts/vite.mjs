// Resolve the frontend CLI with either npm hoisting or pnpm workspace links.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const requireFrontend = createRequire(new URL('../frontend/package.json', import.meta.url));
process.argv.push('--config', fileURLToPath(new URL('../frontend/vite.config.js', import.meta.url)));
await import(pathToFileURL(join(dirname(requireFrontend.resolve('vite/package.json')), 'bin/vite.js')).href);
