import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';
import context from '../public/assets/classic-context.js';

const temp=fs.mkdtempSync(path.join(os.tmpdir(),'classic-entry-'));
const root=execFileSync('python',['tests/browser/build_classic_fixture.py',temp],{encoding:'utf8'}).trim();
process.on('exit',()=>fs.rmSync(temp,{recursive:true,force:true}));

// A minimal DOM adapter for render output, not layout or browser validation.
function page(withContext=true) {
  const elements=new Map();
  const element=id=>{
    if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',dataset:{},
      classList:{toggle(){}},setAttribute(){},addEventListener(){},scrollIntoView(){},
      querySelector:selector=>element(id+selector),querySelectorAll:()=>[]});
    return elements.get(id);
  };
  const storage=new Map();
  const sandbox={console,crypto:globalThis.crypto,TextEncoder,URL,URLSearchParams,Intl,Date,
    document:{getElementById:element},requestAnimationFrame:fn=>fn(),
    location:{pathname:'/',search:'?view=research&date=2026-10-04&newsDate=2026-10-03&release=r-old-20261003&paper=classic%3Acv%3Asift',hash:'#classic-classic-cv-sift'},
    history:{replaceState(_a,_b,url){sandbox.updatedUrl=url;}},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    fetch:async url=>new Response(fs.readFileSync(path.join(root,url.split('?')[0]))),
  };
  sandbox.window=sandbox;
  if(withContext)sandbox.FrontierClassicContext=context;
  vm.createContext(sandbox);
  for(const file of ['classic-client.js','classic-papers.js'])
    vm.runInContext(fs.readFileSync('public/assets/'+file,'utf8'),sandbox);
  return {sandbox,element,ui:sandbox.FrontierClassics};
}
const linkedNews={id:'atlas:release',originalTitle:'Acme unveils Atlas',title:'Acme 发布 Atlas',
  editionDate:'2026-10-03',releaseId:'r-old-20261003',url:'https://example.test/atlas',
  sources:[{url:'https://example.test/atlas'}],
  evidenceRecords:[{evidenceId:'ev-atlas',kind:'body',fetchedAt:'2026-10-03T00:00:00Z',
    url:'https://example.test/atlas',text:"Acme's Atlas uses SIFT for feature matching."}]};

test('first paper-page visit loads related news and preserves the source edition',async()=>{
  const {sandbox,element,ui}=page();
  assert.equal(typeof ui.setNewsProvider,'function');
  ui.setNewsProvider(async()=>[linkedNews]);
  await ui.show({initial:true});
  const html=element('classicCards').innerHTML;
  assert.ok(html.includes('基于尺度不变关键点的独特图像特征'));
  assert.ok(html.includes('Acme 发布 Atlas'));
  assert.ok(html.includes('r-old-20261003'));
  assert.ok(html.includes('阅读导读'));
  assert.ok(html.includes('lang="en"'));
  const updated=new URL(sandbox.updatedUrl,'https://site.test/');
  assert.equal(updated.searchParams.get('date'),'2026-10-04');
  assert.equal(updated.searchParams.get('newsDate'),'2026-10-03');
  assert.equal(updated.searchParams.get('release'),'r-old-20261003');
});
test('optional context and news failures preserve core papers, guides and bookmarks',async()=>{
  for(const withContext of [false,true]){
    const {element,ui}=page(withContext);
    if(ui.setNewsProvider)ui.setNewsProvider(async()=>{throw new Error('news unavailable');});
    await ui.show({initial:true});
    const html=element('classicCards').innerHTML;
    assert.ok(html.includes('阅读导读'));
    assert.ok(html.includes('data-classic-save'));
    assert.ok(html.includes('SIFT') || html.includes('Scale-Invariant'));
  }
});
