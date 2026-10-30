const button=document.getElementById('theme');
function update(){if(!button)return;const light=document.body.classList.contains('light');button.textContent=light?'☾':'☀';button.setAttribute('aria-label',light?'Switch to dark mode':'Switch to light mode');}
try{document.body.classList.toggle('light',localStorage.getItem('studyspace-web-theme')==='light');}catch{/* optional */}update();
button?.addEventListener('click',()=>{const light=document.body.classList.toggle('light');update();try{localStorage.setItem('studyspace-web-theme',light?'light':'dark');}catch{/* optional */}});
