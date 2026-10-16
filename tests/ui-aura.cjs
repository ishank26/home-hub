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
for char,color in [('a','#8aa898'),('b','#143e8c')]:
    for suffix,size in [('.jpg',(1280,800)),('.thumb.jpg',(400,250))]:
        Image.new('RGB',size,color).save(p/(char*32+suffix))
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
    page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url());});
    const noon=new Date();noon.setHours(12,0,0,0);
    await page.clock.install({time:noon});
    await page.request.post(base+'/api/settings',{data:{quietStart:'00:00',quietEnd:'00:00'}});
    await page.goto(base);
    await page.locator('[data-action="nav:photos"]').click();
    await page.locator('.photo-grid img').waitFor();
    assert.equal(await page.locator('.photo-grid img').getAttribute('src'),`/photos/${first}.thumb`);
    await page.waitForFunction(()=>document.querySelector('.photo-grid img')?.naturalWidth===400);
    await page.locator('[data-action="photo:0"]').click();
    await page.waitForFunction(()=>document.querySelector('.viewer img')?.naturalWidth===1280);
    await page.locator('[data-action="close"]').click();
    if(process.env.SNAPSHOTS){
      fs.mkdirSync(process.env.SNAPSHOTS,{recursive:true});
      await page.screenshot({path:path.join(process.env.SNAPSHOTS,'aura-photos.png')});
    }
    await page.locator('[data-action="slideshow"]').click();
    await page.locator('#saver-source').getByText('Aura photos',{exact:true}).waitFor();
    publish([second]);
    await page.clock.runFor(91000);
    await page.waitForFunction(id=>[...document.querySelectorAll('.saver img')].some(img=>img.getAttribute('src')===`/photos/${id}`&&img.naturalWidth===1280),second);
    write('status.json',{state:'failed'});
    await page.clock.runFor(61000);
    await page.locator('#saver-source').getByText('Stale photos',{exact:true}).waitFor();
    publish([]);
    await page.clock.runFor(61000);
    await page.waitForFunction(()=>[...document.querySelectorAll('.saver img')].every(img=>!img.hasAttribute('src')&&img.style.opacity==='0'));
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log('Aura UI passed: thumbnails, full-size viewer, live slideshow additions/removals, stale state, empty cleanup, no external requests or runtime errors.');
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
    fs.rmSync(data,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exit(1);});
