const button=document.getElementById('theme');
function getThemeIcon(light){
  if(light){
    return `
      <svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3.5v2.2M12 18.3v2.2M5.5 12h-2.2M20.7 12h-2.2M6.7 6.7l-1.5-1.5M18.8 18.8l-1.5-1.5M17.3 6.7l1.5-1.5M5.2 18.8l1.5-1.5"/>
        <circle cx="12" cy="12" r="4.2"/>
      </svg>
    `;
  }
  return `
    <svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M19 14.4A7.4 7.4 0 0 1 9.6 5a7.4 7.4 0 1 0 9.4 9.4Z"/>
    </svg>
  `;
}
function update(){
  if(!button)return;
  const light=document.body.classList.contains('light');
  button.innerHTML=getThemeIcon(light);
  button.setAttribute('aria-label',light?'Switch to dark mode':'Switch to light mode');
}
try{document.body.classList.toggle('light',localStorage.getItem('studyspace-web-theme')==='light');}catch{/* optional */}update();
button?.addEventListener('click',()=>{const light=document.body.classList.toggle('light');update();try{localStorage.setItem('studyspace-web-theme',light?'light':'dark');}catch{/* optional */}});
if('serviceWorker' in navigator && location.protocol.startsWith('http')){
  window.addEventListener('load',()=>{navigator.serviceWorker.register('sw.js').catch(()=>{});});
}
