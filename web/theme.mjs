const button = document.getElementById('theme');

function getThemeIcon(light) {
  if (light) {
    return `<svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true" style="width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;display:block">
      <path d="M12 3v2.5M12 18.5V21M4.2 4.2l1.8 1.8M18 18l1.8 1.8M3 12h2.5M18.5 12H21M4.2 19.8l1.8-1.8M18 6l1.8-1.8"/>
      <circle cx="12" cy="12" r="4"/>
    </svg>`;
  }
  return `<svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true" style="width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;display:block">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
  </svg>`;
}

function update() {
  if (!button) return;
  const light = document.body.classList.contains('light');

  const iconSpan = document.getElementById('theme-icon');
  const modeText = document.getElementById('theme-mode-text');

  if (iconSpan && modeText) {
    iconSpan.innerHTML = getThemeIcon(light);
    modeText.textContent = light ? 'Light mode' : 'Dark mode';
    button.setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
    return;
  }

  button.innerHTML = getThemeIcon(light);
  button.setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
}

try {
  const saved = localStorage.getItem('studyspace-web-theme');
  document.body.classList.toggle('light', saved === 'light');
} catch {}
update();

button?.addEventListener('click', () => {
  const light = document.body.classList.toggle('light');
  update();
  try {
    localStorage.setItem('studyspace-web-theme', light ? 'light' : 'dark');
  } catch {}
});

if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  });
}
