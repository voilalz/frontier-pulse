import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const app = readFileSync(new URL('../public/assets/app.js', import.meta.url), 'utf8');
function functionSource(name, next) {
  const start = app.indexOf(`  ${name === 'hydrateCompactItem' ? 'async ' : ''}function ${name}(`);
  return app.slice(start, app.indexOf(`\n  ${next}`, start));
}
test('compact historical details use the pinned release, never canonical fallback', async () => {
  const requests = [];
  const state = {editionCache: new Map(), items: [], searchItems: [], bookmarks: []};
  const context = {state, normalizeReport: x => x, itemKey: x => x.id, writeStorage(){}, BOOKMARK_KEY:'bookmarks',
    fetchJson: async path => {requests.push(path); return {items:[{id:'a', releaseId:'new'}]};},
    fetchPublicationJson: async path => {requests.push('pinned:' + path); return {items:[{id:'a', releaseId:'old'}]};}};
  vm.createContext(context);
  vm.runInContext(functionSource('hydrateCompactItem', 'function facetValue'), context);
  const item = await context.hydrateCompactItem({_compact:true, id:'a', editionDate:'2026-07-16'});
  assert.equal(item.releaseId, 'old');
  assert.deepEqual(requests, ['pinned:./data/archive/2026-07-16.json']);
  assert.equal(state.editionCache.get('2026-07-16').items[0].releaseId, 'old');
});
test('successfully selected history does not inherit latest-report read failure', () => {
  const calls = [];
  const badge = {className:'', classList:{add(){}}, textContent:''};
  const context = {state:{view:'history', currentReport:{editionDate:'2026-07-16'}, latestLoadError:'404'},
    $:()=>badge, renderEditionHealth:(report,label,historical)=>calls.push(historical),
    showAlert:()=>calls.push('failed')};
  vm.createContext(context);
  vm.runInContext(functionSource('updateHealth', 'function '), context);
  context.updateHealth({editionDate:'2026-07-17'});
  assert.deepEqual(calls, [true]);
});
