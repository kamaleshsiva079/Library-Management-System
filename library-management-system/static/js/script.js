// Toast notifications (messages come from Flask flash())
function toast(msg, cat) {
  const box = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = "toast " + (cat === "error" ? "error" : "success");
  t.innerHTML = '<i class="fa-solid ' + (cat === "error" ? "fa-circle-xmark" : "fa-circle-check") + '"></i><span></span>';
  t.querySelector("span").textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

// Live search + dropdown filter for any table (see data-search / data-filter in templates)
function applyFilter(id) {
  const search = document.querySelector('[data-search="' + id + '"]');
  const select = document.querySelector('[data-filter="' + id + '"]');
  const term = search ? search.value.toLowerCase() : "";
  const cat = select ? select.value : "";
  document.querySelectorAll("#" + id + " tbody tr").forEach(tr => {
    const textOk = tr.innerText.toLowerCase().includes(term);
    const catOk = !cat || tr.dataset.cat === cat;
    tr.style.display = textOk && catOk ? "" : "none";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const box = document.getElementById("toasts");
  if (box) JSON.parse(box.dataset.msgs || "[]").forEach(([cat, msg]) => toast(msg, cat));

  document.querySelectorAll("[data-search],[data-filter]").forEach(el => {
    const id = el.dataset.search || el.dataset.filter;
    el.addEventListener("input", () => applyFilter(id));
    el.addEventListener("change", () => applyFilter(id));
  });

  // Edit modal: copies data-* attributes of the clicked button into the form fields of the same name
  document.querySelectorAll(".edit-btn").forEach(btn => btn.addEventListener("click", () => {
    const modal = document.getElementById("editModal"), form = modal.querySelector("form");
    form.action = btn.dataset.action;
    Object.entries(btn.dataset).forEach(([k, v]) => { if (form.elements[k]) form.elements[k].value = v; });
    modal.classList.add("open");
  }));

  // View modal: fills <dd data-field="..."> elements
  document.querySelectorAll(".view-btn").forEach(btn => btn.addEventListener("click", () => {
    const modal = document.getElementById("viewModal");
    modal.querySelectorAll("[data-field]").forEach(el => { el.textContent = btn.dataset[el.dataset.field] || "—"; });
    modal.classList.add("open");
  }));

  document.querySelectorAll(".modal").forEach(m => m.addEventListener("click", e => {
    if (e.target === m || e.target.classList.contains("modal-close")) m.classList.remove("open");
  }));

  const menu = document.getElementById("menuBtn");
  if (menu) menu.addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
});
