export const FORMAT = 'studyspace.study.v1';
export const LMS_ORIGIN = 'https://mujlms.manipal.edu';
export const MAX_FILE = 50 * 1024 * 1024;
const text = (value, max = 20000) => String(value ?? '').slice(0, max);
const list = (value, max = 1000) => Array.isArray(value) ? value.slice(0, max) : [];
export const isLab = (name) => String(name).trim().toLowerCase().endsWith('lab');
export function semesterNumber(value) {
  const source = String(value || '').normalize('NFKC').replaceAll('_', ' ');
  const match = source.match(/\bsem(?:ester)?[\s:\-]*(\d{1,2}|XII|XI|VIII|VII|VI|IV|III|II|IX|V|X|I)\b/i) || source.match(/\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+semester\b/i);
  const roman = { I:1, II:2, III:3, IV:4, V:5, VI:6, VII:7, VIII:8, IX:9, X:10, XI:11, XII:12 };
  const n = match ? Number(match[1]) || roman[match[1].toUpperCase()] : null;
  return n >= 1 && n <= 12 ? n : null;
}
export function safeName(value) {
  let name = text(value, 110).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/[. ]+$/g, '').trim() || 'Untitled';
  if (/^(CON|PRN|AUX|NUL|COM\d|LPT\d)(\.|$)/i.test(name)) name = '_' + name;
  return name;
}
export function lmsURL(value) {
  const url = new URL(value, LMS_ORIGIN);
  if (url.origin !== LMS_ORIGIN || url.username || url.password) throw new Error('Only MUJ LMS URLs are allowed.');
  if (!url.pathname.startsWith('/d2l/') && !url.pathname.startsWith('/content/')) throw new Error('Unexpected MUJ resource path.');
  return url.href;
}
export async function hashBytes(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}
export function emptyStudy(semester = 3) { return { format: FORMAT, semester, courses: [], notes: [], progress: {}, plan: null }; }
export function cleanAnalysis(input) {
  if (!input || !Array.isArray(input.topics)) throw new Error('Gemini returned an incomplete analysis. Retry this note.');
  return {
    summary: text(input.summary, 50000), warning: text(input.warning || input.readability_warning),
    topics: list(input.topics).map(t => ({ name: text(t.name, 300), concepts: list(t.concepts, 40).map(x => text(x, 1000)), definitions: list(t.definitions, 40).map(x => text(x, 3000)), prerequisites: list(t.prerequisites, 30).map(x => text(x, 500)), difficulty: ['foundational','intermediate','tricky'].includes(t.difficulty) ? t.difficulty : 'intermediate', source_pages: list(t.source_pages, 100).filter(n => Number.isInteger(n) && n > 0), videos: cleanVideos(t.videos) })).filter(t => t.name),
    quiz: list(input.quiz, 40).map(q => ({ question: text(q.question, 5000), answer: text(q.answer, 10000), explanation: text(q.explanation, 10000), options: list(q.options, 8).map(x => text(x, 2000)) })),
    flashcards: list(input.flashcards, 100).map(c => ({ front: text(c.front, 4000), back: text(c.back, 10000) }))
  };
}
export function cleanVideos(value) {
  return list(value, 3).filter(v => /^[A-Za-z0-9_-]{11}$/.test(v.id)).map(v => ({ id:v.id, title:text(v.title, 500), channel:text(v.channel, 300), reason:text(v.reason, 2000), score:Math.max(0,Math.min(10,Number(v.score)||0)), views:Math.max(0,Number(v.views)||0) }));
}
export function normalizeStudy(input) {
  if (!input || input.format !== FORMAT) throw new Error('This is not a Studyspace browser study file (studyspace.study.v1).');
  const semester = Number(input.semester);
  if (!Number.isInteger(semester) || semester < 1 || semester > 12) throw new Error('Invalid study-file semester.');
  const study = emptyStudy(semester);
  study.courses = list(input.courses, 500).filter(c => !isLab(c.name)).map(c => ({ id:text(c.id, 100), name:text(c.name, 500), semester: Number.isInteger(c.semester) && c.semester >= 1 && c.semester <= 12 ? c.semester : null }));
  study.notes = list(input.notes, 10000).filter(n => !isLab(n.course)).map(n => ({ id:text(n.id, 300), course:text(n.course, 500), unit:text(n.unit, 1000), title:text(n.title, 1000), hash:/^[a-f0-9]{64}$/.test(n.hash) ? n.hash : '', model:text(n.model, 100), analysis:cleanAnalysis(n.analysis) }));
  for (const [key, value] of Object.entries(input.progress || {}).slice(0, 20000)) {
    if (['__proto__','constructor','prototype'].includes(key)) continue;
    study.progress[key] = { covered:!!value?.covered, weak:!!value?.weak };
  }
  // Plan input is reconstructed, never used to build HTML or execute code.
  if (input.plan && /^\d{4}-\d{2}-\d{2}$/.test(input.plan.exam)) {
    study.plan = { exam:input.plan.exam, daily:Math.max(15,Math.min(720,Number(input.plan.daily)||120)), days:list(input.plan.days, 370).map(d => ({ date:text(d.date, 10), tasks:list(d.tasks, 500).map(t => ({ course:text(t.course,500), topic:text(t.topic,500), minutes:Math.max(1,Math.min(720,Number(t.minutes)||30)) })) })), remaining:Math.max(0,Number(input.plan.remaining)||0) };
  }
  return study;
}
export function exportStudy(study) { return JSON.stringify(normalizeStudy(study), null, 2); }
export function topicKey(note, topic) { return note.id + ':' + topic.name.toLowerCase().trim(); }
export function makePlan(study, exam, daily = 120, today = new Date()) {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const end = new Date(exam + 'T00:00:00');
  const count = Math.round((end - start) / 86400000);
  if (!Number.isFinite(count) || count < 1 || count > 366) throw new Error('Choose an exam date between tomorrow and one year from today.');
  daily = Math.max(15, Math.min(720, Number(daily) || 120));
  const tasks = study.notes.flatMap(n => n.analysis.topics.map(t => ({ course:n.course, topic:t.name, state:study.progress[topicKey(n,t)] || {} }))).sort((a,b) => Number(!!b.state.weak)-Number(!!a.state.weak) || Number(!!a.state.covered)-Number(!!b.state.covered));
  if (!tasks.length) throw new Error('Analyze at least one note before making a plan.');
  const queue = [...tasks.map(t => ({...t, minutes:t.state.weak ? 45 : t.state.covered ? 15 : 30})), ...tasks.map(t => ({...t, topic:'Revision · '+t.topic, minutes:15}))];
  const days = Array.from({ length:count }, (_,i) => { const d = new Date(start); d.setDate(d.getDate()+i); return { date:`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`, tasks:[] }; });
  let index = 0;
  for (const day of days) {
    let capacity = daily;
    while (capacity && index < queue.length) {
      const task = queue[index]; const minutes = Math.min(task.minutes, capacity);
      day.tasks.push({ course:task.course, topic:task.topic, minutes });
      task.minutes -= minutes; capacity -= minutes;
      if (!task.minutes) index++;
    }
  }
  return { exam, daily, days, remaining:queue.slice(index).reduce((sum,t)=>sum+t.minutes,0) };
}
