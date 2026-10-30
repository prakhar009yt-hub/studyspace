import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build, validateBackend } from './build.mjs';
import { demoStudy } from './demo.mjs';
import { normalizeStudy, makePlan, exportStudy } from './study-core.mjs';

test('example workspace uses the real study schema and portable export', () => {
  const study=normalizeStudy(structuredClone(demoStudy));
  assert.equal(study.notes[0].analysis.quiz[0].answer,'Inorder');
  study.plan=makePlan(study,'2026-11-10',60,new Date(2026,10,1));
  const reopened=normalizeStudy(JSON.parse(exportStudy(study)));
  assert.equal(reopened.plan.remaining,0);
  assert.equal(reopened.notes[0].analysis.topics[0].name,'Binary tree traversal');
});

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
    assert.deepEqual((await readdir(output)).sort(), ['app.js', 'companion.html', 'config.js', 'demo.mjs', 'downloads', 'favicon.svg', 'index.html', 'onboarding.mjs', 'privacy.html', 'site.css', 'study-core.mjs', 'study.html', 'study.mjs', 'styles.css', 'theme.mjs', 'workspace.css']);
    const config = await readFile(join(output, 'config.js'), 'utf8');
    assert.match(config, /https:\/\/study\.example\.com\//);
    assert.ok(!config.includes('fixture-do-not-publish'));
    const html = await readFile(join(output, 'index.html'), 'utf8');
    assert.ok(html.includes('Open a study file'));
    assert.ok(!html.includes('127.0.0.1'));
    assert.ok((await readFile(join(output, 'downloads/Studyspace-Extension-Test.zip'))).length > 0);
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
