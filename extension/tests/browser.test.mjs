import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { deflateRawSync } from 'node:zlib';
import { semesterNumber,isLab,lmsURL,emptyStudy,normalizeStudy,exportStudy,makePlan,hashBytes } from '../core.mjs';
import { LMS,limitedBytes } from '../lms.mjs';
import { Gemini,ProviderError,findVideos } from '../google.mjs';
import { zipEntries } from '../media.mjs';
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const analysis={summary:'A summary',topics:[{name:'Binary trees',concepts:['Each node has at most two children.']}],quiz:[],flashcards:[]};
test('Roman semester labels and lab exclusion',()=>{
  assert.equal(semesterNumber('BTECH-0005_Sem_III_July_Dec_2026'),3);
  assert.equal(semesterNumber('BTECH-FIRST_Sem_II_Jan_May_2026'),2);
  assert.equal(semesterNumber('CSC2103_JULY_DEC_2026'),null);
  assert.equal(semesterNumber('Semester VIII'),8);
  assert.equal(isLab('Database Systems LAB  '),true);assert.equal(isLab('Collaboration'),false);
});
test('LMS URLs cannot leave MUJ or fetch arbitrary resources',()=>{
  assert.equal(lmsURL('/content/enforced/123/a.pdf'),'https://mujlms.manipal.edu/content/enforced/123/a.pdf');
  for(const value of ['https://evil.test/a','//evil.test/d2l/','https://user:pass@mujlms.manipal.edu/d2l/a','/admin','javascript:alert(1)'])assert.throws(()=>lmsURL(value));
});
test('Export allowlist strips credentials, source URLs, raw files and labs',()=>{
  const study=emptyStudy();Object.assign(study,{key:'PRIVATE_SENTINEL',cookie:'PRIVATE_SENTINEL',courses:[{id:'1',name:'Trees',semester:3},{id:'2',name:'Trees Lab',semester:3}],notes:[{id:'1:1',course:'Trees',title:'Trees.pdf',url:'PRIVATE_SENTINEL',bytes:'PRIVATE_SENTINEL',analysis},{id:'2:1',course:'Trees Lab',analysis}]});
  const value=exportStudy(study);assert.ok(!value.includes('PRIVATE_SENTINEL'));assert.ok(!value.includes('Trees Lab'));assert.equal(normalizeStudy(JSON.parse(value)).notes.length,1);
  assert.throws(()=>normalizeStudy({format:'other'}));
});
test('Planner prioritizes weak topics and reports insufficient time',()=>{
  const study=normalizeStudy({...emptyStudy(),notes:[{id:'1',course:'CS',analysis:{...analysis,topics:[{name:'Covered'},{name:'Weak'},{name:'New'}]}}],progress:{'1:covered':{covered:true},'1:weak':{weak:true}}});
  const plan=makePlan(study,'2026-11-02',30,new Date(2026,10,1));assert.equal(plan.days[0].tasks[0].topic,'Weak');assert.ok(plan.remaining>0);assert.equal(plan.days[0].tasks[0].minutes,30);
  assert.throws(()=>makePlan(study,'2026-10-30',30,new Date(2026,10,1)));
});
test('Discovery uses explicit semester parent and never visits labs',async()=>{
  const urls=[];const lms=new LMS(async url=>{
    urls.push(url);
    if(url.endsWith('/versions/'))return json([{ProductCode:'lp',LatestVersion:'1.50'},{ProductCode:'le',LatestVersion:'1.90'}]);
    if(url.includes('myenrollments/'))return json({Items:[{OrgUnit:{Id:1,Name:'Algorithms'}},{OrgUnit:{Id:2,Name:'Algorithms Lab'}}]});
    if(url.includes('/parents?'))return json([{CourseOfferingId:1,Semesters:[{Name:'BTECH_Sem_III_2026'}]}]);
    if(url.endsWith('/content/toc'))return json({Modules:[{Title:'Unit 1',Topics:[{Id:3,Title:'Trees',Url:'/content/enforced/1/trees.pdf'},{Id:4,Url:'https://evil.test/file'},{Id:5,Url:'/d2l/link',Type:3}],Modules:[]}]});
    throw new Error('Unexpected URL '+url);
  });
  const courses=await lms.discover();assert.equal(courses.length,1);assert.equal(courses[0].semester,3);
  const files=await lms.files(courses[0]);assert.equal(files.length,1);assert.equal(files[0].unit,'Unit 1');assert.deepEqual(await lms.files({id:2,name:'Algorithms Lab'}),[]);assert.ok(!urls.some(u=>u.includes('/2/content/')));
});
test('Expired sessions and oversized streams fail clearly',async()=>{
  await assert.rejects(new LMS(async()=>json({},401)).discover(),/sign into MUJ/);
  await assert.rejects(limitedBytes(new Response('123456'),3),/size limit/);
  await assert.rejects(new LMS(async()=>new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}})).discover(),/login page/);
});
test('Gemini output rejects truncation and preserves provider status without leaking keys',async()=>{
  const key='PRIVATE_SENTINEL';const gemini=new Gemini(key,'model-test',async(url,options)=>{assert.equal(options.headers['x-goog-api-key'],key);return json({error:{message:key}},429);});
  await assert.rejects(gemini.json('prompt'),error=>error instanceof ProviderError&&error.status===429&&!error.message.includes(key));
  const truncated=new Gemini(key,'model-test',async()=>json({candidates:[{finishReason:'MAX_TOKENS'}]}));await assert.rejects(truncated.json('prompt'),/truncated/);
});
test('PDF analysis reads bytes and validates structured output',async()=>{
  const gemini=new Gemini('test-key','model-test',async(url,options)=>{
    const body=JSON.parse(options.body);assert.equal(body.contents[0].parts[1].inlineData.mimeType,'application/pdf');
    return json({candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify(analysis)}]}}]});
  });
  assert.equal((await gemini.analyze({title:'Trees.pdf',course:'CS',bytes:new TextEncoder().encode('%PDF-test')})).topics[0].name,'Binary trees');
  assert.equal((await hashBytes(new TextEncoder().encode('a'))).length,64);
});
test('Video ranking cannot invent IDs and rejects weak results',async()=>{
  const result=await findVideos({name:'Trees',concepts:[]},'CS','test-key',{json:async()=>({videos:[{id:'abcdefghijk',score:9,reason:'Specific tutorial'},{id:'zzzzzzzzzzz',score:10},{id:'12345678901',score:2}]})},async url=>url.includes('/search?')?json({items:[{id:{videoId:'abcdefghijk'},snippet:{title:'Trees',channelTitle:'Teaching',description:'BST'}},{id:{videoId:'12345678901'},snippet:{title:'Other',channelTitle:'Other'}}]}):json({items:[{id:'abcdefghijk',statistics:{viewCount:'100'},contentDetails:{duration:'PT10M'}}]}));
  assert.equal(result.length,1);assert.equal(result[0].id,'abcdefghijk');assert.equal(result[0].views,100);
});
function officeZip(content,claimedSize=content.length){
  const name=Buffer.from('word/document.xml'),bytes=deflateRawSync(content),local=Buffer.alloc(30),directory=Buffer.alloc(46),end=Buffer.alloc(22);
  local.writeUInt32LE(0x04034b50);local.writeUInt16LE(8,8);local.writeUInt16LE(name.length,26);
  directory.writeUInt32LE(0x02014b50);directory.writeUInt16LE(8,10);directory.writeUInt32LE(bytes.length,20);directory.writeUInt32LE(claimedSize,24);directory.writeUInt16LE(name.length,28);
  end.writeUInt32LE(0x06054b50);end.writeUInt16LE(1,10);end.writeUInt32LE(46+name.length,12);end.writeUInt32LE(30+name.length+bytes.length,16);
  return Buffer.concat([local,name,bytes,directory,name,end]);
}
test('Office decompression is bounded by declared and maximum sizes',async()=>{
  const bytes=Buffer.from('<xml>text</xml>');assert.equal(new TextDecoder().decode((await zipEntries(officeZip(bytes))).get('word/document.xml')),bytes.toString());
  await assert.rejects(zipEntries(officeZip(Buffer.alloc(100000,65),1)),/size limit/);
});
test('Manifest contains scoped permissions and explicit hosts without blanket wildcards',async()=>{
  const manifest=JSON.parse(await readFile(new URL('../manifest.json',import.meta.url),'utf8'));
  assert.deepEqual(manifest.permissions.sort(),['downloads','storage']);assert.equal(manifest.host_permissions.length,3);assert.ok(manifest.content_scripts.length>=1);assert.ok(!manifest.externally_connectable);
});
