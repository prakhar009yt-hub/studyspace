import { normalizeStudy, exportStudy, topicKey, makePlan } from './study-core.mjs';
import { demoStudy } from './demo.mjs';
const $=id=>document.getElementById(id);let study,dirty=false;
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function change(){dirty=true;$('status').textContent='Unsaved changes. Save a new study JSON to keep your progress and plan.';}
function details(title,content){const el=element('details');el.append(element('summary',title));for(const c of content)el.append(c);return el;}
function loadStudy(input,name){
    const next=normalizeStudy(input);study=next;dirty=false;
    $('workspace').hidden=false;$('empty').hidden=true;$('save').disabled=false;
    $('course').replaceChildren(new Option('All subjects',''));
    const names=[...new Set(study.notes.map(n=>n.course))].sort();for(const name of names)$('course').add(new Option(name,name));
    const count=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
    $('stats').textContent=`Semester ${study.semester} · ${count(names.length,'subject')} · ${count(study.notes.length,'analyzed note')} · ${count(study.notes.reduce((s,n)=>s+n.analysis.topics.length,0),'topic')}`;
    $('status').textContent=`Opened ${name}. This file stays in your browser tab.`;$('search').value='';$('exam').value=study.plan?.exam||'';$('minutes').value=study.plan?.daily||120;
    render();renderPlan();
}
async function openFile(file){
  try{
    if(!file)return;if(file.size>30*1024*1024)throw new Error('Study file exceeds the 30 MB limit.');
    if(dirty&&!confirm('Replace unsaved changes with this study file?'))return;
    loadStudy(JSON.parse(await file.text()),file.name);
  }catch(error){$('status').textContent='Could not open file: '+error.message;}
}
$('open').addEventListener('change',async event=>{
  await openFile(event.target.files[0]);event.target.value='';
});
const drop=$('empty');
for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('dragging');});
for(const name of ['dragleave','drop'])drop.addEventListener(name,()=>drop.classList.remove('dragging'));
drop.addEventListener('drop',event=>{event.preventDefault();if(event.dataTransfer.files.length!==1){$('status').textContent='Drop one study JSON at a time.';return;}openFile(event.dataTransfer.files[0]);});
$('demo').addEventListener('click',()=>loadStudy(structuredClone(demoStudy),'example workspace · synthetic data'));
if(new URLSearchParams(location.search).get('demo')==='1')loadStudy(structuredClone(demoStudy),'example workspace · synthetic data');
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&study){event.preventDefault();$('search').focus();}});
$('save').addEventListener('click',()=>{
  if(!study)return;const url=URL.createObjectURL(new Blob([exportStudy(study)],{type:'application/json'}));const a=element('a');a.href=url;a.download=`Studyspace-semester-${study.semester}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);dirty=false;$('status').textContent='Download requested. Check your Downloads folder for the updated study file.';
});
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
    if(note.analysis.quiz.length)card.append(details('Practice quiz',note.analysis.quiz.map((q,i)=>{
      const box=element('section');box.append(element('h3',`${i+1}. ${q.question}`));if(q.options.length){const ul=element('ul');for(const option of q.options)ul.append(element('li',option));box.append(ul);}box.append(details('Reveal answer',[element('p',q.answer),element('p',q.explanation,'muted')]));return box;
    })));
    if(note.analysis.flashcards.length)card.append(details('Flashcards',note.analysis.flashcards.map(c=>details(c.front,[element('p',c.back)]))));
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
