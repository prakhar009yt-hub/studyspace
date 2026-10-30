const tabs=[...document.querySelectorAll('[data-platform]')];
function select(platform,focus=false){
  for(const tab of tabs){const active=tab.dataset.platform===platform;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;document.getElementById(tab.getAttribute('aria-controls')).hidden=!active;if(active&&focus)tab.focus();}
  document.getElementById('download-extension').textContent=`Download for ${platform==='mac'?'Mac':'Windows'} ↓`;
}
for(const tab of tabs){tab.addEventListener('click',()=>select(tab.dataset.platform));tab.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const platform=event.key==='Home'?'windows':event.key==='End'?'mac':tab.dataset.platform==='mac'?'windows':'mac';select(platform,true);}});}
