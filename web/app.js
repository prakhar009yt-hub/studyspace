const $ = (id) => document.getElementById(id);
let savedTheme;
try { savedTheme = localStorage.getItem('studyspace-web-theme'); } catch { /* Storage may be disabled. */ }
function theme(light) {
  document.body.classList.toggle('light', light);
  $('theme').textContent = light ? '☾' : '☀';
  $('theme').setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
}
theme(savedTheme === 'light');
$('theme').addEventListener('click', () => {
  const light = !document.body.classList.contains('light');
  theme(light);
  try { localStorage.setItem('studyspace-web-theme', light ? 'light' : 'dark'); } catch { /* Theme still works without storage. */ }
});

const backend = window.STUDYSPACE_CONFIG?.backend;
const local = window.STUDYSPACE_CONFIG?.mode === 'local';
if (!backend) {
  $('notice').textContent = 'The workspace connection is not configured. Set STUDYSPACE_BACKEND_URL in the Vercel project and redeploy.';
  $('notice').classList.add('error');
} else {
  for (const id of ['direct', 'fallback']) $(id).href = backend;
  $('direct').hidden = false;
  $('launch').disabled = false;
  if (local) {
    $('local-setup').hidden = false;
    $('direct').textContent = 'Open locally ↗';
    $('connection').textContent = 'Runs on your computer';
    $('launch').textContent = 'Open local workspace ↗';
    document.querySelector('.hint').textContent = 'Start Studyspace.cmd first. This opens your own computer’s workspace in a new tab.';
  }
  $('notice').textContent = local
    ? 'Vercel hosts this website. Your computer runs Studyspace at 127.0.0.1:8765. If the connection is refused, run Studyspace.cmd. No shared cloud backend or VPN is needed.'
    : 'Ready to open. Notes, AI analysis and saved progress run on your connected backend. If the embedded workspace cannot sign in, use Open directly.';
  let slowLoad;
  function loadWorkspace() {
    $('welcome').hidden = true;
    $('footer').hidden = true;
    $('frame-section').hidden = false;
    $('loading').hidden = false;
    $('connection').textContent = 'Connected workspace';
    $('frame-help').hidden = false;
    clearTimeout(slowLoad);
    $('app-frame').src = backend;
    slowLoad = setTimeout(() => {
      $('loading').textContent = 'Still opening? Use Open directly to check your backend or sign in.';
    }, 15000);
  }
  $('app-frame').addEventListener('load', () => {
    clearTimeout(slowLoad);
    // A cross-origin frame load does not prove the server is healthy or signed in.
    $('loading').hidden = true;
  });
  $('launch').addEventListener('click', () => {
    if (local) {
      // User-initiated top-level navigation avoids cross-origin iframe/LNA restrictions.
      window.open(backend, '_blank', 'noopener,noreferrer');
    } else loadWorkspace();
  });
  $('reload').addEventListener('click', loadWorkspace);
}
