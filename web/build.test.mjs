import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build, validateBackend } from './build.mjs';

test('production backend requires HTTPS without embedded credentials or arbitrary routes', () => {
  assert.equal(validateBackend('https://study.example.com'), 'https://study.example.com/');
  for (const bad of ['', 'file:///secret', 'javascript:alert(1)', 'http://example.com', 'https://user:password@example.com', 'https://example.com/?key=secret', 'https://example.com/#token', 'https://example.com/Notes', 'https://localhost']) {
    assert.throws(() => validateBackend(bad));
  }
});
test('local preview is explicitly opt-in', () => {
  assert.throws(() => validateBackend('http://127.0.0.1:8503'));
  assert.equal(validateBackend('http://127.0.0.1:8503', true), 'http://127.0.0.1:8503/');
  assert.throws(() => validateBackend('http://example.com', true));
});
test('build output contains only static files and public backend configuration', async () => {
  const output = await mkdtemp(join(tmpdir(), 'studyspace-web-'));
  const prior = process.env.GEMINI_API_KEY;
  process.env.GEMINI_API_KEY = 'fixture-do-not-publish';
  try {
    await build('https://study.example.com', { output });
    assert.deepEqual((await readdir(output)).sort(), ['app.js', 'config.js', 'downloads', 'favicon.svg', 'index.html', 'styles.css']);
    const config = await readFile(join(output, 'config.js'), 'utf8');
    assert.match(config, /https:\/\/study\.example\.com\//);
    assert.ok(!config.includes('fixture-do-not-publish'));
    const html = await readFile(join(output, 'index.html'), 'utf8');
    assert.ok(html.includes('Open my workspace'));
  } finally {
    if (prior === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = prior;
    await rm(output, { recursive: true, force: true });
  }
});
test('local mode uses each visitor’s loopback companion without a backend or API key', async () => {
  const output = await mkdtemp(join(tmpdir(), 'studyspace-local-'));
  try {
    await build(undefined, { output });
    const config = await readFile(join(output, 'config.js'), 'utf8');
    assert.match(config, /"mode":"local"/);
    assert.match(config, /http:\/\/127\.0\.0\.1:8765\//);
    assert.ok((await readFile(join(output, 'downloads/Studyspace-Windows.zip'))).length > 0);
    await build('https://unused.example.com', { output, mode: 'local' });
    assert.ok(!(await readFile(join(output, 'config.js'), 'utf8')).includes('unused.example.com'));
  } finally { await rm(output, { recursive: true, force: true }); }
});
