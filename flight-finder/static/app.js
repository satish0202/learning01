"use strict";

const $ = (sel) => document.querySelector(sel);
const form = $("#search-form");
const submitBtn = $("#submit");
const formError = $("#form-error");

function isoDate(d) {
  const tz = d.getTimezoneOffset() * 60000;
  return new Date(d - tz).toISOString().slice(0, 10);
}

function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtMoney(amount, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${currency} ${Math.round(amount)}`;
  }
}

function fmtDuration(min) {
  const h = Math.floor(min / 60), m = min % 60;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

function fmtTime(iso) {
  return iso.slice(11, 16);
}

function fmtDay(iso) {
  return new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short",
  });
}

function stopsLabel(leg) {
  if (leg.stops === 0) return "Non-stop";
  const via = leg.via && leg.via.length ? ` via ${leg.via.join(", ")}` : "";
  return `${leg.stops} stop${leg.stops > 1 ? "s" : ""}${via}`;
}

// --- Form setup -----------------------------------------------------------

function setupForm() {
  form.depart_date.min = addDays(0);
  form.return_date.min = addDays(0);
  form.depart_date.value = addDays(21);
  form.return_date.value = addDays(28);

  form.querySelectorAll("input[name=trip]").forEach((r) =>
    r.addEventListener("change", () => {
      const oneway = form.trip.value === "oneway";
      $("#return-field").hidden = oneway;
      form.return_date.required = !oneway;
    })
  );
  form.depart_date.addEventListener("change", () => {
    form.return_date.min = form.depart_date.value;
    if (form.return_date.value && form.return_date.value < form.depart_date.value) {
      form.return_date.value = form.depart_date.value;
    }
  });
  form.addEventListener("submit", onSubmit);
}

async function loadProviders() {
  const select = $("#provider");
  try {
    const res = await fetch("/api/providers");
    const providers = await res.json();
    select.innerHTML = providers.map((p) =>
      `<option value="${esc(p.name)}" ${p.available ? "" : "disabled"} title="${esc(p.description)}">` +
      `${esc(p.label)}${p.available ? "" : " (not configured)"}</option>`
    ).join("");
    const live = providers.find((p) => p.name !== "demo" && p.available);
    if (live) select.value = live.name;
  } catch {
    select.innerHTML = `<option value="demo">Demo data (offline)</option>`;
  }
}

function readSpec() {
  const f = new FormData(form);
  const val = (k) => (f.get(k) ?? "").toString().trim();
  const spec = {
    origin: val("origin").toUpperCase(),
    destination: val("destination").toUpperCase(),
    depart_date: val("depart_date"),
    return_date: form.trip.value === "return" ? val("return_date") || null : null,
    adults: Number(val("adults") || 1),
    cabin: val("cabin"),
    currency: val("currency"),
    sort_by: val("sort_by"),
    provider: val("provider") || "demo",
    max_price: val("max_price") ? Number(val("max_price")) : null,
    max_stops: val("max_stops") === "" ? null : Number(val("max_stops")),
    earliest_departure: val("earliest_departure") || null,
    latest_departure: val("latest_departure") || null,
    airlines: val("airlines") ? val("airlines").split(/[,\s]+/).filter(Boolean) : null,
  };
  return spec;
}

function validate(spec) {
  const code = /^[A-Z]{3}$/;
  if (!code.test(spec.origin)) return "Enter a 3-letter 'From' airport code, like JFK.";
  if (!code.test(spec.destination)) return "Enter a 3-letter 'To' airport code, like LHR.";
  if (spec.origin === spec.destination) return "'From' and 'To' must be different airports.";
  if (!spec.depart_date) return "Choose a departure date.";
  if (form.trip.value === "return" && !spec.return_date) return "Choose a return date, or switch to one way.";
  if (spec.return_date && spec.return_date < spec.depart_date) return "Return date is before the departure date.";
  return null;
}

function showError(msg) {
  formError.textContent = msg;
  formError.hidden = !msg;
}

function apiError(body, status) {
  const d = body && body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => {
      const field = (e.loc || []).filter((x) => x !== "body").join(".");
      return field ? `${field}: ${e.msg}` : e.msg;
    }).join(" · ");
  }
  return `Search failed (HTTP ${status}).`;
}

// --- Search ---------------------------------------------------------------

async function onSubmit(e) {
  e.preventDefault();
  const spec = readSpec();
  const problem = validate(spec);
  if (problem) return showError(problem);
  showError("");

  submitBtn.disabled = true;
  submitBtn.textContent = "Searching…";
  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(apiError(body, res.status));
    renderResult(body);
    if (window.matchMedia("(max-width: 820px)").matches) {
      $(".results").scrollIntoView({ behavior: "smooth" });
    }
    loadHistory();
  } catch (err) {
    showError(err.message || "Search failed.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Find flights";
  }
}

function legHtml(leg, label) {
  return `
    <div class="leg">
      <div class="airline">${esc(leg.airline)}
        <small>${esc(label)} · ${esc(fmtDay(leg.depart_at))} · ${esc(leg.flight_numbers.join(" / "))}</small>
      </div>
      <div class="times">
        <div class="t">${esc(fmtTime(leg.depart_at))}<small>${esc(leg.origin)}</small></div>
        <div class="line ${leg.stops === 0 ? "nonstop" : ""}">${esc(fmtDuration(leg.duration_minutes))}<br>${esc(stopsLabel(leg))}</div>
        <div class="t">${esc(fmtTime(leg.arrive_at))}<small>${esc(leg.destination)}</small></div>
      </div>
    </div>`;
}

function renderResult(r) {
  const req = r.request;
  const header = $("#results-header");
  const dates = req.return_date
    ? `${fmtDay(req.depart_date)} – ${fmtDay(req.return_date)}`
    : `${fmtDay(req.depart_date)}, one way`;
  header.innerHTML = `
    <h2>${esc(req.origin)} → ${esc(req.destination)}</h2>
    <p>${esc(dates)} · ${req.adults} adult${req.adults > 1 ? "s" : ""} · ${esc(req.cabin.replace("_", " "))}
       · ${r.offers.length} match${r.offers.length === 1 ? "" : "es"} of ${r.total_found} found
       · search #${r.search_id}</p>`;
  header.hidden = false;

  $("#notes").innerHTML = (r.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
  $("#results-empty").hidden = r.offers.length > 0;
  $("#results-empty").innerHTML = r.offers.length
    ? ""
    : "<p>No flights match this spec. Try raising the max price or allowing more stops.</p>";

  const cheapest = Math.min(...r.offers.map((o) => o.price));
  const fastest = Math.min(...r.offers.map((o) => o.outbound.duration_minutes + (o.inbound ? o.inbound.duration_minutes : 0)));
  $("#results").innerHTML = r.offers.map((o) => {
    const total = o.outbound.duration_minutes + (o.inbound ? o.inbound.duration_minutes : 0);
    const badges = [
      o.price === cheapest ? "Cheapest" : null,
      total === fastest ? "Fastest" : null,
    ].filter(Boolean).map((b) => `<span class="badge">${b}</span> `).join("");
    return `
      <li class="card">
        <div class="legs">
          ${legHtml(o.outbound, "Outbound")}
          ${o.inbound ? legHtml(o.inbound, "Return") : ""}
        </div>
        <div class="price">
          ${badges}
          <strong>${esc(fmtMoney(o.price, o.currency))}</strong>
          <small>total · ${esc(o.provider)}</small>
          ${o.booking_url ? `<br><a href="${esc(o.booking_url)}" target="_blank" rel="noopener">Book</a>` : ""}
        </div>
      </li>`;
  }).join("");
}

// --- History --------------------------------------------------------------

async function loadHistory() {
  const list = $("#history-list");
  try {
    const res = await fetch("/api/searches?limit=10");
    const items = await res.json();
    if (!items.length) {
      list.innerHTML = `<li class="muted">No searches yet.</li>`;
      return;
    }
    list.innerHTML = items.map((s) => `
      <li>
        <a data-id="${s.id}">${esc(s.origin)} → ${esc(s.destination)}, ${esc(fmtDay(s.depart_date))}${s.return_date ? " ⇄" : ""}</a>
        <span class="muted">${s.cheapest_price != null ? esc(fmtMoney(s.cheapest_price, s.currency)) : "none"}</span>
      </li>`).join("");
    list.querySelectorAll("a[data-id]").forEach((a) =>
      a.addEventListener("click", () => openSearch(a.dataset.id))
    );
  } catch {
    list.innerHTML = `<li class="muted">Could not load history.</li>`;
  }
}

async function openSearch(id) {
  const res = await fetch(`/api/searches/${id}`);
  if (res.ok) renderResult(await res.json());
}

setupForm();
loadProviders();
loadHistory();
