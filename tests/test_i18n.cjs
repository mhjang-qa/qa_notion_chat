const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync(require('node:path').join(__dirname, '../i18n.js'), 'utf8');
function page(search, saved, storageBlocked = false) {
  const events = {};
  const nodes = ['버그요정 버니의 결함 제보 가이드', 'BUNI 결함 제보 안내', '제보자 이름을 입력해 주세요.'].map(nodeValue => ({nodeValue, parentElement: {closest: () => false}}));
  const button = {setAttribute(){},getAttribute(){},addEventListener(){}};
  const placeholder = {placeholder: '질문을 입력하세요.'};
  const document = { title: '버그요정 버니의 결함 제보 가이드', documentElement: {}, body: {},
    createTreeWalker() { let i = 0; return {nextNode(){this.currentNode = nodes[i++];return Boolean(this.currentNode);}}; },
    querySelectorAll: () => [placeholder], getElementById: () => button,
    addEventListener: (event, callback) => events[event] = callback };
  const context = {document, location: {search,href:'https://example.com/embed.html'+search}, URL, URLSearchParams, NodeFilter:{SHOW_TEXT:4},
    history:{replaceState(){}}, CustomEvent: class {},
    localStorage:{getItem(){if(storageBlocked) throw Error('blocked');return saved;},setItem(key,value){if(storageBlocked) throw Error('blocked');saved=value;}}};
  context.window = {dispatchEvent(){}};
  vm.runInNewContext(script, context);
  events.DOMContentLoaded();
  return {i18n:context.window.BuniI18n, nodes, document, placeholder, context, saved:()=>saved};
}
let p = page('?lang=en', 'ko');
assert.equal(p.document.documentElement.lang, 'en');
assert.equal(p.placeholder.placeholder, 'Enter your question.');
assert.equal(p.document.title, 'BUNI Bug Reporting Guide');
p.i18n.setLanguage('ko');
assert.equal(p.nodes[0].nodeValue, '버그요정 버니의 결함 제보 가이드');
assert.equal(p.nodes[1].nodeValue, 'BUNI 결함 제보 안내');
assert.equal(p.document.title, '버그요정 버니의 결함 제보 가이드');
assert.equal(p.saved(), 'ko');
p.i18n.setLanguage('en');
assert.equal(p.nodes[2].nodeValue, "Enter the reporter's name.");
assert.equal(page('', 'en').i18n.language, 'en');
assert.equal(page('?lang=ko', 'en').i18n.language, 'ko');
p = page('?lang=en', '', true);
p.i18n.setLanguage('ko');
assert.equal(p.i18n.language, 'ko');
console.log('UI localization: URL, persistence, blocked storage, and lossless Korean round-trip passed.');

// Run the actual embed boot script with asset loading held pending.
const embed = fs.readFileSync(require('node:path').join(__dirname, '../embed.html'), 'utf8');
const bootScript = [...embed.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
for (const savedLanguage of ['ko', 'en']) {
  const bootPage = page('', savedLanguage);
  const {context, document} = bootPage;
  const title = {}, hint = {}, status = {}, chat = {hidden: true};
  const boot = {hidden: false, querySelector: selector => selector === 'h1' ? title : hint};
  const assets = [];
  let tick, timerCleared = false;
  document.getElementById = id => ({buniBoot: boot, buniBootText: status, chatWidget: chat})[id];
  document.querySelectorAll = () => [];
  document.createElement = tag => ({tag});
  document.head = document.body = {appendChild: asset => assets.push(asset)};
  Object.assign(context.window, {
    setInterval(callback, delay) { assert.equal(delay, 1900); tick = callback; return 1; },
    clearInterval() { timerCleared = true; },
    addEventListener() {}
  });
  vm.runInNewContext(bootScript, context);
  assert.equal(boot.lang, 'ko');
  assert.equal(title.textContent, '버니가 준비 중입니다');
  assert.equal(status.textContent, '버니가 노션에서 깨어나는 중입니다.');
  tick();
  assert.equal(boot.lang, 'en');
  assert.equal(title.textContent, 'BUNI is getting ready');
  assert.equal(hint.textContent, 'The first visit may take a little longer');
  assert.equal(status.textContent, 'BUNI is waking up in Notion.');
  tick();
  assert.equal(status.textContent, '버니가 버그를 정리 중입니다.');
  tick();
  assert.equal(status.textContent, 'BUNI is organizing bug reports.');
  context.window.BUNI_BOOT_ERROR();
  assert.equal(status.textContent, 'Unable to load BUNI. Please refresh in a moment.');
  tick();
  assert.equal(status.textContent, '버니를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.');
  assert.equal(bootPage.i18n.language, savedLanguage);
  assert.equal(bootPage.saved(), savedLanguage);
  context.window.BUNI_LOAD_CHAT_ASSETS();
  assets.find(asset => asset.tag === 'script').onload();
  assert.equal(timerCleared, false);
  assert.equal(boot.hidden, false);
  assets.find(asset => asset.tag === 'link').onload();
  assert.equal(timerCleared, true);
  assert.equal(boot.hidden, true);
  assert.equal(chat.hidden, false);
}
console.log('Boot screen: Korean/English alternation, paired messages, persistent errors, language preference, and asset readiness passed.');
