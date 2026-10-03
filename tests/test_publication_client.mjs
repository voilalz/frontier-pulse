import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import test from 'node:test';
const require = createRequire(import.meta.url);
let p;
try { p = require('../public/assets/publication-client.js'); } catch { p = null; }
const manifest = {schemaVersion:1, releaseId:'r-test', editionDate:'2026-09-28', basePath:'./releases/r-test/'};

test('China midnight and deadline are independent of browser timezone', () => {
  assert.ok(p, 'publication client missing');
  assert.deepEqual(p.clock(new Date('2026-09-27T16:01:00Z')), {date:'2026-09-28', minutes:1});
  assert.match(p.formatDate('2026-09-28T00:00:00Z'), /08:00/);
  assert.equal(p.health({editionDate:'2026-09-27', now:new Date('2026-09-27T23:59:00Z')}).overdue, false);
  assert.equal(p.health({editionDate:'2026-09-27', now:new Date('2026-09-28T00:00:00Z')}).overdue, true);
});
test('current stale edition differs from deliberately selected history', () => {
  assert.ok(p);
  const now = new Date('2026-09-28T02:00:00Z');
  assert.equal(p.health({editionDate:'2026-09-27', now}).label, '今日待更新');
  assert.equal(p.health({editionDate:'2026-09-27', historical:true, failed:true, now}).label, '历史版本');
  assert.equal(p.health({editionDate:'2026-09-28', now}).label, '今日已更新');
  assert.equal(p.health({editionDate:'2026-09-27', failed:true, now}).label, '更新失败');
});
test('manifest pins canonical daily and archived paths to one version', () => {
  assert.ok(p);
  assert.equal(p.resolve(manifest, './data/news.json'), './releases/r-test/data/news.json');
  assert.equal(p.resolve(manifest, './data/archive/search-2026-09.json'), './releases/r-test/data/archive/search-2026-09.json');
  assert.equal(p.resolve(null, './data/news.json'), './data/news.json');
  for (const path of ['./data/../evil', '//evil.test/data/a', './data/%2e%2e/evil', './data/a.json?q=x']) {
    assert.throws(() => p.resolve(manifest, path));
  }
});
test('invalid or foreign-origin manifests cannot choose endpoints', () => {
  assert.ok(p);
  for (const patch of [{releaseId:'../x'}, {basePath:'https://evil.test/'}, {editionDate:'bad'}, {schemaVersion:2}]) {
    assert.throws(() => p.validateManifest({...manifest, ...patch}));
  }
});
test('latest caches must match pinned release and date, historical files may predate it', () => {
  assert.ok(p);
  assert.equal(p.accepts(manifest, {releaseId:'r-test', editionDate:'2026-09-28'}), true);
  assert.equal(p.accepts(manifest, {releaseId:'other', editionDate:'2026-09-28'}), false);
  assert.equal(p.accepts(manifest, {editionDate:'2026-09-28'}), false);
  assert.equal(p.accepts(manifest, {releaseId:'r-test', editionDate:'2026-09-27'}), false);
  assert.equal(p.accepts(null, {editionDate:'2026-09-27'}), true);
});
