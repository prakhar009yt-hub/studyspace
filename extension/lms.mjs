import { lmsURL, isLab, semesterNumber, MAX_FILE } from './core.mjs';

export async function limitedBytes(response, maximum=MAX_FILE) {
  if (Number(response.headers.get('content-length'))>maximum) throw new Error('File is too large (50 MB maximum).');
  const reader=response.body.getReader(), chunks=[]; let size=0;
  try {
    while (true) {
      const {value,done}=await reader.read(); if (done) break;
      size+=value.length;
      if (size>maximum) { await reader.cancel(); throw new Error('Response exceeds the size limit.'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const result=new Uint8Array(size); let offset=0;
  for (const chunk of chunks) { result.set(chunk,offset); offset+=chunk.length; }
  return result;
}
export class LMS {
  constructor(request=fetch) { this.request=request; }
  async response(path) {
    const response=await this.request(lmsURL(path),{credentials:'include',redirect:'error',signal:AbortSignal.timeout(90000)});
    if ([401,403].includes(response.status)) throw new Error(`MUJ HTTP ${response.status}: sign into MUJ in this browser. If this persists, MUJ may require an approved API application; this extension cannot bypass that restriction.`);
    if (!response.ok) throw new Error(`MUJ HTTP ${response.status}. Retry later.`);
    return response;
  }
  async json(path) {
    const response=await this.response(path);
    if (!response.headers.get('content-type')?.includes('json')) throw new Error('MUJ returned a login page instead of data. Sign into MUJ, then reconnect.');
    return JSON.parse(new TextDecoder().decode(await limitedBytes(response,10*1024*1024)));
  }
  async discover(update=()=>{}) {
    const versions=await this.json('/d2l/api/versions/');
    this.versions=Object.fromEntries(versions.map(v=>[v.ProductCode,v.LatestVersion]));
    if (!['lp','le'].every(k=>/^\d+\.\d+$/.test(this.versions[k]))) throw new Error('MUJ did not advertise supported Brightspace API versions.');
    const courses=new Map(), seen=new Set(); let bookmark='';
    do {
      const data=await this.json(`/d2l/api/lp/${this.versions.lp}/enrollments/myenrollments/?orgUnitTypeId=3${bookmark?'&bookmark='+encodeURIComponent(bookmark):''}`);
      for (const item of data.Items||[]) {
        const o=item.OrgUnit;
        if (o && /^\d+$/.test(String(o.Id)) && !isLab(o.Name)) courses.set(String(o.Id),{id:String(o.Id),name:String(o.Name),semester:semesterNumber(`${o.Name} ${o.Code||''}`)});
      }
      if (!data.PagingInfo?.HasMoreItems) break;
      bookmark=data.PagingInfo.Bookmark;
      if (!bookmark || seen.has(bookmark) || seen.size>100) throw new Error('MUJ returned invalid enrollment pagination.');
      seen.add(bookmark);
    } while (true);
    const unknown=[...courses.values()].filter(c=>!c.semester);
    for (let i=0;i<unknown.length;i+=25) {
      update('Reading semester relationships…');
      const batch=unknown.slice(i,i+25);
      for (const endpoint of ['parents','parentorgunits']) {
        try {
          const data=await this.json(`/d2l/api/lp/${this.versions.lp}/courses/${endpoint}?orgUnitIdsCSV=${batch.map(c=>c.id).join(',')}`);
          for (const item of data) {
            const c=courses.get(String(item.CourseOfferingId));
            if (c) c.semester=detect(item.Semesters || [item.Semester]) || c.semester;
          }
          if (batch.every(c=>c.semester)) break;
        } catch (error) { if (/HTTP 401|login page/.test(error.message)) throw error; }
      }
    }
    for (const course of unknown.filter(c=>!c.semester)) {
      update('Checking semester: '+course.name);
      for (const route of [`courses/${course.id}`,`orgstructure/${course.id}/ancestors/`,`enrollments/myenrollments/${course.id}/parentOrgUnits`]) {
        try {
          const data=await this.json(`/d2l/api/lp/${this.versions.lp}/${route}`);
          course.semester=detect(Array.isArray(data)?data:data.Semester?[data.Semester]:(data.Items||[]).map(i=>i.OrgUnit||i));
          if (course.semester) break;
        } catch (error) { if (/HTTP 401|login page/.test(error.message)) throw error; }
      }
    }
    return [...courses.values()];
  }
  async files(course) {
    if (isLab(course.name)) return [];
    const toc=await this.json(`/d2l/api/le/${this.versions.le}/${course.id}/content/toc`);
    const files=[];
    const walk=(modules,parent='')=>{
      for (const module of modules||[]) {
        const unit=[parent,module.Title].filter(Boolean).join(' / ');
        for (const topic of module.Topics||[]) {
          if (Number(topic.Type)===3) continue;
          try {
            const url=lmsURL(topic.Url||topic.URL||'');
            if (!topic.Url && !topic.URL || /\.(mp4|webm|mkv|mp3)(\?|$)/i.test(url)) continue;
            files.push({id:course.id+':'+(topic.Id||url),url,course:course.name,unit,title:topic.Title||'Attachment'});
          } catch { /* External teaching links are never fetched as files. */ }
        }
        walk(module.Modules,unit);
      }
    };
    walk(toc.Modules);
    return [...new Map(files.map(f=>[f.url,f])).values()];
  }
  async download(file) {
    const response=await this.response(file.url);
    const mime=(response.headers.get('content-type')||'').split(';')[0];
    if (/text\/html/.test(mime)) throw new Error('MUJ returned a web page. Open this item in LMS and export its attachment to PDF.');
    let title=file.title;
    const disposition=response.headers.get('content-disposition')||'';
    const match=disposition.match(/filename\*=UTF-8''([^;]+)/i)||disposition.match(/filename="([^"]+)"/i)||disposition.match(/filename=([^;]+)/i);
    if (match) { try { title=decodeURIComponent(match[1]); } catch { title=match[1]; } }
    else if (!/\.(pdf|pptx|docx|txt|md)$/i.test(title)) {
      const ext={ 'application/pdf':'pdf','application/vnd.openxmlformats-officedocument.presentationml.presentation':'pptx','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'docx','text/plain':'txt' }[mime];
      if (ext) title+='.'+ext;
      else { const path=new URL(file.url).pathname; const suffix=path.match(/\.(pdf|pptx|docx|txt|md)$/i); if(suffix) title+=suffix[0]; }
    }
    return {...file,title,mime,bytes:await limitedBytes(response)};
  }
}
function detect(groups) {
  const numbers=new Set(groups.filter(Boolean).map(g=>semesterNumber(`${g.Name||''} ${g.Code||''}`)).filter(Boolean));
  return numbers.size===1?[...numbers][0]:null;
}
