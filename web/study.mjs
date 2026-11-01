import { normalizeStudy, exportStudy, topicKey, makePlan } from './study-core.mjs';
import { demoStudy } from './demo.mjs';

const $ = id => document.getElementById(id);
let study = null, dirty = false, currentFileHandle = null, extensionConnected = false, activePage = 'Home';

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function details(title, content) {
  const el = element('details');
  el.append(element('summary', title));
  for (const c of content) el.append(c);
  return el;
}

// Navigation between the 9 Streamlit pages
function navigate(pageName) {
  activePage = pageName;
  document.querySelectorAll('.st-nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.page === pageName);
  });
  document.querySelectorAll('.st-page').forEach(sec => {
    sec.classList.toggle('active', sec.id === 'page-' + pageName);
  });
  if ($('topbar-page-name')) $('topbar-page-name').textContent = pageName;
  if ($('st-sidebar')) $('st-sidebar').classList.remove('open');

  if (pageName === 'Home') renderHome();
  else if (pageName === 'Notes') render();
  else if (pageName === 'Topics') renderTopics();
  else if (pageName === 'Videos') renderVideos();
  else if (pageName === 'Progress') renderProgress();
  else if (pageName === 'Planner') renderPlan();
}

document.querySelectorAll('.st-nav-item').forEach(btn => {
  btn.addEventListener('click', () => navigate(btn.dataset.page));
});
document.addEventListener('click', e => {
  const goto = e.target.closest('[data-goto]');
  if (goto) {
    e.preventDefault();
    navigate(goto.dataset.goto);
  }
});
$('menu-btn')?.addEventListener('click', () => {
  $('st-sidebar')?.classList.toggle('open');
});



// Semester dropdown in LMS tab
if ($('semester')) {
  $('semester').replaceChildren();
  for (let i = 1; i <= 12; i++) $('semester').add(new Option('Semester ' + i, String(i)));
  $('semester').value = '3';
}

function change() {
  dirty = true;
  if ($('status')) $('status').textContent = 'Unsaved changes. Save your study JSON before closing.';
  if ($('saved')) $('saved').textContent = 'Unsaved changes. Save your study JSON before closing.';
  if (study) window.postMessage({ type: 'STUDYSPACE_SAVE_DATA', payload: study }, '*');
}

// Extension bridge
function onExtensionConnected() {
  if (extensionConnected) return;
  extensionConnected = true;
  const pill = $('ext-status-pill');
  if (pill) pill.style.display = 'inline-flex';
  window.postMessage({ type: 'STUDYSPACE_GET_DATA' }, '*');
}

function checkExtension() {
  if (document.documentElement.dataset.studyspaceExtension === 'true' || window.__STUDYSPACE_EXTENSION_ACTIVE__ || window.__STUDYSPACE_EXTENSION_READY__) {
    onExtensionConnected();
  }
}

window.addEventListener('message', event => {
  if (event.source !== window || !event.data) return;
  if (event.data.type === 'STUDYSPACE_EXTENSION_READY' || event.data.type === 'STUDYSPACE_PONG') {
    onExtensionConnected();
  } else if (event.data.type === 'STUDYSPACE_DATA_RESPONSE') {
    const payload = event.data.payload;
    if (payload?.studyspace_study?.notes?.length && !study) {
      loadStudy(payload.studyspace_study, 'MUJ LMS (Synced via Extension)');
      if ($('status')) $('status').textContent = '✓ Connected to extension · Loaded your study notes!';
    } else if (payload?.muj_logged_in) {
      const pill = $('ext-status-pill');
      if (pill) pill.textContent = '✓ LMS Logged In';
    }
  }
});

window.addEventListener('load', () => {
  checkExtension();
  setTimeout(checkExtension, 300);
  setTimeout(checkExtension, 1000);
});
checkExtension();

