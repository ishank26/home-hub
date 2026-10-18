/* Govee on/off readback and cloud outage isolation through the actual HTTP/UI. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'hub-govee-ui-'));
 const source=`
import sys,time
from pathlib import Path
from integrations import HomeAssistant,SourceUnavailable
from govee import GoveeCloud
from server import Hub,Store,make_handler,ThreadingHTTPServer
root=Path(sys.argv[1]);ha=HomeAssistant({'lights':[{'entity':'light.synthetic','name':'HA synthetic light'}]},'synthetic-ha-token')
def read_state(entity):
    time.sleep(.03)
    return {'state':'on','attributes':{}}
ha.read_state=read_state
entries=[{'sku':'H6008','device':'00:00:00:00:00:00:00:0'+str(i),'name':'Govee synthetic '+str(i)} for i in range(1,5)]
cloud=GoveeCloud(entries,'synthetic-govee-key');values={e['device']:0 for e in entries}
def request(endpoint,payload=None):
    if (root/'offline').exists():raise SourceUnavailable('synthetic outage')
    if endpoint=='device/control':
        values[payload['device']]=payload['capability']['value'];return {'code':200}
    return {'code':200,'payload':{'sku':payload['sku'],'device':payload['device'],'capabilities':[
      {'type':'devices.capabilities.online','instance':'online','state':{'value':True}},
      {'type':'devices.capabilities.on_off','instance':'powerSwitch','state':{'value':values[payload['device']]}}]}}
cloud.request=request
lights=cloud.lights
def current():
    if (root/'offline').exists():
        with cloud.lock:
            cloud.cache={k:(0,v[1]) for k,v in cloud.cache.items()}
    return lights()
cloud.lights=current
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Hub(Store(root),ha,govee=cloud),[]))
print(server.server_port,flush=True);server.serve_forever()
`;
 const child=spawn('python3',['-B','-c',source,dir],{cwd:root,stdio:['ignore','pipe','inherit']});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{child.stdout.once('data',b=>resolve(b.toString().trim()));child.on('exit',()=>reject(Error('fixture exit')))});
  const base='http://127.0.0.1:'+port;browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:800},hasTouch:true});
  const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url())});
  await page.goto(base);await page.locator('[data-action="nav:home"]').click();
  await page.getByRole('button',{name:/Govee synthetic 1/}).waitFor();
  if(await page.getByRole('button',{name:/Govee synthetic 1/}).isDisabled()) {await page.locator('[data-action="nav:today"]').click();await page.locator('[data-action="nav:home"]').click();}
  assert.equal(await page.locator('.light').count(),5);
  await page.getByRole('button',{name:/Govee synthetic 1/}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('.light')].find(x=>x.textContent.includes('Govee synthetic 1'))?.getAttribute('aria-pressed')==='true');
  assert.equal(await page.getByRole('button',{name:/HA synthetic light/}).getAttribute('aria-pressed'),'true');
  fs.writeFileSync(path.join(dir,'offline'),'1');await page.locator('[data-action="nav:today"]').click();await page.locator('[data-action="nav:home"]').click();
  await page.getByRole('button',{name:/Govee synthetic 1/}).waitFor();
  assert.equal(await page.getByRole('button',{name:/Govee synthetic 1/}).isDisabled(),true);
  assert.equal(await page.getByRole('button',{name:/HA synthetic light/}).isDisabled(),false);
  await page.screenshot({path:'/tmp/home-hub-govee-outage-qa.png'});
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.locator('[data-action="retry:5"]').click();
  await page.getByText('Govee unavailable or refreshing · Retry shortly',{exact:true}).waitFor();
  assert(!((await page.content()).includes('synthetic-govee-key')));
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log('Govee UI passed: five lights, confirmed cloud on/off routing, HA controls preserved during cloud outage, unavailable cloud controls disabled, no exposed key/external requests/JS errors.');
 }finally{if(browser)await browser.close();child.kill();fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
