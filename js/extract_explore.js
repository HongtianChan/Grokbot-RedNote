(() => {
  try {
    const loginWall = detectLoginWall();
    const seen = new Set();
    const notes = [];
    const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");

    const idFromHref = (href) => {
      if (!href || typeof href !== "string") return null;
      if (/\/user\/profile\//.test(href)) return null;
      const m =
        href.match(/\/explore\/([0-9a-z]+)/i) ||
        href.match(/\/discovery\/item\/([0-9a-z]+)/i) ||
        href.match(/\/search_result\/([0-9a-z]{16,})/i);
      if (!m) return null;
      return { id: m[1], url: href };
    };

    const visibleText = (el) => {
      if (!el) return "";
      return (el.innerText || el.textContent || "")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
    };

    const looksLikeCount = (s) =>
      /^[\d.]+[万wW万+]?\+?$/.test(s) || /^(赞|收藏|评论)\s*[\d.]+/.test(s);

    const looksLikeDate = (s) => {
      const t = String(s || "").trim();
      if (!t) return false;
      return (
        /^(刚刚|剛才|昨天|今天|前天)(\s+\d{1,2}:\d{2})?$/.test(t) ||
        /^\d+\s*(秒前|分钟前|分鐘前|小时前|小時前|天前|周前|週前|个月前|個月前)$/.test(t) ||
        /^\d{1,2}[-/.]\d{1,2}([-.\/]\d{2,4})?$/.test(t)
      );
    };

    const isPromoted = (card, blob) => {
      const text = String(blob || "");
      if (/广告|推广|贊助|赞助|品牌合作|商业推广|商业合作|Sponsored|\bAD\b|官方推广/.test(text)) {
        return true;
      }
      if (card && card.querySelector && card.querySelector('[class*="promo"], [class*="sponsor"], [class*="advert"]')) {
        return true;
      }
      return false;
    };

    document.querySelectorAll("a[href]").forEach((a) => {
      const parsed = idFromHref(a.href);
      if (!parsed) return;
      if (seen.has(parsed.id)) {
        const existing = notes.find((n) => n.id === parsed.id);
        if (existing && /xsec_token=/.test(parsed.url) && !/xsec_token=/.test(existing.url)) {
          existing.url = parsed.url;
        }
        return;
      }

      let card = a.closest("section.note-item") || a.closest("section") || a.closest("li") || a.closest("article");
      if (!card) {
        let p = a.parentElement;
        let hops = 0;
        while (p && hops < 6) {
          const lines = visibleText(p);
          if (lines.length >= 2 && (p.offsetHeight || 0) > 80) {
            card = p;
            break;
          }
          p = p.parentElement;
          hops += 1;
        }
      }
      card = card || a;

      let title = textOf(card.querySelector(".footer .title, .title"));
      let author = textOf(card.querySelector(".name-time-wrapper .name, a.author .name, .footer .name"))
        .split("\n")[0]
        .trim();
      let likes = textOf(card.querySelector(".like-wrapper .count, .footer span.count, .count"));
      const lines = visibleText(card);
      if (!title || !author || !likes) {
        for (const line of lines) {
          if (!title && line.length >= 2 && !looksLikeCount(line) && !looksLikeDate(line) && line.length < 200) {
            title = line;
            continue;
          }
          if (looksLikeCount(line) && !likes) {
            likes = line.replace(/^(赞|点赞)\s*/, "");
          }
        }
        if (!author && lines.length >= 2) {
          const candidates = lines.filter((line) => line !== title && !looksLikeCount(line) && !looksLikeDate(line));
          if (candidates.length) author = candidates[candidates.length - 1];
        }
      }
      if (!title) title = (a.getAttribute("title") || a.innerText || "").trim().split("\n")[0];
      if (!title) return;

      seen.add(parsed.id);
      const blob = lines.join("\n") + "\n" + title;
      notes.push({
        id: parsed.id,
        url: parsed.url,
        title: title.slice(0, 200),
        author: (author || "").slice(0, 80),
        likes: String(likes || "").slice(0, 20),
        promoted: isPromoted(card, blob)
      });
    });

    return JSON.stringify({
      ok: true,
      loginWall,
      pageUrl: location.href,
      pageTitle: document.title,
      count: notes.length,
      notes
    });
  } catch (err) {
    return JSON.stringify({ ok: false, error: String(err), pageUrl: location.href });
  }

  function detectLoginWall() {
    const url = location.href || "";
    if (/\/login\b|passport\.xiaohongshu|login_mode=/.test(url)) return true;
    const text = document.body ? document.body.innerText || "" : "";
    const strongLogin =
      /手机号登录|验证码登录|二维码已过期/.test(text) &&
      /登录后|立即登录|同意协议/.test(text);
    const hasProfileLink = !!document.querySelector('a[href*="/user/profile/"]');
    const hasNotes =
      document.querySelectorAll('a[href*="/explore/"], a[href*="/search_result/"], a[href*="/discovery/item/"]').length >= 3;
    if (hasNotes || hasProfileLink) return false;
    return strongLogin;
  }
})();
