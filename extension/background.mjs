chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: 'https://studyspace-amber-seven.vercel.app/study.html' });
});
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'OPEN_APP') {
    chrome.tabs.create({ url: chrome.runtime.getURL('app.html') });
  }
  return true;
});
