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
  return {i18n:context.window.BuniI18n, nodes, document, placeholder, saved:()=>saved};
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
