import { normalizeStudy, exportStudy, topicKey, makePlan } from './study-core.mjs';
import { demoStudy } from './demo.mjs';
const $=id=>document.getElementById(id);let study,dirty=false,currentFileHandle=null;
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function change(){dirty=true;$('status').textContent='Unsaved changes. Save to rewrite/update your study file.';}
function details(title,content){const el=element('details');el.append(element('summary',title));for(const c of content)el.append(c);return el;}
function loadStudy(input,name,handle=null){
    const next=normalizeStudy(input);study=next;dirty=false;currentFileHandle=handle;
    $('workspace').hidden=false;$('empty').hidden=true;$('save').disabled=false;
    $('course').replaceChildren(new Option('All subjects',''));
    const names=[...new Set(study.notes.map(n=>n.course))].sort();for(const name of names)$('course').add(new Option(name,name));
    const count=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
    $('stats').textContent=`Semester ${study.semester} · ${count(names.length,'subject')} · ${count(study.notes.length,'analyzed note')} · ${count(study.notes.reduce((s,n)=>s+n.analysis.topics.length,0),'topic')}`;
    $('status').textContent=`Opened ${name}. ${currentFileHandle?'Saves will update this file in-place.':'This file stays in your browser tab.'}`;$('search').value='';$('exam').value=study.plan?.exam||'';$('minutes').value=study.plan?.daily||120;
    render();renderPlan();
}
function mergeStudy(input,name,handle=null){
  const next=normalizeStudy(input);let added=0,updated=0;
  for(const note of next.notes){
    const pos=study.notes.findIndex(n=>n.id===note.id);
    if(pos>=0){study.notes[pos]=note;updated++;}
    else{study.notes.push(note);added++;}
  }
  for(const course of next.courses){
    if(!study.courses.some(c=>c.name===course.name))study.courses.push(course);
  }
  Object.assign(study.progress,next.progress);
  if(handle)currentFileHandle=handle;
  const names=[...new Set(study.notes.map(n=>n.course))].sort();
  $('course').replaceChildren(new Option('All subjects',''));
  for(const n of names)$('course').add(new Option(n,n));
  const count=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
  $('stats').textContent=`Semester ${study.semester} · ${count(names.length,'subject')} · ${count(study.notes.length,'analyzed note')} · ${count(study.notes.reduce((s,n)=>s+n.analysis.topics.length,0),'topic')}`;
  change();render();renderPlan();
  $('status').textContent=`Merged ${added} new note(s), updated ${updated} existing. Save to rewrite your file.`;
}
async function openFile(file,handle=null){
  try{
    if(!file)return;if(file.size>30*1024*1024)throw new Error('Study file exceeds the 30 MB limit.');
    const parsed=JSON.parse(await file.text());
    if(study&&study.notes.length){
      if(confirm(`A study workspace is already open.\n\nClick OK to APPEND/MERGE notes from "${file.name}" into this file.\nClick Cancel to replace current workspace.`)){
        mergeStudy(parsed,file.name,handle||currentFileHandle);return;
      }
    }
    if(dirty&&!confirm('Replace unsaved changes with this study file?'))return;
    loadStudy(parsed,file.name,handle);
  }catch(error){$('status').textContent='Could not open file: '+error.message;}
}
$('open').addEventListener('change',async event=>{
  await openFile(event.target.files[0]);event.target.value='';
});
$('open').parentElement?.addEventListener('click',async event=>{
  if(window.showOpenFilePicker){
    event.preventDefault();
    try{
      const [handle]=await window.showOpenFilePicker({types:[{description:'Study JSON',accept:{'application/json':['.json']}}],multiple:false});
      const file=await handle.getFile();
      await openFile(file,handle);
    }catch(e){if(e.name!=='AbortError')$('open').click();}
  }
});
const drop=$('empty');
for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('dragging');});
for(const name of ['dragleave','drop'])drop.addEventListener(name,()=>drop.classList.remove('dragging'));
drop.addEventListener('drop',event=>{event.preventDefault();if(event.dataTransfer.files.length!==1){$('status').textContent='Drop one study JSON at a time.';return;}openFile(event.dataTransfer.files[0]);});
$('demo').addEventListener('click',()=>loadStudy(structuredClone(demoStudy),'example workspace · synthetic data'));
if(new URLSearchParams(location.search).get('demo')==='1')loadStudy(structuredClone(demoStudy),'example workspace · synthetic data');
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&study){event.preventDefault();$('search').focus();}});
$('save').addEventListener('click',async()=>{
  if(!study)return;
  const content=exportStudy(study);
  if(currentFileHandle&&window.showSaveFilePicker){
    try{
      const writable=await currentFileHandle.createWritable();
      await writable.write(content);
      await writable.close();
      dirty=false;
      $('status').textContent=`Saved! Updated ${currentFileHandle.name} in-place without creating a new file.`;
      return;
    }catch(e){
      if(e.name==='AbortError')return;
      currentFileHandle=null;
    }
  }
  if(window.showSaveFilePicker){
    try{
      const handle=await window.showSaveFilePicker({suggestedName:`Studyspace-semester-${study.semester}.json`,types:[{description:'Study JSON',accept:{'application/json':['.json']}}]});
      currentFileHandle=handle;
      const writable=await handle.createWritable();
      await writable.write(content);
      await writable.close();
      dirty=false;
      $('status').textContent=`Saved! Further saves will update ${handle.name} in-place.`;
      return;
    }catch(e){if(e.name==='AbortError')return;}
  }
  const url=URL.createObjectURL(new Blob([content],{type:'application/json'}));const a=element('a');a.href=url;a.download=`Studyspace-semester-${study.semester}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);dirty=false;$('status').textContent='Download requested. Check your Downloads folder for the updated study file.';
});
let practiceModal=null;
function closePractice(){if(practiceModal){practiceModal.remove();practiceModal=null;}}
function startFlashcardPractice(title,cards){
  closePractice();if(!cards.length)return;
  let index=0,flipped=false;
  const overlay=element('div',undefined,'practice-overlay');
  const dialog=element('div',undefined,'practice-dialog');dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
  const header=element('div',undefined,'practice-header');
  const countEl=element('span','','eyebrow');
  const closeBtn=element('button','✕ Close','practice-btn-sm');closeBtn.addEventListener('click',closePractice);
  header.append(countEl,closeBtn);
  const cardBox=element('div',undefined,'practice-card');
  const sideEl=element('div','PROMPT (FRONT)','card-side');
  const textEl=element('div','','card-text');
  const hintEl=element('div','Click or press Space to flip','card-hint');
  cardBox.append(sideEl,textEl,hintEl);
  function flip(){
    flipped=!flipped;sideEl.textContent=flipped?'ANSWER (BACK)':'PROMPT (FRONT)';
    textEl.textContent=flipped?cards[index].back:cards[index].front;
    cardBox.style.borderColor=flipped?'var(--rose)':'var(--line)';
  }
  cardBox.addEventListener('click',flip);
  const nav=element('div',undefined,'practice-nav');
  const prevBtn=element('button','← Previous');prevBtn.addEventListener('click',()=>{if(index>0){index--;update();}});
  const flipBtn=element('button','Flip card ⤾','primary');flipBtn.addEventListener('click',flip);
  const nextBtn=element('button','Next →');nextBtn.addEventListener('click',()=>{if(index<cards.length-1){index++;update();}});
  nav.append(prevBtn,flipBtn,nextBtn);
  function update(){
    flipped=false;cardBox.style.borderColor='var(--line)';
    sideEl.textContent='PROMPT (FRONT)';textEl.textContent=cards[index].front;
    countEl.textContent=`${title} · Card ${index+1} of ${cards.length}`;
    prevBtn.disabled=index===0;nextBtn.disabled=index===cards.length-1;
  }
  dialog.append(header,cardBox,nav);overlay.append(dialog);document.body.append(overlay);practiceModal=overlay;
  function onKeyDown(e){
    if(!practiceModal){window.removeEventListener('keydown',onKeyDown);return;}
    if(e.key==='Escape')closePractice();
    else if(e.key===' '||e.key==='Enter'){e.preventDefault();flip();}
    else if(e.key==='ArrowLeft'&&index>0){e.preventDefault();index--;update();}
    else if(e.key==='ArrowRight'&&index<cards.length-1){e.preventDefault();index++;update();}
  }
  window.addEventListener('keydown',onKeyDown);
  update();
}
function startQuizPractice(title,questions){
  closePractice();if(!questions.length)return;
  let index=0,score=0,answered=false;
  const overlay=element('div',undefined,'practice-overlay');
  const dialog=element('div',undefined,'practice-dialog');dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
  const header=element('div',undefined,'practice-header');
  const countEl=element('span','','eyebrow');
  const scoreEl=element('span','Score: 0','badge');
  const closeBtn=element('button','✕ Close','practice-btn-sm');closeBtn.addEventListener('click',closePractice);
  const right=element('div',undefined,'row');right.append(scoreEl,closeBtn);header.append(countEl,right);
  const qTitle=element('h2');
  const optionsBox=element('div',undefined,'quiz-options');
  const feedbackBox=element('div',undefined,'quiz-feedback');feedbackBox.hidden=true;
  const nav=element('div',undefined,'practice-nav');
  const nextBtn=element('button','Next question →','primary');nextBtn.disabled=true;
  nextBtn.addEventListener('click',()=>{if(index<questions.length-1){index++;renderQ();}else showSummary();});
  nav.append(element('div'),nextBtn);
  function renderQ(){
    answered=false;feedbackBox.hidden=true;feedbackBox.replaceChildren();nextBtn.disabled=true;
    const q=questions[index];
    countEl.textContent=`${title} · Question ${index+1} of ${questions.length}`;
    scoreEl.textContent=`Score: ${score} / ${index}`;
    qTitle.textContent=q.question;optionsBox.replaceChildren();
    const opts=(q.options&&q.options.length)?q.options:['True','False'];
    for(const opt of opts){
      const btn=element('button',opt,'quiz-option');
      btn.addEventListener('click',()=>{
        if(answered)return;answered=true;
        const norm=s=>String(s).trim().toLowerCase();
        const isCorrect=norm(opt)===norm(q.answer)||norm(opt).startsWith(norm(q.answer))||norm(q.answer).startsWith(norm(opt));
        if(isCorrect){btn.classList.add('correct');score++;}
        else{
          btn.classList.add('incorrect');
          for(const b of optionsBox.children){
            if(norm(b.textContent)===norm(q.answer)||norm(b.textContent).startsWith(norm(q.answer))||norm(q.answer).startsWith(norm(b.textContent)))b.classList.add('correct');
          }
        }
        for(const b of optionsBox.children)b.disabled=true;
        scoreEl.textContent=`Score: ${score} / ${index+1}`;
        feedbackBox.hidden=false;
        feedbackBox.append(element('strong',isCorrect?'✓ Correct! ':`✗ Incorrect (Answer: ${q.answer}). `),document.createTextNode(q.explanation||''));
        nextBtn.disabled=false;nextBtn.textContent=index===questions.length-1?'Finish quiz →':'Next question →';nextBtn.focus();
      });
      optionsBox.append(btn);
    }
  }
  function showSummary(){
    dialog.replaceChildren();
    dialog.append(element('h2','Practice complete!'),element('p',`You scored ${score} out of ${questions.length} (${Math.round(score/questions.length*100)}%).`));
    const row=element('div',undefined,'row');
    const retryBtn=element('button','Retry quiz','primary');retryBtn.addEventListener('click',()=>startQuizPractice(title,questions));
    const doneBtn=element('button','Done');doneBtn.addEventListener('click',closePractice);
    row.append(retryBtn,doneBtn);dialog.append(row);
  }
  dialog.append(header,qTitle,optionsBox,feedbackBox,nav);overlay.append(dialog);document.body.append(overlay);practiceModal=overlay;
  function onKeyDown(e){
    if(!practiceModal){window.removeEventListener('keydown',onKeyDown);return;}
    if(e.key==='Escape')closePractice();
    else if(e.key==='Enter'&&!nextBtn.disabled){e.preventDefault();nextBtn.click();}
  }
  window.addEventListener('keydown',onKeyDown);
  renderQ();
}
function render(){
  $('notes').replaceChildren();if(!study)return;
  const query=$('search').value.toLowerCase().trim();let count=0;
  for(const note of study.notes){
    if($('course').value&&note.course!==$('course').value)continue;
    if(query&&!JSON.stringify([note.title,note.course,note.analysis.summary,note.analysis.topics]).toLowerCase().includes(query))continue;
    count++;const card=element('article',undefined,'panel note');card.append(element('span',note.course,'badge'),element('h2',note.title),element('p',note.unit,'muted'));
    if(note.analysis.warning)card.append(element('p',note.analysis.warning,'error'));
    card.append(details('Study summary',[element('p',note.analysis.summary,'pre')]));
    for(const topic of note.analysis.topics){
      const section=element('section',undefined,'topic');section.append(element('h3',topic.name));
      const state=study.progress[topicKey(note,topic)]||{};const checks=element('div',undefined,'row');
      for(const [key,label] of [['covered','I’ve covered this'],['weak','Needs more practice']]){
        const wrapper=element('label',undefined,'check');const input=element('input');input.type='checkbox';input.checked=!!state[key];
        input.addEventListener('change',()=>{study.progress[topicKey(note,topic)]={...(study.progress[topicKey(note,topic)]||{}),[key]:input.checked};change();});wrapper.append(input,document.createTextNode(label));checks.append(wrapper);
      }
      section.append(checks);const list=element('ul');for(const concept of topic.concepts)list.append(element('li',concept));section.append(list);
      if(topic.definitions.length)section.append(details('Key definitions',topic.definitions.map(x=>element('p',x))));
      if(topic.prerequisites.length)section.append(element('p','Before this: '+topic.prerequisites.join(' · '),'muted'));
      if(topic.source_pages.length)section.append(element('small','Source pages: '+topic.source_pages.join(', ')));
      for(const v of topic.videos){const a=element('a',v.title+' ↗');a.href='https://www.youtube.com/watch?v='+v.id;a.target='_blank';a.rel='noopener noreferrer';const p=element('p');p.append(a,element('small',' · '+v.channel),element('br'),document.createTextNode(v.reason));section.append(p);}
      card.append(section);
    }
    if(note.analysis.quiz.length){
      const quizDetails=details('Practice quiz',note.analysis.quiz.map((q,i)=>{
        const box=element('section');box.append(element('h3',`${i+1}. ${q.question}`));if(q.options.length){const ul=element('ul');for(const option of q.options)ul.append(element('li',option));box.append(ul);}box.append(details('Reveal answer',[element('p',q.answer),element('p',q.explanation,'muted')]));return box;
      }));
      const pBtn=element('button',`⚡ Practice quiz (${note.analysis.quiz.length})`,'practice-btn-sm primary');
      pBtn.addEventListener('click',e=>{e.preventDefault();startQuizPractice(note.title,note.analysis.quiz);});
      quizDetails.querySelector('summary').append(pBtn);
      card.append(quizDetails);
    }
    if(note.analysis.flashcards.length){
      const flashDetails=details('Flashcards',note.analysis.flashcards.map(c=>details(c.front,[element('p',c.back)])));
      const pBtn=element('button',`⚡ Practice flashcards (${note.analysis.flashcards.length})`,'practice-btn-sm primary');
      pBtn.addEventListener('click',e=>{e.preventDefault();startFlashcardPractice(note.title,note.analysis.flashcards);});
      flashDetails.querySelector('summary').append(pBtn);
      card.append(flashDetails);
    }
    $('notes').append(card);
  }
  if(!count)$('notes').append(element('p','No matching notes. Try another subject or search.','empty'));
}
$('search').addEventListener('input',render);$('course').addEventListener('change',render);
$('plan').addEventListener('click',()=>{try{study.plan=makePlan(study,$('exam').value,$('minutes').value);change();renderPlan();}catch(error){$('status').textContent=error.message;}});
function renderPlan(){
  $('schedule').replaceChildren();if(!study?.plan)return;
  const plan=study.plan;if(plan.remaining)$('schedule').append(element('p',`${plan.remaining} minutes do not fit before the exam. Increase daily time or prioritize the most important topics.`,'error'));
  for(const day of plan.days){if(!day.tasks.length)continue;const list=element('ul');for(const task of day.tasks)list.append(element('li',`${task.minutes} min · ${task.course} · ${task.topic}`));$('schedule').append(details(day.date+' · '+day.tasks.reduce((s,t)=>s+t.minutes,0)+' min',[list]));}
}
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
