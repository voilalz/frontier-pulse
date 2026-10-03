import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import api from '../public/assets/classic-client.js';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'classic-client-'));
const root = execFileSync('python', ['tests/browser/build_classic_fixture.py', temp], {encoding:'utf8'}).trim();
process.on('exit', () => fs.rmSync(temp, {recursive:true, force:true}));
const fetcher = async url => new Response(fs.readFileSync(path.join(root, url.split('?')[0])));

test('verified pinned release contains complete real two-paper editions', async () => {
  const state = await api.load(fetcher);
  assert.equal(state.edition.items.length, 2);
  assert.equal(state.edition.recommendationDate, '2026-10-04');
  assert.deepEqual(state.edition.items.map(p=>p.primaryDomain), ['CV','UAV']);
  assert.deepEqual(Object.keys(state.archive.editions), ['2026-10-03','2026-10-04']);
  assert.equal(state.cached, false);
});
test('changed pinned payload is refused and previously verified cache is retained', async () => {
  const previous = await api.load(fetcher);
  const corrupt = async url => url.includes('edition.json') ? new Response('{}') : fetcher(url);
  await assert.rejects(api.load(corrupt), /哈希/);
  const retained = await api.load(corrupt, previous.cache, true);
  assert.equal(retained.cached, true);
  assert.deepEqual(retained.edition, previous.edition);
});
test('unsafe manifest paths and poisoned offline cache cannot be displayed', async () => {
  const state = await api.load(fetcher);
  const poisoned = structuredClone(state.cache);
  poisoned.manifest.basePath = 'https://other.invalid/';
  await assert.rejects(api.verify(poisoned), /路径/);
  const payload = structuredClone(state.cache);
  payload.payloads['archive.json'] = '{}';
  await assert.rejects(api.load(async()=>{throw new Error('offline');}, payload), /哈希/);
});
test('selection and title-author-domain history exclude future and unpublished dates', async () => {
  const state = await api.load(fetcher);
  assert.equal(api.select(state,'2026-10-04','2026-10-03'), null);
  assert.equal(api.select(state,'2026-10-02','2026-10-04'), null);
  assert.equal(api.search(state.archive,'','CV','2026-10-04').length,1);
  assert.equal(api.search(state.archive,'Lowe','','2026-10-04').length,1);
  assert.equal(api.search(state.archive,'','','2026-10-03').length,2);
});
test('Beijing dates and pending/cache health preserve recommendation identity', async () => {
  const state = await api.load(fetcher);
  assert.equal(api.beijingDate(new Date('2026-10-03T18:00:00Z')),'2026-10-04');
  assert.equal(api.health(state,'','2026-10-04'), '今日已更新');
  assert.equal(api.health(state,'','2026-10-05'), '今日待更新');
  assert.equal(api.health(state,'2026-10-03','2026-10-04'), '历史推荐');
  assert.equal(api.health(state,'','2026-10-04',true), '经典缓存');
});
test('citation includes all authors, publication year, venue and canonical source', async () => {
  const paper = (await api.load(fetcher)).edition.items[1];
  const citation = api.citation(paper);
  for (const value of [...paper.authors,paper.title,paper.venue,String(paper.year),paper.canonicalUrl]) assert.ok(citation.includes(value));
});
test('malformed saved classics are isolated before rendering', async () => {
  const paper = (await api.load(fetcher)).edition.items[0];
  assert.equal(api.validFavorite({date:'2026-10-04',paper}),true);
  for (const row of [null,{}, {date:'2026-02-30',paper}, {date:'2026-10-04',paper:{...paper,authors:null}},
    {date:'2026-10-04',paper:{...paper,sourceLocators:[null]}}, {date:'2026-10-04',paper:{...paper,fullText:null}}]) assert.equal(api.validFavorite(row),false);
});
