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
 await page.evaluate(()=>{window.__browse=[];window.open=(url,target,features)=>{window.__browse.push({url,target,features});return {};};});
 await page.getByRole('button',{name:'Find on web',exact:true}).click();
 await page.getByLabel('Search recipes or enter a website',{exact:true}).fill('easy pasta & tomatoes');
 await page.getByRole('button',{name:'Search / Browse',exact:true}).click();
 const opened=await page.evaluate(()=>window.__browse[0]);
 assert.equal(opened.url,'https://duckduckgo.com/?q=easy%20pasta%20%26%20tomatoes');
 assert.equal(opened.features,'noopener,noreferrer');
 await page.getByText('To paste: press and hold the link field, then choose Paste.',{exact:true}).waitFor();
 await page.getByLabel('Or paste a recipe link',{exact:true}).fill('https://example.com/pasta');
 await page.getByRole('button',{name:'Open recipe',exact:true}).click();
 await page.getByRole('heading',{name:'Simple tomato pasta'}).waitFor();
 await page.getByRole('button',{name:'Save recipe',exact:true}).click();
 await page.getByText('Saved ✓',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Focus mode',exact:true}).click();
 assert.equal(await page.locator('#rail').isVisible(),false);
 await page.getByRole('button',{name:'Larger text'}).click();assert(await page.locator('.recipe-reader').evaluate(el=>getComputedStyle(el).fontSize==='29px'));
 const step=page.getByRole('button',{name:'1. Boil the pasta until tender.',exact:true});await step.click();assert.equal(await step.getAttribute('aria-pressed'),'true');
 await page.screenshot({path:'/tmp/home-hub-recipe-desktop.png'});
 await page.getByRole('button',{name:'Share source',exact:true}).click();
 assert.equal(await page.getByRole('textbox',{name:'Recipe share link'}).inputValue(),'https://example.com/pasta');
 await page.getByRole('button',{name:'Copy link',exact:true}).click();await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByRole('button',{name:'Reader link',exact:true}).click();
 const link=await page.getByRole('textbox',{name:'Recipe share link'}).inputValue();assert(link.startsWith(base+'/?recipeId='));
 const mobile=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});mobile.on('pageerror',e=>errors.push(e.message));
 await mobile.goto(link);await mobile.getByRole('heading',{name:'Simple tomato pasta'}).waitFor();
 await mobile.waitForFunction(()=>document.querySelector('#stage').classList.contains('recipe-focus'));
 assert.equal(await mobile.locator('#rail').isVisible(),false);
 assert(await mobile.locator('.recipe-scroll').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
 await mobile.screenshot({path:'/tmp/home-hub-recipe-mobile.png'});
 await mobile.getByRole('button',{name:'← Recipes',exact:true}).click();await mobile.locator('.recipe-card').filter({hasText:'Simple tomato pasta'}).waitFor();
 // Persistent manual CRUD, input escaping, catalog filter and fresh reader link.
 await mobile.getByRole('button',{name:'New recipe',exact:true}).click();
 await mobile.getByLabel('Recipe title',{exact:true}).fill('Kitchen test <b>soup</b>');
 await mobile.getByLabel('Ingredients — one per line',{exact:true}).fill('1 cup water\n1 pinch salt');
 await mobile.getByLabel('Steps — one per line',{exact:true}).fill('Bring to a simmer.\nServe warm.');
 await mobile.getByLabel('Tags — separated by commas',{exact:true}).fill('Dinner, Easy');
 await mobile.getByLabel('Personal notes',{exact:true}).fill('<img src=x onerror=alert(1)>');
 await mobile.clock.install();
 await mobile.getByLabel('Personal notes',{exact:true}).blur();
 await mobile.clock.runFor(181000);
 assert.equal(await mobile.getByLabel('Recipe title',{exact:true}).inputValue(),'Kitchen test <b>soup</b>');
 assert.equal(await mobile.getByLabel('Steps — one per line',{exact:true}).inputValue(),'Bring to a simmer.\nServe warm.');
 assert.equal(await mobile.getByLabel('Personal notes',{exact:true}).inputValue(),'<img src=x onerror=alert(1)>');
 await mobile.getByRole('button',{name:'Save changes',exact:true}).click();
 await mobile.getByRole('heading',{name:'Kitchen test <b>soup</b>',exact:true}).waitFor();
 assert.equal(await mobile.locator('.recipe-reader img').count(),0);
 await mobile.getByRole('button',{name:'Edit',exact:true}).click();
 await mobile.getByLabel('Recipe title',{exact:true}).fill('Kitchen test soup edited');
 // Successful write followed by a failed optional listing must still update revision/UI.
 await mobile.route('**/api/recipes',route=>route.request().method()==='GET' ? route.fulfill({status:503,contentType:'application/json',body:'{"error":"synthetic list outage"}'}) : route.continue());
 await mobile.getByRole('button',{name:'Save changes',exact:true}).click();
 await mobile.getByRole('heading',{name:'Kitchen test soup edited',exact:true}).waitFor();
 await mobile.getByText('Recipe saved. Catalog refresh unavailable; retry later.',{exact:true}).waitFor();
 await mobile.unroute('**/api/recipes');
 await mobile.getByRole('button',{name:'Reader link',exact:true}).click();
 const manualLink=await mobile.getByRole('textbox',{name:'Recipe share link'}).inputValue();
 await mobile.goto(manualLink);await mobile.getByRole('heading',{name:'Kitchen test soup edited',exact:true}).waitFor();
 await mobile.getByRole('button',{name:'← Recipes',exact:true}).click();
 await mobile.getByLabel('Search saved recipes',{exact:true}).fill('Kitchen');
 assert.equal(await mobile.locator('.recipe-card').count(),1);
 await mobile.screenshot({path:'/tmp/home-hub-recipe-catalog-mobile.png'});
 const catalogPage=await browser.newPage({viewport:{width:1280,height:800}});
 await catalogPage.goto(base);await catalogPage.getByRole('button',{name:'Recipes',exact:true}).click();
 await catalogPage.locator('.recipe-card').filter({hasText:'Kitchen test soup edited'}).waitFor();
 await catalogPage.screenshot({path:'/tmp/home-hub-recipe-catalog-desktop.png'});
 await catalogPage.close();
 await mobile.locator('.recipe-card').click();
 await mobile.getByRole('button',{name:'Delete',exact:true}).click();
 await mobile.route('**/api/recipes',route=>route.request().method()==='GET' ? route.fulfill({status:503,contentType:'application/json',body:'{"error":"synthetic list outage"}'}) : route.continue());
 await mobile.getByRole('button',{name:'Delete recipe',exact:true}).click();
 await mobile.getByRole('button',{name:'New recipe',exact:true}).waitFor();
 await mobile.getByText('Recipe deleted. Catalog refresh unavailable; retry later.',{exact:true}).waitFor();
 await mobile.unroute('**/api/recipes');
 assert.equal(await mobile.getByRole('button',{name:'Kitchen test soup edited',exact:true}).count(),0);
 assert.equal(await mobile.getByRole('button',{name:'Quotes',exact:true}).count(),0);
 await mobile.getByLabel('Search saved recipes',{exact:true}).fill('');
 await mobile.getByRole('button',{name:'Simple tomato pasta',exact:false}).click();
 await mobile.getByRole('button',{name:'Edit',exact:true}).click();
 // Simulate another window saving first: stale editor stays intact on 409.
 const record=(await (await page.request.get(base+'/api/recipes')).json()).recipes[0];
 await page.request.patch(base+'/api/recipes/'+record.id,{data:{revision:record.revision,saved:true}});
 await mobile.getByLabel('Recipe title',{exact:true}).fill('Stale edit');
 await mobile.getByRole('button',{name:'Save changes',exact:true}).click();
 await mobile.getByText('Recipe changed in another window. Reopen it before editing or deleting.',{exact:true}).waitFor();
 assert.equal(await mobile.getByLabel('Recipe title',{exact:true}).inputValue(),'Stale edit');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log('Recipe UI passed: import/save, manual create/edit/delete, persistence/reload, title/tag search, escaped text, stale-edit conflict, focus/font/checkoff, source share, stable reader links, desktop/mobile layout, no external requests or script errors.');
 }finally{if(browser)await browser.close();child.kill();fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
