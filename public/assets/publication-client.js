/* Shared publication clock/manifest contract; no DOM dependency. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FrontierPublication = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function clock(value = new Date()) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(value).filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
    return {date: `${parts.year}-${parts.month}-${parts.day}`, minutes: Number(parts.hour) * 60 + Number(parts.minute)};
  }
  function formatDate(value, includeTime = true) {
    const date = new Date(value);
    if (!Number.isFinite(date.valueOf())) return '时间未知';
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
      ...(includeTime ? {hour:'2-digit', minute:'2-digit', hour12:false, timeZoneName:'short'} : {}),
    }).format(date);
  }
  function health({editionDate, historical = false, failed = false, now = new Date()}) {
    if (historical) return {label:'历史版本', kind:'history', overdue:false};
    if (failed) return {label:'更新失败', kind:'failed', overdue:false};
    const china = clock(now);
    if (editionDate === china.date) return {label:'今日已更新', kind:'current', overdue:false};
    return {label:'今日待更新', kind:'pending', overdue:china.minutes >= 480};
  }
  function validateManifest(manifest) {
    if (!manifest || manifest.schemaVersion !== 1 || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(manifest.releaseId)
        || !/^\d{4}-\d{2}-\d{2}$/.test(manifest.editionDate)
        || manifest.basePath !== `./releases/${manifest.releaseId}/`) throw new Error('发布清单格式无效');
    return manifest;
  }
  function resolve(manifest, canonicalPath) {
    if (!/^\.\/data\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.json$/.test(canonicalPath)) throw new Error('发布路径无效');
    return manifest ? validateManifest(manifest).basePath + canonicalPath.slice(2) : canonicalPath;
  }
  function accepts(manifest, payload) {
    const retained = payload?.schemaVersion === 2 && Array.isArray(payload.chapters)
      && payload.readerStatus === 'retained' && payload.publicationEditionDate === manifest?.editionDate
      && payload.editionDate === manifest?.deepreadEditionDate;
    return Boolean(payload && (!manifest || (payload.releaseId === manifest.releaseId
      && (payload.editionDate === manifest.editionDate || retained))));
  }
  function validateEditionVersion(bundle, releaseId) {
    if (bundle?.schemaVersion !== 1) throw new Error('历史版本格式无效');
    const manifest = validateManifest(bundle.manifest);
    if (manifest.releaseId !== releaseId || !accepts(manifest,bundle.news)
        || !Array.isArray(bundle.news.items) || !accepts(manifest,bundle.deepread)
        || !Array.isArray(bundle.deepread.chapters)) throw new Error('历史版本内容不一致');
    return bundle;
  }
  return {clock, formatDate, health, validateManifest, resolve, accepts, validateEditionVersion};
});
