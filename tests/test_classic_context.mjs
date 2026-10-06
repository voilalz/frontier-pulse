import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import client from '../public/assets/classic-client.js';

const require = createRequire(import.meta.url);
const context = fs.existsSync('public/assets/classic-context.js')
  ? require('../public/assets/classic-context.js') : {};
const papers = ['AI','CV','GNC','SLAM','UAV'].flatMap(domain =>
  JSON.parse(fs.readFileSync(`research/classics/${domain}.json`)).papers);
const rows = papers.map(paper => ({date:'2026-10-04',paper}));
const cases = [
  ['classic:ai:transformer','Transformer','序列建模'],
  ['classic:ai:ppo','PPO','策略优化'],
  ['classic:cv:resnet','ResNet','残差特征提取'],
  ['classic:cv:sift','SIFT','局部特征匹配'],
  ['classic:slam:orbslam2','ORB-SLAM2','视觉定位建图'],
  ['classic:slam:vinsmono','VINS-Mono','视觉惯性状态估计'],
  ['classic:gnc:kalman1960','Kalman filter','线性状态估计'],
  ['classic:gnc:mayne2000','constrained model predictive control','约束预测控制'],
  ['classic:uav:mellinger-minimum-snap-2011','minimum-snap trajectory','平滑飞行轨迹'],
  ['classic:uav:loquercio-dronet-2018','DroNet','视觉飞行策略'],
];
const news = method => ({id:'atlas:release',originalTitle:'Acme unveils Atlas',
  title:'Acme 发布 Atlas',editionDate:'2026-10-03',releaseId:'r-old-20261003',
  url:'https://example.test/atlas',sources:[{url:'https://example.test/atlas'}],
  evidenceRecords:[{evidenceId:'ev-atlas',kind:'body',fetchedAt:'2026-10-03T00:00:00Z',
    url:'https://example.test/atlas',text:`Acme's Atlas uses ${method} for onboard processing.`}]});

test('Chinese title search finds a published classic without changing its snapshot', () => {
  const p = papers.find(p=>p.id==='classic:slam:orbslam2');
  const archive = {editions:{'2026-10-04':{items:[p]}}};
  const before = JSON.stringify(archive);
  assert.equal(client.search(archive,'视觉定位建图','','2026-10-06').length,1);
  assert.equal(JSON.stringify(archive),before);
});
test('all accepted titles have Chinese display names, and changed identities fall back', () => {
  assert.equal(typeof context.displayTitle,'function');
  assert.equal(papers.length,200);
  for (const paper of papers) assert.match(context.displayTitle(paper),/[\u4e00-\u9fff]/);
  assert.equal(context.displayTitle({id:'classic:cv:sift',title:'A different paper'}),'A different paper');
});
test('ten concrete adopted methods produce source-backed links to published papers', () => {
  assert.equal(typeof context.relatedPapers,'function');
  for (const [id,method] of cases) {
    const links = context.relatedPapers(news(method),rows,'2026-10-06');
    assert.ok(links.some(link=>link.paper.id===id),method);
    assert.equal(links.find(link=>link.paper.id===id).evidence.url,'https://example.test/atlas');
  }
});
test('topic, title-only, negated, prospective and other-subject mentions are omitted', () => {
  assert.equal(typeof context.relatedPapers,'function');
  for (const sentence of [
    'Acme researches robotics and navigation.',
    "Acme's Atlas does not use ORB-SLAM2.",
    "Acme's Atlas may use ORB-SLAM2 next year.",
    'Beta uses ORB-SLAM2 for its rover.',
    'Acme said Beta uses ORB-SLAM2.',
    'Acme compares Atlas with Beta which uses ORB-SLAM2.',
    "Acme's Atlas uses stereo cameras; Beta uses ORB-SLAM2.",
  ]) {
    const n=news('ORB-SLAM2');n.evidenceRecords[0].text=sentence;
    assert.deepEqual(context.relatedPapers(n,rows,'2026-10-06'),[],sentence);
  }
  assert.deepEqual(context.relatedPapers({...news('ORB-SLAM2'),evidenceRecords:[]},rows),[]);
  const n=news('ORB-SLAM2');n.evidenceRecords[0].url='https://other.test/unsupported';
  assert.deepEqual(context.relatedPapers(n,rows),[]);
});
test('unpublished classics are omitted and both directions preserve dates and versions', () => {
  assert.equal(typeof context.relatedPapers,'function');
  const n=news('ORB-SLAM2'),p=rows.find(r=>r.paper.id==='classic:slam:orbslam2');
  assert.deepEqual(context.relatedPapers(n,[], '2026-10-06'),[]);
  assert.deepEqual(context.relatedPapers(n,[{...p,date:'2026-10-07'}],'2026-10-06'),[]);
  assert.equal(context.relatedNews(p.paper,[n],rows,'2026-10-06').length,1);
  const paperLink=new URL(context.paperHref(p,n),'https://site.test/');
  assert.equal(paperLink.searchParams.get('date'),'2026-10-04');
  assert.equal(paperLink.searchParams.get('newsDate'),'2026-10-03');
  assert.equal(paperLink.searchParams.get('release'),'r-old-20261003');
  const newsLink=new URL(context.newsHref(n),'https://site.test/');
  assert.equal(newsLink.searchParams.get('date'),'2026-10-03');
  assert.equal(newsLink.searchParams.get('release'),'r-old-20261003');
  assert.equal(newsLink.hash,'#item-atlas-release');
});
test('classic client keeps its original functions when optional context fails to load', () => {
  const sandbox={};vm.runInNewContext(fs.readFileSync('public/assets/classic-client.js','utf8'),sandbox);
  assert.equal(typeof sandbox.FrontierClassicClient.search,'function');
  assert.equal(sandbox.FrontierClassicClient.search({editions:{'2026-10-04':{items:[papers[0]]}}},'Learning','','2026-10-06').length,1);
});
