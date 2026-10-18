/* Synthetic photo integration through real HTTP, image decoding and screensaver. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn, execFileSync} = require('node:child_process');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-aura-ui-'));
  const cache = path.join(data, 'photos', 'cache');
  fs.mkdirSync(cache, {recursive:true});
  const first = 'a'.repeat(32), second = 'b'.repeat(32);
  const python = process.env.AURA_PYTHON || path.join(os.homedir(), '.local/share/home-hub/aura-venv/bin/python');
  execFileSync(python, ['-c', `
from PIL import Image
from pathlib import Path
import sys
p=Path(sys.argv[1])
for char,color in [('a','#8aa898'),('b','#143e8c')]+[(f'{i:032x}','#8aa898') for i in range(303)]:
    for suffix,size in [('.jpg',(1280,800)),('.thumb.jpg',(400,250))]:
        Image.new('RGB',size,color).save(p/((char*32 if len(char)==1 else char)+suffix))
`, cache]);
  const write = (name, value) => {
    const target = path.join(data, 'photos', name);
    fs.writeFileSync(target+'.tmp', JSON.stringify(value), {mode:0o600});
    fs.renameSync(target+'.tmp', target);
  };
  const publish = ids => {
    write('manifest.json',{syncedAt:new Date().toISOString(), photos:ids.map(id=>({id}))});
    write('status.json',{state:'current'});
  };
  publish([first]);
  const config = path.join(data,'config.json');
  fs.writeFileSync(config, JSON.stringify({photos:{source:'aura'}}), {mode:0o600});
  const server = spawn('python3',['server.py','--port','0','--config',config],{
    cwd:root,env:{...process.env,HOME_HUB_DATA:data},stdio:['ignore','pipe','inherit']
  });
  let browser;
  try {
    const base = await new Promise((resolve,reject)=>{
      server.stdout.on('data',chunk=>{
        const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/);
        if(match) resolve(`http://127.0.0.1:${match[1]}`);
      });
      server.on('error',reject);server.on('exit',code=>reject(new Error(`Server exited ${code}`)));
    });
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1280,height:800},hasTouch:true});
    const errors=[],external=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(!r.url().startsWith(base) && !r.url().startsWith('blob:'+base+'/'))external.push(r.url());});
    const noon=new Date();noon.setHours(12,0,0,0);
    await page.clock.install({time:noon});
    await page.request.post(base+'/api/settings',{data:{quietStart:'00:00',quietEnd:'00:00'}});
    await page.goto(base);
    await page.locator('[data-action="nav:photos"]').click();
    await page.locator('.photo-grid img').waitFor();
    assert(await page.locator('.photo-grid img').evaluate(img=>img.src.startsWith('blob:') || img.getAttribute('src').endsWith('.thumb')));
    await page.waitForFunction(()=>window.HubPhotoCache.info()?.count===1);
    await page.waitForFunction(()=>document.querySelector('.photo-grid img')?.naturalWidth===400);
    await page.locator('[data-action="photo:0"]').click();
    await page.waitForFunction(()=>document.querySelector('.viewer img')?.naturalWidth===1280);
    await page.locator('[data-action="close"]').click();
    if(process.env.SNAPSHOTS){
      fs.mkdirSync(process.env.SNAPSHOTS,{recursive:true});
      await page.screenshot({path:path.join(process.env.SNAPSHOTS,'aura-photos.png')});
    }
    // A fresh page can use persistent device blobs when the photo server is unreachable.
    await page.route('**/api/photos/manifest',route=>route.abort());
    await page.route('**/photos/**',route=>route.abort());
    await page.reload();
    await page.locator('[data-action="nav:photos"]').click();
    await page.waitForFunction(()=>document.querySelector('.photo-grid img')?.naturalWidth===400);
    assert((await page.locator('.photo-grid img').getAttribute('src')).startsWith('blob:'));
    assert.equal(await page.locator('.head .pill').filter({hasText:/Stale/}).count(),0);
    await page.locator('[data-action="photo:0"]').click();
    await page.waitForFunction(()=>document.querySelector('.viewer img')?.naturalWidth===1280);
    await page.locator('[data-action="close"]').click();
    await page.unroute('**/api/photos/manifest');await page.unroute('**/photos/**');
    await page.locator('[data-action="slideshow"]').click();
    await page.locator('#saver-source').getByText('Aura photos',{exact:true}).waitFor();
    publish([second]);
    const limitedManifest=JSON.parse(fs.readFileSync(path.join(data,'photos','manifest.json')));
    limitedManifest.windowLimited=true;limitedManifest.syncPending=true;write('manifest.json',limitedManifest);
    await page.clock.runFor(91000);
    await page.waitForFunction(id=>[...document.querySelectorAll('.saver img')].some(img=>(img.getAttribute('src')===`/photos/${id}` || img.getAttribute('src')===window.HubPhotoCache.url(id,false))&&img.naturalWidth===1280),second);
    await page.locator('#saver-source').getByText('Aura photos · syncing more photos',{exact:true}).waitFor();
    limitedManifest.syncPending=false;write('manifest.json',limitedManifest);
    await page.clock.runFor(61000);
    await page.locator('#saver-source').getByText('Aura photos · 1,000-photo selection',{exact:true}).waitFor();
    write('status.json',{state:'failed'});
    const staleManifest=page.waitForResponse('**/api/photos/manifest');
    await page.clock.runFor(61000);
    assert.equal((await (await staleManifest).json()).state,'stale');
    await page.locator('#saver-source').getByText('Aura photos · 1,000-photo selection',{exact:true}).waitFor();
    assert.equal(await page.getByText('Stale photos',{exact:true}).count(),0);
    publish([]);
    await page.clock.runFor(61000);
    await page.waitForFunction(()=>[...document.querySelectorAll('.saver img')].every(img=>!img.hasAttribute('src')&&img.style.opacity==='0'));
    // Replacement remains bounded and failed downloads keep the previous complete sample.
    const many=Array.from({length:303},(_,i)=>i.toString(16).padStart(32,'0')).concat([first,second]);
    publish(many);
    await page.evaluate(async()=>{const m=await(await fetch('/api/photos/manifest')).json();await window.HubPhotoCache.sync(m);});
    assert.equal(await page.evaluate(()=>window.HubPhotoCache.info().count),300);
    const persisted=await page.evaluate(()=>new Promise((resolve,reject)=>{
      const request=indexedDB.open('home-hub-photos',1);
      request.onsuccess=()=>{const db=request.result,tx=db.transaction('sample');const get=tx.objectStore('sample').get('current');get.onsuccess=()=>resolve(get.result.items.length);};request.onerror=reject;
    }));assert.equal(persisted,300);
    publish([first]);await page.route('**/photos/'+first,route=>route.abort());
    const failed=await page.evaluate(async()=>{const m=await(await fetch('/api/photos/manifest')).json();try{await window.HubPhotoCache.sync(m);return false;}catch{return true;}});
    assert.equal(failed,true);assert.equal(await page.evaluate(()=>window.HubPhotoCache.info().count),300);
    await page.unroute('**/photos/'+first);
    await page.keyboard.press('Escape');await page.locator('.clock-big').waitFor();
    // Disabling source cancels an older download and prevents offline resurrection.
    let releaseDownload;
    await page.route('**/photos/'+first,async route=>{
      await new Promise(resolve=>{releaseDownload=resolve;});
      try{await route.continue();}catch{/* the cache may already have aborted it */}
    });
    const slowRequest=page.waitForRequest('**/photos/'+first);
    await page.evaluate(()=>{window.pendingPhotoSave=fetch('/api/photos/manifest').then(r=>r.json()).then(m=>window.HubPhotoCache.sync(m)).catch(()=>null);});
    await slowRequest;
    await page.route('**/api/photos/manifest',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({source:'unconfigured',state:'failed',photos:[],collections:['All','Aura']})}));
    await page.locator('[data-action="nav:photos"]').click();
    await page.waitForFunction(()=>window.HubPhotoCache.info()===null);
    releaseDownload();await page.evaluate(()=>window.pendingPhotoSave);
    assert.equal(await page.evaluate(()=>window.HubPhotoCache.load()),null);
    await page.unroute('**/api/photos/manifest');await page.route('**/api/photos/manifest',route=>route.abort());
    await page.reload();await page.locator('[data-action="nav:photos"]').click();
    assert.equal(await page.evaluate(()=>window.HubPhotoCache.load()),null);
    assert.equal(await page.locator('.photo-grid img').count(),0);
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log('Aura UI passed: persistent tablet blobs, reload with photo network blocked, thumbnails, full-size viewer, live slideshow additions/removals, stale state, empty cleanup, disable cancels in-flight sync and clears offline copy, no external requests or runtime errors.');
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
    fs.rmSync(data,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exit(1);});
