// 用可控的异步响应验证真实页面函数，不连接服务器。
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(require('node:path').join(__dirname, '../web_prototype/index.html'), 'utf8');
const load = html.slice(html.indexOf('    async function loadRealChapter(chNum)'), html.indexOf('    // 轻量全局 Toast'));
const save = html.slice(html.indexOf('    async function saveCurrentChapterToBackend()'), html.indexOf('    // 角色特质与实时调参'));
const requests = [];
const elements = new Map();
const context = vm.createContext({console, API_BASE:'/api', document: {getElementById(id) {
  if (id === 'editor-container') return null;
  if (!elements.has(id)) elements.set(id, {classList:{remove(){},add(){}},value: 1, innerText: '第一章正文', querySelectorAll: () => [{innerText: '第一章正文'}]});
  return elements.get(id);
}}, fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve})), showToast() {}, renderChaptersTree() {}});
vm.runInContext(`let currentProject={name:'book',chapters:[]},currentChapterNum=1,chapterLoadVersion=0,chapterLoading=false,evolutionProposal=null,editorTarget={project:'book',chapter:1};\n${load}\n${save}`, context);
const run = code => vm.runInContext(code, context);
const response = content => ({ok:true,json:async()=>({title:'title',content,word_count:content.length})});
(async()=>{
  let pending=run('loadRealChapter(2)');
  await run('saveCurrentChapterToBackend()');
  assert.equal(requests.length,1,'加载期间禁止保存');
  requests[0].resolve({ok:false}); await pending;
  assert.equal(run('currentChapterNum'),1,'失败保留原章号');
  const saving=run('saveCurrentChapterToBackend()');
  assert.match(requests[1].url,/chapters\/1\/save$/);
  requests[1].resolve(response('saved')); await saving;
  const older=run('loadRealChapter(2)'), newer=run('loadRealChapter(3)');
  requests[3].resolve(response('third')); await newer;
  requests[2].resolve(response('second')); await older;
  assert.equal(run('currentChapterNum'),3,'过期响应不得覆盖当前章');
  assert.equal(run('editorTarget.chapter'),3);
  console.log('PASS: loading save guard, failed load identity, stale response');
})().catch(error=>{console.error(error);process.exitCode=1;});
