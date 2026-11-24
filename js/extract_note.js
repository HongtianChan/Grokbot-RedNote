(() => {
  try {
    const loginWall = detectLoginWall();
    const meta = (key) => {
      const el = document.querySelector('meta[property="' + key + '"], meta[name="' + key + '"]');
      return el ? (el.getAttribute("content") || "").trim() : "";
    };
    const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
    const firstText = (selectors) => {
      for (const sel of selectors) {
        const t = textOf(document.querySelector(sel));
        if (t) return t;
      }
      return "";
    };
    const siteSuffix = /\s*[-|–—−‐-]\s*(小红书|xiaohongshu|rednote|RED)\s*$/i;

    let title = firstText(["#detail-title", ".note-scroller .title", "h1"]) ||
      meta("og:title") ||
      meta("twitter:title");
    title = (title || "").replace(siteSuffix, "").trim();
    if (!title) title = (document.title || "").replace(siteSuffix, "").trim();

    // Caption of this note only. Comment nodes also use .note-text, and
    // image-only notes often have an empty #detail-desc — that is the page.
    let body = firstText(["#detail-desc", ".note-scroller > .note-content .desc", ".note-scroller #detail-desc"]);
    if (body) {
      body = body.replace(/展开\s*$/, "").replace(/收起\s*$/, "").replace(/Expand\s*$/i, "").replace(/Collapse\s*$/i, "").trim();
    }
    if (!body || body.length < 8) {
      const og = meta("og:description") || meta("description");
      if (
        og &&
        og.length > (body || "").length &&
        og !== title &&
        og.replace(siteSuffix, "").trim() !== title
      ) {
        body = og;
      }
    }

    // The first /user/profile/ link is the signed-in sidebar ("Me" / "我").
    // The note author is in the note header.
    let author = firstText([
      ".author-container .username",
      ".author-container a.name",
      ".interaction-container > .author-container .username"
    ]);
    author = (author || "").split("\n")[0].replace(/\s*(Follow|关注|已关注)\s*$/u, "").trim();
    if (!author || isSelfLabel(author)) {
      const profiles = document.querySelectorAll(".author-container a[href*='/user/profile/']");
      for (const a of profiles) {
        const t = (textOf(a.querySelector(".username")) || textOf(a) || a.getAttribute("title") || "")
          .trim()
          .split("\n")[0];
        if (t && t.length < 40 && !isSelfLabel(t) && !/关注|粉丝|Follow/.test(t)) {
          author = t;
          break;
        }
      }
    }
    if (isSelfLabel(author)) author = "";

    const counts = { likes: "", saves: "", comments: "" };
    const applyCount = (kind, raw) => {
      const v = normalizeCount(raw);
      if (v && !counts[kind]) counts[kind] = v;
    };

    // Visible note engage-bar: like / collect / comment. Never comment-row likes.
    const engage = document.querySelector(
      ".interact-container .buttons, .buttons.engage-bar-style, .interact-container"
    );
    if (engage) {
      applyCount("likes", textOf(engage.querySelector(".like-wrapper .count")));
      applyCount("saves", textOf(engage.querySelector(".collect-wrapper .count")));
      applyCount("comments", textOf(engage.querySelector(".chat-wrapper .count")));
    }
    if (!counts.comments) {
      const label = Array.from(
        document.querySelectorAll(".note-scroller span, .note-scroller div, .note-scroller a")
      ).map((el) => textOf(el)).find((t) => /^\d[\d.,]*\s*(comments?|条评论|条点评)$/i.test(t));
      if (label) applyCount("comments", label);
    }
    if (!counts.likes) applyCount("likes", meta("og:xhs:note_like"));
    if (!counts.saves) applyCount("saves", meta("og:xhs:note_collect"));
    if (!counts.comments) applyCount("comments", meta("og:xhs:note_comment"));

    if (!counts.likes || !counts.saves || !counts.comments) {
      const boxed = document.querySelectorAll(
        ".interact-container, .buttons.engage-bar-style, .engage-bar-container"
      );
      for (const box of boxed) {
        const nums = (box.innerText || "")
          .split(/\s+/)
          .map((s) => normalizeCount(s))
          .filter(Boolean);
        if (nums.length >= 2 && nums.length <= 5) {
          if (!counts.likes) counts.likes = nums[0];
          if (!counts.saves && nums[1]) counts.saves = nums[1];
          if (!counts.comments && nums[2]) counts.comments = nums[2];
          break;
        }
      }
    }

    const commentItems = extractCommentItems();

    return JSON.stringify({
      ok: true,
      loginWall,
      title: title.slice(0, 300),
      author: (author || "").slice(0, 80),
      body: (body || "").slice(0, 8000),
      likes: counts.likes,
      saves: counts.saves,
      comments: counts.comments,
      comment_items: commentItems,
      url: location.href,
      pageTitle: document.title
    });
  } catch (err) {
    return JSON.stringify({ ok: false, error: String(err), url: location.href });
  }

  function extractCommentItems() {
    const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
    const items = [];
    const seen = new Set();
    const header = document.querySelector(".author-container, .note-scroller .author, .interaction-container > .author-container");
    const roots = document.querySelectorAll(
      ".comment-item, .parent-comment, [class*='comment-item'], .comments-container li, .comment-list li, .list-container .comment"
    );
    const consider = roots.length ? Array.from(roots) : Array.from(
      document.querySelectorAll(".comments-container a[href*='/user/profile/'], .comment-list a[href*='/user/profile/']")
    ).map((a) => a.closest("li, section, div") || a);

    const push = (node) => {
      if (!node || (header && header.contains(node) && node === header)) return;
      if (header && header.contains(node) && !node.closest(".comments-container, .comment-list, .list-container")) return;
      const link = node.querySelector ? node.querySelector("a[href*='/user/profile/']") : null;
      const href = link ? link.href : "";
      const idMatch = href.match(/\/user\/profile\/([0-9a-z]+)/i);
      const name = (
        textOf(node.querySelector && node.querySelector(".author, .name, .username, .nickname")) ||
        textOf(link) ||
        ""
      ).split("\n")[0].replace(/\s*(Follow|关注|已关注)\s*$/u, "").trim();
      let text = textOf(node.querySelector && node.querySelector(".content, .note-text, .comment-inner .content, .comment-text"));
      if (!text) {
        const lines = (node.innerText || "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean)
          .filter((s) => s !== name && !/^(回复|点赞|展开|收起)$/.test(s) && !/^\d[\d.,]*[万wW+]?$/.test(s));
        text = lines[0] || "";
      }
      text = (text || "").replace(/^(回复\s*@?\S+[:：]\s*)/, "").trim();
      if (!text && !idMatch) return;
      if (text.length < 1) return;
      const key = (idMatch ? idMatch[1] : name) + "|" + text.slice(0, 48);
      if (seen.has(key)) return;
      seen.add(key);
      const likeRaw = textOf(node.querySelector && node.querySelector(".like-wrapper .count, .likes, .count"));
      items.push({
        text: text.slice(0, 500),
        author: (name || "").slice(0, 80),
        user_id: idMatch ? idMatch[1] : "",
        profile_url: href || "",
        likes: normalizeCount(likeRaw) || "",
        time: ""
      });
    };
    consider.forEach(push);
    return items.slice(0, 40);
  }

  function isSelfLabel(value) {
    return /^(Me|我|我的)$/i.test(String(value || "").trim());
  }

  function normalizeCount(raw) {
    if (raw == null) return "";
    let s = String(raw).trim();
    if (!s) return "";
    const labeled = s.match(/^([\d.,]+[万wW+]?\+?)\s*(comments?|条评论|条点评|评论)?$/i);
    if (labeled) s = labeled[1];
    if (/^(点赞|收藏|评论|喜欢|赞|Like|Likes|Collect|Save|Favorite|Comment|Comments|Chat)$/i.test(s)) {
      return "";
    }
    if (/^\d{1,3}(,\d{3})+(\.\d+)?[万wW+]?\+?$/.test(s)) s = s.replace(/,/g, "");
    if (!/^[\d.,]+[万wW+]?\+?$/.test(s)) return "";
    return s;
  }

  function detectLoginWall() {
    const url = location.href || "";
    if (/\/login\b|passport\.xiaohongshu|login_mode=/.test(url)) return true;
    const text = document.body ? document.body.innerText || "" : "";
    const strongLogin =
      /手机号登录|验证码登录|二维码已过期/.test(text) &&
      /登录后|立即登录|同意协议/.test(text);
    const hasNote =
      !!document.querySelector("h1, #detail-desc, meta[property='og:title']") &&
      !/登录 - 小红书/.test(document.title || "");
    if (hasNote && !strongLogin) return false;
    return strongLogin;
  }
})();
