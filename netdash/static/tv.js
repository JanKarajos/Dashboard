/* TV režim – domovská obrazovka ovládaná šípkami. Zámerne ES5 kvôli starším prehliadačom v TV. */
(function () {
  "use strict";

  var DAYS = ["nedeľa", "pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota"];
  var MONTHS = ["januára", "februára", "marca", "apríla", "mája", "júna", "júla", "augusta", "septembra", "októbra", "novembra", "decembra"];
  var WEATHER = [[0, "☀", "Jasno"], [1, "🌤", "Prevažne jasno"], [2, "⛅", "Polojasno"], [3, "☁", "Zamračené"],
    [48, "🌫", "Hmla"], [57, "🌦", "Mrholenie"], [67, "🌧", "Dážď"], [77, "❄", "Sneženie"], [82, "🌧", "Prehánky"],
    [86, "🌨", "Snehové prehánky"], [99, "⛈", "Búrka"]];
  var COLORS = [["#ffd9a0", "Teplá biela"], ["#ffffff", "Biela"], ["#ff3b30", "Červená"], ["#ff9500", "Oranžová"],
    ["#34c759", "Zelená"], ["#007aff", "Modrá"], ["#af52de", "Fialová"]];
  var CAT_ORDER = { media: 0, smart: 1, server: 3 };

  var devices = [], controls = {}, lastAction = 0, weatherLoaded = false, userMoved = false;

  function $(id) { return document.getElementById(id); }

  function xhr(method, url, body, cb) {
    var r = new XMLHttpRequest();
    r.open(method, url, true);
    if (body !== undefined) {
      r.setRequestHeader("Content-Type", "application/json");
      r.setRequestHeader("X-NetDash", "1");
    }
    r.onreadystatechange = function () {
      if (r.readyState !== 4) return;
      var data = {};
      try { data = JSON.parse(r.responseText); } catch (e) { /* nič */ }
      if (r.status === 401) { showLogin(); return cb(new Error("PIN")); }
      if (r.status < 200 || r.status >= 300) return cb(new Error(data.error || ("HTTP " + r.status)));
      cb(null, data);
    };
    r.send(body === undefined ? null : JSON.stringify(body));
  }

  function toast(msg) {
    var t = $("toast");
    t.textContent = msg;
    t.style.display = "block";
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { t.style.display = "none"; }, 5000);
  }

  /* ---------------------------------------------------------- hodiny, počasie */
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function tick() {
    var d = new Date();
    $("clock").textContent = d.getHours() + ":" + pad(d.getMinutes());
    var day = DAYS[d.getDay()];
    $("date").textContent = day.charAt(0).toUpperCase() + day.slice(1) + ", " + d.getDate() + ". " + MONTHS[d.getMonth()];
  }

  function loadWeather(loc) {
    if (!loc) return;
    var r = new XMLHttpRequest();
    r.open("GET", "https://api.open-meteo.com/v1/forecast?latitude=" + loc[0] + "&longitude=" + loc[1] +
      "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1", true);
    r.onreadystatechange = function () {
      if (r.readyState !== 4 || r.status !== 200) return;
      try {
        var j = JSON.parse(r.responseText), code = j.current.weather_code, w = WEATHER[WEATHER.length - 1];
        for (var i = 0; i < WEATHER.length; i++) if (code <= WEATHER[i][0]) { w = WEATHER[i]; break; }
        $("weather").innerHTML = w[1] + " " + Math.round(j.current.temperature_2m) + "°" +
          "<small>" + w[2] + " · " + Math.round(j.daily.temperature_2m_min[0]) + "° / " + Math.round(j.daily.temperature_2m_max[0]) + "°</small>";
      } catch (e) { /* nič */ }
    };
    r.send(null);
  }

  /* ---------------------------------------------------------- dáta */
  function loadState() {
    xhr("GET", "/api/state", undefined, function (err, d) {
      setTimeout(loadState, 60000);
      if (err) return;
      $("login").style.display = "none";
      if (!weatherLoaded) { weatherLoaded = true; loadWeather(d.location); setInterval(function () { loadWeather(d.location); }, 1800000); }
      var on = 0;
      for (var i = 0; i < d.devices.length; i++) if (d.devices[i].online) on++;
      $("net").innerHTML = "Sieť: <b>" + on + "</b> zariadení online";
      devices = d.devices.filter(function (x) { return x.controllable && (x.online || x.category === "media"); });
      devices.sort(function (a, b) {
        var ca = CAT_ORDER[a.category] !== undefined ? CAT_ORDER[a.category] : 2;
        var cb = CAT_ORDER[b.category] !== undefined ? CAT_ORDER[b.category] : 2;
        return ca - cb || a.display_name.localeCompare(b.display_name);
      });
      for (var k = 0; k < devices.length; k++) loadControls(devices[k]);
      render();
    });
  }

  function loadControls(dev) {
    xhr("GET", "/api/devices/" + encodeURIComponent(dev.id) + "/controls", undefined, function (err, d) {
      controls[dev.id] = err ? [] : d.controls;
      render();
    });
  }

  function send(dev, id, value, tile) {
    lastAction = Date.now();
    if (tile) tile.className += " busy";
    xhr("POST", "/api/devices/" + encodeURIComponent(dev.id) + "/controls", { id: id, value: value }, function (err, d) {
      if (err) { toast(dev.display_name + ": " + err.message); if (tile) tile.className = tile.className.replace(" busy", ""); return; }
      controls[dev.id] = d.controls;
      render();
    });
  }

  /* ---------------------------------------------------------- vykreslenie */
  function tile(key, title, sub, opts, onclick) {
    var b = document.createElement("button");
    b.className = "tile" + (opts.cls ? " " + opts.cls : "");
    b.setAttribute("data-key", key);
    var top = document.createElement("div");
    if (opts.icon) { var ic = document.createElement("div"); ic.className = "ico"; ic.textContent = opts.icon; top.appendChild(ic); }
    if (opts.swatch) { var sw = document.createElement("div"); sw.className = "swatch"; sw.style.background = opts.swatch; top.appendChild(sw); }
    var t = document.createElement("div"); t.className = "t"; t.textContent = title;
    var s = document.createElement("div"); s.className = "s"; s.textContent = sub || "";
    b.appendChild(top); b.appendChild(t); b.appendChild(s);
    if (onclick) b.onclick = function () { onclick(b); };
    else b.tabIndex = -1;
    return b;
  }

  function tilesFor(dev, list) {
    var out = [], sensors = [];
    for (var i = 0; i < list.length; i++) {
      (function (c) {
        var key = dev.id + "|" + c.id, label = c.label;
        if (c.type === "toggle") {
          out.push(tile(key, label, c.value ? "Zapnuté" : "Vypnuté", { cls: c.value ? "on" : "", icon: c.value ? "●" : "○" },
            function (b) { send(dev, c.id, !c.value, b); }));
        } else if (c.type === "button") {
          var icons = { power: "⏻", play: "▶", pause: "⏸", up: "▲", down: "▼", stop: "■", next: "⏭", prev: "⏮", link: "🔗", home: "⌂" };
          out.push(tile(key, label, "", { cls: "sm", icon: icons[c.icon] || "•" }, function (b) { send(dev, c.id, true, b); }));
        } else if (c.type === "slider") {
          var step = Math.max(c.step || 1, Math.round((c.max - c.min) / 10));
          var val = c.value + (c.unit || "");
          out.push(tile(key + "-", label + " −", val, { cls: "sm", icon: "−" },
            function (b) { send(dev, c.id, Math.max(c.min, Number(c.value) - step), b); }));
          out.push(tile(key + "+", label + " +", val, { cls: "sm", icon: "+" },
            function (b) { send(dev, c.id, Math.min(c.max, Number(c.value) + step), b); }));
        } else if (c.type === "select") {
          var opts = (c.options || []).filter(function (o) { return o[0] !== "" && o[0] !== -1 && o[1] !== "—"; }).slice(0, 24);
          for (var k = 0; k < opts.length; k++) {
            (function (o) {
              var active = String(o[0]) === String(c.value);
              out.push(tile(key + "=" + o[0], o[1], c.label, { cls: active ? "on" : "app", icon: "▸" },
                function (b) { send(dev, c.id, o[0], b); }));
            })(opts[k]);
          }
        } else if (c.type === "color") {
          for (var m = 0; m < COLORS.length; m++) {
            (function (col) {
              out.push(tile(key + "=" + col[0], col[1], label, { cls: "sm", swatch: col[0] }, function (b) { send(dev, c.id, col[0], b); }));
            })(COLORS[m]);
          }
        } else if (c.type === "sensor") {
          sensors.push(label + " " + c.value + (c.unit ? " " + c.unit : ""));
        } else if (c.type === "notice" && list.length <= 3) {
          out.push(tile(key, "Nastav na počítači", label.slice(0, 70), { cls: "info" }));
        }
      })(list[i]);
    }
    return { tiles: out, sensors: sensors };
  }

  function rail(title, sub, tiles) {
    var r = document.createElement("section");
    r.className = "rail";
    var h = document.createElement("h2");
    h.textContent = title;
    if (sub) { var sp = document.createElement("span"); sp.textContent = sub; h.appendChild(sp); }
    var row = document.createElement("div");
    row.className = "tiles";
    for (var i = 0; i < tiles.length; i++) row.appendChild(tiles[i]);
    r.appendChild(h); r.appendChild(row);
    return r;
  }

  function render() {
    var focusedKey = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-key");
    var root = $("rails");
    var rails = [];
    for (var i = 0; i < devices.length; i++) {
      var dev = devices[i], list = controls[dev.id];
      if (!list) continue;
      var groups = [], byGroup = {};
      for (var k = 0; k < list.length; k++) {
        var g = list[k].group || "";
        if (list[k].type === "pad") continue;
        if (!byGroup[g]) { byGroup[g] = []; groups.push(g); }
        byGroup[g].push(list[k]);
      }
      // svetlá Hue/HA: všetky skupiny jedného zariadenia do riadkov podľa skupiny
      var split = groups.length > 3;
      if (!split) {
        var r = tilesFor(dev, list.filter(function (c) { return c.type !== "pad"; }));
        if (r.tiles.length) rails.push(rail(dev.display_name, r.sensors.join(" · "), r.tiles));
      } else {
        for (var n = 0; n < groups.length; n++) {
          var rr = tilesFor(dev, byGroup[groups[n]]);
          if (rr.tiles.length) rails.push(rail(dev.display_name + (groups[n] ? " – " + groups[n] : ""), rr.sensors.join(" · "), rr.tiles));
        }
      }
    }
    root.innerHTML = "";
    if (!rails.length) {
      var e = document.createElement("div"); e.className = "empty";
      e.textContent = devices.length ? "Načítavam ovládanie…" : "Zatiaľ žiadne ovládateľné zariadenia. Preskenuj sieť v dashboarde.";
      root.appendChild(e);
    }
    for (var j = 0; j < rails.length; j++) root.appendChild(rails[j]);
    var target = null, all = focusables();
    for (var q = 0; q < all.length; q++) if (all[q].getAttribute("data-key") === focusedKey) target = all[q];
    if (!userMoved && all.length) target = all[0];
    if (!target && all.length && (!document.activeElement || document.activeElement === document.body)) target = all[0];
    if (target) focus(target);
  }

  /* ---------------------------------------------------------- navigácia šípkami */
  function focusables() {
    var list = document.querySelectorAll(".tile"), out = [];
    for (var i = 0; i < list.length; i++) if (list[i].tabIndex !== -1) out.push(list[i]);
    return out;
  }

  function focus(el) {
    el.focus();
    var firstRail = document.querySelector(".rail");
    if (firstRail && firstRail.contains(el)) {
      window.scrollTo(0, 0);
      var row = el.parentNode;
      if (el.offsetLeft + el.offsetWidth > row.scrollLeft + row.clientWidth || el.offsetLeft < row.scrollLeft) row.scrollLeft = el.offsetLeft - 20;
      return;
    }
    try { el.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" }); }
    catch (e) { el.scrollIntoView(false); }
  }

  function move(dir) {
    var cur = document.activeElement, all = focusables();
    if (!cur || all.indexOf(cur) < 0) { if (all.length) focus(all[0]); return; }
    var a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2, best = null, bestScore = 1e9;
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el === cur) continue;
      var b = el.getBoundingClientRect(), bx = b.left + b.width / 2, by = b.top + b.height / 2;
      var dx = bx - ax, dy = by - ay, main, cross;
      if (dir === "left") { if (dx > -5) continue; main = -dx; cross = Math.abs(dy); }
      else if (dir === "right") { if (dx < 5) continue; main = dx; cross = Math.abs(dy); }
      else if (dir === "up") { if (dy > -5) continue; main = -dy; cross = Math.abs(dx); }
      else { if (dy < 5) continue; main = dy; cross = Math.abs(dx); }
      if ((dir === "left" || dir === "right") && cross > a.height / 2) continue; // vodorovne len v rámci riadku
      var score = main + cross * ((dir === "up" || dir === "down") ? 0.5 : 3);
      if ((dir === "up" || dir === "down")) score = main * 3 + Math.abs(b.left - a.left) * 0.2 + (b.left > -10 ? 0 : 400);
      if (score < bestScore) { bestScore = score; best = el; }
    }
    if (best) focus(best);
  }

  document.addEventListener("keydown", function (e) {
    if ($("login").style.display !== "none") return;
    var k = e.keyCode, dir = { 37: "left", 38: "up", 39: "right", 40: "down" }[k];
    if (dir) { e.preventDefault(); userMoved = true; move(dir); }
    if (k === 13) userMoved = true;
  });

  /* ---------------------------------------------------------- PIN */
  function showLogin() {
    $("login").style.display = "flex";
    setTimeout(function () { $("pin").focus(); }, 50);
  }
  $("loginForm").onsubmit = function (e) {
    e.preventDefault();
    xhr("POST", "/api/login", { pin: $("pin").value }, function (err) {
      if (err) { toast(err.message); return; }
      $("login").style.display = "none";
      loadState();
    });
  };

  /* obnova stavu ovládania */
  setInterval(function () {
    if (Date.now() - lastAction < 6000) return;
    for (var i = 0; i < devices.length; i++) loadControls(devices[i]);
  }, 20000);

  tick();
  setInterval(tick, 5000);
  loadState();
})();
