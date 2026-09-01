// REACH page: widening a lever calls the backend and updates the counts
// live, without a full page reload. Uses event delegation so it keeps
// working after #lever-list is re-rendered.

function formatVal(v) {
  return Array.isArray(v) ? v.join(", ") : v;
}

function renderReach(data) {
  const mutualEl = document.getElementById("mutual-open");
  const fitsEl = document.getElementById("fits-filters");
  const noMatchesEl = document.getElementById("no-matches-note");
  if (!mutualEl) return;

  mutualEl.textContent = data.counts.mutual_open;
  fitsEl.textContent = data.counts.fits_user_filters;
  noMatchesEl.style.display = data.counts.no_realistic_matches ? "block" : "none";

  const list = document.getElementById("lever-list");
  list.innerHTML = "";
  data.deltas.forEach((d) => {
    const same = JSON.stringify(d.from) === JSON.stringify(d.to);
    const card = document.createElement("div");
    card.className = "lever-card" + (d.sensitive ? " sensitive" : "");
    card.innerHTML = `
      <div class="lever-row">
        <div class="lever-name">${d.lever.replace(/_/g, " ")}</div>
        ${d.sensitive ? '<div class="micro sensitive-tag">You control &middot; not suggested</div>' : ""}
      </div>
      <div class="lever-values">${formatVal(d.from)} &rarr; ${formatVal(d.to)}</div>
      <div class="lever-delta">+${d.delta_mutual_open} open up</div>
      <button class="btn-widen" data-lever="${d.lever}" ${same ? "disabled" : ""}>${same ? "Fully open" : "Widen"}</button>
    `;
    list.appendChild(card);
  });
}

async function widenLever(lever, btn) {
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Widening…";
  try {
    const res = await fetch("/reach/widen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lever }),
    });
    if (!res.ok) throw new Error("widen request failed");
    const data = await res.json();
    renderReach(data);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

document.addEventListener("click", (event) => {
  const btn = event.target.closest(".btn-widen");
  if (!btn || btn.disabled) return;
  widenLever(btn.dataset.lever, btn);
});

// REACH range sliders: two overlaid <input type=range> per bar (one for
// the low handle, one for the high). Dragging updates the visual bar
// immediately; releasing (the "change" event, not "input") posts the new
// range to the backend so we're not firing a request per pixel of drag.

function updateSliderVisual(card) {
  const min = parseFloat(card.dataset.min);
  const max = parseFloat(card.dataset.max);
  const minInput = card.querySelector(".range-min");
  const maxInput = card.querySelector(".range-max");
  const lo = parseFloat(minInput.value);
  const hi = parseFloat(maxInput.value);
  const loPct = ((lo - min) / (max - min)) * 100;
  const hiPct = ((hi - min) / (max - min)) * 100;
  const selected = card.querySelector(".slider-selected");
  selected.style.left = loPct + "%";
  selected.style.width = Math.max(0, hiPct - loPct) + "%";
  card.querySelector(".sv-min").textContent = lo;
  card.querySelector(".sv-max").textContent = hi;
}

async function setRange(lever, lo, hi) {
  try {
    const res = await fetch("/reach/set-range", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lever, min: lo, max: hi }),
    });
    if (!res.ok) throw new Error("set-range request failed");
    renderReach(await res.json());
  } catch (err) {
    // slider stays where the user left it; counts just won't refresh
  }
}

function initReachSliders() {
  document.querySelectorAll(".slider-card").forEach((card) => {
    const minInput = card.querySelector(".range-min");
    const maxInput = card.querySelector(".range-max");

    const clampAndDraw = (activeInput) => {
      if (parseFloat(minInput.value) > parseFloat(maxInput.value)) {
        if (activeInput === minInput) maxInput.value = minInput.value;
        else minInput.value = maxInput.value;
      }
      updateSliderVisual(card);
    };
    // whichever handle was last grabbed gets top stacking, so it stays
    // draggable even once the two thumbs meet at the same position
    minInput.addEventListener("pointerdown", () => {
      minInput.style.zIndex = 3;
      maxInput.style.zIndex = 2;
    });
    maxInput.addEventListener("pointerdown", () => {
      maxInput.style.zIndex = 3;
      minInput.style.zIndex = 2;
    });

    minInput.addEventListener("input", () => clampAndDraw(minInput));
    maxInput.addEventListener("input", () => clampAndDraw(maxInput));
    const commit = () => setRange(card.dataset.lever, parseFloat(minInput.value), parseFloat(maxInput.value));
    minInput.addEventListener("change", commit);
    maxInput.addEventListener("change", commit);

    updateSliderVisual(card);
  });
}

document.addEventListener("DOMContentLoaded", initReachSliders);
