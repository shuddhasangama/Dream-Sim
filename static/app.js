// REACH: every filter is one row — a name, an Any switch, and (for a
// range) a slider. Switching Any, dragging a slider or pressing "Any for
// everything" all post to the backend and get the SAME full state back,
// so the counts on screen can never disagree with what is saved.
//
// 2026-09-10: the numbers are patched in place rather than the rows being
// rebuilt. Re-rendering the list would destroy the slider you are holding
// and reset a <details> you had opened.

function renderReach(data) {
  const mutualEl = document.getElementById("mutual-open");
  if (!mutualEl) return;
  const fitsEl = document.getElementById("fits-filters");
  const noMatchesEl = document.getElementById("no-matches-note");

  mutualEl.textContent = data.counts.mutual_open;
  if (fitsEl) fitsEl.textContent = data.counts.fits_user_filters;
  if (noMatchesEl) noMatchesEl.hidden = !data.counts.no_realistic_matches;

  (data.filters || []).forEach((f) => {
    const box = document.querySelector('.filter-any[data-filter="' + f.name + '"]');
    if (!box) return;
    const row = box.closest(".filter");
    box.checked = f.ignored;
    row.classList.toggle("is-any", f.ignored);

    const readout = row.querySelector(".filter-readout");
    if (readout && row.classList.contains("is-choice")) {
      readout.textContent = f.ignored ? "Any" : f.on_label;
    }
    const delta = row.querySelector(".filter-delta");
    if (delta) {
      if (f.delta_if_ignored <= 0) delta.textContent = "";
      else if (f.ignored) {
        delta.textContent = "\u2212" + f.delta_if_ignored +
          (row.classList.contains("is-choice") ? " if switched back on" : " if you set a range");
      } else {
        delta.textContent = "+" + f.delta_if_ignored + " on Any";
      }
    }
  });

  const summary = document.getElementById("ignored-summary");
  if (summary) {
    summary.innerHTML = data.ignored_count
      ? data.ignored_count + " set to Any. Nothing was deleted \u2014 switch one back and it returns as you left it."
      : "Set anything to <strong>Any</strong> and it stops narrowing your pool.";
  }
  const showAll = document.getElementById("show-all");
  if (showAll) {
    showAll.dataset.ignore = data.all_ignored ? "false" : "true";
    showAll.textContent = data.all_ignored ? "Put them back" : "Any for everything";
  }
}

async function postReach(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(url + " failed");
  renderReach(await res.json());
}

document.addEventListener("change", (event) => {
  const box = event.target.closest(".filter-any");
  if (!box) return;
  const row = box.closest(".filter");
  row.classList.toggle("is-any", box.checked);
  postReach("/reach/ignore", { filter: box.dataset.filter, ignore: box.checked })
    .catch(() => {
      // Put the switch back rather than showing a state the server did
      // not accept.
      box.checked = !box.checked;
      row.classList.toggle("is-any", box.checked);
    });
});

document.addEventListener("click", (event) => {
  const btn = event.target.closest("#show-all");
  if (!btn || btn.disabled) return;
  const wanted = btn.dataset.ignore === "true";
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Working\u2026";
  postReach("/reach/show-all", { ignore: wanted })
    .catch(() => { btn.textContent = original; })
    .finally(() => { btn.disabled = false; });
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
  document.querySelectorAll(".filter[data-lever]").forEach((card) => {
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
    // A row switched to Any is not filtering, so its handles are inert
    // until it is switched back. Left visible rather than removed, so the
    // person can see what the range will be.
    const commit = () => {
      if (card.classList.contains("is-any")) return;
      setRange(card.dataset.lever, parseFloat(minInput.value), parseFloat(maxInput.value));
    };
    minInput.addEventListener("change", commit);
    maxInput.addEventListener("change", commit);

    updateSliderVisual(card);
  });
}

document.addEventListener("DOMContentLoaded", initReachSliders);
