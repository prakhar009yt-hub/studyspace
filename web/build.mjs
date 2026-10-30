import { mkdir, copyFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

export function validateBackend(value, allowLocal = false) {
  if (!value) throw new Error('Set STUDYSPACE_BACKEND_URL to your protected HTTPS backend URL in Vercel, then redeploy.');
  let url;
  try { url = new URL(value); } catch { throw new Error('STUDYSPACE_BACKEND_URL must be an absolute HTTPS URL.'); }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(allowLocal && local && url.protocol === 'http:')) {
    throw new Error('The backend must use HTTPS. HTTP localhost is permitted only for local preview.');
  }
  if (local && !allowLocal) throw new Error('A Vercel deployment cannot use localhost as its backend. Use your protected server’s HTTPS domain.');
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('Use a backend URL without credentials, query parameters or fragments.');
  }
  if (url.pathname !== '/') throw new Error('Use the backend root URL, not a note, settings or login path.');
  return url.origin + '/';
}

export async function build(value, { output = resolve(root, 'dist'), allowLocal = false } = {}) {
  const backend = validateBackend(value, allowLocal);
  await mkdir(output, { recursive: true });
  for (const file of ['index.html', 'styles.css', 'app.js', 'favicon.svg']) {
    await copyFile(resolve(root, file), resolve(output, file));
  }
  // This URL is public configuration. No provider keys or environment dumps.
  await writeFile(resolve(output, 'config.js'), 'window.STUDYSPACE_CONFIG = Object.freeze(' + JSON.stringify({ backend }).replaceAll('<', '\\u003c') + ');\n');
  return output;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    await build(process.env.STUDYSPACE_BACKEND_URL, { allowLocal: process.argv.includes('--allow-local') && process.env.VERCEL !== '1' });
    console.log('Studyspace web build ready in web/dist. Provider keys remain on the backend.');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
