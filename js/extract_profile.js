(() => {
  try {
    const loginWall = detectLoginWall();

    const hrefId = (href) => {
      if (!href) return "";
      const m = String(href).match(/\/user\/profile\/([0-9a-z]+)/i);
      return m ? m[1] : "";
    };
    const userId = hrefId(location.href) || hrefId(document.querySelector("a[href*='/user/profile/']")?.href || "");

    const pageText = document.body ? document.body.innerText || "" : "";
    const likesHidden = /喜欢的内容(暂未)?(不可见|未公开|已设为私密)|赞过.*?(不可见|未公开|私密)|该用户已设置/.test(pageText);
    const followsHidden = /关注(列表)?(不可见|未公开|已设为私密)/.test(pageText);

    const name = firstName();
    const bio = firstBio();
    const counts = readCounts(pageText);
    const location = firstLocation(pageText);
    const posts = readNoteCards();
    const follows = readFollowCards();

    return JSON.stringify({
      ok: true,
      loginWall,
      user_id: userId,
      name: (name || "").slice(0, 80),
      bio: (bio || "").slice(0, 500),
      location: (location || "").slice(0, 80),
      profile_url: location.href,
      followers: counts.followers,
      following: counts.following,
      likes_collected: counts.likes_collected,
      notes_count: counts.notes_count,
      posted: posts,
      follows: follows,
      likes_public: !likesHidden,
      following_public: !followsHidden && follows.length > 0 ? true : (followsHidden ? false : null),
      pageTitle: document.title,
      tab_hint: detectTab(pageText)
    });
  } catch (err) {
    return JSON.stringify({ ok: false, error: String(err), url: location.href });
  }

  function firstName() {
    const sels = [
      ".user-name", ".user-nickname", ".nickname",
      ".user-info .name", "h1", ".profile-name"
    ];
    for (const sel of sels) {
      const t = textOf(document.querySelector(sel)).split("\n")[0].trim();
      if (t && t.length < 40 && !/关注|粉丝|笔记|获赞/.test(t)) return t;
    }
    const title = (document.title || "").replace(/\s*[-|–—]\s*(小红书|xiaohongshu|rednote|RED)\s*$/i, "").trim();
    return title;
  }

  function firstBio() {
    const sels = [".user-desc", ".user-signature", ".desc", ".profile-bio", ".user-info .bio"];
    for (const sel of sels) {
      const t = textOf(document.querySelector(sel));
      if (t && t.length >= 2 && t.length < 500 && !/^关注|^粉丝/.test(t)) return t;
    }
    return "";
  }

  function firstLocation(pageText) {
    const m = String(pageText || "").match(/(IP\s*属地|常住地|现居)[:：\s]*([^\s\n]{1,20})/);
    return m ? m[2] : "";
  }

  function readCounts(pageText) {
    const out = { followers: "", following: "", likes_collected: "", notes_count: "" };
    const grab = (label) => {
      const patterns = [
        new RegExp("([\\d.,]+[万wW+]?\\+?)\\s*" + label),
        new RegExp(label + "\\s*([\\d.,]+[万wW+]?\\+?)")
      ];
      for (const re of patterns) {
        const m = pageText.match(re);
        if (m) return m[1];
      }
      return "";
    };
    out.following = grab("关注");
    out.followers = grab("粉丝");
    out.likes_collected = grab("获赞与收藏") || grab("获赞");
    out.notes_count = grab("笔记");
    return out;
  }

  function detectTab(pageText) {
    if (/赞过/.test(pageText) && /不可见|未公开|私密/.test(pageText)) return "likes-private";
    return "";
  }

  function idFromHref(href) {
    if (!href || typeof href !== "string") return null;
    if (/\/user\/profile\//.test(href) && !/\/explore\/|\/discovery\/item\/|\/search_result\//.test(href)) {
      return { type: "user", id: (href.match(/\/user\/profile\/([0-9a-z]+)/i) || [])[1], url: href };
    }
    const m =
      href.match(/\/explore\/([0-9a-z]+)/i) ||
      href.match(/\/discovery\/item\/([0-9a-z]+)/i) ||
      href.match(/\/search_result\/([0-9a-z]{16,})/i);
    if (!m) return null;
    return { type: "note", id: m[1], url: href };
  }

  function readNoteCards() {
    const seen = new Set();
    const notes = [];
    document.querySelectorAll("a[href]").forEach((a) => {
      const parsed = idFromHref(a.href);
      if (!parsed || parsed.type !== "note") return;
      if (seen.has(parsed.id)) return;
      let card = a.closest("section, li, article") || a;
      let title = textOf(card.querySelector(".footer .title, .title, .name"));
      if (!title) {
        const lines = visibleText(card).filter((s) => s.length >= 2 && s.length < 200 && !/^[\d.]+[万wW+]?\+?$/.test(s));
        title = lines[0] || textOf(a).split("\n")[0];
      }
      if (!title) return;
      seen.add(parsed.id);
      notes.push({
        title: title.slice(0, 200),
        url: parsed.url,
        id: parsed.id
      });
    });
    return notes.slice(0, 16);
  }

  function readFollowCards() {
    const seen = new Set();
    const people = [];
    // Follow lists usually show profile links plus a name, not note cards.
    const listRoot =
      document.querySelector(".follows-list, .follow-list, .user-list, .fans-list") || document;
    listRoot.querySelectorAll("a[href*='/user/profile/']").forEach((a) => {
      const id = (a.href.match(/\/user\/profile\/([0-9a-z]+)/i) || [])[1];
      if (!id || seen.has(id)) return;
      // Skip the profile owner's own header link when it is the page user.
      const pageId = (location.href.match(/\/user\/profile\/([0-9a-z]+)/i) || [])[1];
      if (pageId && id === pageId) return;
      const name = (textOf(a.querySelector(".name, .username, .nickname")) || textOf(a))
        .split("\n")[0]
        .replace(/\s*(Follow|关注|已关注)\s*$/u, "")
        .trim();
      if (!name || name.length > 40) return;
      seen.add(id);
      people.push({ name: name.slice(0, 80), user_id: id, url: a.href });
    });
    return people.slice(0, 24);
  }

  function textOf(el) {
    return el ? (el.innerText || el.textContent || "").trim() : "";
  }

  function visibleText(el) {
    if (!el) return "";
    return (el.innerText || el.textContent || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function detectLoginWall() {
    const url = location.href || "";
    if (/\/login\b|passport\.xiaohongshu|login_mode=/.test(url)) return true;
    const text = document.body ? document.body.innerText || "" : "";
    const strongLogin =
      /手机号登录|验证码登录|二维码已过期/.test(text) &&
      /登录后|立即登录|同意协议/.test(text);
    const hasProfile = /\/user\/profile\//.test(url) && !!document.querySelector("h1, .user-name, .nickname, .user-nickname");
    if (hasProfile && !strongLogin) return false;
    return strongLogin;
  }
})();
