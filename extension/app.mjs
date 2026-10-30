import { LMS } from './lms.mjs';
import { Gemini, ProviderError, findVideos } from './google.mjs';
import { emptyStudy, normalizeStudy, exportStudy, safeName, hashBytes, isLab } from './core.mjs';
const $=id=>document.getElementById(id);
const lms=new LMS(); let courses=[],study=emptyStudy(),busy=false,stopped=false,dirty=false;
function log(message,error=false) {
  const item=document.createElement('li'); item.textContent=new Date().toLocaleTimeString()+' · '+message; if(error)item.className='error';
  $('log').prepend(item); if($('log').children.length>200)$('log').lastChild.remove();
  $('stage').textContent=message;
  if(error)$('log').parentElement.open=true;
}
function changed(){dirty=true;$('saved').textContent='Unsaved changes. Save your study JSON before closing.';}
function lock(value){busy=value;for(const id of ['connect','sync','videos','semester','import','save'])$(id).disabled=value;for(const select of $('courses').querySelectorAll('select'))select.disabled=value;$('stop').disabled=!value;}
function action(id,fn){$(id).addEventListener('click',async()=>{if(busy)return;lock(true);stopped=false;try{await fn();}catch(error){log(error instanceof TypeError?'Network request failed. Check your connection, optional host access, and MUJ login.':error.message,true);}finally{lock(false);}});}
async function permission(origins){if(!await chrome.permissions.request({origins}))throw new Error('Host access was declined. Click again and allow only the listed sites to continue.');}
for(let i=1;i<=12;i++){const option=new Option('Semester '+i,String(i));$('semester').add(option);}$('semester').value='3';
function drawCourses(){
  $('courses').replaceChildren();
  for(const course of courses){
    const row=document.createElement('div');row.className='course';const name=document.createElement('span');name.textContent=course.name;
    const select=document.createElement('select');select.setAttribute('aria-label','Semester for '+course.name);select.add(new Option('Not assigned',''));
    for(let i=1;i<=12;i++)select.add(new Option('Semester '+i,String(i)));select.value=course.semester?String(course.semester):'';
    select.addEventListener('change',()=>{course.semester=Number(select.value)||null;study.courses=courses;changed();});row.append(name,select);$('courses').append(row);
  }
}
action('connect',async()=>{
  await permission(['https://mujlms.manipal.edu/*']);log('Reading your enrolled subjects…');
  courses=await lms.discover(log);study.courses=courses;drawCourses();changed();
  log(`Found ${courses.length} non-lab subjects. ${courses.filter(c=>!c.semester).length} need a semester assignment.`);
});
$('semester').addEventListener('change',()=>{
  if(study.notes.length&&!confirm('Start a separate study file for this semester? Save your current JSON first. Unsaved notes and progress will be removed from this tab.')){$('semester').value=String(study.semester);return;}
  study=emptyStudy(Number($('semester').value));study.courses=courses;changed();
});
$('stop').addEventListener('click',()=>{stopped=true;log('Stopping after the current requests. Save your partial study file.');});
async function saveBlob(blob,filename){
  const url=URL.createObjectURL(blob);
  try {
    const id=await chrome.downloads.download({url,filename,saveAs:true});
    await new Promise((resolve,reject)=>{
      const onChange=delta=>{if(delta.id!==id)return;if(delta.state?.current==='complete'){chrome.downloads.onChanged.removeListener(onChange);resolve();}else if(delta.state?.current==='interrupted'){chrome.downloads.onChanged.removeListener(onChange);reject(new Error('Download cancelled or interrupted.'));}};
      chrome.downloads.onChanged.addListener(onChange);
      chrome.downloads.search({id}).then(items=>{const state=items[0]?.state;if(['complete','interrupted'].includes(state))onChange({id,state:{current:state}});});
    });
  }finally{URL.revokeObjectURL(url);}
}
$('save').addEventListener('click',async()=>{
  try{await saveBlob(new Blob([exportStudy(study)],{type:'application/json'}),`Studyspace-semester-${study.semester}.json`);dirty=false;$('saved').textContent='Save requested. Check your Downloads folder; save again after further changes.';}
  catch(error){log('Study file was not saved: '+error.message,true);}
});
$('import').addEventListener('change',async event=>{
  try{
    const file=event.target.files[0];if(!file)return;if(file.size>30*1024*1024)throw new Error('Study file exceeds 30 MB.');
    if(dirty && !confirm('Replace unsaved study data with this file?'))return;
    study=normalizeStudy(JSON.parse(await file.text()));courses=study.courses;$('semester').value=String(study.semester);drawCourses();dirty=false;log(`Opened ${study.notes.length} analyzed notes. Connect MUJ again before syncing.`);
  }catch(error){log(error.message,true);}finally{event.target.value='';}
});
function client(){return new Gemini($('gemini').value,$('model').value.trim());}
action('sync',async()=>{
  if(!$('consent').checked)throw new Error('Confirm that selected notes may be sent to Gemini.');
  const gemini=client();
  await permission(['https://mujlms.manipal.edu/*','https://generativelanguage.googleapis.com/*']);
  if(!lms.versions)throw new Error('Click Find my subjects to connect MUJ first.');
  const selected=courses.filter(c=>c.semester===Number($('semester').value)&&!isLab(c.name));
  if(!selected.length)throw new Error('No subjects assigned to this semester. Check the semester assignments above.');
  let files=[];
  for(const course of selected){if(stopped)break;log('Reading folders: '+course.name);try{files.push(...await lms.files(course));}catch(error){log(course.name+': '+error.message,true);}}
  files=[...new Map(files.map(f=>[f.id,f])).values()];
  if(!files.length)throw new Error(stopped?'Stopped.':'No downloadable files found. Check the activity log and LMS access.');
  let index=0,downloaded=0,analyzed=0,cached=0,errors=0,finished=0,analysisBlocked=false;const start=Date.now(),active=new Map();
  const progress=()=>{
    $('counts').textContent=`${downloaded}/${files.length} fetched · ${analyzed} analyzed · ${cached} reused · ${errors} errors`;
    $('progress').max=files.length;$('progress').value=finished;
    const seconds=finished?(Date.now()-start)/1000/finished*(files.length-finished):null;
    $('eta').textContent=(seconds===null?'Estimating…':`About ${Math.ceil(seconds/60)} min remaining (rough estimate).`)+(active.size?' Active: '+[...active.values()].join(' · '):'');
  };
  const timer=setInterval(progress,1000);
  async function worker(slot){
    while(index<files.length&&!stopped){
      const file=files[index++];active.set(slot,'Fetching '+file.title);progress();
      try{
        const fetched=await lms.download(file);downloaded++;const hash=await hashBytes(fetched.bytes);
        if($('originals').checked){const url=URL.createObjectURL(new Blob([fetched.bytes],{type:fetched.mime}));try{await chrome.downloads.download({url,filename:`Studyspace/Semester-${study.semester}/${safeName(file.course)}/${safeName(fetched.title)}`,conflictAction:'uniquify'});}catch{log('Could not save original: '+file.title,true);}finally{setTimeout(()=>URL.revokeObjectURL(url),60000);}}
        const prior=study.notes.find(n=>n.id===file.id);
        if(prior?.hash===hash&&prior.model===gemini.model){cached++;continue;}
        if(analysisBlocked){errors++;log('Analysis deferred after provider error: '+file.title,true);continue;}
        active.set(slot,'Analyzing '+file.title);progress();
        const analysis=await gemini.analyze(fetched,message=>{active.set(slot,file.title+': '+message);progress();});
        const note={id:file.id,course:file.course,unit:file.unit,title:file.title,hash,model:gemini.model,analysis};
        const position=study.notes.findIndex(n=>n.id===file.id);if(position>=0)study.notes[position]=note;else study.notes.push(note);
        analyzed++;changed();log('Analyzed '+file.title);
      }catch(error){errors++;if(error instanceof ProviderError && [400,401,403,404,429].includes(error.status)){analysisBlocked=true;log(error.message+' Further analysis paused; remaining originals can still be fetched.',true);}else log(file.title+': '+error.message,true);}
      finally{finished++;active.delete(slot);progress();}
    }
  }
  try{await Promise.all([worker(1),worker(2)]);}finally{clearInterval(timer);progress();}
  $('eta').textContent=stopped?'Stopped. Import your saved JSON before resuming.':'Finished. Errors and deferred files can be retried by syncing again.';
  log(`${stopped?'Stopped':'Sync finished'}: ${downloaded} fetched, ${analyzed} analyzed, ${cached} reused, ${errors} errors. Save your study JSON.`);
});
action('videos',async()=>{
  const key=$('youtube').value.trim();if(!key)throw new Error('Enter your YouTube Data API v3 key.');
  const gemini=client();await permission(['https://generativelanguage.googleapis.com/*','https://www.googleapis.com/*']);
  const names=new Set(courses.filter(c=>c.semester===study.semester).map(c=>c.name));let done=0;
  for(const note of study.notes.filter(n=>names.has(n.course)))for(const topic of note.analysis.topics){
    if(stopped)break;if(topic.videos.length)continue;log('Finding video candidates: '+topic.name);
    topic.videos=await findVideos(topic,note.course,key,gemini);changed();done++;log(`${topic.name}: ${topic.videos.length} suitable videos.`);
  }
  log(`Video lookup finished for ${done} topics. Save your study JSON.`);
});
function theme(){const light=document.body.classList.contains('light');$('theme').textContent=light?'☾':'☀';$('theme').setAttribute('aria-label',light?'Switch to dark mode':'Switch to light mode');}
$('theme').addEventListener('click',()=>{document.body.classList.toggle('light');theme();});theme();
window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='';}});
