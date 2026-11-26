(() => {
  try {
    const labels = ["最多点赞", "最热"];
    const textOf = (el) => ((el && (el.innerText || el.textContent)) || "")
      .trim()
      .split("\n")[0]
      .trim();
    const isWanted = (el) => labels.indexOf(textOf(el)) !== -1 && textOf(el).length <= 20;
    const selectedHint = (el) => {
      const cls = el && el.className ? String(el.className) : "";
      const aria = (
        (el && (el.getAttribute("aria-selected") || el.getAttribute("aria-pressed") || el.getAttribute("aria-current"))) ||
        ""
      ).toLowerCase();
      return aria === "true" || /active|selected|current|checked/.test(cls);
    };
    const findWanted = (root) => {
      const scope = root || document;
      const nodes = Array.from(
        scope.querySelectorAll("div.tags, span, button, div, li, a")
      );
      for (let i = 0; i < nodes.length; i += 1) {
        if (isWanted(nodes[i])) return nodes[i];
      }
      return null;
    };
    const alreadySelected = () => {
      const panel = document.querySelector("div.filter-panel");
      if (!panel) return false;
      const el = findWanted(panel);
      return !!(el && selectedHint(el));
    };
    const hoverClick = (el) => {
      if (!el) return;
      ["mouseenter", "mouseover", "pointerenter", "pointerover"].forEach((type) => {
        el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
      });
      if (typeof el.click === "function") el.click();
    };
    const openFilter = () => {
      const btn = document.querySelector("div.filter");
      if (btn) hoverClick(btn);
      const openers = Array.from(document.querySelectorAll("button, div, span")).filter((el) => {
        const t = textOf(el);
        return t === "筛选" || t === "排序" || t === "综合" || t === "Filters" || t === "Sort";
      });
      for (let i = 0; i < Math.min(openers.length, 4); i += 1) hoverClick(openers[i]);
    };

    if (alreadySelected()) {
      return JSON.stringify({ ok: true, applied: true, clicked: "", already: true });
    }

    openFilter();
    let target = findWanted(document.querySelector("div.filter-panel")) || findWanted(document);
    let clicked = "";
    if (target) {
      hoverClick(target);
      clicked = textOf(target);
    }
    return JSON.stringify({
      ok: true,
      applied: Boolean(clicked) || alreadySelected(),
      clicked: clicked,
      already: !clicked && alreadySelected(),
    });
  } catch (err) {
    return JSON.stringify({ ok: false, applied: false, error: String(err) });
  }
})();
