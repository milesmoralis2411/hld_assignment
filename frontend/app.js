// Frontend logic for the Search Typeahead UI.
// Talks to the FastAPI backend: /suggest, /search, /trending, /metrics, /cache/debug

const $ = (id) => document.getElementById(id);
const input = $("search");
const list = $("suggestions");
const statusEl = $("status");

let suggestions = [];
let activeIndex = -1;
let debounceTimer = null;
let lastRequestId = 0;

function ranking() {
  const r = document.querySelector('input[name="ranking"]:checked');
  return r ? r.value : "count";
}

function setStatus(msg, kind = "") {
  statusEl.className = "status " + kind;
  statusEl.textContent = kind === "loading" ? "" : msg;
}

// ---- debounced suggestion fetching (avoids a backend call per keystroke) ----
input.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  const q = input.value;
  if (!q.trim()) { hideSuggestions(); refreshRouting(""); return; }
  setStatus("", "loading");
  debounceTimer = setTimeout(() => fetchSuggestions(q), 130);
});

async function fetchSuggestions(q) {
  const reqId = ++lastRequestId;
  try {
    const res = await fetch(`/suggest?q=${encodeURIComponent(q)}&ranking=${ranking()}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (reqId !== lastRequestId) return; // a newer keystroke already fired
    suggestions = data.suggestions || [];
    renderSuggestions(q, data.source);
    refreshRouting(q);
  } catch (e) {
    setStatus("Could not load suggestions: " + e.message, "error");
    hideSuggestions();
  }
}

function highlight(text, prefix) {
  const i = text.toLowerCase().indexOf(prefix.toLowerCase());
  if (i !== 0) return text;
  return `<mark>${text.slice(0, prefix.length)}</mark>${text.slice(prefix.length)}`;
}

function renderSuggestions(q, source) {
  if (!suggestions.length) {
    list.innerHTML = `<li class="muted">No matches for “${q}”</li>`;
    list.classList.remove("hidden");
    setStatus(`0 suggestions · source: ${source}`);
    return;
  }
  activeIndex = -1;
  list.innerHTML = suggestions.map((s, idx) => {
    const extra = s.recency_score !== undefined
      ? `count ${s.count} · recency ${s.recency_score}`
      : `count ${s.count}`;
    return `<li data-idx="${idx}">
      <span class="q">${highlight(s.query, q)}</span>
      <span class="meta">${extra}</span></li>`;
  }).join("");
  list.classList.remove("hidden");
  setStatus(`${suggestions.length} suggestions · source: ${source} · ranking: ${ranking()}`);

  [...list.querySelectorAll("li")].forEach((li) => {
    li.addEventListener("mousedown", (e) => {
      e.preventDefault();
      submit(suggestions[+li.dataset.idx].query);
    });
  });
}

function hideSuggestions() {
  list.classList.add("hidden");
  list.innerHTML = "";
  activeIndex = -1;
  setStatus("");
}

// ---- keyboard navigation ----
input.addEventListener("keydown", (e) => {
  const items = [...list.querySelectorAll("li[data-idx]")];
  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeIndex = Math.min(activeIndex + 1, items.length - 1);
    updateActive(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeIndex = Math.max(activeIndex - 1, 0);
    updateActive(items);
  } else if (e.key === "Enter") {
    if (activeIndex >= 0 && suggestions[activeIndex]) {
      submit(suggestions[activeIndex].query);
    } else {
      submit(input.value);
    }
  } else if (e.key === "Escape") {
    hideSuggestions();
  }
});

function updateActive(items) {
  items.forEach((li, i) => li.classList.toggle("active", i === activeIndex));
  if (items[activeIndex]) {
    input.value = suggestions[activeIndex].query;
    items[activeIndex].scrollIntoView({ block: "nearest" });
  }
}

$("search-btn").addEventListener("click", () => submit(input.value));

// ---- submit a search (POST /search) ----
async function submit(query) {
  query = (query || "").trim();
  if (!query) return;
  input.value = query;
  hideSuggestions();
  setStatus("", "loading");
  try {
    const res = await fetch("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const box = $("result");
    box.classList.remove("hidden");
    $("result-body").textContent = JSON.stringify(data, null, 2);
    setStatus(`Submitted “${query}” — counted toward popularity & trending.`);
    setTimeout(loadTrending, 250);
    setTimeout(loadMetrics, 250);
  } catch (e) {
    setStatus("Search failed: " + e.message, "error");
  }
}

// ---- trending ----
async function loadTrending() {
  try {
    const res = await fetch("/trending");
    const data = await res.json();
    const el = $("trending");
    if (!data.trending || !data.trending.length) {
      el.innerHTML = `<li class="muted">No activity yet — run a few searches.</li>`;
      return;
    }
    el.innerHTML = data.trending.map((t) =>
      `<li data-q="${t.query}">${t.query}
        <span class="score">recency ${t.recency_score} · count ${t.count}</span></li>`
    ).join("");
    [...el.querySelectorAll("li[data-q]")].forEach((li) =>
      li.addEventListener("click", () => { input.value = li.dataset.q; fetchSuggestions(li.dataset.q); }));
  } catch (e) {
    $("trending").innerHTML = `<li class="muted">Could not load trending.</li>`;
  }
}

// ---- metrics ----
async function loadMetrics() {
  try {
    const m = await (await fetch("/metrics")).json();
    $("m-p95").textContent = m.latency.p95_ms + " ms";
    $("m-p50").textContent = m.latency.p50_ms + " ms";
    $("m-hit").textContent = (m.cache.overall_hit_rate * 100).toFixed(1) + " %";
    $("m-hm").textContent = `${m.cache.total_hits} / ${m.cache.total_misses}`;
    $("m-db").textContent = `${m.database.db_reads} / ${m.database.db_writes}`;
    $("m-sub").textContent = m.batch_writes.raw_submissions;
    $("m-wr").textContent = (m.batch_writes.write_reduction * 100).toFixed(1) + " %";
    $("m-idx").textContent = `${m.index.words} / ${m.index.nodes}`;
  } catch (e) { /* ignore */ }
}

// ---- cache routing (consistent hashing) ----
async function refreshRouting(prefix) {
  if (!prefix.trim()) {
    $("r-key").textContent = "–"; $("r-node").textContent = "–";
    $("r-status").textContent = "–"; $("r-ring").textContent = "–";
    return;
  }
  try {
    const r = await (await fetch(`/cache/debug?prefix=${encodeURIComponent(prefix)}&ranking=${ranking()}`)).json();
    $("r-key").textContent = r.key;
    $("r-node").textContent = r.owner_node;
    $("r-status").textContent = r.cache_status;
    $("r-ring").textContent = r.total_points_on_ring;
  } catch (e) { /* ignore */ }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".search-wrap")) hideSuggestions();
});
$("refresh-trending").addEventListener("click", loadTrending);
$("refresh-metrics").addEventListener("click", loadMetrics);
document.querySelectorAll('input[name="ranking"]').forEach((r) =>
  r.addEventListener("change", () => { if (input.value.trim()) fetchSuggestions(input.value); }));

// initial load
loadTrending();
loadMetrics();
setInterval(loadMetrics, 5000);
