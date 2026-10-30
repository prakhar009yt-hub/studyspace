import { MAX_FILE } from './core.mjs';

// Read only supported ZIP members using the browser's native decompressor.
// No remote JavaScript, native process, or executable document content.
export async function zipEntries(bytes) {
  const data = new Uint8Array(bytes); const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let footer = -1;
  for (let i=data.length-22; i>=Math.max(0,data.length-65557); i--) if (view.getUint32(i,true)===0x06054b50) {footer=i;break;}
  if (footer < 0) throw new Error('Invalid Office ZIP file. Export this document to PDF.');
  const count=view.getUint16(footer+10,true); let pos=view.getUint32(footer+16,true); let total=0;
  if (count>10000) throw new Error('Office document contains too many entries. Export to PDF.');
  const entries = new Map();
  for (let i=0;i<count;i++) {
    if (pos+46>data.length || view.getUint32(pos,true)!==0x02014b50) throw new Error('Invalid Office ZIP directory.');
    const flags=view.getUint16(pos+8,true), method=view.getUint16(pos+10,true), compressed=view.getUint32(pos+20,true), size=view.getUint32(pos+24,true), nameLength=view.getUint16(pos+28,true), extra=view.getUint16(pos+30,true), comment=view.getUint16(pos+32,true), offset=view.getUint32(pos+42,true);
    if (pos+46+nameLength+extra+comment>data.length) throw new Error('Truncated ZIP directory.');
    const name=new TextDecoder().decode(data.subarray(pos+46,pos+46+nameLength)); pos+=46+nameLength+extra+comment;
    if (!/^(word\/document\.xml|ppt\/slides\/slide\d+\.xml|ppt\/media\/[^/]+\.(png|jpe?g|webp))$/i.test(name)) continue;
    if (flags & 1 || size>MAX_FILE || (total+=size)>MAX_FILE*2) throw new Error('Encrypted or oversized Office document. Export to PDF.');
    if (offset+30>data.length || view.getUint32(offset,true)!==0x04034b50) throw new Error('Invalid Office ZIP entry.');
    const start=offset+30+view.getUint16(offset+26,true)+view.getUint16(offset+28,true);
    if (start+compressed>data.length) throw new Error('Truncated Office document.');
    let value=data.subarray(start,start+compressed);
    if (method===8) {
      const reader=new Blob([value]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader();
      const chunks=[]; let length=0;
      try {
        while (true) {
          const chunk=await reader.read(); if (chunk.done) break;
          length+=chunk.value.length;
          if (length>size || length>MAX_FILE) { await reader.cancel(); throw new Error('Office decompression size limit exceeded.'); }
          chunks.push(chunk.value);
        }
      } finally { reader.releaseLock(); }
      value=new Uint8Array(length); let position=0;
      for (const chunk of chunks) { value.set(chunk,position); position+=chunk.length; }
    }
    else if (method!==0) throw new Error('Unsupported Office compression. Export to PDF.');
    if (value.length!==size) throw new Error('Office document size check failed.');
    entries.set(name,value);
  }
  return entries;
}
export function base64(bytes) {
  const data=new Uint8Array(bytes); let value='';
  for(let i=0;i<data.length;i+=16384) value+=String.fromCharCode(...data.subarray(i,i+16384));
  return btoa(value);
}
export async function mediaParts(file) {
  if (file.bytes.byteLength>MAX_FILE) throw new Error('This test version supports files up to 50 MB. Split larger PDFs first.');
  const extension=file.title.toLowerCase().split('.').pop();
  if (extension==='pdf' || file.mime?.includes('pdf')) return [{ inlineData:{ mimeType:'application/pdf', data:base64(file.bytes) } }];
  if (['txt','md'].includes(extension)) return [{ text:new TextDecoder().decode(file.bytes) }];
  if (!['docx','pptx'].includes(extension)) throw new Error('Use PDF, PPTX, DOCX, TXT or MD. Convert older DOC/PPT files to PDF.');
  const entries=await zipEntries(file.bytes); const parts=[];
  const names=[...entries.keys()].filter(x=>x.endsWith('.xml')).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  for (const name of names) {
    const xml=new DOMParser().parseFromString(new TextDecoder().decode(entries.get(name)),'application/xml');
    if (xml.querySelector('parsererror')) throw new Error('Could not read Office document XML. Export to PDF.');
    const texts=[...xml.getElementsByTagNameNS('*','t')].map(n=>n.textContent).join(' ');
    parts.push({text:`${name}: ${texts}`});
  }
  let imageBytes=0;
  for (const [name,bytes] of entries) if (!name.endsWith('.xml')) {
    if ((imageBytes+=bytes.length)>8*1024*1024) break;
    parts.push({text:'Embedded slide image: '+name}, {inlineData:{mimeType:/\.png$/i.test(name)?'image/png':/\.webp$/i.test(name)?'image/webp':'image/jpeg',data:base64(bytes)}});
  }
  if (!parts.length) throw new Error('No readable document content. Export to PDF.');
  parts.unshift({text:'Office text extraction: slide image relationships, animations and vector diagrams may be incomplete. Flag uncertain or missing diagrams; do not invent content. PDF export gives best fidelity.'});
  return parts;
}
