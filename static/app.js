/* Home Hub: local HLS player, no credentials, Chrome/WebView 106 compatible. */
(() => {
  "use strict";
  const $ = (s, root = document) => root.querySelector(s);
  const stage = $("#stage"),
    main = $("#main"),
    rail = $("#rail"),
    overlay = $("#overlay");
  const names = {
    today: "Today",
    calendar: "Calendar",
    shopping: "Shopping",
    weather: "Weather",
    quotes: "Quotes",
    photos: "Photos",
    home: "Smart Home",
    settings: "Settings",
  };
  const svg = (content, size = 26) =>
    `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${content}</svg>`;
  const sun =
    '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1"></path>';
  const bulb =
    '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.7 1 2.5h6c0-.8.2-1.7 1-2.5A6 6 0 0 0 12 3z"></path>';
  const icons = [
    svg('<path d="M3 11l9-7 9 7M5 10v10h14V10"></path>'),
    svg(
      '<rect x="3" y="5" width="18" height="16" rx="2"></rect><path d="M3 10h18M8 3v4M16 3v4"></path>',
    ),
    svg(
      '<path d="M3 4h2l2.5 11h11L21 7H6.5"></path><circle cx="9" cy="19" r="1.5"></circle><circle cx="17" cy="19" r="1.5"></circle>',
    ),
    svg(sun),
    svg('<path d="M7 7h4v4c0 3-2 5-4 6M15 7h4v4c0 3-2 5-4 6"></path>'),
    svg(
      '<rect x="3" y="4" width="18" height="16" rx="2"></rect><circle cx="9" cy="10" r="2"></circle><path d="M21 17l-5-5-9 8"></path>',
    ),
    svg(bulb),
    svg(
      '<circle cx="12" cy="12" r="3"></circle><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"></path>',
    ),
  ];
  const esc = (value) =>
    String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const button = (text, action, cls = "btn", extra = "") =>
    `<button class="${cls}" data-action="${action}" ${extra}>${text}</button>`;
  // Text is escaped at interpolation sites. This allowlist is a second boundary:
  // no scripts, event attributes, external image URLs, or arbitrary CSS survive.
  function renderHTML(target, markup) {
    const doc = new DOMParser().parseFromString(markup, "text/html");
    const tags = new Set([
      "DIV",
      "SPAN",
      "SMALL",
      "I",
      "B",
      "BR",
      "P",
      "Q",
      "H1",
      "H2",
      "BUTTON",
      "ARTICLE",
      "SECTION",
      "HEADER",
      "FORM",
      "INPUT",
      "SELECT",
      "OPTION",
      "LABEL",
      "BLOCKQUOTE",
      "IMG",
      "DETAILS",
      "SUMMARY",
      "SVG",
      "PATH",
      "CIRCLE",
      "RECT",
    ]);
    const attrs = new Set([
      "class",
      "id",
      "role",
      "type",
      "name",
      "value",
      "placeholder",
      "maxlength",
      "required",
      "autocomplete",
      "disabled",
      "for",
      "alt",
      "loading",
      "decoding",
      "open",
      "tabindex",
      "width",
      "height",
      "viewBox",
      "fill",
      "stroke",
      "stroke-width",
      "stroke-linecap",
      "stroke-linejoin",
      "d",
      "cx",
      "cy",
      "r",
      "x",
      "y",
      "rx",
    ]);
    const styles = new Set([
      "font-size",
      "max-width",
      "grid-template-columns",
      "height",
      "top",
      "left",
      "width",
      "opacity",
    ]);
    for (const node of doc.body.querySelectorAll("*")) {
      if (!tags.has(node.tagName.toUpperCase())) {
        node.remove();
        continue;
      }
      for (const attr of [...node.attributes]) {
        if (attr.name === "style") {
          for (const property of [...node.style])
            if (
              !styles.has(property) ||
              /url|expression|var\(/i.test(
                node.style.getPropertyValue(property),
              )
            )
              node.style.removeProperty(property);
        } else if (
          attr.name === "src" &&
          node.tagName === "IMG" &&
          /^\/photos\/[A-Za-z0-9_%.-]+$/.test(attr.value)
        ) {
          /* same-origin opaque photo only */
        } else if (
          !attrs.has(attr.name) &&
          !/^aria-[a-z-]+$|^data-[a-z-]+$/.test(attr.name)
        )
          node.removeAttribute(attr.name);
      }
    }
    target.replaceChildren(...doc.body.childNodes);
  }
  const cache = new Map();
  const state = {
    view: "today",
    mode: "active",
    generation: 0,
    timers: [],
    settings: {
      clock24h: false,
      units: "F",
      idleMinutes: 3,
      photoSeconds: 30,
      quietStart: "22:00",
      quietEnd: "06:00",
      returnTodayMinutes: 2,
    },
    today: null,
    status: null,
    lastError: "",
    lastInput: Date.now(),
    idleTodayAt: null,
    calMode: 3,
    calDate: midnight(new Date()),
    filters: new Set(),
    collection: "All",
    quoteIndex: null,
    favorites: [],
    shoppingBusy: new Set(),
    shoppingErrors: new Map(),
    homeBusy: false,
  };
  let toastTimer,
    toastUndo = null,
    modalFocus = null,
    saverPhotos = [],
    photoIndex = 0,
    hintTimer,
    adminTimer;
  function rainWindow(weather) {
    const hour = (weather.hourly || []).find((h) =>
      ["rain", "snow"].includes(h.kind),
    );
    return hour
      ? `${hour.kind === "snow" ? "Snow" : "Rain"} from ${time(hour.time)} · ${hour.pop == null ? "" : hour.pop + "%"}`
      : "";
  }
  try {
    const saved = JSON.parse(
      localStorage.getItem("hub.quoteFavorites") || "[]",
    );
    if (Array.isArray(saved))
      state.favorites = saved.filter((x) => typeof x === "string");
  } catch {
    /* storage may be disabled */
  }

  function midnight(d) {
    const value = new Date(d);
    value.setHours(0, 0, 0, 0);
    return value;
  }
  function addDays(d, n) {
    const value = new Date(d);
    value.setDate(value.getDate() + n);
    return value;
  }
  function sameDay(a, b) {
    return midnight(a).getTime() === midnight(b).getTime();
  }
  function time(d) {
    return new Date(d).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
      hour12: !state.settings.clock24h,
    });
  }
  function date(
    d,
    options = { weekday: "long", month: "long", day: "numeric" },
  ) {
    return new Date(d).toLocaleDateString([], options);
  }
  function temp(value) {
    return value == null
      ? "—"
      : `${Math.round(state.settings.units === "C" ? ((value - 32) * 5) / 9 : value)}°`;
  }
  function wxIcon(kind, size = 40) {
    const cloud =
      '<path d="M7 17h10a4 4 0 0 0 0-8 6 6 0 0 0-11.5 1.5A3.3 3.3 0 0 0 7 17z"></path>';
    return svg(
      {
        sun,
        cloud,
        rain: cloud + '<path d="M9 19l-1 3M13 19l-1 3M17 19l-1 3"></path>',
        snow: '<path d="M12 2v20M3 7l18 10M3 17L21 7"></path>',
      }[kind] || cloud,
      size,
    );
  }
  function color(id, calendars = []) {
    const cal = calendars.find((c) => c.id === id);
    return (
      { blue: "family", orange: "work", teal: "school", purple: "sports" }[
        cal && cal.color
      ] || "family"
    );
  }
  function relative(start, end) {
    const mins = Math.round((new Date(start) - Date.now()) / 60000);
    return mins < 0
      ? new Date(end) > Date.now()
        ? "Now"
        : "Ended"
      : mins < 60
        ? `In ${mins} min`
        : `In ${Math.floor(mins / 60)}h ${mins % 60}m`;
  }

  function shoppingRequestKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
  }

  async function request(path, method = "GET", body) {
    if (method === "POST" && path === "/api/shopping" && body && !body.requestKey)
      body.requestKey = shoppingRequestKey();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(path, {
        method,
        signal: controller.signal,
        cache: "no-store",
        credentials: "same-origin",
        headers: method === "GET" ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (method === "GET") remember(path, data);
      return { data, stale: false, at: Date.now() };
    } catch (error) {
      state.lastError = `${method} ${path.split("?")[0]}: ${error.name === "AbortError" ? "Timed out" : error.message}`;
      if (method === "GET" && cache.has(path))
        return { ...cache.get(path), stale: true };
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  function remember(path, data) {
    cache.delete(path);
    cache.set(path, { data, at: Date.now() });
    while (cache.size > 32) cache.delete(cache.keys().next().value);
  }
  function later(fn, ms) {
    const id = setInterval(fn, ms);
    state.timers.push(id);
    return id;
  }
  function clearView() {
    cameraLoads.forEach(controller => controller.abort());
    cameraLoads.clear();
    cameraObjectURLs.forEach(url => URL.revokeObjectURL(url));
    cameraObjectURLs.clear();
    state.timers.forEach(clearInterval);
    state.timers = [];
    clearTimeout(hintTimer);
    closeModal();
    renderHTML(overlay, "");
  }
  function fit() {
    const scale = Math.min(innerWidth / 1280, innerHeight / 800);
    stage.style.transform = `scale(${scale})`;
    stage.style.left = `${(innerWidth - 1280 * scale) / 2}px`;
    stage.style.top = `${(innerHeight - 800 * scale) / 2}px`;
  }
  function renderRail() {
    renderHTML(
      rail,
      Object.entries(names)
        .map(([id, label], i) =>
          button(
            `<span aria-hidden="true">${icons[i]}</span>${label}`,
            `nav:${id}`,
            "rail-item",
            state.view === id ? 'aria-current="page"' : "",
          ),
        )
        .join("") +
        '<div class="rail-spacer"></div>' +
        button(
          '<i class="dot sample"></i><span>Checking sources…</span>',
          "nav:settings",
          "rail-sync",
        ),
    );
    syncFooter();
  }
  function syncFooter() {
    const el = $(".rail-sync");
    if (!el || !state.status) return;
    const sources = state.status.data.sources;
    const bad =
      state.status.stale ||
      sources.some((s) => ["stale", "failed"].includes(s.state));
    renderHTML(
      el,
      `<i class="dot ${bad ? "warn" : sources.some((s) => s.state === "sample") ? "sample" : ""}"></i><span>${bad ? "Sources stale" : sources.some((s) => s.state === "sample") ? "Sample sources" : "Sources current"}</span>`,
    );
  }
  function alerts() {
    const el = $("#alerts");
    if (!el) return;
    const severity = { critical: 0, severe: 1, error: 2, warn: 3, info: 4 };
    const items = state.today
      ? [...(state.today.data.alerts || [])].sort(
          (a, b) =>
            (severity[a.severity] == null ? 5 : severity[a.severity]) -
            (severity[b.severity] == null ? 5 : severity[b.severity]),
        )
      : [];
    renderHTML(
      el,
      items
        .slice(0, 1)
        .map((a) =>
          button(
            `<span aria-hidden="true">⚠</span><span class="grow">${esc(a.text)}</span><span>${esc(a.detail)}${items.length > 1 ? " · +" + (items.length - 1) + " more" : ""}${state.today.stale ? " · Stale" : state.today.data.source === "sample" ? " · Sample" : ""}</span><span>›</span>`,
            `nav:${names[a.view] ? a.view : "today"}`,
            "alert",
          ),
        )
        .join(""),
    );
  }
  function badge(result) {
    return result.stale
      ? `<span class="pill warn">Stale · last loaded ${esc(time(result.at))}</span>`
      : result.data.source === "sample"
        ? '<span class="pill">Sample data</span>'
        : result.data.source === "unconfigured"
          ? '<span class="pill warn">Setup needed</span>'
          : "";
  }
  function frame(title, result, body, controls = "") {
    renderHTML(
      main,
      `<div id="alerts"></div><section class="view" data-view="${state.view}" aria-label="${esc(title)}"><header class="head"><h1>${esc(title)}</h1><span class="sub"></span>${badge(result)}${controls}</header>${body}</section>`,
    );
    alerts();
  }
  const savedScroll = new Map();
  const scrollElements = () => [
    ...main.querySelectorAll(
      ".cal-grid, .shop-cols, .photo-grid, .settings-scroll",
    ),
  ];
  const captureScroll = () =>
    scrollElements().map((el) => [el.scrollTop, el.scrollLeft]);
  function restoreScroll(values = []) {
    scrollElements().forEach((el, i) => {
      if (values[i]) {
        el.scrollTop = values[i][0];
        el.scrollLeft = values[i][1];
      }
    });
  }
  async function navigate(view = state.view) {
    if (!names[view]) return;
    const switched = state.view !== view;
    if (state.mode === "active" && switched)
      savedScroll.set(state.view, captureScroll());
    state.view = view;
    state.mode = "active";
    state.idleTodayAt = null;
    rail.hidden = false;
    main.hidden = false;
    clearView();
    const generation = ++state.generation;
    renderRail();
    renderHTML(
      main,
      '<div id="alerts"></div><section class="view"><div class="empty">Loading…</div></section>',
    );
    alerts();
    try {
      await renders[view](generation);
      if (current(generation) && switched) restoreScroll(savedScroll.get(view));
    } catch {
      if (generation === state.generation)
        frame(
          names[view],
          { data: {} },
          `<div class="empty">This source is unavailable. ${button("Retry", "refresh")}</div><p class="meta">${esc(state.lastError)}</p>`,
        );
    }
  }
  const current = (gen) => gen === state.generation && state.mode === "active";
  function toast(text, undo = null, actionLabel = "Undo", duration = 5000) {
    clearTimeout(toastTimer);
    const old = $(".toast");
    if (old) old.remove();
    toastUndo = undo;
    const el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    renderHTML(
      el,
      `<span>${esc(text)}</span>${undo ? button(actionLabel, "undo", "") : ""}`,
    );
    stage.appendChild(el);
    toastTimer = duration ? setTimeout(() => {
      el.remove();
      toastUndo = null;
    }, duration) : null;
  }
  function modal(title, body) {
    closeModal();
    modalFocus = document.activeElement;
    renderHTML(
      overlay,
      `<div class="modal-back"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><h2 id="dialog-title">${esc(title)}</h2>${body}${button("Close", "close")}</section></div>`,
    );
    $('[data-action="close"]', overlay).focus();
  }
  function closeModal() {
    stopLiveCamera();
    clearCameraImages(overlay);
    if (modalFocus) {
      renderHTML(overlay, "");
      if (modalFocus.isConnected) modalFocus.focus();
      modalFocus = null;
    }
  }
  function eventDetail(id) {
    const e = (
      state.view === "calendar" && state.calendar
        ? state.calendar.data.events
        : state.today
          ? state.today.data.events
          : []
    ).find((e) => e.id === id);
    if (!e) return;
    modal(
      e.title,
      `<p>${esc(date(e.start))}</p><p>${e.allDay ? "All day" : `${esc(time(e.start))} – ${esc(time(e.end))}`}</p><p>${esc(e.location || "No location specified")}</p><p class="meta">Read only${state.calendar && state.calendar.stale ? " · Stale data" : ""}</p>`,
    );
  }

  async function today(gen, supplied = null) {
    const result = supplied || (await request("/api/today"));
    if (!current(gen)) return;
    state.today = result;
    const d = result.data,
      w = d.weather.current;
    frame(
      "Today",
      result,
      `<div class="today-top"><div><div class="clock-big" data-clock></div><div class="date-big" data-date></div></div>${button(`<span style="font-size:64px" aria-hidden="true">${wxIcon(w.kind, 64)}</span><span><span class="t">${temp(w.temp)}</span><br><span class="s">${esc(w.summary)} · H ${temp(d.weather.daily[0]?.hi)} L ${temp(d.weather.daily[0]?.lo)}</span><br><span class="r">${esc(rainWindow(d.weather))}</span></span>`, "nav:weather", "wx-tile")}</div><div class="today-grid"><article class="card"><div class="card-head"><h2>Next up</h2>${button("Calendar ›", "nav:calendar", "link")}</div>${d.events.length ? d.events.map((e) => `<button class="ev-row item" data-action="event:${esc(e.id)}"><span class="time">${esc(time(e.start))}</span><i class="dot d-${color(e.calendar, d.calendars)}"></i><span class="title">${esc(e.title)}<span>${esc((d.calendars.find((c) => c.id === e.calendar) || {}).name)}</span></span><span class="pill ${d.events[0] === e ? "hot" : ""}" data-relative="${esc(e.id)}">${relative(e.start, e.end)}</span></button>`).join("") : `<div class="empty">${d.calendarSource === 'unconfigured' ? 'Calendar needs setup' : d.calendarSource === 'failed' ? 'Calendar unavailable' : 'Nothing coming up'}</div>`}</article><article class="card today-shopping" data-action="nav:shopping"><div class="card-head"><h2>Shopping</h2>${button("Open list ›", "nav:shopping", "link")}</div><div class="shop-count">${d.shoppingSource === "failed" ? "—" : d.shoppingOpen} <span>${d.shoppingSource === "failed" ? "Shopping unavailable" : "open items"}</span></div>${d.shoppingTop.map((i) => `<div class="mini-row row-line">${esc(i.name)}<span>${esc(i.qty)}</span></div>`).join("")}${d.shoppingOpen > 3 ? `<p class="meta">+ ${d.shoppingOpen - 3} more</p>` : ""}</article></div>${button(`<q>${esc(d.quote.text)}</q><span>— ${esc(d.quote.author)}</span>`, "nav:quotes", "quote-line")}`,
    );
    updateClocks();
    later(updateClocks, 1000);
    later(() => {
      d.events.forEach((e) => {
        const el = $(`[data-relative="${e.id}"]`);
        if (el) el.textContent = relative(e.start, e.end);
      });
    }, 60000);
  }

  // Interval graph coloring: each connected overlap group shares equal-width lanes.
  function layoutEvents(events, day) {
    const end = addDays(day, 1).getTime();
    const values = events
      .map((e) => ({
        e,
        start: Math.max(new Date(e.start).getTime(), day.getTime()),
        end: Math.min(new Date(e.end).getTime(), end),
      }))
      .sort((a, b) => a.start - b.start || b.end - a.end);
    // Short appointments still get a 56px tap area. Include that visual extent
    // in lane assignment, so expanding a block does not cover its neighbor.
    values.forEach((v) => {
      v.hitEnd = Math.max(v.end, v.start + (56 * 60000 * 60) / 40);
    });
    let group = [],
      limit = 0;
    function flush() {
      const lanes = [];
      group.forEach((v) => {
        let lane = lanes.findIndex((t) => t <= v.start);
        if (lane < 0) lane = lanes.length;
        lanes[lane] = v.hitEnd;
        v.lane = lane;
      });
      group.forEach((v) => {
        v.lanes = lanes.length;
      });
      group = [];
    }
    values.forEach((v) => {
      if (group.length && v.start >= limit) flush();
      group.push(v);
      limit = Math.max(group.length === 1 ? 0 : limit, v.hitEnd);
    });
    flush();
    return values;
  }
  async function calendar(gen) {
    let start = midnight(state.calDate),
      days = state.calMode;
    if (days === 42) {
      start.setDate(1);
      start = addDays(start, -start.getDay());
    }
    const result = await request(
      `/api/calendar?from=${encodeURIComponent(start.toISOString())}&days=${days}`,
    );
    if (!current(gen)) return;
    state.calendar = result;
    const d = result.data;
    const events = d.events.filter((e) => !state.filters.has(e.calendar));
    const controls = `<div class="seg">${[
      [1, "Day"],
      [3, "3 Day"],
      [7, "Week"],
      [42, "Month"],
    ]
      .map(([n, label]) =>
        button(
          label,
          `calmode:${n}`,
          "",
          `aria-pressed="${state.calMode === n}"`,
        ),
      )
      .join(
        "",
      )}</div>${button("‹", "calprev", "btn icon", 'aria-label="Previous period"')}${button("Today", "caltoday")}${button("›", "calnext", "btn icon", 'aria-label="Next period"')}`;
    const legend = `<div class="cal-legend">${d.calendars.map((c) => button(`<i class="dot d-${color(c.id, d.calendars)}"></i>${esc(c.name)}`, `filter:${esc(c.id)}`, `c-${color(c.id, d.calendars)}`, `aria-pressed="${!state.filters.has(c.id)}"`)).join("")}</div>`;
    const toolbar = `<div class="head calendar-toolbar">${legend}<span class="sub">${esc(date(start, { month: "short", day: "numeric" }))}${days > 1 ? " – " + esc(date(addDays(start, days - 1), { month: "short", day: "numeric" })) : ""}</span><input type="date" aria-label="Calendar date" id="calendar-date" value="${state.calDate.getFullYear()}-${String(state.calDate.getMonth() + 1).padStart(2, "0")}-${String(state.calDate.getDate()).padStart(2, "0")}"></div>`;
    const onDay = (day) =>
      events.filter(
        (e) => new Date(e.start) < addDays(day, 1) && new Date(e.end) > day,
      );
    let body;
    if (days === 42) {
      body = `<div class="month">${Array.from({ length: 42 }, (_, i) => {
        const day = addDays(start, i);
        return `<button class="mcell ${day.getMonth() !== state.calDate.getMonth() ? "out" : ""} ${sameDay(day, new Date()) ? "today" : ""}" data-action="monthday:${day.getTime()}" aria-label="${esc(date(day))}"><span class="n">${i < 7 ? date(day, { weekday: "short" }) + " " : ""}${day.getDate()}</span>${onDay(
          day,
        )
          .slice(0, 3)
          .map(
            (e) =>
              `<span class="e c-${color(e.calendar, d.calendars)}">${e.allDay ? "" : esc(time(e.start)) + " "}${esc(e.title)}</span>`,
          )
          .join(
            "",
          )}${onDay(day).length > 3 ? '<span class="month-more">+' + (onDay(day).length - 3) + " more</span>" : ""}</button>`;
      }).join("")}</div>`;
    } else {
      const dayList = Array.from({ length: days }, (_, i) => addDays(start, i));
      const columns = `64px repeat(${days}, minmax(0, 1fr))`;
      body = `<div class="cal-days" style="grid-template-columns:${columns}"><span class="meta">All day</span>${dayList
        .map(
          (day) =>
            `<div class="cal-dayhead"><div class="lbl"><b class="${sameDay(day, new Date()) ? "today" : ""}">${esc(date(day, { weekday: "short" }))}</b><span class="num ${sameDay(day, new Date()) ? "today" : ""}">${day.getDate()}</span></div>${onDay(
              day,
            )
              .filter((e) => e.allDay)
              .map((e) =>
                button(
                  esc(e.title),
                  `event:${esc(e.id)}`,
                  `allday c-${color(e.calendar, d.calendars)}`,
                ),
              )
              .join("")}</div>`,
        )
        .join(
          "",
        )}</div><div class="cal-grid" style="grid-template-columns:${columns}"><div class="cal-col" style="height:960px">${Array.from({ length: 24 }, (_, h) => `<span class="hour-lbl" style="top:${h * 40 + 10}px">${esc(new Date(2020, 0, 1, h).toLocaleTimeString([], { hour: "numeric", hour12: !state.settings.clock24h }))}</span>`).join("")}</div>${dayList
        .map(
          (day) =>
            `<div class="cal-col ${sameDay(day, new Date()) ? "today" : ""}" style="height:960px">${Array.from({ length: 24 }, (_, h) => `<div class="hour-line" style="top:${h * 40}px"></div>`).join("")}${layoutEvents(
              onDay(day).filter((e) => !e.allDay),
              day,
            )
              .map((v) => {
                const minute = (t) => {
                  const dt = new Date(t);
                  return sameDay(dt, day)
                    ? dt.getHours() * 60 + dt.getMinutes()
                    : 1440;
                };
                const top = (minute(v.start) * 40) / 60,
                  height = Math.max(
                    56,
                    ((minute(v.end) - minute(v.start)) * 40) / 60,
                  );
                return button(
                  `<b>${esc(v.e.title)}</b><span>${esc(time(v.e.start))}${days < 7 && v.e.location ? " · " + esc(v.e.location) : ""}</span>`,
                  `event:${esc(v.e.id)}`,
                  `ev c-${color(v.e.calendar, d.calendars)}`,
                  `style="top:${top}px;height:${height}px;left:${(v.lane * 100) / v.lanes}%;width:calc(${100 / v.lanes}% - 3px)"`,
                );
              })
              .join(
                "",
              )}${sameDay(day, new Date()) ? '<div class="now-line" data-now-line></div>' : ""}</div>`,
        )
        .join("")}</div>`;
    }
    frame("Calendar", result, toolbar + body, controls);
    const grid = $(".cal-grid");
    if (grid) grid.scrollTop = 7 * 40;
    updateClocks();
    later(updateClocks, 60000);
  }

  function drawShopping(result) {
    const scroll = captureScroll();
    const expanded = $(".completed-group") && $(".completed-group").open;
    const form = $("#add-form");
    const draft = form ? Object.fromEntries(new FormData(form)) : null;
    state.shopping = result;
    const d = result.data;
    const row = (i) =>
      `<div class="shopping-row"><button class="item ${i.done ? "done" : ""}" data-action="toggle:${i.id}" aria-pressed="${i.done}" ${state.shoppingBusy.size ? "disabled" : ""}><span class="box">${i.done ? "✓" : ""}</span><span class="nm">${esc(i.name)}${i.notes ? `<small>${esc(i.notes)}</small>` : ""}</span><span class="qt">${state.shoppingBusy.has(i.id) ? "Saving…" : state.shoppingErrors.has(i.id) ? "Not saved · Retry" : esc(i.qty)}</span></button>${button("×", `delete:${i.id}`, "delete-item", `aria-label="Delete ${esc(i.name)}" ${state.shoppingBusy.size ? "disabled" : ""}`)}</div>`;
    const groups = d.categories
      .map((c) => {
        const items = d.items.filter((i) => i.category === c && !i.done);
        return items.length
          ? `<section class="group"><h2>${esc(c)}</h2>${items.map(row).join("")}</section>`
          : "";
      })
      .filter(Boolean);
    const completed = d.items.filter((i) => i.done);
    frame(
      "Shopping",
      result,
      `<form class="add-row" id="add-form"><input name="name" aria-label="New shopping item" placeholder="Add an item…" maxlength="60" required autocomplete="off"><input name="qty" aria-label="Quantity" placeholder="Qty" maxlength="30" style="max-width:100px"><input name="notes" aria-label="Notes" placeholder="Notes" maxlength="120" style="max-width:150px"><select name="category" aria-label="Category">${d.categories.map((c) => `<option>${esc(c)}</option>`).join("")}</select><button class="btn primary" type="submit">Add</button></form><div class="quick"><span class="meta">Quick add</span>${d.quickAdd.map((n, i) => button("+ " + esc(n), `quick:${i}`, "chip")).join("")}</div><div class="shop-cols">${groups.length ? `<div class="shop-col">${groups.slice(0, Math.ceil(groups.length / 2)).join("")}</div><div class="shop-col">${groups.slice(Math.ceil(groups.length / 2)).join("")}</div>` : '<div class="empty">Nothing left to get</div>'}<details class="completed-group"><summary>Completed (${completed.length}) · ${esc(completed.map((i) => i.name).join(", ") || "None yet")}</summary>${completed.map(row).join("")}</details></div><div class="done-bar"><b>${completed.length} completed</b><span class="names">${esc(completed.map((i) => i.name).join(", "))}</span>${button("Clear completed", "clearshopping", "link", completed.length ? "" : "disabled")}</div>`,
    );
    if (draft)
      Object.entries(draft).forEach(([key, value]) => {
        const input = $(`[name="${key}"]`, $("#add-form"));
        if (input) input.value = value;
      });
    restoreScroll(scroll);
    if (expanded) $(".completed-group").open = true;
    if (state.shoppingBusy.size) $("#add-form button").disabled = true;
    $(".head .sub").textContent =
      `${d.items.filter((i) => !i.done).length} open · ${result.stale ? "Offline copy" : d.source === "homeassistant" ? "Synced with Home Assistant" : "Saved locally"} ${time(result.at)}`;
  }
  async function shopping(gen) {
    const r = await request("/api/shopping");
    if (current(gen)) drawShopping(r);
  }
  async function shoppingWrite(path, method, body, id, undo) {
    if (state.shoppingBusy.size) return;
    id = id || "__list";
    const gen = state.generation;
    if (method === "POST" && path === "/api/shopping" && !body.requestKey) {
      const fingerprint = JSON.stringify(body);
      if (!state.pendingShoppingAdd || state.pendingShoppingAdd.fingerprint !== fingerprint) {
        state.pendingShoppingAdd = {fingerprint, key: shoppingRequestKey()};
      }
      body.requestKey = state.pendingShoppingAdd.key;
    }
    if (id) {
      state.shoppingBusy.add(id);
      state.shoppingErrors.delete(id);
      if (state.view === "shopping") drawShopping(state.shopping);
    }
    try {
      const r = await request(path, method, body);
      remember("/api/shopping", r.data);
      state.shopping = r;
      if (id) state.shoppingErrors.delete(id);
      if (undo) toast("Item deleted", undo);
      if (method === "POST" && path === "/api/shopping") state.pendingShoppingAdd = null;
      if (method === "POST" && path === "/api/shopping" && current(gen)) {
        const form = $("#add-form");
        if (form) form.reset();
      }
      refreshCommon();
    } catch {
      if (id !== "__list")
        state.shoppingErrors.set(id, { path, method, body, undo });
      else toast("Not saved · Please retry");
    } finally {
      state.shoppingBusy.delete(id);
      if (current(gen) && state.view === "shopping")
        drawShopping(state.shopping);
    }
  }

  async function weather(gen) {
    const r = await request("/api/weather");
    if (!current(gen)) return;
    const d = r.data,
      c = d.current;
    frame(
      "Weather",
      r,
      `<div class="wx-top"><article class="card wx-hero"><span style="font-size:84px">${wxIcon(c.kind, 84)}</span><div><div class="lab">${esc(d.currentLabel || (d.source === "unconfigured" ? "Setup needed" : "Now · observed"))}</div><div class="big">${temp(c.temp)}</div><div class="s">${esc(c.summary)}${c.feelsLike == null ? "" : " · feels like " + temp(c.feelsLike)}</div><div class="hl">High ${temp(d.daily[0]?.hi)} · Low ${temp(d.daily[0]?.lo)}</div></div></article><article class="card wx-detail">${[
        [
          "Rain today",
          d.daily[0] && d.daily[0].pop != null ? d.daily[0].pop + "%" : null,
        ],
        ["Wind", c.wind],
        ["Humidity", c.humidity == null ? null : c.humidity + "%"],
        ["UV index", c.uv],
        ["Sunrise", c.sunrise],
        ["Sunset", c.sunset],
      ]
        .filter(([, v]) => v != null)
        .map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`)
        .join(
          "",
        )}</article></div><article class="card"><h2>Next 12 hours</h2><div class="hours">${d.hourly.map((h) => `<div class="hour ${h.pop >= 50 ? "wet" : ""}"><span class="h">${esc(new Date(h.time).toLocaleTimeString([], { hour: "numeric", hour12: !state.settings.clock24h }))}</span><span style="font-size:30px">${wxIcon(h.kind, 30)}</span><span class="t">${temp(h.temp)}</span>${h.pop == null ? "" : `<span class="pop">${h.pop}%</span>`}</div>`).join("")}</div></article><div class="days7">${d.daily.map((day, i) => `<article class="day7 ${i === 0 ? "today" : ""}"><span class="d">${i === 0 ? "Today" : esc(date(day.date, { weekday: "short" }))}</span><span style="font-size:40px">${wxIcon(day.kind)}</span><span class="c">${esc(day.summary)}</span><span class="t">${temp(day.hi)} <span>${temp(day.lo)}</span></span>${day.pop == null ? "" : `<span class="pop">${day.pop}% rain</span>`}</article>`).join("")}</div>`,
    );
    $(".head .sub").textContent =
      `${d.location || ""}${d.observedAt ? " · Observed " + time(d.observedAt) : ""}${d.forecastAt ? " · Retrieved " + time(d.forecastAt) : ""} · ${d.provider || "Select your weather location on the server"}`;
    $(".head .sub").classList.add("meta");
  }
  async function quotes(gen) {
    const r = await request("/api/quotes");
    if (!current(gen)) return;
    state.quotes = r;
    if (state.quoteIndex === null) state.quoteIndex = r.data.todayIndex;
    drawQuote();
  }
  function drawQuote() {
    const r = state.quotes,
      q = r.data.quotes[state.quoteIndex % r.data.quotes.length],
      saved = state.favorites.includes(q.text);
    frame(
      "Quotes",
      r,
      `<article class="quote-card"><span class="pill">${state.quoteIndex === r.data.todayIndex ? "Today's quote" : "From the collection"}</span><blockquote>${esc(q.text)}</blockquote><div class="a">${esc(q.author)}</div><div class="s">${esc(q.source)}</div></article><div class="center-row">${button(saved ? "Saved ✓" : "Save", "savequote", "btn", `aria-pressed="${saved}"`)}${button("Next quote →", "nextquote", "btn primary")}</div>`,
    );
  }
  function photoURL(photo, thumbnail = false) {
    return `/photos/${encodeURIComponent(photo.id)}${/^p\d{2}$/.test(photo.id) ? ".svg" : thumbnail ? ".thumb" : ""}`;
  }
  async function readPhotos() {
    const r = await request("/api/photos/manifest");
    r.stale = r.stale || r.data.state === "stale";
    if (r.stale && r.data.syncedAt) r.at = Date.parse(r.data.syncedAt);
    if (!r.data.collections.includes(state.collection)) state.collection = "All";
    return r;
  }
  async function photos(gen) {
    const r = await readPhotos();
    if (!current(gen)) return;
    state.photos = r;
    drawPhotos();
  }
  function drawPhotos() {
    const r = state.photos,
      list = r.data.photos.filter(
        (p) =>
          state.collection === "All" ||
          p.collections.includes(state.collection),
      );
    state.filteredPhotos = list;
    frame(
      "Photos",
      r,
      `<div class="quick">${r.data.collections.map((c, i) => button(esc(c), `collection:${i}`, "chip", `aria-pressed="${state.collection === c}"`)).join("")}<span class="meta">${list.length} photos${r.data.windowLimited ? " · bounded selection" : ""} · ${r.data.syncedAt ? "Synced " + esc(time(r.data.syncedAt)) : "Not synced yet"}</span></div><div class="photo-grid">${list.map((p, i) => button(`<img src="${photoURL(p, true)}" alt="Photo ${i + 1}" loading="lazy" decoding="async">`, `photo:${i}`, "")).join("") || '<div class="empty">No photos in this collection</div>'}</div>`,
      button(
        "Start slideshow",
        "slideshow",
        "btn primary",
        list.length ? "" : "disabled",
      ),
    );
  }
  function viewer(index) {
    const list = state.filteredPhotos;
    photoIndex = (index + list.length) % list.length;
    if (!modalFocus) modalFocus = document.activeElement;
    renderHTML(
      overlay,
      `<section class="viewer" role="dialog" aria-modal="true" aria-label="Photo viewer"><img src="${photoURL(list[photoIndex])}" alt="Photo ${photoIndex + 1}"><div class="bar">${button("‹ Previous", "photoprev")}${button("Close", "close")}${button("Next ›", "photonext")}</div></section>`,
    );
    $('[data-action="close"]', overlay).focus();
  }

  const cameraObjectURLs = new Set(), cameraLoads = new Set(), cameraControllers = new WeakMap();
  function clearCameraImage(img) {
    cameraControllers.get(img)?.abort();
    if (img.dataset.objectUrl) {
      URL.revokeObjectURL(img.dataset.objectUrl);
      cameraObjectURLs.delete(img.dataset.objectUrl);
      delete img.dataset.objectUrl;
    }
    img.removeAttribute('src');
  }
  function clearCameraImages(root) {
    root.querySelectorAll('[data-camera-id]').forEach(clearCameraImage);
  }
  async function refreshCamera(img) {
    if (img.dataset.busy || !/^[a-f0-9]{16}$/.test(img.dataset.cameraId || '')) return;
    img.dataset.busy = '1';
    const gen = state.generation, controller = new AbortController();
    cameraLoads.add(controller);
    cameraControllers.set(img, controller);
    const timer = setTimeout(() => controller.abort(), 7000);
    let objectUrl;
    const note = img.closest('.cam, .camera-frame')?.querySelector('.camera-note');
    try {
      const response = await fetch(`/camera/${img.dataset.cameraId}.jpg`, {signal:controller.signal, credentials:'same-origin', cache:'no-store'});
      if (response.status === 410) {
        clearCameraImage(img);
        if (note) note.textContent = 'Camera unavailable';
        return;
      }
      if (!response.ok || !response.headers.get('content-type')?.startsWith('image/jpeg')) throw new Error('Snapshot unavailable');
      const blob = await response.blob();
      if (blob.size > 2000000) throw new Error('Snapshot too large');
      objectUrl = URL.createObjectURL(blob);
      const image = new Image();
      await new Promise((resolve, reject) => {image.onload=resolve;image.onerror=reject;image.src=objectUrl;});
      if (!img.isConnected || gen !== state.generation || controller.signal.aborted) return;
      if (img.dataset.objectUrl) {
        URL.revokeObjectURL(img.dataset.objectUrl);
        cameraObjectURLs.delete(img.dataset.objectUrl);
      }
      img.src = objectUrl;
      img.dataset.objectUrl = objectUrl;
      cameraObjectURLs.add(objectUrl);
      objectUrl = null;
      if (note) note.textContent = 'Snapshot loaded ' + time(Date.now());
    } catch {
      if (img.isConnected && note) note.textContent = img.dataset.objectUrl ? 'Update failed · previous snapshot' : 'Snapshot unavailable';
    } finally {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      clearTimeout(timer);
      cameraLoads.delete(controller);
      if (cameraControllers.get(img) === controller) cameraControllers.delete(img);
      delete img.dataset.busy;
    }
  }
  function refreshCameras() {
    document.querySelectorAll('[data-camera-id]').forEach(img => refreshCamera(img));
  }
  let liveCamera = null;
  function stopLiveCamera() {
    const live = liveCamera;
    liveCamera = null;
    if (!live) return;
    live.controller.abort();
    live.hls?.destroy();
    live.video.pause();
    live.video.removeAttribute('src');
    live.video.load();
    if (live.session) {
      fetch('/api/camera/stop', {method:'POST', credentials:'same-origin', keepalive:true,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({session:live.session})}).catch(()=>{});
    }
  }
  async function cameraViewer(index) {
    const camera = state.home?.data.cameras[index];
    if (!camera || camera.available === false || state.home.stale) return;
    modal(camera.name, `<div class="camera-live"></div><p class="camera-live-note" role="status">Starting live video…</p><p class="meta">Live video may have a short delay. Closing this viewer stops playback.</p>`);
    const video = document.createElement('video');
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    $('.camera-live', overlay).append(video);
    const note = $('.camera-live-note', overlay);
    const live = {video, controller:new AbortController(), session:null, hls:null};
    liveCamera = live;
    const fail = message => {
      if (liveCamera !== live) return;
      stopLiveCamera();
      note.textContent = message;
    };
    const timer = setTimeout(()=>fail('Live video timed out · close and reopen to retry'),30000);
    video.addEventListener('playing',()=>{clearTimeout(timer);if(liveCamera===live)note.textContent='Live video · delayed feed';});
    video.addEventListener('waiting',()=>{if(liveCamera===live)note.textContent='Buffering live video…';});
    video.addEventListener('error',()=>fail('Live video unavailable · close and reopen to retry'));
    try {
      const response = await fetch('/api/camera/live', {method:'POST',credentials:'same-origin',signal:live.controller.signal,
        headers:{'Content-Type':'application/json'},body:JSON.stringify({id:camera.id})});
      if (!response.ok) throw new Error('Live video unavailable');
      const result = await response.json();
      const match = /^\/camera\/live\/([a-f0-9]{32})\/master_playlist\.m3u8$/.exec(result.url || '');
      if (!match) throw new Error('Invalid stream');
      live.session = match[1];
      if (liveCamera !== live) return;
      if (window.Hls?.isSupported()) {
        live.hls = new Hls({enableWorker:false,lowLatencyMode:false,maxBufferLength:8,maxMaxBufferLength:15,
          backBufferLength:0,maxBufferSize:8000000,manifestLoadingMaxRetry:3,levelLoadingMaxRetry:2,fragLoadingMaxRetry:1});
        live.hls.on(Hls.Events.ERROR,(_,data)=>{
          if(data.response?.code===410) fail('Camera unavailable');
          else if(data.fatal) fail('Live video interrupted · close and reopen to retry');
        });
        live.hls.attachMedia(video);
        live.hls.loadSource(result.url);
        live.hls.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>{if(liveCamera===live)note.textContent='Press play to start live video';}));
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src=result.url;
        await video.play();
      } else fail('This browser cannot play the camera video');
    } catch {
      fail('Live video unavailable · close and reopen to retry');
    } finally {
      if (liveCamera !== live) clearTimeout(timer);
    }
  }
  async function home(gen) {
    const r = await request("/api/home");
    if (current(gen)) {
      state.home = r;
      drawHome();
      if (state.cameraRefreshGen !== gen) {
        state.cameraRefreshGen = gen;
        later(refreshCameras, 30000);
      }
    }
  }
  function drawHome() {
    clearCameraImages(main);
    const r = state.home,
      d = r.data;
    frame(
      "Smart Home",
      r,
      `<div class="status-row">${d.contacts.map((c) => `<div class="contact ${c.open ? "open" : ""}"><i class="dot ${c.open ? "warn" : ""}"></i>${esc(c.name)} · ${c.available === false ? "Unavailable" : c.open ? "Open" + (c.openMinutes ? " " + c.openMinutes + " min" : "") : "Closed"}</div>`).join("")}<span class="meta">${esc(d.hub.name)} · ${d.hub.online ? "Online" : "Unavailable"}</span></div><div class="scenes">${d.scenes.map((s, i) => button(state.homeBusy ? "Sending…" : esc(s.name), `scene:${i}`, i === 2 ? "off" : "", state.homeBusy || r.stale ? "disabled" : "")).join("")}</div><div class="lights">${d.lights.map((l, i) => button(`<span class="top"><span>${svg(bulb, 30)}</span><span>${l.available === false ? "Unavailable" : state.homeBusy ? "Sending…" : l.on ? "On" : "Off"}</span></span><span class="n">${esc(l.name)}</span><span class="d">${esc(l.detail)}${l.on && l.brightness != null ? " · " + l.brightness + "%" : ""}</span>`, `light:${i}`, `light ${state.homeBusy ? "busy" : ""}`, `aria-pressed="${l.on}" ${state.homeBusy || r.stale || l.available === false ? "disabled" : ""}`)).join("")}</div><div class="cams">${d.cameras.map((c, i) => d.source === 'homeassistant' ? button(`<span class="tag">${esc(c.name)}</span>${c.available && !r.stale ? `<img data-camera-id="${esc(c.id)}" alt="Camera snapshot">` : ''}<span class="note camera-note">${r.stale ? 'State stale · open Smart Home to retry' : c.available ? 'Loading snapshot…' : 'Camera unavailable'}</span>`, `camera:${i}`, 'cam', c.available && !r.stale ? '' : 'disabled') : `<article class="cam"><span class="tag">${esc(c.name)}</span><span class="note">Sample placeholder · no live camera connected</span></article>`).join("")}<article class="pending"><b>${esc(d.doorbell.name)}</b><span>${d.doorbell.verified ? "Verified · video unavailable" : "Pending verification"}</span></article></div>`,
    );
    refreshCameras();
  }
  async function homeCommand(commands, undo = null) {
    if (state.homeBusy) return;
    const gen = state.generation;
    state.homeBusy = true;
    if (state.view === "home") drawHome();
    let message = "";
    try {
      for (const command of commands) {
        const r = await request("/api/home/action", "POST", command);
        if (r.data.result !== "confirmed")
          throw new Error("Unconfirmed command");
        message = r.data.message;
      }
      const r = await request("/api/home");
      state.home = r;
      toast(
        message +
          (r.data.source === "sample"
            ? " · confirmed by sample adapter"
            : " · confirmed"),
        undo,
      );
    } catch {
      toast("Command not confirmed · Retry");
      try {
        state.home = await request("/api/home");
      } catch {
        /* last known state remains */
      }
    } finally {
      state.homeBusy = false;
      if (current(gen) && state.view === "home") drawHome();
      refreshCommon();
    }
  }

  async function settings(gen) {
    const [r, sources] = await Promise.all([
      request("/api/settings"),
      request("/api/status"),
    ]);
    if (!current(gen)) return;
    state.settings = r.data;
    state.status = sources;
    state.settingsResult = r;
    drawSettings();
    syncFooter();
  }
  function drawSettings() {
    const s = state.settings,
      r = state.settingsResult;
    frame(
      "Settings",
      r,
      `<div class="set-grid"><article class="card settings-scroll"><h2>Sources</h2>${state.status.data.sources.map((src, i) => `<div class="src row-line"><i class="dot ${state.status.stale || ["failed", "stale"].includes(src.state) ? "warn" : src.state === "sample" ? "sample" : ""}"></i><div class="grow"><b>${esc(src.name)}</b><span>${state.status.stale ? "Stale status" : esc(src.state)} · ${src.updatedAt ? esc(time(src.updatedAt)) : "Not connected"}</span></div>${button("Retry", `retry:${i}`, "link")}</div>`).join("")}<p class="meta">Sample sources are not connected to real services.</p></article><article class="card settings-scroll"><h2>Display</h2><div class="set-row"><span class="l">Clock</span><div class="seg">${button("12 hour", "clock:12", "", `aria-pressed="${!s.clock24h}"`)}${button("24 hour", "clock:24", "", `aria-pressed="${s.clock24h}"`)}</div></div><div class="set-row"><span class="l">Temperature</span><div class="seg">${["F", "C"].map((u) => button("°" + u, `units:${u}`, "", `aria-pressed="${s.units === u}"`)).join("")}</div></div>${[
        ["idleMinutes", "Screensaver after", "min"],
        ["photoSeconds", "Photo interval", "sec"],
        ["returnTodayMinutes", "Return to Today", "min"],
      ]
        .map(
          ([key, label, unit]) =>
            `<div class="set-row"><span class="l">${label}</span><div class="stepper">${button("−", `step:${key}:-1`, "btn icon", `aria-label="Decrease ${label}"`)}<b>${s[key]} ${unit}</b>${button("+", `step:${key}:1`, "btn icon", `aria-label="Increase ${label}"`)}</div></div>`,
        )
        .join(
          "",
        )}<div class="set-row"><label for="quietStart">Quiet starts</label><input id="quietStart" type="time" value="${esc(s.quietStart)}" data-setting="quietStart"><label for="quietEnd">Ends</label><input id="quietEnd" type="time" value="${esc(s.quietEnd)}" data-setting="quietEnd"></div></article></div><div class="diag"><span>${esc(navigator.userAgent)}</span><span>Screen ${screen.width} × ${screen.height}</span>${button("Diagnostics", "diagnostics", "link")}</div><div class="meta" id="admin-hold">Admin: hold here with two fingers for 3 seconds. No credentials are stored in this browser.</div>`,
    );
  }
  async function saveSettings(change) {
    if (state.settingsBusy) return;
    state.settingsBusy = true;
    const gen = state.generation;
    const view = $(".view");
    if (view) view.setAttribute("aria-busy", "true");
    try {
      const r = await request("/api/settings", "POST", change);
      state.settings = r.data;
      state.settingsResult = r;
      remember("/api/settings", r.data);
      toast("Settings saved");
    } catch {
      toast("Settings not saved · Retry");
    } finally {
      state.settingsBusy = false;
      if (current(gen) && state.view === "settings") drawSettings();
    }
  }
  async function retrySource(index) {
    const src = state.status.data.sources[index],
      paths = {
        calendar: `/api/calendar?from=${encodeURIComponent(midnight(new Date()).toISOString())}&days=3`,
        weather: "/api/weather",
        photos: "/api/photos/manifest",
        shopping: "/api/shopping",
        home: "/api/home",
        govee: "/api/home",
      };
    try {
      const r = await request(paths[src.id]);
      const cloudPending = src.id === "govee" && !r.data.lights.filter(l=>l.id.startsWith("g")).every(l=>l.available);
      toast(
        cloudPending ? "Govee unavailable or refreshing · Retry shortly" : r.stale
          ? "Still unavailable · showing cached data"
          : r.data.source === "sample"
            ? "Sample source refreshed"
            : "Source refreshed",
      );
      await refreshCommon();
      if (state.view === "settings" && state.mode === "active") drawSettings();
    } catch {
      toast("Source unavailable · Retry later");
    }
  }

  function updateClocks() {
    const at = new Date();
    document.querySelectorAll("[data-clock]").forEach((el) => {
      const parts = at
        .toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
          hour12: !state.settings.clock24h,
        })
        .split(/\s+/);
      if (el.classList.contains("clock-big") && parts.length > 1) {
        el.textContent = parts[0];
        const suffix = document.createElement("small");
        suffix.textContent = parts.slice(1).join(" ");
        el.appendChild(suffix);
      } else el.textContent = time(at);
    });
    document.querySelectorAll("[data-date]").forEach((el) => {
      const weather = state.today && state.today.data.weather.current;
      el.textContent =
        date(at) +
        (state.mode !== "active" && weather
          ? ` · ${temp(weather.temp)}${state.mode === "saver" ? " " + weather.summary : ""}${state.today.stale ? " · Stale" : ""}`
          : "");
    });
    document.querySelectorAll("[data-now-line]").forEach((el) => {
      el.style.top = `${((at.getHours() * 60 + at.getMinutes()) * 40) / 60}px`;
    });
    const drift = $("[data-drift]");
    if (drift) {
      const minute = Math.floor(Date.now() / 60000);
      drift.style.transform = `translate(${(minute % 17) - 8}px,${(Math.floor(minute / 17) % 17) - 8}px)`;
    }
  }
  function quiet(at = new Date()) {
    const clock = at.getHours() * 60 + at.getMinutes();
    const parse = (t) =>
      /^\d{2}:\d{2}$/.test(t)
        ? Number(t.slice(0, 2)) * 60 + Number(t.slice(3))
        : 0;
    const start = parse(state.settings.quietStart),
      end = parse(state.settings.quietEnd);
    return (
      start !== end &&
      (start < end
        ? clock >= start && clock < end
        : clock >= start || clock < end)
    );
  }
  async function enterSaver(forcePhotos = false) {
    clearView();
    renderHTML(main, "");
    main.hidden = true;
    rail.hidden = true;
    const gen = ++state.generation;
    state.mode = !forcePhotos && quiet() ? "night" : "saver";
    if (state.mode === "night") {
      renderHTML(
        overlay,
        `<section class="saver night" aria-label="Night clock"><div class="t" data-clock></div><div class="d" data-date></div><div class="next" id="tomorrow">Loading tomorrow…</div><div class="foot">Quiet hours until ${esc(state.settings.quietEnd)} · tap to open Today</div><div id="night-alert"></div></section>`,
      );
      const start = addDays(midnight(new Date()), 1);
      try {
        const r = await request(
          `/api/calendar?from=${encodeURIComponent(start.toISOString())}&days=1`,
        );
        if (gen !== state.generation) return;
        const e = r.data.events
          .filter((e) => !e.allDay)
          .sort((a, b) => new Date(a.start) - new Date(b.start))[0];
        $("#tomorrow").textContent =
          `${r.stale ? "Stale · " : r.data.source === "sample" ? "Sample · " : ""}${e ? "Tomorrow · " + time(e.start) + " · " + e.title : "No timed events tomorrow"}`;
      } catch {
        if (gen === state.generation)
          $("#tomorrow").textContent = "Tomorrow unavailable";
      }
      renderNightAlert();
    } else {
      renderHTML(
        overlay,
        '<section class="saver" aria-label="Photo screensaver"><img alt="Slideshow photo" style="opacity:0"><img alt="Slideshow photo" style="opacity:0"><div class="scrim"></div><div class="clock" data-drift><div class="t" data-clock></div><div class="d" data-date></div><div class="meta" id="saver-source"></div></div><div class="hint" style="opacity:0">↑ Swipe up to open</div></section>',
      );
      let refreshBusy = false;
      async function refreshPhotos() {
        if (refreshBusy || gen !== state.generation) return;
        refreshBusy = true;
        try {
          const r = await readPhotos();
          if (gen !== state.generation) return;
          saverPhotos = r.data.photos.filter(
            (p) => state.collection === "All" || p.collections.includes(state.collection),
          );
          $("#saver-source").textContent = r.stale
            ? "Stale photos"
            : r.data.source === "sample"
              ? "Sample photos"
              : r.data.source === "unconfigured" ? "Aura photos need setup"
                : r.data.windowLimited ? "Aura photos · 1,000-photo selection" : "Aura photos";
          if (!saverPhotos.length) {
            overlay.querySelectorAll(".saver img").forEach((img) => {
              img.onload = null;
              img.onerror = null;
              img.removeAttribute("src");
              img.style.opacity = "0";
            });
          }
        } catch {
          if (gen === state.generation)
            $("#saver-source").textContent = "Photos unavailable";
        } finally {
          refreshBusy = false;
        }
      }
      await refreshPhotos();
      if (gen !== state.generation) return;
      later(refreshPhotos, 60000);
      let index = 0,
        layer = 0;
      function nextPhoto() {
        if (!saverPhotos.length) return;
        const images = overlay.querySelectorAll(".saver img");
        const next = images[layer];
        if (!next) return;
        next.onload = () => {
          if (gen === state.generation) {
            next.style.opacity = "1";
            images[1 - layer].style.opacity = "0";
            layer = 1 - layer;
          }
        };
        next.onerror = () => {
          if (gen === state.generation)
            $("#saver-source").textContent = "Photo unavailable · retrying";
        };
        next.src = photoURL(saverPhotos[index++ % saverPhotos.length]);
      }
      nextPhoto();
      later(nextPhoto, state.settings.photoSeconds * 1000);
    }
    if (gen === state.generation) {
      updateClocks();
      later(updateClocks, 1000);
    }
  }
  function renderNightAlert() {
    const el = $("#night-alert");
    if (!el) return;
    const a = state.today && state.today.data.alerts[0];
    renderHTML(
      el,
      a
        ? `<div class="nalert">⚠ ${esc(a.text)}${state.today.stale ? " · Stale" : state.today.data.source === "sample" ? " · Sample" : ""}</div>`
        : "",
    );
  }
  function wake() {
    state.lastInput = Date.now();
    navigate("today");
  }
  function idleCheck() {
    if (state.mode !== "active") {
      if (state.mode === "saver" && quiet()) enterSaver();
      else if (state.mode === "night" && !quiet()) enterSaver();
      return;
    }
    const elapsed = Date.now() - state.lastInput,
      returnMs = state.settings.returnTodayMinutes * 60000;
    if (state.view !== "today" && elapsed >= returnMs) {
      navigate("today");
      state.idleTodayAt = Date.now();
      return;
    }
    const base = state.idleTodayAt || state.lastInput;
    if (
      state.view === "today" &&
      Date.now() - base >= state.settings.idleMinutes * 60000
    )
      enterSaver();
  }
  async function refreshCommon(poll = false) {
    if (state.commonBusy) return;
    state.commonBusy = true;
    const gen = state.generation;
    try {
      if (!state.settingsLoaded) await loadSettings();
      const results = await Promise.allSettled([
        request("/api/today"),
        request("/api/status"),
      ]);
      if (results[0].status === "fulfilled") state.today = results[0].value;
      if (results[1].status === "fulfilled") state.status = results[1].value;
      alerts();
      syncFooter();
      renderNightAlert();
      // Never reset a form or modal while someone is using it. Reads still update
      // the global alert/health, and the mounted view refreshes on the next poll.
      if (
        current(gen) &&
        !modalFocus &&
        !state.shoppingBusy.size &&
        !state.homeBusy &&
        !state.settingsBusy &&
        !document.activeElement.matches("input, select") &&
        (poll || state.view === "today")
      ) {
        const scroll = captureScroll();
        state.timers.forEach(clearInterval);
        state.timers = [];
        try {
          if (state.view === "today" && state.today)
            await today(gen, state.today);
          else await renders[state.view](gen);
        } catch {
          /* retain mounted view on a cold-source failure */
        }
        if (current(gen)) restoreScroll(scroll);
      }
    } finally {
      state.commonBusy = false;
    }
  }
  const renders = {
    today,
    calendar,
    shopping,
    weather,
    quotes,
    photos,
    home,
    settings,
  };

  async function action(value) {
    const [kind, arg, delta] = value.split(":");
    if (kind === "nav") return navigate(arg);
    if (kind === "refresh") return navigate();
    if (kind === "close") return closeModal();
    if (kind === "undo") {
      const fn = toastUndo;
      toastUndo = null;
      const el = $(".toast");
      if (el) el.remove();
      if (fn) {
        try {
          await fn();
        } catch {
          toast("Undo not confirmed", fn, "Retry", 0);
        }
      }
      return;
    }
    if (kind === "event") return eventDetail(arg);
    if (kind === "camera") return cameraViewer(Number(arg));
    if (kind === "monthday") {
      const day = new Date(Number(arg)),
        events = state.calendar.data.events.filter(
          (e) =>
            !state.filters.has(e.calendar) &&
            new Date(e.start) < addDays(day, 1) &&
            new Date(e.end) > day,
        );
      return modal(
        date(day),
        `<div class="day-events">${events.length ? events.map((e) => button(`${esc(e.title)} · ${e.allDay ? "All day" : esc(time(e.start))}`, `event:${esc(e.id)}`, "btn")).join("") : "<p>No events</p>"}</div>${button("Open Day view", "calday:" + arg)}`,
      );
    }
    if (kind === "calday") {
      state.calDate = new Date(Number(arg));
      state.calMode = 1;
      return navigate();
    }
    if (kind === "calmode") {
      state.calMode = Number(arg);
      return navigate();
    }
    if (kind === "caltoday") {
      state.calDate = midnight(new Date());
      return navigate();
    }
    if (kind === "calprev" || kind === "calnext") {
      const direction = kind === "calprev" ? -1 : 1;
      if (state.calMode === 42) {
        state.calDate.setDate(1);
        state.calDate.setMonth(state.calDate.getMonth() + direction);
      } else state.calDate = addDays(state.calDate, direction * state.calMode);
      return navigate();
    }
    if (kind === "filter") {
      if (state.filters.has(arg)) state.filters.delete(arg);
      else state.filters.add(arg);
      return navigate();
    }
    if (kind === "quick")
      return shoppingWrite("/api/shopping", "POST", {
        name: state.shopping.data.quickAdd[Number(arg)],
      });
    if (kind === "toggle") {
      const retry = state.shoppingErrors.get(arg);
      if (retry)
        return shoppingWrite(
          retry.path,
          retry.method,
          retry.body,
          arg,
          retry.undo,
        );
      const item = state.shopping.data.items.find((i) => i.id === arg);
      return shoppingWrite(
        "/api/shopping/" + arg,
        "PATCH",
        { done: !item.done },
        arg,
      );
    }
    if (kind === "delete") {
      const i = state.shopping.data.items.find((i) => i.id === arg);
      const restoreKey = shoppingRequestKey();
      let restoredId = null;
      return shoppingWrite(
        "/api/shopping/" + arg,
        "DELETE",
        {},
        arg,
        async () => {
          let r = restoredId ? await request("/api/shopping") : await request("/api/shopping", "POST", {
            name: i.name,
            qty: i.qty,
            notes: i.notes || "",
            category: i.category,
            requestKey: restoreKey,
          });
          restoredId = restoredId || r.data.addedId;
          if (!restoredId) throw new Error("Restored item not confirmed");
          if (i.done) {
            r = await request("/api/shopping/" + restoredId, "PATCH", {
              done: true,
            });
          }
          remember("/api/shopping", r.data);
          state.shopping = r;
          if (state.view === "shopping") drawShopping(r);
          toast("Item restored");
          refreshCommon();
        },
      );
    }
    if (kind === "clearshopping")
      return shoppingWrite("/api/shopping/clear", "POST", {});
    if (kind === "nextquote") {
      state.quoteIndex =
        (state.quoteIndex + 1) % state.quotes.data.quotes.length;
      return drawQuote();
    }
    if (kind === "savequote") {
      const text = state.quotes.data.quotes[state.quoteIndex].text;
      state.favorites = state.favorites.includes(text)
        ? state.favorites.filter((t) => t !== text)
        : [...state.favorites, text];
      try {
        localStorage.setItem(
          "hub.quoteFavorites",
          JSON.stringify(state.favorites),
        );
      } catch {
        toast("Saved for this session only");
      }
      return drawQuote();
    }
    if (kind === "collection") {
      state.collection = state.photos.data.collections[Number(arg)];
      return drawPhotos();
    }
    if (kind === "photo") return viewer(Number(arg));
    if (kind === "photoprev" || kind === "photonext")
      return viewer(photoIndex + (kind === "photoprev" ? -1 : 1));
    if (kind === "slideshow") return enterSaver(true);
    if (kind === "light" || kind === "scene") {
      const before = state.home.data.lights.map((l) => ({
        kind: "light",
        id: l.id,
        on: l.on,
      }));
      if (kind === "light") {
        const l = state.home.data.lights[Number(arg)];
        return homeCommand([{ kind: "light", id: l.id, on: !l.on }], () =>
          homeCommand(before.filter((b) => b.id === l.id)),
        );
      }
      return homeCommand(
        [{ kind: "scene", id: state.home.data.scenes[Number(arg)].id }],
        () => homeCommand(before),
      );
    }
    if (kind === "clock") return saveSettings({ clock24h: arg === "24" });
    if (kind === "units") return saveSettings({ units: arg });
    if (kind === "step") {
      const bounds = {
          idleMinutes: [1, 30, 1],
          photoSeconds: [10, 300, 10],
          returnTodayMinutes: [1, 30, 1],
        },
        [lo, hi, increment] = bounds[arg];
      return saveSettings({
        [arg]: Math.min(
          hi,
          Math.max(lo, state.settings[arg] + Number(delta) * increment),
        ),
      });
    }
    if (kind === "retry") return retrySource(Number(arg));
    if (kind === "diagnostics")
      return modal(
        "Diagnostics",
        `<p>${esc(navigator.userAgent)}</p><p>Viewport ${innerWidth} × ${innerHeight}; screen ${screen.width} × ${screen.height}</p><p>Last error: ${esc(state.lastError || "None")}</p><p>Backend stores credentials; admin setup is performed on the server.</p>`,
      );
  }
  document.addEventListener("click", (e) => {
    if (state.mode === "night") return wake();
    if (state.mode === "saver") {
      const hint = $(".hint");
      if (hint) {
        hint.style.opacity = "1";
        clearTimeout(hintTimer);
        hintTimer = setTimeout(() => {
          hint.style.opacity = "0";
        }, 3000);
      }
      return;
    }
    const el = e.target.closest("[data-action]");
    if (el && !el.disabled)
      action(el.dataset.action).catch(() => toast("Action failed · Retry"));
    else if (e.target.classList.contains("modal-back")) closeModal();
  });
  document.addEventListener("submit", (e) => {
    if (e.target.id !== "add-form") return;
    e.preventDefault();
    const form = e.target,
      data = new FormData(form),
      name = String(data.get("name")).trim();
    if (!name) return;
    const submit = $("button", form);
    submit.disabled = true;
    submit.textContent = "Saving…";
    shoppingWrite("/api/shopping", "POST", {
      name,
      qty: data.get("qty"),
      notes: data.get("notes"),
      category: data.get("category"),
    }).finally(() => {
      if (form.isConnected) {
        submit.disabled = false;
        submit.textContent = "Add";
      }
    });
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "calendar-date" && e.target.value) {
      state.calDate = midnight(new Date(e.target.value + "T12:00:00"));
      navigate();
    }
    if (e.target.dataset.setting)
      saveSettings({ [e.target.dataset.setting]: e.target.value });
  });
  function inputActivity() {
    if (state.mode === "active") {
      state.lastInput = Date.now();
      state.idleTodayAt = null;
    }
  }
  ["pointerdown", "keydown", "input"].forEach((type) =>
    document.addEventListener(type, inputActivity, { passive: true }),
  );
  let swipeStart = null;
  document.addEventListener("pointerdown", (e) => {
    if (state.mode === "saver") swipeStart = { y: e.clientY, at: Date.now() };
  });
  document.addEventListener("pointerup", (e) => {
    if (
      state.mode === "saver" &&
      swipeStart &&
      e.clientY - swipeStart.y < -80 &&
      Date.now() - swipeStart.at < 800
    )
      wake();
    swipeStart = null;
  });
  document.addEventListener("pointercancel", () => {
    swipeStart = null;
  });
  document.addEventListener(
    "touchstart",
    (e) => {
      if (
        state.mode === "active" &&
        state.view === "settings" &&
        e.touches.length === 2 &&
        e.target.closest("#admin-hold")
      ) {
        clearTimeout(adminTimer);
        const gen = state.generation;
        adminTimer = setTimeout(() => {
          if (current(gen))
            modal(
              "Admin setup",
              "<p>Real-service adapters and secrets are configured on the server, not on this frame. No browser admin actions are enabled yet.</p>",
            );
        }, 3000);
      }
    },
    { passive: true },
  );
  ["touchend", "touchcancel", "touchmove"].forEach((type) =>
    document.addEventListener(type, () => clearTimeout(adminTimer), {
      passive: true,
    }),
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (state.mode !== "active") wake();
      else closeModal();
    }
    if (e.key === "Tab" && modalFocus) {
      const focusable = [
        ...overlay.querySelectorAll("button, input, select, [tabindex]"),
      ].filter((el) => !el.disabled);
      if (!focusable.length) return;
      const first = focusable[0],
        last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });
  window.addEventListener("resize", fit);
  fit();
  window.addEventListener("online", () => {
    refreshCommon();
    if (state.mode === "active" && !$("#add-form input:focus")) navigate();
  });
  window.addEventListener("error", () => {
    state.lastError = "Browser script error";
  });
  async function loadSettings() {
    try {
      const r = await request("/api/settings");
      state.settings = r.data;
      state.settingsLoaded = !r.stale;
    } catch {
      /* safe defaults until the server answers */
    }
  }
  async function start() {
    await loadSettings();
    await navigate("today");
    refreshCommon();
    setInterval(() => refreshCommon(true), 60000);
    // After a cold start without the server (e.g. the frame booted first), retry
    // sooner than the regular poll until settings and Today data have arrived.
    setInterval(() => {
      if (!state.settingsLoaded || !state.today) refreshCommon(true);
    }, 10000);
    setInterval(idleCheck, 1000);
  }
  start();
})();
