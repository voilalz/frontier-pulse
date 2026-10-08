"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const os=require('node:os'),http=require('node:http'),{execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const output=process.env.FRONTIER_BROWSER_OUTPUT || path.join(os.tmpdir(),'frontier-topic-evidence');
fs.mkdirSync(output,{recursive:true});
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'frontier-topics-'));
const roots=Object.fromEntries(['partial','qualified','brief'].map(state=>[state,
  execFileSync('python3',[path.join(__dirname,'build_topic_fixture.py'),path.join(temp,state),state],
    {cwd:root,encoding:'utf8'}).trim()]));
let activeRoot=roots.partial,tamper=false;
const media={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json'};
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(process.env.FRONTIER_FONT_SOURCE&&/^\/fixture-fonts\/[a-z0-9-]+\.woff2?$/.test(url.pathname)){
    res.writeHead(200,{'Content-Type':'font/woff2'});
    fs.createReadStream(path.join(process.env.FRONTIER_FONT_SOURCE,'files',path.basename(url.pathname))).pipe(res);return;
  }
  const file=path.resolve(activeRoot,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
  if(!file.startsWith(activeRoot+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){
    res.writeHead(404);res.end('missing');return;
  }
  if(tamper&&url.pathname.endsWith('/data/deepread.json')){
    const payload=JSON.parse(fs.readFileSync(file));payload.chapters[0].blocks.reverse();
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(payload));return;
  }
  res.writeHead(200,{'Content-Type':media[path.extname(file)]||'application/octet-stream'});
  fs.createReadStream(file).pipe(res);
});
const results=[];
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,
    ...(process.env.FRONTIER_CHROME?{executablePath:process.env.FRONTIER_CHROME,args:['--disable-gpu']}: {})});
  try{
    for(const device of [{name:'desktop',viewport:{width:1440,height:1000}},
                         {name:'mobile',viewport:{width:390,height:844},isMobile:true,hasTouch:true}]){
      for(const state of ['partial','qualified','brief','tampered']){
        activeRoot=roots[state==='tampered'?'qualified':state];tamper=state==='tampered';
        const context=await browser.newContext({...device,timezoneId:'Asia/Shanghai'});
        await context.route(/^https:\/\//,route=>route.request().url().endsWith('/offline-illustration.svg')
          ? route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="320"><rect width="1000" height="320" fill="#183d4b"/><circle cx="500" cy="150" r="85" fill="#cce36d"/><path d="M180 230H820M220 95L780 230" stroke="#f4f3ee" stroke-width="3"/></svg>'})
          : route.abort());
        const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
        await page.clock.install({time:new Date('2026-09-30T00:15:00Z')});
        try{
          await page.goto(base+'/?view=deepread',{waitUntil:'networkidle'});
          if(process.env.FRONTIER_FONT_SOURCE){
            const css=fs.readFileSync(path.join(process.env.FRONTIER_FONT_SOURCE,'400.css'),'utf8')
              .replaceAll('./files/',base+'/fixture-fonts/');
            await page.addStyleTag({content:css+'\nbody{font-family:"Noto Sans SC",sans-serif}'});
            await page.evaluate(()=>document.fonts.ready);
          }
          if(state==='tampered'){
            await page.waitForFunction(()=>document.querySelector('#deepreadSection .empty'));
            assert.equal(await page.locator('.deepread-topics').count(),0);
          }else{
            await page.waitForFunction(()=>document.querySelector('.deepread-topics'));
            const count=state==='qualified'?2:state==='partial'?1:0;
            assert.equal(await page.locator('.deepread-chapter').count(),count);
            if(count){
              assert.equal(await page.locator('.deepread-hero').count(),1);
              assert.equal(await page.locator('.deepread-footnotes').count(),count);
              await page.locator('.deepread-ref a').first().click();
              assert.equal(await page.locator('.deepread-footnotes').first().getAttribute('open'),'');
              assert.equal(await page.locator('.deepread-analysis-label').count(),count);
            }
            if(state==='qualified')assert.equal(await page.locator('.deepread-source-thumb').count(),1);
            if(state==='partial')assert.match(await page.locator('.deepread-note').textContent(),/合格主题已先行发布/);
            if(state==='brief')assert.equal(await page.locator('.deepread-briefs li').count(),2);
            await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
            if(process.env.FRONTIER_TOPIC_SCREENSHOTS==='true')
              await page.screenshot({path:path.join(output,device.name+'-'+state+'.png'),fullPage:true});
          }
          assert.deepEqual(errors,[]);
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
          results.push({device:device.name,state,status:'passed'});
          console.log(`PASS ${device.name}: ${state}`);
        }finally{await context.close();}
      }
    }
  }finally{await browser.close();server.close();}
  fs.writeFileSync(path.join(output,'deepread-browser-results.json'),JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
