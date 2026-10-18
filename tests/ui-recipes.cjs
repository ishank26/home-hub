/* Browser plugin not available; regular Playwright tests the local application. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'hub-recipe-ui-'));
 const source=`
import sys
from pathlib import Path
import server
from recipes import parse_recipe
server.read_recipe=lambda url: parse_recipe('<script type="application/ld+json">{"@type":"Recipe","name":"Simple tomato pasta","description":"An easy supper for a quiet evening.","recipeYield":"2","recipeIngredient":["2 cups pasta","3 ripe tomatoes","1 tablespoon olive oil"],"recipeInstructions":[{"text":"Boil the pasta until tender."},{"text":"Warm the tomatoes with olive oil."},{"text":"Toss together and serve."}]}</script>',url)
s=server.ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(server.Hub(server.Store(Path(sys.argv[1]))),[]))
print(s.server_port,flush=True);s.serve_forever()
`;
 const child=spawn('python3',['-B','-c',source,dir],{cwd:root,stdio:['ignore','pipe','inherit']});let browser;
 try{
 const port=await new Promise((ok,no)=>{child.stdout.once('data',b=>ok(b.toString().trim()));child.on('exit',()=>no(Error('fixture exit')))});
 const base='http://127.0.0.1:'+port;browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:800},hasTouch:true});
 const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url())});
 await page.goto(base);assert.equal(await page.title(),'Home Hub');
 await page.getByRole('button',{name:'Recipes',exact:true}).click();
 await page.getByLabel('Recipe link',{exact:true}).fill('https://example.com/pasta');
 await page.getByRole('button',{name:'Open recipe',exact:true}).click();
 await page.getByRole('heading',{name:'Simple tomato pasta'}).waitFor();
 await page.getByRole('button',{name:'Focus mode',exact:true}).click();
 assert.equal(await page.locator('#rail').isVisible(),false);
 await page.getByRole('button',{name:'Larger text'}).click();assert(await page.locator('.recipe-reader').evaluate(el=>getComputedStyle(el).fontSize==='29px'));
 const step=page.getByRole('button',{name:'1. Boil the pasta until tender.',exact:true});await step.click();assert.equal(await step.getAttribute('aria-pressed'),'true');
 await page.screenshot({path:'/tmp/home-hub-recipe-desktop.png'});
 await page.getByRole('button',{name:'Share source',exact:true}).click();
 assert.equal(await page.getByRole('textbox',{name:'Recipe share link'}).inputValue(),'https://example.com/pasta');
 await page.getByRole('button',{name:'Copy link',exact:true}).click();await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByRole('button',{name:'Reader link',exact:true}).click();
 const link=await page.getByRole('textbox',{name:'Recipe share link'}).inputValue();assert(link.startsWith(base+'/?recipe='));
 const mobile=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});mobile.on('pageerror',e=>errors.push(e.message));
 await mobile.goto(link);await mobile.getByRole('heading',{name:'Simple tomato pasta'}).waitFor();
 await mobile.waitForFunction(()=>document.querySelector('#stage').classList.contains('recipe-focus'));
 assert.equal(await mobile.locator('#rail').isVisible(),false);
 assert(await mobile.locator('.recipe-scroll').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
 await mobile.screenshot({path:'/tmp/home-hub-recipe-mobile.png'});
 await mobile.getByRole('button',{name:'← Recipes',exact:true}).click();await mobile.getByRole('button',{name:'Simple tomato pasta',exact:true}).waitFor();
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log('Recipe UI passed: import, focus, font size, step checkoff, share/copy fallback, deep reader link, saved recipe, desktop/mobile layout, no external requests/errors.');
 }finally{if(browser)await browser.close();child.kill();fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
