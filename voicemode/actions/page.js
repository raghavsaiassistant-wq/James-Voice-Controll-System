// Injected into the controlled page. Collects interactive elements, tags them with
// data-vm-id, and draws feedback (highlight, numbered badges, toast).
window.__vm = window.__vm || (() => {
  const NS = "__vm_layer";

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && parseFloat(s.opacity || "1") > 0.05;
  }

  function nameOf(el) {
    const pick = (...xs) => xs.find((x) => x && String(x).trim());
    let n = pick(el.getAttribute("aria-label"), el.getAttribute("title"));
    if (!n && el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) n = lab.innerText;
    }
    if (!n) n = pick(el.innerText, el.value && el.type !== "password" ? el.value : "",
                     el.getAttribute("placeholder"), el.getAttribute("alt"));
    if (!n) { const img = el.querySelector("img[alt]"); if (img) n = img.alt; }
    if (!n) n = pick(el.getAttribute("name"), el.id);
    return (n || "").replace(/\s+/g, " ").trim().slice(0, 100);
  }

  function roleOf(el) {
    const r = el.getAttribute("role");
    if (r) return r;
    const t = el.tagName.toLowerCase();
    if (t === "a") return "link";
    if (t === "button" || t === "summary") return "button";
    if (t === "select") return "combobox";
    if (t === "textarea") return "textbox";
    if (t === "input") {
      const ty = (el.type || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(ty)) return "button";
      if (ty === "checkbox" || ty === "radio") return ty;
      if (ty === "search") return "searchbox";
      return "textbox";
    }
    if (el.isContentEditable) return "textbox";
    return "button";
  }

  function inChrome(el) {
    return !!el.closest("header, nav, footer, [role=navigation], [role=banner], [role=contentinfo]");
  }

  function snapshot(limit) {
    const sel = "a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button]," +
      "[role=link], [role=tab], [role=menuitem], [role=checkbox], [role=option], [role=searchbox]," +
      "[role=textbox], [contenteditable=true], [onclick]";
    const vh = innerHeight, out = [];
    let i = 0;
    for (const el of document.querySelectorAll(sel)) {
      if (!visible(el)) continue;
      const name = nameOf(el);
      const role = roleOf(el);
      if (!name && !["textbox", "searchbox", "combobox"].includes(role)) continue;
      const r = el.getBoundingClientRect();
      const id = "e" + String(++i).padStart(3, "0");
      el.setAttribute("data-vm-id", id);
      out.push({
        id, role, name,
        placeholder: el.getAttribute("placeholder") || "",
        href: el.getAttribute("href") || "",
        inView: r.bottom > 0 && r.top < vh,
        top: Math.round(r.top + scrollY),
        chrome: inChrome(el),
        search: role === "searchbox" || /search|query|q$/i.test((el.name || "") + " " + (el.id || "") + " " + (el.getAttribute("placeholder") || "") + " " + (el.getAttribute("aria-label") || "")),
      });
      if (out.length >= limit) break;
    }
    return out;
  }

  function results(selectors) {
    for (const s of selectors) {
      const els = [...document.querySelectorAll(s)].filter(visible);
      if (els.length) return els.map((e) => e.closest("[data-vm-id]") ? e.closest("[data-vm-id]").getAttribute("data-vm-id") : (e.getAttribute("data-vm-id") || ""))
        .filter(Boolean);
    }
    return [];
  }

  function layer() {
    let l = document.getElementById(NS);
    if (!l) {
      l = document.createElement("div");
      l.id = NS;
      l.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647";
      document.documentElement.appendChild(l);
    }
    return l;
  }

  function clear() { const l = document.getElementById(NS); if (l) l.innerHTML = ""; }

  function highlight(id) {
    const el = document.querySelector(`[data-vm-id="${id}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect(), d = document.createElement("div");
    d.style.cssText = `position:fixed;left:${r.left - 3}px;top:${r.top - 3}px;width:${r.width + 6}px;` +
      `height:${r.height + 6}px;border:3px solid #22c55e;border-radius:6px;box-shadow:0 0 12px #22c55e;`;
    layer().appendChild(d);
    setTimeout(() => d.remove(), 900);
  }

  function badges(ids) {
    clear();
    ids.forEach((id, k) => {
      const el = document.querySelector(`[data-vm-id="${id}"]`);
      if (!el) return;
      el.scrollIntoView({ block: "nearest" });
      const r = el.getBoundingClientRect(), b = document.createElement("div");
      b.textContent = String(k + 1);
      b.style.cssText = `position:fixed;left:${Math.max(0, r.left - 14)}px;top:${Math.max(0, r.top - 14)}px;` +
        "min-width:26px;height:26px;border-radius:13px;background:#f59e0b;color:#111;font:bold 16px/26px sans-serif;" +
        "text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.4)";
      const o = document.createElement("div");
      o.style.cssText = `position:fixed;left:${r.left - 2}px;top:${r.top - 2}px;width:${r.width + 4}px;` +
        `height:${r.height + 4}px;border:2px dashed #f59e0b;border-radius:4px`;
      layer().appendChild(o);
      layer().appendChild(b);
    });
  }

  function scrollTarget() {
    const se = document.scrollingElement || document.documentElement;
    if (se.scrollHeight > innerHeight + 20) return se;
    let el = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
    while (el && el !== document.body) {
      const s = getComputedStyle(el);
      if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 20) return el;
      el = el.parentElement;
    }
    return se;
  }

  function scroll(direction, amount) {
    const t = scrollTarget();
    const h = t === (document.scrollingElement || document.documentElement) ? innerHeight : t.clientHeight;
    const before = t.scrollTop;
    if (amount === "end") t.scrollTo({ top: direction === "down" ? t.scrollHeight : 0, behavior: "smooth" });
    else t.scrollBy({ top: (direction === "down" ? 1 : -1) * (amount === "small" ? 0.3 : 0.8) * h, behavior: "smooth" });
    return before;
  }

  return { snapshot, results, highlight, badges, clear, scroll };
})();
