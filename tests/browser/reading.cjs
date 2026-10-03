"use strict";
// Real assets, real publication pipeline and real service worker; no mocked app code.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const root = path.resolve(__dirname, "../..");
const output = process.env.FRONTIER_BROWSER_OUTPUT || path.join(os.tmpdir(), "frontier-browser-evidence");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "frontier-reading-"));
fs.mkdirSync(output, {recursive:true});
const publicRoot = execFileSync("python", [path.join(__dirname,"build_fixture.py"), temp], {cwd:root,encoding:"utf8"}).trim();
const media = {".html":"text/html", ".js":"application/javascript", ".css":"text/css", ".json":"application/json", ".svg":"image/svg+xml", ".png":"image/png"};
let fault = "";
const server = http.createServer((request,response) => {
  const url = new URL(request.url,"http://localhost");
  if ((fault === "news" && /\/data\/news\.json$/.test(url.pathname)) || (fault === "manifest" && url.pathname === "/data/release.json")) {
    response.writeHead(503); response.end("injected read failure"); return;
  }
  if (fault && url.pathname === "/data/status.json") {
    response.writeHead(200,{"Content-Type":"application/json"});
    response.end(JSON.stringify({state:"failed",message:"injected publication failure"})); return;
  }
  const file = path.resolve(publicRoot, "."+decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname));
  if (!file.startsWith(publicRoot+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404);response.end("missing");return;
  }
  response.writeHead(200,{"Content-Type":media[path.extname(file)]||"application/octet-stream"});
  fs.createReadStream(file).pipe(response);
});
const results = [];
let browser;
async function main() {
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless:true, ...(process.env.FRONTIER_CHROME ? {executablePath:process.env.FRONTIER_CHROME}: {})});
  for (const device of [
    {name:"desktop",viewport:{width:1440,height:1000},timezoneId:"America/Los_Angeles"},
    {name:"mobile",viewport:{width:390,height:844},timezoneId:"Asia/Tokyo",isMobile:true,hasTouch:true},
  ]) {
    for (const scenario of ["today","navigation-evidence","archive","overdue","failed-refresh","offline-cache"]) {
      fault="";
      const context = await browser.newContext(device);
      // External images are irrelevant to these authored offline regressions.
      await context.route(/^https:\/\//, route=>route.abort());
      const page = await context.newPage();
      const errors=[];page.on("pageerror",error=>errors.push(error.message));
      await page.clock.install({time:new Date(scenario === "overdue" ? "2026-10-01T00:10:00Z" : "2026-09-30T00:10:00Z")});
      try {
        await page.goto(base,{waitUntil:"networkidle"});
        await page.waitForFunction(()=>document.querySelectorAll("#stories .story").length===10);
        const before = await page.locator("#stories .story h3").allTextContents();
        if (scenario === "today") {
          assert.equal(await page.locator("#dataState").textContent(),"今日已更新");
          assert.equal(await page.locator("#atomBtn,#atomButton,#emailBtn,a[href$='feed.xml']").count(),0);
          assert.match(await page.locator("#briefUpdated").textContent(),/09.*30.*08:10/);
        } else if (scenario === "navigation-evidence") {
          for (const view of ["deepread","stream","research","history","bookmarks","watchlist","latest"]) {
            await page.locator(`.view-tabs [data-view="${view}"]`).click();
            await page.waitForFunction(v=>document.querySelector(`.view-tabs [data-view="${v}"]`).classList.contains("active"),view);
            assert.equal(await page.locator("#atomBtn,#emailBtn").count(),0);
          }
          await page.locator('.view-tabs [data-view="deepread"]').click();
          const proof=page.locator(".deepread-evidence").first();
          await proof.locator("summary").click();
          assert.equal(await proof.getAttribute("open"),"");
          assert.ok((await proof.locator("blockquote").textContent()).length>=10);
          assert.match(await proof.locator("a").first().getAttribute("href"),/^https:\/\//);
          assert.match(await proof.locator("[data-evidence-id]").first().getAttribute("data-evidence-id"),/^evd-/);
          await page.evaluate(()=>scrollTo({top:0,behavior:"instant"}));
          await page.waitForFunction(()=>scrollY===0);
          await page.screenshot({path:path.join(output,device.name+"-deepread.png"),fullPage:true});
        } else if (scenario === "archive") {
          await page.locator('.view-tabs [data-view="history"]').click();
          await page.locator("#editionPicker").fill("2026-09-29");
          await page.locator("#editionPicker").dispatchEvent("change");
          await page.waitForFunction(()=>document.querySelector("#dataState").textContent==="历史版本"
            && document.querySelectorAll("#stories .story").length===10
            && document.querySelector("#stories .story").id.startsWith("item-2026-09-29"));
          assert.equal(await page.locator("#stories .story").count(),10);
          assert.equal(await page.locator("#systemAlert").isVisible(),false);
          // Search shards contain compact rows; expansion must hydrate the pinned archive.
          await page.locator("#search").fill("NASA");
          await page.waitForFunction(()=>document.querySelectorAll("#stories details[data-details-key]").length>0);
          const details=page.locator("#stories details[data-details-key]").first();
          await details.locator("summary").click();
          await page.waitForFunction(()=>!document.querySelector("#stories .detail-loading"));
          assert.equal(await page.locator("#systemAlert").isVisible(),false);
        } else if (scenario === "overdue") {
          assert.equal(await page.locator("#dataState").textContent(),"今日待更新");
          assert.equal(await page.locator("#systemAlert").isVisible(),true);
          assert.match(await page.locator("#alertTitle").textContent(),/今日.*尚未更新/);
          await page.locator('.view-tabs [data-view="history"]').click();
          await page.locator("#editionPicker").fill("2026-09-29");
          await page.locator("#editionPicker").dispatchEvent("change");
          await page.waitForFunction(()=>document.querySelector("#dataState").textContent==="历史版本");
          assert.equal(await page.locator("#systemAlert").isVisible(),false);
        } else if (scenario === "failed-refresh") {
          for (const injection of ["news","manifest"]) {
            fault=injection;
            if (injection==="manifest") await page.evaluate(()=>localStorage.removeItem("fp-release-manifest-v1"));
            await page.locator("#reloadBtn").click();
            await page.waitForFunction(()=>!document.querySelector("#reloadBtn").disabled);
            assert.deepEqual(await page.locator("#stories .story h3").allTextContents(),before);
            assert.equal(await page.locator("#dataState").textContent(),"更新失败");
            assert.match(await page.locator("#alertTitle").textContent(),/更新失败/);
          }
        } else if (scenario === "offline-cache") {
          await page.evaluate(()=>navigator.serviceWorker.ready);
          await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));
          await page.reload({waitUntil:"networkidle"});
          await page.waitForFunction(()=>document.querySelectorAll("#stories .story").length===10);
          await context.setOffline(true);
          await page.reload({waitUntil:"networkidle"});
          await page.waitForFunction(()=>document.querySelectorAll("#stories .story").length===10);
          assert.deepEqual(await page.locator("#stories .story h3").allTextContents(),before);
          assert.equal(await page.locator("#dataState").textContent(),"今日已更新");
        }
        assert.deepEqual(errors,[]);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"document overflows viewport");
        results.push({device:device.name,scenario,status:"passed"});
        console.log(`PASS ${device.name}: ${scenario}`);
      } catch(error) {
        results.push({device:device.name,scenario,status:"failed",error:error.message});
        await page.screenshot({path:path.join(output,device.name+"-"+scenario+"-failed.png"),fullPage:true});
        console.error(`FAIL ${device.name}: ${scenario}: ${error.message}`);
      } finally {await context.close();}
    }
  }
  fs.writeFileSync(path.join(output,"results.json"),JSON.stringify({cases:results,passed:results.filter(r=>r.status==="passed").length,total:results.length},null,2));
  if(results.some(r=>r.status!=="passed"))process.exitCode=1;
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
  fs.rmSync(temp,{recursive:true,force:true});
});