function updateStatsAndDropdowns() {
  if (!study) return;
  const names = [...new Set(study.notes.map(n => n.course))].sort();
  const count = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  // Update sidebar course filter
  if ($('sidebar-course-select')) {
    const prev = $('sidebar-course-select').value;
    $('sidebar-course-select').replaceChildren(new Option('All courses', ''));
    for (const n of names) $('sidebar-course-select').add(new Option(n, n));
    if (names.includes(prev)) $('sidebar-course-select').value = prev;
  }
  if ($('sidebar-sem-num')) $('sidebar-sem-num').textContent = String(study.semester);
  if ($('topbar-semester-label')) $('topbar-semester-label').textContent = `Semester ${study.semester}`;

  // Update Notes tab course filter
  if ($('course')) {
    const prev = $('course').value;
    $('course').replaceChildren(new Option('All subjects', ''));
    for (const n of names) $('course').add(new Option(n, n));
    if (names.includes(prev)) $('course').value = prev;
  }

  // Update stats summary in Notes tab
  const totalTopics = study.notes.reduce((s, n) => s + n.analysis.topics.length, 0);
  if ($('stats')) {
    $('stats').textContent = `Semester ${study.semester} · ${count(names.length, 'subject')} · ${count(study.notes.length, 'analyzed note')} · ${count(totalTopics, 'topic')}`;
  }
}

function loadStudy(input, name, handle = null) {
  const next = normalizeStudy(input);
  study = next;
  dirty = false;
  currentFileHandle = handle;
  if ($('empty')) $('empty').hidden = study.notes.length > 0;
  if ($('save')) $('save').disabled = false;
  if ($('saved')) $('saved').textContent = `Loaded ${study.notes.length} notes from ${name}.`;

  updateStatsAndDropdowns();
  if ($('exam')) $('exam').value = study.plan?.exam || '';
  if ($('minutes')) $('minutes').value = study.plan?.daily || 120;

  renderHome();
  render();
  renderTopics();
  renderVideos();
  renderProgress();
  renderPlan();
}

function mergeStudy(input, name, handle = null) {
  const next = normalizeStudy(input);
  let added = 0, updated = 0;
  for (const note of next.notes) {
    const pos = study.notes.findIndex(n => n.id === note.id);
    if (pos >= 0) { study.notes[pos] = note; updated++; }
    else { study.notes.push(note); added++; }
  }
  for (const course of next.courses) {
    if (!study.courses.some(c => c.name === course.name)) study.courses.push(course);
  }
  Object.assign(study.progress, next.progress);
  if (handle) currentFileHandle = handle;
  updateStatsAndDropdowns();
  change();
  renderHome();
  render();
  renderTopics();
  renderVideos();
  renderProgress();
  renderPlan();
  if ($('status')) $('status').textContent = `Merged ${added} new note(s), updated ${updated} existing from ${name}.`;
}

async function openFile(file, handle = null) {
  try {
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) throw new Error('Study file exceeds 30 MB limit.');
    const parsed = JSON.parse(await file.text());
    if (study && study.notes.length) {
      if (confirm(`Workspace already has ${study.notes.length} note(s).\n\nClick OK to MERGE notes from "${file.name}".\nClick Cancel to replace current workspace.`)) {
        mergeStudy(parsed, file.name, handle || currentFileHandle);
        navigate('Home');
        return;
      }
    }
    if (dirty && !confirm('Replace unsaved changes with this study file?')) return;
    loadStudy(parsed, file.name, handle);
    navigate('Home');
  } catch (error) {
    if ($('status')) $('status').textContent = 'Could not open file: ' + error.message;
  }
}

for (const id of ['open', 'import']) {
  $(id)?.addEventListener('change', async event => {
    await openFile(event.target.files[0]);
    event.target.value = '';
  });
}

