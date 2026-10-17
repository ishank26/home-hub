/* Real image decode, snapshot viewer/outage/cleanup against a synthetic HA source. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-camera-ui-'));
  const python = process.env.AURA_PYTHON || path.join(os.homedir(), '.local/share/home-hub/aura-venv/bin/python');
  const source = `
import io,sys
from pathlib import Path
from email.message import Message
from PIL import Image
from integrations import HomeAssistant
from server import Hub,Store,make_handler,ThreadingHTTPServer
data=Path(sys.argv[1]); buffer=io.BytesIO(); Image.new('RGB',(400,250),'#59746b').save(buffer,format='JPEG'); raw=buffer.getvalue()
ha=HomeAssistant({'lights':[{'entity':'light.synthetic','name':'Synthetic light'}],'cameras':[{'entity':'camera.synthetic_'+str(i),'name':'Synthetic camera '+str(i+1)} for i in range(4)]},'synthetic-camera-token')
ha.request=lambda path,body=None: {'state':('off' if (data/'privacy').exists() else 'idle') if 'camera.' in path else 'off','attributes':{}}
ha.action=lambda body: {'result':'confirmed','message':'Light confirmed'}
class Response(io.BytesIO):
    def __init__(self):
        super().__init__(raw);self.headers=Message();self.headers['Content-Type']='image/jpeg'
def open_image(*args,**kwargs):
    if (data/'fail-camera').exists(): raise OSError('synthetic outage')
    return Response()
ha.transport.open=open_image
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Hub(Store(data),ha),[]))
print('http://127.0.0.1:'+str(server.server_port),flush=True);server.serve_forever()
`;
  const server = spawn(python, ['-B','-c',source,data], {cwd:root,stdio:['ignore','pipe','inherit']});
  let browser;
  try {
    const base = await new Promise((resolve,reject)=>{
      server.stdout.on('data',chunk=>{const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/);if(match)resolve(`http://127.0.0.1:${match[1]}`);});
      server.on('error',reject);server.on('exit',code=>reject(new Error(`Fixture exited ${code}`)));
    });
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1280,height:800},hasTouch:true});
    await page.addInitScript(()=>{
      window.liveCameraURLs=new Set();
      const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
      URL.createObjectURL=blob=>{const url=create(blob);window.liveCameraURLs.add(url);return url;};
      URL.revokeObjectURL=url=>{window.liveCameraURLs.delete(url);revoke(url);};
    });
    const errors=[],external=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('blob:'))external.push(r.url());});
    const noon=new Date();noon.setHours(12,0,0,0);await page.clock.install({time:noon});
    await page.request.post(base+'/api/settings',{data:{quietStart:'00:00',quietEnd:'00:00'}});
    await page.goto(base);await page.locator('[data-action="nav:home"]').click();
    await page.waitForFunction(()=>document.querySelectorAll('.cam img').length===4&&[...document.querySelectorAll('.cam img')].every(img=>img.naturalWidth===400));
    assert.equal(await page.evaluate(()=>document.querySelector('#main').scrollHeight<=800),true);
    for (let i=0;i<5;i++) {
      await page.locator('[data-action="light:0"]').click();
      await page.waitForFunction(()=>!document.querySelector('[data-action="light:0"]').disabled&&[...document.querySelectorAll('.cam img')].every(img=>img.naturalWidth===400));
      assert.equal(await page.evaluate(()=>window.liveCameraURLs.size),4);
    }
    await page.screenshot({path:'/tmp/home-hub-camera-qa.png'});
    await page.route('**/api/camera/live',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"synthetic unavailable"}'}));
    await page.locator('[data-action="camera:0"]').click();
    await page.getByText('Live video unavailable · close and reopen to retry',{exact:true}).waitFor();
    assert.equal(await page.getByRole('dialog').count(),1);
    assert.equal(await page.locator('video').count(),1);
    assert.equal(await page.locator('video').evaluate(v=>!v.getAttribute('src')&&v.paused),true);
    fs.writeFileSync(path.join(data,'fail-camera'),'1');
    await page.clock.runFor(31000);
    await page.locator('.cam').getByText('Update failed · previous snapshot',{exact:true}).first().waitFor();
    assert.equal(await page.locator('.cam img').first().evaluate(img=>img.naturalWidth),400);
    fs.unlinkSync(path.join(data,'fail-camera'));fs.writeFileSync(path.join(data,'privacy'),'1');
    await page.clock.runFor(31000);
    await page.locator('.cam').getByText('Camera unavailable',{exact:true}).first().waitFor();
    assert.equal(await page.locator('.cam img').first().getAttribute('src'),null);
    assert.equal(await page.evaluate(()=>window.liveCameraURLs.size),0);
    await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.locator('[data-action="nav:today"]').click();
    assert.equal(await page.locator('[data-camera-id]').count(),0);
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log('Camera UI passed: four decoded snapshots, stage bounds, one live-video failure viewer and decoder teardown, refresh/outage label, last image retained during outage, privacy clears images, repeated redraw URL bounds, navigation cleanup, no external requests or JS errors.');
  } finally {
    if(browser)await browser.close();server.kill('SIGTERM');fs.rmSync(data,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exit(1);});
