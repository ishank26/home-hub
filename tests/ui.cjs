/* Optional dev-only Chromium test. See README.md; no browser deps at runtime. */
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const data = fs.mkdtempSync(path.join(os.tmpdir(), "hub-ui-"));
  const server = spawn("python3", ["server.py", "--port", "0"], {
    cwd: path.join(__dirname, ".."),
    env: { ...process.env, HOME_HUB_DATA: data },
    stdio: ["ignore", "pipe", "inherit"],
  });
  let browser;
  try {
    const base = await new Promise((resolve, reject) => {
      server.stdout.on("data", (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/);
        if (match) resolve(`http://127.0.0.1:${match[1]}`);
      });
      server.on("error", reject);
      server.on("exit", (code) => reject(new Error(`Server exited ${code}`)));
    });
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      hasTouch: true,
      userAgent:
        "Mozilla/5.0 (Linux; Android 6.0.1; HomeHub) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/106.0.5249.126 Safari/537.36",
    });
    const page = await context.newPage(),
      errors = [],
      external = [];
    page.on("pageerror", (error) => {
      errors.push(error.message);
      if (process.env.DEBUG_UI) console.error(error);
    });
    if (process.env.DEBUG_UI) {
      page.on("console", (msg) => console.log(msg.text()));
      page.on("response", async (r) => {
        if (r.request().method() !== "GET")
          console.log(r.url(), r.status(), await r.text());
      });
    }
    page.on("request", (request) => {
      if (!request.url().startsWith(base) && !request.url().startsWith("homehub://brightness?value=")) external.push(request.url());
    });
    // Disable quiet hours for deterministic daytime/idle tests.
    await context.request.post(base + "/api/settings", {
      data: { quietStart: "00:00", quietEnd: "00:00" },
    });
    // Sample events are anchored to the backend's current day. Keep browser
    // dates aligned while fixing the clock to noon for deterministic idle tests.
    const uiNow = new Date();
    uiNow.setHours(12, 0, 0, 0);
    await page.clock.install({ time: uiNow });
    await page.goto(base);
    await page.locator(".clock-big").waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator(".rail-item").count(), 9);
    assert.equal(
      await page
        .locator("#rail")
        .evaluate((el) => el.scrollWidth <= el.clientWidth),
      true,
      "Sidebar text overflows",
    );
    assert.equal(await page.locator('[aria-current="page"]').count(), 1);
    assert.equal(await page.locator(".view").count(), 1);
    const nav = async (id) => {
      await page.locator(`.rail-item[data-action="nav:${id}"]`).click();
      await page
        .locator(".view h1")
        .filter({
          hasText: {
            today: "Today",
            calendar: "Calendar",
            shopping: "Shopping",
            weather: "Weather",
            photos: "Photos",
            home: "Smart Home",
            settings: "Settings",
            browser: "Browser",
          }[id],
        })
        .waitFor();
    };
    await nav("settings");
    assert.equal(await page.locator('#tablet-brightness').isDisabled(),true);
    // Capability arrives only from the installed kiosk. Exercise sanitized markup too.
    await page.evaluate(()=>Object.defineProperty(navigator,'userAgent',{value:navigator.userAgent+' HomeHubKiosk/0.6',configurable:true}));
    await page.evaluate(()=>window.dispatchEvent(new CustomEvent('homehub:device',{detail:{brightness:70,browserEmbedded:true}})));
    await page.locator('#tablet-brightness:not([disabled])').waitFor();
    assert.equal(await page.locator('#tablet-brightness').getAttribute('min'),'10');
    assert.equal(await page.locator('#tablet-brightness').getAttribute('max'),'100');
    await page.locator('#tablet-brightness').fill('55');
    assert.equal(await page.locator('#brightness-value').innerText(),'55%');
    await page.evaluate(()=>Object.defineProperty(navigator,'userAgent',{value:navigator.userAgent.replace(' HomeHubKiosk/0.6',''),configurable:true}));
    await nav("browser");
    await page.evaluate(()=>{window.__browserOpens=[];window.open=(url,target,features)=>{window.__browserOpens.push({url,target,features});return {};};});
    await page.getByLabel('Search or enter a website',{exact:true}).fill('weather & gardening');
    await page.getByRole('button',{name:'Go',exact:true}).click();
    const browserOpen=await page.evaluate(()=>window.__browserOpens[0]);
    assert.equal(browserOpen.url,'https://duckduckgo.com/?q=weather%20%26%20gardening');
    assert.equal(browserOpen.features,'noopener,noreferrer');
    await page.getByLabel('Search or enter a website',{exact:true}).fill('javascript:alert(1)');
    await page.getByRole('button',{name:'Go',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.__browserOpens.length),1);
    await page.getByRole('button',{name:'Open browser',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.__browserOpens[1].url),'https://duckduckgo.com/');
    await page.screenshot({path:'/tmp/home-hub-browser-sidebar.png'});
    await nav('today');
    const fits = async () => {
      const fitsStage = await page.evaluate(
        () => document.querySelector("#main").scrollHeight <= 800,
      );
      if (!fitsStage) {
        await page.screenshot({ path: "/tmp/hub-overflow.png" });
        console.log(
          await page
            .locator(".view")
            .evaluate((el) =>
              [...el.children].map((c) => [
                c.className,
                c.getBoundingClientRect().height,
              ]),
            ),
        );
      }
      assert.equal(fitsStage, true, "Main overflows stage");
      if (process.env.SNAPSHOTS) {
        fs.mkdirSync(process.env.SNAPSHOTS, { recursive: true });
        await page.clock.runFor(200);
        const view = await page.locator(".view").getAttribute("data-view");
        await page.screenshot({
          path: path.join(process.env.SNAPSHOTS, `${view}.png`),
        });
      }
    };
    await fits();
    await nav("calendar");
    await page.locator(".cal-grid").waitFor();
    assert.equal(await page.locator(".cal-dayhead").count(), 3);
    await page.locator('[data-action="calmode:7"]').click();
    await page.waitForFunction(
      () => document.querySelectorAll(".cal-dayhead").length === 7,
    );
    await page.locator('[data-action="calmode:42"]').click();
    await page.waitForFunction(
      () => document.querySelectorAll(".mcell").length === 42,
    );
    await page.locator(".mcell").first().click();
    await page.locator('[role="dialog"]').waitFor();
    await page.keyboard.press("Escape");
    await page.locator('[data-action="calmode:3"]').click();
    await page.locator(".cal-grid").waitFor();
    await page.locator('[data-action="filter:work"]').click();
    await page.waitForFunction(
      () =>
        document
          .querySelector('[data-action="filter:work"]')
          ?.getAttribute("aria-pressed") === "false",
    );
    await page.locator(".ev").first().click();
    await page.locator('[role="dialog"]').waitFor();
    await page.keyboard.press("Escape");
    await fits();
    await page.locator(".cal-grid").evaluate((el) => {
      el.scrollTop = 400;
    });
    await nav("photos");
    await nav("calendar");
    assert.equal(
      await page.locator(".cal-grid").evaluate((el) => el.scrollTop),
      400,
    );
    await nav("shopping");
    await page
      .getByLabel("New shopping item")
      .fill("<img src=x onerror=alert(1)>");
    await page.getByLabel("Quantity", { exact: true }).fill("2");
    await page.getByLabel("Notes", { exact: true }).fill("A test note");
    await page.locator("#add-form button").click();
    if (process.env.DEBUG_UI) {
      await page.waitForTimeout(500);
      console.log(await page.locator("body").innerText());
      await page.screenshot({ path: "/tmp/hub-shopping.png" });
    }
    const row = page
      .locator(".shopping-row")
      .filter({ hasText: "<img src=x onerror=alert(1)>" });
    await row.waitFor();
    assert.equal(await row.locator("img").count(), 0);
    assert.match(await row.innerText(), /A test note/);
    assert.equal(await page.getByLabel("New shopping item").inputValue(), "");
    const rowId = await row.locator(".item").getAttribute("data-action");
    await row.locator(".item").click();
    await page.waitForFunction(
      (id) =>
        document
          .querySelector(`[data-action="${id}"]`)
          .getAttribute("aria-pressed") === "true",
      rowId,
    );
    assert.equal(
      await page.locator(".completed-group").getAttribute("open"),
      null,
    );
    await page.locator(".completed-group summary").click();
    await row.locator(".item").click();
    await page.waitForFunction(
      (id) =>
        document
          .querySelector(`[data-action="${id}"]`)
          .getAttribute("aria-pressed") === "false",
      rowId,
    );
    await row.locator(".delete-item").click();
    await page.getByText("Item deleted", { exact: true }).waitFor();
    await page.locator('.toast [data-action="undo"]').click();
    await row.waitFor();
    // Row errors retain the previous confirmed checkbox state and retry intent.
    await page.route("**/api/shopping/*", (route) =>
      route.request().method() === "PATCH" ? route.abort() : route.continue(),
    );
    await row.locator(".item").click();
    await row.getByText("Not saved · Retry", { exact: true }).waitFor();
    assert.equal(
      await row.locator(".item").getAttribute("aria-pressed"),
      "false",
    );
    await page.unroute("**/api/shopping/*");
    await row.locator(".item").click();
    await page.waitForFunction(
      () =>
        document
          .querySelector(".completed-group .item")
          ?.getAttribute("aria-pressed") === "true",
    );
    // Undo must retry with the same create key and complete the restored ID,
    // even when a concurrent phone edit becomes the final item in the list.
    if ((await page.locator('.completed-group').getAttribute('open')) === null)
      await page.locator('.completed-group summary').click();
    await row.locator('.delete-item').click();
    await page.getByText('Item deleted', {exact:true}).waitFor();
    const restoreKeys = [];
    let restoredId, phoneId;
    await page.route('**/api/shopping', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      restoreKeys.push(route.request().postDataJSON().requestKey);
      if (restoreKeys.length === 1) return route.abort();
      const response = await route.fetch();
      restoredId = (await response.json()).addedId;
      const phone = await context.request.post(base + '/api/shopping', {data:{name:'Concurrent phone item'}});
      phoneId = (await phone.json()).addedId;
      const list = await (await context.request.get(base + '/api/shopping')).json();
      await route.fulfill({json:{...list, addedId:restoredId}});
    });
    await page.locator('.toast [data-action="undo"]').click();
    await page.getByText('Undo not confirmed', {exact:true}).waitFor();
    await page.clock.runFor(6000);
    await page.locator('.toast').getByRole('button', {name:'Retry',exact:true}).click();
    await page.getByText('Item restored', {exact:true}).waitFor();
    await page.unroute('**/api/shopping');
    assert.equal(restoreKeys.length, 2);
    assert.equal(restoreKeys[0], restoreKeys[1]);
    const shared = await (await context.request.get(base + '/api/shopping')).json();
    assert.equal(shared.items.find(i => i.id === restoredId).done, true);
    assert.equal(shared.items.find(i => i.id === phoneId).done, false);
    await fits();
    await nav("weather");
    await page.locator(".day7").first().waitFor();
    assert.equal(await page.locator(".day7").count(), 7);
    assert.equal(await page.locator(".hour").count(), 12);
    await fits();
    await page.route("**/api/weather", (route) => route.abort());
    await nav("photos");
    await nav("weather");
    await page.getByText(/Stale · last loaded/).waitFor();
    await page.unroute("**/api/weather");
    await nav("photos");
    await page.route("**/api/weather", () => {});
    const pendingWeather = page.waitForRequest("**/api/weather");
    await page.locator('.rail-item[data-action="nav:weather"]').click();
    await pendingWeather;
    await page.clock.runFor(8100);
    await page.getByText(/Stale · last loaded/).waitFor();
    await page.unroute("**/api/weather");
    await nav("photos");
    await nav("today");
    assert.equal(await page.locator('.quote-line q').count(),1);
    assert.equal(await page.locator('[data-action="nav:quotes"]').count(),0);
    await fits();
    await nav("photos");
    assert.equal(await page.locator(".photo-grid button").count(), 16);
    await page.locator('[data-action="collection:2"]').click();
    assert.equal(await page.locator(".photo-grid button").count(), 5);
    await page.locator(".photo-grid button").first().click();
    await page.locator(".viewer").waitFor();
    await page.locator('[data-action="photonext"]').click();
    await page.locator('[data-action="close"]').click();
    await page.locator('[data-action="slideshow"]').click();
    await page.locator(".saver").waitFor();
    assert.equal(
      await page.locator(".view").count(),
      0,
      "Saver must unmount the main view",
    );
    await page.mouse.click(1000, 200);
    assert.equal(
      await page.locator(".hint").evaluate((el) => el.style.opacity),
      "1",
    );
    await page.clock.runFor(3100);
    assert.equal(
      await page.locator(".hint").evaluate((el) => el.style.opacity),
      "0",
    );
    await page.mouse.move(500, 650);
    await page.mouse.down();
    await page.mouse.move(500, 500);
    await page.mouse.up();
    await page.locator(".clock-big").waitFor();
    await page.route("**/api/home", (route) => route.abort());
    await nav("home");
    await page.getByText(/This source is unavailable/).waitFor();
    await page.unroute("**/api/home");
    await page.locator('[data-action="refresh"]').click();
    await page.locator(".lights").waitFor();
    const light = page.locator('[data-action="light:0"]');
    const wasOn = await light.getAttribute("aria-pressed");
    await light.click();
    await page.getByText(/confirmed by sample adapter/).waitFor();
    assert.notEqual(await light.getAttribute("aria-pressed"), wasOn);
    await page.locator('.toast [data-action="undo"]').click();
    await page.waitForFunction(
      (expected) =>
        document
          .querySelector('[data-action="light:0"]')
          .getAttribute("aria-pressed") === expected,
      wasOn,
    );
    await fits();
    await nav("settings");
    await page.locator('[data-action="clock:24"]').click();
    await page.getByText("Settings saved", { exact: true }).waitFor();
    assert.equal(
      await page
        .locator('[data-action="clock:24"]')
        .getAttribute("aria-pressed"),
      "true",
    );
    await page.locator('[data-action="diagnostics"]').click();
    await page.locator('[role="dialog"]').waitFor();
    await page.keyboard.press("Escape");
    await fits();
    await page.locator("#admin-hold").click();
    assert.equal(await page.locator('[role="dialog"]').count(), 0);
    await page.locator("#admin-hold").dispatchEvent("touchstart", {
      touches: [{ identifier: 1 }, { identifier: 2 }],
    });
    await page.clock.runFor(3100);
    await page.locator('[role="dialog"]').waitFor();
    await page.keyboard.press("Escape");
    // Fixed idle chain: other view -> Today after 2 min -> saver after delay.
    await nav("photos");
    await page.clock.runFor(121000);
    await page.locator(".clock-big").waitFor();
    await page.clock.runFor(181000);
    await page.locator(".saver").waitFor();
    await page.keyboard.press("Escape");
    await page.locator(".clock-big").waitFor();
    // Quiet-hour idle and night tap wake, without touching device brightness.
    await context.request.post(base + "/api/settings", {
      data: { quietStart: "00:00", quietEnd: "23:59", idleMinutes: 1 },
    });
    await nav("settings");
    await nav("today");
    await page.clock.runFor(61000);
    await page.locator(".saver.night").waitFor();
    assert.equal(await page.locator(".saver img").count(), 0);
    assert.doesNotMatch(await page.locator(".foot").innerText(), /\$\{/);
    await page.mouse.click(640, 400);
    await page.locator(".clock-big").waitFor();
    await page.setViewportSize({ width: 640, height: 400 });
    await page.waitForFunction(
      () => document.querySelector("#stage").style.transform === "scale(0.5)",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "UI tests passed: nine navigation entries, mutations, injection, stale fallback, modals, saver, idle, night, admin hold, scaling.",
    );
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise((resolve) => {
      if (server.exitCode !== null || server.signalCode !== null) resolve();
      else server.once("exit", resolve);
    });
    fs.rmSync(data, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