for (const dropId of ['empty', 'empty-drop']) {
  const drop = $(dropId);
  if (!drop) continue;
  for (const name of ['dragenter', 'dragover']) {
    drop.addEventListener(name, event => {
      event.preventDefault();
      drop.classList.add('dragging');
    });
  }
  for (const name of ['dragleave', 'drop']) {
    drop.addEventListener(name, () => drop.classList.remove('dragging'));
  }
  drop.addEventListener('drop', event => {
    event.preventDefault();
    if (event.dataTransfer.files.length !== 1) {
      if ($('status')) $('status').textContent = 'Drop one study JSON at a time.';
      return;
    }
    openFile(event.dataTransfer.files[0]);
  });
}

$('demo')?.addEventListener('click', () => {
  loadStudy(structuredClone(demoStudy), 'example workspace · synthetic data');
  navigate('Home');
});
if (new URLSearchParams(location.search).get('demo') === '1') {
  loadStudy(structuredClone(demoStudy), 'example workspace · synthetic data');
}

// Shortcut: Ctrl/Cmd + K
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    navigate('Notes');
    $('search')?.focus();
  }
});

// Save study JSON
$('save')?.addEventListener('click', async () => {
  if (!study) return;
  const content = exportStudy(study);
  if (currentFileHandle && window.showSaveFilePicker) {
    try {
      const writable = await currentFileHandle.createWritable();
      await writable.write(content);
      await writable.close();
      dirty = false;
      const msg = `Saved! Updated ${currentFileHandle.name} in-place without creating a duplicate.`;
      if ($('status')) $('status').textContent = msg;
      if ($('saved')) $('saved').textContent = msg;
      return;
    } catch (e) {
      if (e.name === 'AbortError') return;
      currentFileHandle = null;
    }
  }
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({ suggestedName: `Studyspace-semester-${study.semester}.json`, types: [{ description: 'Study JSON', accept: { 'application/json': ['.json'] } }] });
      currentFileHandle = handle;
      const writable = await handle.createWritable();
      await writable.write(content);
      await writable.close();
      dirty = false;
      const msg = `Saved! Further saves will update ${handle.name} in-place.`;
      if ($('status')) $('status').textContent = msg;
      if ($('saved')) $('saved').textContent = msg;
      return;
    } catch (e) {
      if (e.name === 'AbortError') return;
    }
  }
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const a = element('a');
  a.href = url;
  a.download = `Studyspace-semester-${study.semester}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  dirty = false;
  const msg = 'Download requested. Check your Downloads folder for the updated study file.';
  if ($('status')) $('status').textContent = msg;
  if ($('saved')) $('saved').textContent = msg;
});

// Filter synchronization
$('sidebar-course-select')?.addEventListener('change', e => {
  if ($('course')) $('course').value = e.target.value;
  render();
  renderTopics();
  renderVideos();
});
$('course')?.addEventListener('change', e => {
  if ($('sidebar-course-select')) $('sidebar-course-select').value = e.target.value;
  render();
});
$('search')?.addEventListener('input', render);

// 1. RENDER HOME PAGE
function renderHome() {
  if (!study) {
    if ($('stat-notes')) $('stat-notes').textContent = '00';
    if ($('stat-topics')) $('stat-topics').textContent = '00';
    if ($('stat-covered')) $('stat-covered').textContent = '00';
    if ($('stat-videos')) $('stat-videos').textContent = '00';
    return;
  }
  const totalNotes = study.notes.length;
  const allTopics = study.notes.flatMap(n => n.analysis.topics);
  const totalTopics = allTopics.length;
  let coveredCount = 0, weakTopics = [];
  for (const note of study.notes) {
    for (const t of note.analysis.topics) {
      const state = study.progress[topicKey(note, t)] || {};
      if (state.covered) coveredCount++;
      if (state.weak && !state.covered) weakTopics.push(t.name);
    }
  }
  const totalVideos = allTopics.reduce((s, t) => s + (t.videos?.length || 0), 0);

  const pad = n => String(n).padStart(2, '0');
  if ($('stat-notes')) $('stat-notes').textContent = pad(totalNotes);
  if ($('stat-topics')) $('stat-topics').textContent = pad(totalTopics);
  if ($('stat-covered')) $('stat-covered').textContent = pad(coveredCount);
  if ($('stat-videos')) $('stat-videos').textContent = pad(totalVideos);
  const subjectNames = [...new Set(study.notes.map(n => n.course))];
  if ($('stat-notes-foot')) $('stat-notes-foot').textContent = `Semester ${study.semester} · ${subjectNames.length} subjects`;

  // Focus corner
  if (weakTopics.length && $('focus-title')) {
    $('focus-title').textContent = 'A little extra attention';
    $('focus-detail').textContent = `Focus on: ${weakTopics.slice(0, 3).join(', ')}`;
  } else if (study.plan?.exam && $('focus-title')) {
    $('focus-title').textContent = 'Your exam is on the horizon';
    $('focus-detail').textContent = `Scheduled for ${study.plan.exam}. Prioritize the concepts you find hardest.`;
  }

  // Home recent notes
  const listEl = $('home-notes-list');
  if (listEl) {
    listEl.replaceChildren();
    if (!study.notes.length) {
      listEl.append(element('p', 'No notes added yet. Fetch from LMS or open a study JSON to begin.', 'muted'));
    } else {
      for (const note of study.notes.slice(0, 3)) {
        const card = element('div', undefined, 'panel');
        card.style.margin = '10px 0';
        card.append(
          element('div', `${note.course} · ${note.unit}`, 'badge'),
          element('h3', note.title),
          element('p', (note.analysis.summary || '').slice(0, 160) + '…', 'muted')
        );
        const btn = element('button', 'Continue studying →', 'button');
        btn.addEventListener('click', () => {
          navigate('Notes');
          if ($('search')) $('search').value = note.title;
          render();
        });
        card.append(btn);
        listEl.append(card);
      }
    }
  }
}

// 2. RENDER TOPICS PAGE
function renderTopics() {
  const container = $('topics-list-container');
  if (!container) return;
  container.replaceChildren();
  if (!study || !study.notes.length) {
    container.append(element('p', 'No topics discovered yet. Load your notes or sync LMS first.', 'muted'));
    return;
  }
  const viewFilter = $('topic-filter-view')?.value || 'all';
  const query = $('topic-search-input')?.value.toLowerCase().trim() || '';
  const selectedCourse = $('sidebar-course-select')?.value || '';

  let count = 0;
  for (const note of study.notes) {
    if (selectedCourse && note.course !== selectedCourse) continue;
    for (const topic of note.analysis.topics) {
      const state = study.progress[topicKey(note, topic)] || {};
      if (viewFilter === 'covered' && !state.covered) continue;
      if (viewFilter === 'review' && !(state.weak || !state.covered)) continue;
      if (query && !(topic.name + ' ' + note.course + ' ' + (topic.concepts || []).join(' ')).toLowerCase().includes(query)) continue;

      count++;
      const item = element('div', undefined, 'panel');
      item.style.margin = '12px 0';
      const topRow = element('div', undefined, 'row');
      topRow.append(element('span', `${note.course} · ${note.unit}`, 'badge'));
      if (state.covered) topRow.append(element('span', '✓ Covered', 'badge'));
      if (state.weak) topRow.append(element('span', '⚠ Needs review', 'badge'));
      item.append(topRow, element('h3', topic.name));

      if (topic.concepts?.length) {
        item.append(element('p', topic.concepts.join(' · '), 'muted'));
      }

      const actionsRow = element('div', undefined, 'row');
      const covLabel = element('label', undefined, 'check');
      const covInput = element('input');
      covInput.type = 'checkbox';
      covInput.checked = !!state.covered;
      covInput.addEventListener('change', () => {
        study.progress[topicKey(note, topic)] = { ...(study.progress[topicKey(note, topic)] || {}), covered: covInput.checked };
        change();
        renderTopics();
        renderHome();
      });
      covLabel.append(covInput, document.createTextNode('Mark as covered'));

      const weakLabel = element('label', undefined, 'check');
      const weakInput = element('input');
      weakInput.type = 'checkbox';
      weakInput.checked = !!state.weak;
      weakInput.addEventListener('change', () => {
        study.progress[topicKey(note, topic)] = { ...(study.progress[topicKey(note, topic)] || {}), weak: weakInput.checked };
        change();
        renderTopics();
        renderHome();
      });
      weakLabel.append(weakInput, document.createTextNode('Needs review'));

      const openBtn = element('button', 'Open in Notes →', 'button');
      openBtn.addEventListener('click', () => {
        navigate('Notes');
        if ($('search')) $('search').value = topic.name;
        render();
      });

      actionsRow.append(covLabel, weakLabel, openBtn);
      item.append(actionsRow);
      container.append(item);
    }
  }
  if (!count) {
    container.append(element('p', 'No matching topics found for this filter.', 'empty'));
  }
}
$('topic-filter-view')?.addEventListener('change', renderTopics);
$('topic-search-input')?.addEventListener('input', renderTopics);

// 3. RENDER VIDEOS PAGE
function renderVideos() {
  const container = $('videos-grid-container');
  if (!container) return;
  container.replaceChildren();
  if (!study || !study.notes.length) {
    container.append(element('p', 'No videos found. Use Find topic videos in LMS tab or load an example workspace.', 'muted'));
    return;
  }
  const selectedCourse = $('sidebar-course-select')?.value || '';
  let count = 0;
  for (const note of study.notes) {
    if (selectedCourse && note.course !== selectedCourse) continue;
    for (const topic of note.analysis.topics) {
      for (const v of topic.videos || []) {
        count++;
        const card = element('div', undefined, 'panel');
        card.style.margin = '12px 0';
        const a = element('a', v.title + ' ↗');
        a.href = 'https://www.youtube.com/watch?v=' + v.id;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.style.fontSize = '1.1rem';
        a.style.fontWeight = '700';

        const meta = element('p', `${note.course} · Topic: ${topic.name} · Channel: ${v.channel || 'YouTube'}`, 'muted');
        const reason = element('p', v.reason || 'Recommended study video for this concept.');
        card.append(a, meta, reason);
        container.append(card);
      }
    }
  }
  if (!count) {
    container.append(element('p', 'No video recommendations found. Click "Find topic videos" in the LMS tab or open the demo workspace.', 'empty'));
  }
}

// 4. RENDER PROGRESS PAGE
function renderProgress() {
  const container = $('progress-course-bars');
  if (!container) return;
  container.replaceChildren();
  if (!study || !study.notes.length) {
    container.append(element('p', 'No notes loaded yet. Open a study file or connect MUJ LMS to track progress.', 'muted'));
    return;
  }
  const courses = [...new Set(study.notes.map(n => n.course))].sort();
  for (const course of courses) {
    const courseNotes = study.notes.filter(n => n.course === course);
    const topics = courseNotes.flatMap(n => n.analysis.topics);
    let covered = 0;
    for (const note of courseNotes) {
      for (const t of note.analysis.topics) {
        if (study.progress[topicKey(note, t)]?.covered) covered++;
      }
    }
    const percent = topics.length ? Math.round((covered / topics.length) * 100) : 0;
    const card = element('div', undefined, 'panel');
    card.style.margin = '12px 0';
    card.append(
      element('h3', `${course} (${covered} / ${topics.length} topics covered · ${percent}%)`),
      element('progress')
    );
    card.querySelector('progress').max = topics.length || 1;
    card.querySelector('progress').value = covered;
    container.append(card);
  }
}

// 5. PRACTICE MODALS (Flashcards & Quiz)
let practiceModal = null;
function closePractice() {
  if (practiceModal) {
    practiceModal.remove();
    practiceModal = null;
  }
}

function startFlashcardPractice(title, cards) {
  closePractice();
  if (!cards.length) return;
  let index = 0, flipped = false;
  const overlay = element('div', undefined, 'practice-overlay');
  const dialog = element('div', undefined, 'practice-dialog');
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  const header = element('div', undefined, 'practice-header');
  const countEl = element('span', '', 'eyebrow');
  const closeBtn = element('button', '✕ Close', 'practice-btn-sm');
  closeBtn.addEventListener('click', closePractice);
  header.append(countEl, closeBtn);

  const cardBox = element('div', undefined, 'practice-card');
  const sideEl = element('div', 'PROMPT (FRONT)', 'card-side');
  const textEl = element('div', '', 'card-text');
  const hintEl = element('div', 'Click or press Space to flip', 'card-hint');
  cardBox.append(sideEl, textEl, hintEl);

  function flip() {
    flipped = !flipped;
    sideEl.textContent = flipped ? 'ANSWER (BACK)' : 'PROMPT (FRONT)';
    textEl.textContent = flipped ? cards[index].back : cards[index].front;
    cardBox.style.borderColor = flipped ? 'var(--rose)' : 'var(--line)';
  }
  cardBox.addEventListener('click', flip);

  const nav = element('div', undefined, 'practice-nav');
  const prevBtn = element('button', '← Previous');
  prevBtn.addEventListener('click', () => { if (index > 0) { index--; update(); } });
  const flipBtn = element('button', 'Flip card ⤾', 'primary');
  flipBtn.addEventListener('click', flip);
  const nextBtn = element('button', 'Next →');
  nextBtn.addEventListener('click', () => { if (index < cards.length - 1) { index++; update(); } });
  nav.append(prevBtn, flipBtn, nextBtn);

  function update() {
    flipped = false;
    cardBox.style.borderColor = 'var(--line)';
    sideEl.textContent = 'PROMPT (FRONT)';
    textEl.textContent = cards[index].front;
    countEl.textContent = `${title} · Card ${index + 1} of ${cards.length}`;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === cards.length - 1;
  }

  dialog.append(header, cardBox, nav);
  overlay.append(dialog);
  document.body.append(overlay);
  practiceModal = overlay;

  function onKeyDown(e) {
    if (!practiceModal) { window.removeEventListener('keydown', onKeyDown); return; }
    if (e.key === 'Escape') closePractice();
    else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); flip(); }
    else if (e.key === 'ArrowLeft' && index > 0) { e.preventDefault(); index--; update(); }
    else if (e.key === 'ArrowRight' && index < cards.length - 1) { e.preventDefault(); index++; update(); }
  }
  window.addEventListener('keydown', onKeyDown);
  update();
}

function startQuizPractice(title, questions) {
  closePractice();
  if (!questions.length) return;
  let index = 0, score = 0, answered = false;
  const overlay = element('div', undefined, 'practice-overlay');
  const dialog = element('div', undefined, 'practice-dialog');
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  const header = element('div', undefined, 'practice-header');
  const countEl = element('span', '', 'eyebrow');
  const scoreEl = element('span', 'Score: 0', 'badge');
  const closeBtn = element('button', '✕ Close', 'practice-btn-sm');
  closeBtn.addEventListener('click', closePractice);
  const right = element('div', undefined, 'row');
  right.append(scoreEl, closeBtn);
  header.append(countEl, right);

  const qTitle = element('h2');
  const optionsBox = element('div', undefined, 'quiz-options');
  const feedbackBox = element('div', undefined, 'quiz-feedback');
  feedbackBox.hidden = true;
  const nav = element('div', undefined, 'practice-nav');
  const nextBtn = element('button', 'Next question →', 'primary');
  nextBtn.disabled = true;
  nextBtn.addEventListener('click', () => {
    if (index < questions.length - 1) { index++; renderQ(); }
    else showSummary();
  });
  nav.append(element('div'), nextBtn);

  function renderQ() {
    answered = false;
    feedbackBox.hidden = true;
    feedbackBox.replaceChildren();
    nextBtn.disabled = true;
    const q = questions[index];
    countEl.textContent = `${title} · Question ${index + 1} of ${questions.length}`;
    scoreEl.textContent = `Score: ${score} / ${index}`;
    qTitle.textContent = q.question;
    optionsBox.replaceChildren();
    const opts = (q.options && q.options.length) ? q.options : ['True', 'False'];
    for (const opt of opts) {
      const btn = element('button', opt, 'quiz-option');
      btn.addEventListener('click', () => {
        if (answered) return;
        answered = true;
        const norm = s => String(s).trim().toLowerCase();
        const isCorrect = norm(opt) === norm(q.answer) || norm(opt).startsWith(norm(q.answer)) || norm(q.answer).startsWith(norm(opt));
        if (isCorrect) { btn.classList.add('correct'); score++; }
        else {
          btn.classList.add('incorrect');
          for (const b of optionsBox.children) {
            if (norm(b.textContent) === norm(q.answer) || norm(b.textContent).startsWith(norm(q.answer)) || norm(q.answer).startsWith(norm(b.textContent))) b.classList.add('correct');
          }
        }
        for (const b of optionsBox.children) b.disabled = true;
        scoreEl.textContent = `Score: ${score} / ${index + 1}`;
        feedbackBox.hidden = false;
        feedbackBox.append(element('strong', isCorrect ? '✓ Correct! ' : `✗ Incorrect (Answer: ${q.answer}). `), document.createTextNode(q.explanation || ''));
        nextBtn.disabled = false;
        nextBtn.textContent = index === questions.length - 1 ? 'Finish quiz →' : 'Next question →';
        nextBtn.focus();
      });
      optionsBox.append(btn);
    }
  }

  function showSummary() {
    dialog.replaceChildren();
    dialog.append(element('h2', 'Practice complete!'), element('p', `You scored ${score} out of ${questions.length} (${Math.round(score / questions.length * 100)}%).`));
    const row = element('div', undefined, 'row');
    const retryBtn = element('button', 'Retry quiz', 'primary');
    retryBtn.addEventListener('click', () => startQuizPractice(title, questions));
    const doneBtn = element('button', 'Done');
    doneBtn.addEventListener('click', closePractice);
    row.append(retryBtn, doneBtn);
    dialog.append(row);
  }

  dialog.append(header, qTitle, optionsBox, feedbackBox, nav);
  overlay.append(dialog);
  document.body.append(overlay);
  practiceModal = overlay;

  function onKeyDown(e) {
    if (!practiceModal) { window.removeEventListener('keydown', onKeyDown); return; }
    if (e.key === 'Escape') closePractice();
    else if (e.key === 'Enter' && !nextBtn.disabled) { e.preventDefault(); nextBtn.click(); }
  }
  window.addEventListener('keydown', onKeyDown);
  renderQ();
}

// 6. RENDER NOTES PAGE
function render() {
  if (!$('notes')) return;
  $('notes').replaceChildren();
  if (!study || !study.notes.length) return;
  const query = $('search')?.value.toLowerCase().trim() || '';
  const currentCourse = $('course')?.value || $('sidebar-course-select')?.value || '';
  let count = 0;

  for (const note of study.notes) {
    if (currentCourse && note.course !== currentCourse) continue;
    if (query && !JSON.stringify([note.title, note.course, note.analysis.summary, note.analysis.topics]).toLowerCase().includes(query)) continue;
    count++;
    const card = element('article', undefined, 'panel note');
    card.append(element('span', note.course, 'badge'), element('h2', note.title), element('p', note.unit, 'muted'));
    if (note.analysis.warning) card.append(element('p', note.analysis.warning, 'error'));
    card.append(details('Study summary', [element('p', note.analysis.summary, 'pre')]));

    for (const topic of note.analysis.topics) {
      const section = element('section', undefined, 'topic');
      section.append(element('h3', topic.name));
      const state = study.progress[topicKey(note, topic)] || {};
      const checks = element('div', undefined, 'row');
      for (const [key, label] of [['covered', 'I’ve covered this'], ['weak', 'Needs more practice']]) {
        const wrapper = element('label', undefined, 'check');
        const input = element('input');
        input.type = 'checkbox';
        input.checked = !!state[key];
        input.addEventListener('change', () => {
          study.progress[topicKey(note, topic)] = { ...(study.progress[topicKey(note, topic)] || {}), [key]: input.checked };
          change();
          renderHome();
        });
        wrapper.append(input, document.createTextNode(label));
        checks.append(wrapper);
      }
      section.append(checks);
      const list = element('ul');
      for (const concept of topic.concepts) list.append(element('li', concept));
      section.append(list);
      if (topic.definitions?.length) section.append(details('Key definitions', topic.definitions.map(x => element('p', x))));
      if (topic.prerequisites?.length) section.append(element('p', 'Before this: ' + topic.prerequisites.join(' · '), 'muted'));
      if (topic.source_pages?.length) section.append(element('small', 'Source pages: ' + topic.source_pages.join(', ')));
      for (const v of topic.videos || []) {
        const a = element('a', v.title + ' ↗');
        a.href = 'https://www.youtube.com/watch?v=' + v.id;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        const p = element('p');
        p.append(a, element('small', ' · ' + v.channel), element('br'), document.createTextNode(v.reason));
        section.append(p);
      }
      card.append(section);
    }

    if (note.analysis.quiz?.length) {
      const quizDetails = details('Practice quiz', note.analysis.quiz.map((q, i) => {
        const box = element('section');
        box.append(element('h3', `${i + 1}. ${q.question}`));
        if (q.options?.length) {
          const ul = element('ul');
          for (const option of q.options) ul.append(element('li', option));
          box.append(ul);
        }
        box.append(details('Reveal answer', [element('p', q.answer), element('p', q.explanation, 'muted')]));
        return box;
      }));
      const pBtn = element('button', `⚡ Practice quiz (${note.analysis.quiz.length})`, 'practice-btn-sm primary');
      pBtn.addEventListener('click', e => { e.preventDefault(); startQuizPractice(note.title, note.analysis.quiz); });
      quizDetails.querySelector('summary').append(pBtn);
      card.append(quizDetails);
    }

    if (note.analysis.flashcards?.length) {
      const flashDetails = details('Flashcards', note.analysis.flashcards.map(c => details(c.front, [element('p', c.back)])));
      const pBtn = element('button', `⚡ Practice flashcards (${note.analysis.flashcards.length})`, 'practice-btn-sm primary');
      pBtn.addEventListener('click', e => { e.preventDefault(); startFlashcardPractice(note.title, note.analysis.flashcards); });
      flashDetails.querySelector('summary').append(pBtn);
      card.append(flashDetails);
    }
    $('notes').append(card);
  }
  if (!count) $('notes').append(element('p', 'No matching notes. Try another subject or search.', 'empty'));
}

// 7. RENDER PLANNER PAGE
$('plan')?.addEventListener('click', () => {
  try {
    study.plan = makePlan(study, $('exam').value, $('minutes').value);
    change();
    renderPlan();
    renderHome();
  } catch (error) {
    alert(error.message);
  }
});

function renderPlan() {
  if (!$('schedule')) return;
  $('schedule').replaceChildren();
  if (!study?.plan) return;
  const plan = study.plan;
  if (plan.remaining) $('schedule').append(element('p', `${plan.remaining} minutes do not fit before the exam. Increase daily time or prioritize the most important topics.`, 'error'));
  for (const day of plan.days) {
    if (!day.tasks.length) continue;
    const list = element('ul');
    for (const task of day.tasks) list.append(element('li', `${task.minutes} min · ${task.course} · ${task.topic}`));
    $('schedule').append(details(day.date + ' · ' + day.tasks.reduce((s, t) => s + t.minutes, 0) + ' min', [list]));
  }
}

window.addEventListener('beforeunload', event => {
  if (dirty) {
    event.preventDefault();
    event.returnValue = '';
  }
});
