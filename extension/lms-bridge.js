// Studyspace LMS Content Bridge - runs natively inside https://mujlms.manipal.edu/*
(function () {
  'use strict';

  function isLoggedIn() {
    return Boolean(
      document.querySelector('d2l-navigation') ||
      document.querySelector('.d2l-navigation-s-header') ||
      document.querySelector('a[href*="/logout"]') ||
      document.querySelector('a[href*="logout.d2l"]') ||
      location.pathname.startsWith('/d2l/home') ||
      (document.title && document.title.includes('Homepage'))
    );
  }

  function reportStatus() {
    const loggedIn = isLoggedIn();
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.set({
        muj_logged_in: loggedIn,
        muj_last_seen: Date.now()
      }).catch(() => {});
    }
    if (loggedIn) {
      injectIndicator();
    }
  }

  function injectIndicator() {
    if (document.getElementById('studyspace-lms-pill')) return;
    const pill = document.createElement('div');
    pill.id = 'studyspace-lms-pill';
    pill.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:999999;background:#0d1520;color:#edf7ff;border:1px solid #007ba7;border-radius:100px;padding:8px 16px;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;font-weight:600;box-shadow:0 8px 30px rgba(0,0,0,0.5);display:flex;align-items:center;gap:10px;animation:studyspaceEnter 0.3s ease;';

    const text = document.createElement('span');
    text.innerHTML = '<span style="color:#35bee0">✦</span> Studyspace Active';

    const link = document.createElement('a');
    link.href = (typeof chrome !== 'undefined' && chrome.runtime?.getURL) ? chrome.runtime.getURL('app.html') : 'https://studyspace-amber-seven.vercel.app/study.html';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open Study Workspace ↗';
    link.style.cssText = 'color:#35bee0;text-decoration:none;background:#007ba733;padding:4px 10px;border-radius:20px;transition:background 0.2s;';
    link.onmouseenter = () => { link.style.background = '#007ba766'; };
    link.onmouseleave = () => { link.style.background = '#007ba733'; };

    const close = document.createElement('button');
    close.textContent = '✕';
    close.title = 'Dismiss';
    close.style.cssText = 'background:none;border:none;color:#8899a6;cursor:pointer;font-size:12px;padding:2px 4px;margin-left:4px;';
    close.onclick = () => pill.remove();

    pill.append(text, link, close);
    document.body.append(pill);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reportStatus);
  } else {
    reportStatus();
  }
})();
