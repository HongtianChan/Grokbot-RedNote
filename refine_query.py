#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query-rewriting model for Xiaohongshu search.

Guiding principle: the job is not always to search what the user already
knows to ask for. For abstract prompts, or when they explicitly ask for
anti-cocoon (反茧房) exploration, find what is hard to find — topics
real users are posting and discussing, not official or promoted trend
lists. Sample the explore feed for diversity. Concrete queries stay
precise and are not broadened.

When anti-cocoon applies, term selection uses a 51% default bias toward
diverse user-generated topics over official or heavily pushed ones,
while still requiring that a topic is actually being discussed (the
other 49%).

Pure Python 3.9 standard library: no extra packages.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Preferred Xiaohongshu form for common near-synonyms.
# Longer keys must be listed so the greedy tokenizer can match them first.
SYNONYMS = {
    # drinks / cafes
    "coffee": "咖啡",
    "cafe": "咖啡店",
    "café": "咖啡店",
    "coffeeshop": "咖啡店",
    "coffee shop": "咖啡店",
    "咖啡馆": "咖啡店",
    "咖啡厅": "咖啡店",
    "咖啡店": "咖啡店",
    "咖啡": "咖啡",
    "拿铁": "拿铁",
    "latte": "拿铁",
    "美式": "美式",
    "手冲": "手冲",
    "特调": "特调",
    "饮品": "饮品",
    "好喝": "好喝",
    # food
    "restaurant": "餐厅",
    "restaurants": "餐厅",
    "餐厅": "餐厅",
    "饭店": "餐厅",
    "餐馆": "餐厅",
    "美食": "美食",
    "好吃": "美食",
    "小吃": "小吃",
    "夜宵": "夜宵",
    "早餐": "早餐",
    "brunch": "早午餐",
    "早午餐": "早午餐",
    "甜点": "甜点",
    "dessert": "甜点",
    "甜品": "甜品",
    "蛋糕": "蛋糕",
    "火锅": "火锅",
    "烧烤": "烧烤",
    "bbq": "烧烤",
    "米其林": "米其林",
    "探店": "探店",
    # value / quality
    "便宜": "平价",
    "不贵": "平价",
    "性价比": "平价",
    "平价": "平价",
    "cheap": "平价",
    "affordable": "平价",
    "budget": "平价",
    "豪华": "高端",
    "高端": "高端",
    "奢侈": "轻奢",
    "轻奢": "轻奢",
    # beauty
    "skincare": "护肤",
    "skin care": "护肤",
    "护肤": "护肤",
    "护肤品": "护肤",
    "美妆": "美妆",
    "彩妆": "彩妆",
    "makeup": "妆容",
    "妆容": "妆容",
    "化妆": "妆容",
    "口红色号": "口红",
    "lipstick": "口红",
    "防晒": "防晒",
    "sunscreen": "防晒",
    "穿搭": "穿搭",
    "ootd": "穿搭",
    "outfit": "穿搭",
    "outfits": "穿搭",
    "衣服": "穿搭",
    "搭配": "穿搭",
    "发型": "发型",
    "hairstyle": "发型",
    "美甲": "美甲",
    "nails": "美甲",
    # travel / stay
    "macau": "澳门",
    "macao": "澳门",
    "澳门": "澳门",
    "hong kong": "香港",
    "hongkong": "香港",
    "香港": "香港",
    "shenzhen": "深圳",
    "深圳": "深圳",
    "zhuhai": "珠海",
    "珠海": "珠海",
    "guangzhou": "广州",
    "广州": "广州",
    "dim sum": "点心",
    "dimsum": "点心",
    "点心": "点心",
    "tea": "茶",
    "travel": "旅行",
    "trip": "旅行",
    "旅游": "旅行",
    "旅行": "旅行",
    "出行": "旅行",
    "游玩": "旅行",
    "攻略": "攻略",
    "行程": "行程",
    "itinerary": "行程",
    "hotel": "酒店",
    "hotels": "酒店",
    "酒店": "酒店",
    "民宿": "民宿",
    "airbnb": "民宿",
    "景点": "景点",
    "打卡": "打卡",
    "拍照": "拍照",
    "出片": "出片",
    "好看": "出片",
    "photogenic": "出片",
    "photo": "拍照",
    "photography": "拍照",
    # home / life
    "装修": "装修",
    "家居": "家居",
    "收纳": "收纳",
    "recipe": "食谱",
    "recipes": "食谱",
    "食谱": "食谱",
    "做法": "做法",
    # digital / study
    "laptop": "笔记本",
    "电脑": "电脑",
    "手机": "手机",
    "app": "app",
    "软件": "软件",
    "学习": "学习",
    "study": "学习",
    "考研": "考研",
    "英语": "英语",
    # fitness
    "健身": "健身",
    "gym": "健身",
    "减肥": "减脂",
    "减脂": "减脂",
    "workout": "健身",
    # intent-like adjectives kept as topic modifiers
    "新开": "新开",
    "最近": "近期",
    "近期": "近期",
    "周末": "周末",
    "附近": "附近",
    "本地": "本地",
    "小众": "小众",
    "隐形": "小众",
    "必去": "必去",
    "必吃": "必吃",
    "必喝": "必喝",
    "避雷": "避雷",
    "踩雷": "避雷",
    "种草": "种草",
    "测评": "测评",
    "评测": "测评",
    "对比": "测评",
    "推荐": "推荐",
    "分享": "分享",
    "教程": "教程",
    "合集": "合集",
    "清单": "清单",
    "review": "测评",
    "reviews": "测评",
    "recommend": "推荐",
    "recommendations": "推荐",
    "recommendation": "推荐",
    "tutorial": "教程",
    "guide": "攻略",
    "guides": "攻略",
}

# Multi-word English keys need a phrase pass before word tokens.
_PHRASES = {k: v for k, v in SYNONYMS.items() if " " in k}

STOPWORDS = {
    "我", "我们", "你", "你们", "他", "她", "它", "想", "要", "找", "帮", "帮我",
    "请", "麻烦", "一下", "找一下", "一点", "一些", "怎么", "怎么做", "怎么弄",
    "如何", "怎样", "有没有", "有木有", "哪些", "哪个", "什么", "啥", "可以",
    "能否", "能不能", "吗", "呢", "啊", "呀", "吧", "嘛", "的", "了", "着",
    "过", "在", "和", "与", "或", "又", "以及", "还有", "就是", "感觉", "觉得",
    "比较", "非常", "真的", "好想", "想要", "给我", "看看", "看下", "搜",
    "搜索", "查", "查询", "请问",
    "小红书", "xhs", "xiaohongshu", "rednote", "red", "book",
    "i", "me", "my", "we", "you", "a", "an", "the", "to", "for", "of", "in",
    "on", "at", "and", "or", "is", "are", "do", "does", "please", "help",
    "want", "wanted", "wanna", "looking", "look", "find", "finding", "get",
    "got", "some", "any", "good", "best", "nice", "really", "about", "with",
    "that", "this", "there", "here", "how", "what", "where", "which", "can",
    "could", "would", "should", "need", "needed", "show", "tell", "give",
    "search", "searches", "query",
}

INTENT_WORDS = ("测评", "探店", "攻略", "教程", "避雷", "种草", "合集", "推荐")

# Put these first in a query: 澳门点心, not 点心澳门.
PLACES = {
    "澳门", "香港", "深圳", "珠海", "广州", "东莞", "佛山", "中山", "惠州",
    "江门", "横琴", "氹仔", "路氹", "上海", "北京", "杭州", "成都", "重庆",
    "南京", "武汉", "西安", "长沙", "厦门", "苏州", "台北", "东京", "大阪",
    "京都", "首尔", "新加坡", "伦敦", "巴黎",
}

def _order_topic(tokens: list[str]) -> list[str]:
    places = [t for t in tokens if t in PLACES]
    rest = [t for t in tokens if t not in PLACES]
    return places + rest

# Patterns in the raw input that suggest an intent should be added
# when the user wrote a request sentence rather than a ready keyword.
_INTENT_CUES = (
    (re.compile(r"怎么做|怎么弄|步骤|教程|做法|how\s+to|tutorial", re.I), "教程"),
    (re.compile(r"测评|评测|对比|评一下|好不好用|review", re.I), "测评"),
    (re.compile(r"避雷|踩雷|坑", re.I), "避雷"),
    (re.compile(r"攻略|行程|几天|怎么玩|itinerary|guide", re.I), "攻略"),
    (re.compile(r"探店|哪家好|去哪|去哪儿|打卡点", re.I), "探店"),
    (re.compile(r"种草", re.I), "种草"),
    (re.compile(r"合集|清单", re.I), "合集"),
    (re.compile(r"推荐|安利|suggest|recommend", re.I), "推荐"),
    (re.compile(r"帮我找|有没有|哪里有|哪儿有|想找|推荐一下", re.I), "推荐"),
)

_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(
    r"[\s\u3000,，.。!！?？;；:：、~～…·\-—_=/\\|()\[\]{}<>《》【】「」『』“”\"'`]+"
)


def _preferred(token: str) -> str:
    raw = token.strip()
    if not raw:
        return ""
    low = raw.lower()
    if low in SYNONYMS:
        return SYNONYMS[low]
    if raw in SYNONYMS:
        return SYNONYMS[raw]
    return raw


def _rebuild_dict_keys() -> list[str]:
    keys = set(SYNONYMS.keys())
    bags = [STOPWORDS]
    for name in ("ABSTRACT_META", "OFFICIAL_TERMS", "TIME_WORDS", "PLACES", "CUE_TERMS", "HYPE_TERMS"):
        bag = globals().get(name)
        if bag:
            bags.append(bag)
    for bag in bags:
        keys |= {w for w in bag if isinstance(w, str) and (not w.isascii() or " " in w)}
    return sorted(keys, key=len, reverse=True)


_DICT_KEYS = _rebuild_dict_keys()


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _tokenize_cjk(block: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(block)
    while i < n:
        matched = None
        for key in _DICT_KEYS:
            if " " in key:
                continue
            if not any(_is_cjk(ch) for ch in key):
                continue
            if block.startswith(key, i):
                matched = key
                break
        if matched:
            tokens.append(matched)
            i += len(matched)
            continue
        # Take the longest run of unmatched CJK; split leftover into 2-char
        # chunks, leaving a final 1-char attached to the previous chunk.
        j = i + 1
        while j < n and _is_cjk(block[j]) and not any(
            block.startswith(k, j) for k in _DICT_KEYS if " " not in k and any(_is_cjk(ch) for ch in k)
        ):
            j += 1
        chunk = block[i:j]
        if len(chunk) <= 3:
            tokens.append(chunk)
        else:
            k = 0
            while k < len(chunk):
                remain = len(chunk) - k
                take = 2 if remain != 3 else 3
                tokens.append(chunk[k : k + take])
                k += take
        i = j
    return tokens


def tokenize(text: str) -> list[str]:
    """Split mixed Chinese/English input into keywords."""
    source = (text or "").strip()
    if not source:
        return []
    lowered = source.lower()
    # Replace known English phrases first so "coffee shop" is one term.
    phrases = sorted(_PHRASES.keys(), key=len, reverse=True)
    placeholders: dict[str, str] = {}
    for index, phrase in enumerate(phrases):
        if phrase in lowered:
            mark = "«p%d»" % index
            lowered = lowered.replace(phrase, mark)
            source = re.compile(re.escape(phrase), re.I).sub(mark, source)
            placeholders[mark] = phrase
    tokens: list[str] = []
    buf = ""

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        if buf in placeholders:
            tokens.append(placeholders[buf])
        elif all(_is_cjk(ch) for ch in buf):
            tokens.extend(_tokenize_cjk(buf))
        else:
            tokens.append(buf)
        buf = ""

    i = 0
    while i < len(source):
        ch = source[i]
        # placeholder
        if ch == "«":
            flush_buf()
            end = source.find("»", i)
            if end != -1:
                tokens.append(placeholders.get(source[i : end + 1], source[i : end + 1]))
                i = end + 1
                continue
        latin = _LATIN.match(source, i)
        if latin:
            flush_buf()
            tokens.append(latin.group(0))
            i = latin.end()
            continue
        if _is_cjk(ch):
            buf += ch
            i += 1
            continue
        flush_buf()
        i += 1
    flush_buf()
    return [t for t in tokens if t]


def _infer_intent(original: str, preferred_tokens: list[str]) -> Optional[str]:
    existing = [t for t in preferred_tokens if t in INTENT_WORDS]
    if existing:
        return existing[0]
    for pattern, intent in _INTENT_CUES:
        if pattern.search(original or ""):
            return intent
    return None


def _is_request_sentence(original: str, raw_tokens: list[str]) -> bool:
    if any(t.lower() in STOPWORDS or t in STOPWORDS for t in raw_tokens):
        return True
    if re.search(r"[?？]|一下|帮我|有没有|怎么|如何|please|want|找", original or "", re.I):
        return True
    return len(original or "") >= 16


def _join(tokens: Iterable[str]) -> str:
    parts: list[str] = []
    for token in tokens:
        token = (token or "").strip()
        if not token:
            continue
        if not parts:
            parts.append(token)
            continue
        prev = parts[-1]
        if (_is_cjk(prev[-1]) and _is_cjk(token[0])) or (
            _is_cjk(prev[-1]) and token[0].isascii()
        ) or (prev[-1].isascii() and _is_cjk(token[0])):
            # Xiaohongshu queries are usually a compact Chinese string,
            # even when a latin fragment sits next to CJK.
            if prev[-1].isascii() and token[0].isascii():
                parts.append(" " + token)
            else:
                parts.append(token)
        else:
            parts.append(" " + token if prev[-1].isascii() and token[0].isascii() else token)
    return "".join(parts).strip()


# Adjectives that are implied once a concrete noun is present.
_WEAK_WITH = {
    "好喝": {"咖啡", "咖啡店", "拿铁", "美式", "手冲", "特调", "饮品"},
    "美食": set(),  # kept unless it would duplicate a concrete dish/shop
}

def _core_tokens(raw_tokens: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for token in raw_tokens:
        if token.lower() in STOPWORDS or token in STOPWORDS:
            continue
        pref = _preferred(token)
        if not pref or pref.lower() in STOPWORDS or pref in STOPWORDS:
            continue
        if pref in seen:
            continue
        seen.add(pref)
        out.append(pref)
    nouns = set(out)
    return [t for t in out if not (t == "好喝" and nouns & _WEAK_WITH["好喝"])]


def _score(candidate: str, original: str) -> float:
    text = (candidate or "").strip()
    if not text:
        return -100.0
    score = 0.0
    length = len(re.sub(r"\s+", "", text))
    if 2 <= length <= 12:
        score += 5.0
    elif length == 1:
        score += 1.0
    elif 13 <= length <= 16:
        score += 2.0
    else:
        score -= (length - 16) * 0.8
    intents = [w for w in INTENT_WORDS if w in text]
    if len(intents) == 1:
        score += 1.2
    elif len(intents) > 1:
        score -= 2.0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    if cjk:
        score += 1.5 * (cjk / max(len(text), 1))
    if re.search(r"[?？!！,，.。]", text):
        score -= 3.0
    leftover_stops = 0
    # Check both the raw string and its tokens for leftover stopwords.
    for stop in STOPWORDS:
        if not stop or stop.isascii() and len(stop) <= 2:
            continue
        if stop in text and not any(_preferred(k) == stop for k in SYNONYMS):
            leftover_stops += 1
    if leftover_stops:
        score -= 2.5 * leftover_stops
    # Prefer staying close only when the original is already a clean keyword.
    compact_orig = re.sub(r"\s+", "", (original or "").strip())
    orig_has_stop = any(
        (w in compact_orig) for w in STOPWORDS if not w.isascii() and len(w) >= 1 and w in compact_orig
    )
    if (text == compact_orig or text == (original or "").strip()) and not orig_has_stop:
        score += 1.5
    return score


# Official / platform-push language to avoid as a search term.
OFFICIAL_TERMS = {
    "热搜", "热搜榜", "热门榜", "热点榜", "热榜", "官方", "官方推荐",
    "广告", "推广", "赞助", "品牌合作", "商业推广", "旗舰", "旗舰店",
    "薯队长", "平台推荐", "首页推荐", "本周热门", "今日热榜", "正在热播",
    "trending", "hot list", "official",
}

# Meta words that describe a request, not a searchable topic.
ABSTRACT_META = {
    "热门", "热点", "流行", "趋势", "事情", "事儿", "事", "话题", "内容",
    "商机", "机会", "风口", "生意", "赛道", "方向", "玩法",
    "好玩", "有趣", "看看", "随便", "近期", "最近", "今日", "今天",
    "本周", "这周", "这个月", "现在", "目前",
    "trending", "trend", "trends", "hot", "viral", "popular",
    "opportunity", "opportunities", "business", "idea", "ideas",
}

TIME_WORDS = {
    "最近", "近期", "今日", "今天", "本周", "这周", "这个月", "现在", "目前",
}

EXPLICIT_ANTI_COCOON = re.compile(
    r"反茧房|打破信息茧房|信息茧房|茧房|去茧|突破茧房|多样性探索|"
    r"不要热搜|不要热门榜|不要官方|别推[给荐]|不是首页|真实讨论|"
    r"用户(在)?(聊|讨论|发)|非官方推广|打散推荐|"
    r"anti[- ]?cocoon|filter bubble|diversify|beyond (the |my )?(feed|recommendation)s?",
    re.I,
)

ABSTRACT_REQUEST = re.compile(
    r"(最近.?(比较)?热门|有什么热门|有什么热点|最近有什么|发生了什么|"
    r"有什么商机|有什么机会|有什么风口|能做(点)?什么|"
    r"有什么好玩|推荐点东西|随便看看|看点什么|"
    r"what('?s| is) trending|what('?s| is) hot|business ideas?|"
    r"any opportunities|what should i (sell|make|do))",
    re.I,
)

# When anti-cocoon applies, slight majority weight on diversity vs. popularity.
ANTI_COCOON_WEIGHT = 0.51

CUE_TERMS = {
    "反茧房", "信息茧房", "茧房", "去茧", "突破茧房", "多样性",
}

HYPE_TERMS = {
    "爆款", "必看", "必入", "刷屏", "全网", "轰动", "封神", "顶流",
    "官宣", "热销", "爆单", "爆火",
}

_DICT_KEYS = _rebuild_dict_keys()

# Fallback terms if the explore feed cannot be sampled. These lean toward
# user diary/discussion language, not official charts.
FALLBACK_BY_INTENT = {
    "opportunity": "副业分享",
    "trending": "真实分享",
    "general": "日常记录",
}

def is_explicit_anti_cocoon(text: str) -> bool:
    return bool(EXPLICIT_ANTI_COCOON.search(text or ""))


def _abstract_intent(text: str) -> Optional[str]:
    raw = text or ""
    if re.search(r"商机|机会|风口|生意|赛道|搞钱|副业|opportunity|business idea", raw, re.I):
        return "opportunity"
    if re.search(r"热门|热点|热搜|流行|趋势|最近有什么|trending|viral|what'?s hot", raw, re.I):
        return "trending"
    return None


def _concrete_tokens(tokens: list[str]) -> list[str]:
    out = []
    for token in tokens:
        if token in ABSTRACT_META or token in TIME_WORDS or token in OFFICIAL_TERMS:
            continue
        if token in INTENT_WORDS or token in CUE_TERMS or token in HYPE_TERMS:
            continue
        if token.lower() in STOPWORDS or token in STOPWORDS:
            continue
        out.append(token)
    return out


def classify_query(query: str, topic_tokens: Optional[list[str]] = None) -> dict:
    """Decide precise vs anti-cocoon. Exploration is conditional.

    Concrete query → precise, no broadening.
    Abstract query, or an explicit anti-cocoon request → explore.
    """
    original = (query or "").strip()
    explicit = is_explicit_anti_cocoon(original)
    if topic_tokens is None:
        topic_tokens = _core_tokens(tokenize(original))
    concrete = _concrete_tokens(list(topic_tokens))
    abstract_hit = bool(ABSTRACT_REQUEST.search(original))
    no_concrete = not concrete
    abstract = abstract_hit or (no_concrete and bool(_abstract_intent(original) or len(original) >= 8))
    # A short concrete keyword, even with 热门 as a modifier, stays precise.
    # "最近澳门有什么热门咖啡店" has 澳门 + 咖啡店 → precise.
    if concrete and not explicit:
        mode = "precise"
        reason = "concrete query"
    elif explicit or abstract or (no_concrete and not original):
        mode = "anti_cocoon" if original else "precise"
        if explicit:
            reason = "explicit anti-cocoon request"
        else:
            reason = "abstract query"
    else:
        mode = "precise"
        reason = "concrete query"
    return {
        "mode": mode,
        "reason": reason,
        "explicit": explicit,
        "abstract": bool(abstract and mode == "anti_cocoon"),
        "seed": concrete,
        "intent_kind": _abstract_intent(original),
    }


def _officialish(text: str) -> bool:
    blob = text or ""
    if any(term and term in blob for term in OFFICIAL_TERMS):
        return True
    if re.search(r"热搜|热榜|官方推荐|品牌合作|广告", blob):
        return True
    return False


def _fallback_keyword(classification: dict) -> str:
    if classification.get("seed"):
        # Explicit anti-cocoon with a topic: do not just repeat the
        # seed as a hot-list query; add a user-discussion angle.
        return _join(classification["seed"] + ["真实分享"])
    kind = classification.get("intent_kind") or "general"
    return FALLBACK_BY_INTENT.get(kind, FALLBACK_BY_INTENT["general"])


def _title_ngrams(title: str) -> set[str]:
    """CJK n-grams from a note title, plus any dictionary terms."""
    grams: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", title or ""):
        # Whole known terms first
        i = 0
        while i < len(run):
            matched = None
            for key in _DICT_KEYS:
                if " " in key or not any(_is_cjk(ch) for ch in key):
                    continue
                if run.startswith(key, i) and len(key) >= 2:
                    matched = key
                    break
            if matched:
                if matched not in ABSTRACT_META and matched not in OFFICIAL_TERMS and matched not in CUE_TERMS and matched not in STOPWORDS:
                    grams.add(matched)
                i += len(matched)
            else:
                i += 1
        for n in range(2, min(6, len(run)) + 1):
            for i in range(0, len(run) - n + 1):
                gram = run[i : i + n]
                if gram in ABSTRACT_META or gram in OFFICIAL_TERMS or gram in CUE_TERMS:
                    continue
                if gram in STOPWORDS or gram in HYPE_TERMS:
                    continue
                if gram in TIME_WORDS:
                    continue
                grams.add(gram)
    return grams


def _prefer_longer(df: dict[str, int]) -> dict[str, int]:
    """Drop a gram that is only a substring of a longer gram with equal or higher df."""
    keep = dict(df)
    items = list(df.items())
    for short, short_df in items:
        for long, long_df in items:
            if short != long and short in long and long_df >= short_df and len(long) > len(short):
                keep.pop(short, None)
                break
    return keep


def apply_explore_sample(refinement: dict, sample: Optional[dict]) -> dict:
    """Pick a search term from real explore-feed posts.

    Score = 51% diversity (not the most pushed cluster) + 49% support
    (actually being posted by users). Promoted / official-list language
    is dropped. If the user also named a seed topic, prefer notes that
    relate to it without collapsing back to the obvious term alone.
    """
    refinement = dict(refinement or {})
    classification = refinement.get("classification") or {}
    seed = list(classification.get("seed") or [])
    notes = []
    for note in (sample or {}).get("notes") or []:
        if not isinstance(note, dict):
            continue
        if note.get("promoted"):
            continue
        title = str(note.get("title") or "").strip()
        if not title or _officialish(title):
            continue
        notes.append(note)
    refinement["explore"] = {
        "pageUrl": (sample or {}).get("pageUrl") or "",
        "loginWall": bool((sample or {}).get("loginWall")),
        "sampled": len((sample or {}).get("notes") or []),
        "usable": len(notes),
    }
    if not notes:
        refinement["keyword"] = _fallback_keyword(classification)
        refinement["changed"] = refinement["keyword"] != refinement.get("query")
        refinement["fallback"] = True
        refinement["candidates"] = [{"keyword": refinement["keyword"], "score": 0, "source": "fallback"}]
        return refinement

    raw_df: dict[str, int] = {}
    per_note: list[set[str]] = []
    for note in notes:
        grams = _title_ngrams(note.get("title") or "")
        per_note.append(grams)
        for gram in grams:
            raw_df[gram] = raw_df.get(gram, 0) + 1

    # Prefer phrases that appear in at least two posts, unless the sample is tiny.
    min_df = 2 if len(notes) >= 6 else 1
    df = {g: c for g, c in raw_df.items() if c >= min_df or (min_df == 1 and len(g) >= 3)}
    df = _prefer_longer(df)
    if not df:
        df = _prefer_longer({g: c for g, c in raw_df.items() if len(g) >= 3})

    if not df:
        refinement["keyword"] = _fallback_keyword(classification)
        refinement["changed"] = refinement["keyword"] != refinement.get("query")
        refinement["fallback"] = True
        return refinement

    max_df = max(df.values()) or 1
    candidates = []
    for gram, count in df.items():
        if gram in seed and not any(g != gram and gram in g for g in df):
            # Bare seed term: keep, but down-rank so a more specific
            # user-discussed angle can win.
            support = count / max_df
            diversity = 1.0 - support
            score = ANTI_COCOON_WEIGHT * diversity + (1.0 - ANTI_COCOON_WEIGHT) * support
            score -= 0.25
            candidates.append((gram, score, count, "seed"))
            continue
        support = count / max_df
        diversity = 1.0 - support
        score = ANTI_COCOON_WEIGHT * diversity + (1.0 - ANTI_COCOON_WEIGHT) * support
        if 2 <= count < max_df:
            score += 0.12
        if seed and any(s in gram or gram in s for s in seed) and gram not in seed:
            score += 0.18
        candidates.append((gram, score, count, "explore"))

    candidates.sort(key=lambda item: item[1], reverse=True)
    keyword = candidates[0][0] if candidates else _fallback_keyword(classification)
    refinement["keyword"] = keyword
    refinement["changed"] = keyword != refinement.get("query")
    refinement["fallback"] = False
    refinement["tokens"] = _core_tokens(tokenize(keyword)) or [keyword]
    refinement["candidates"] = [
        {"keyword": c, "score": round(s, 3), "support": n, "source": src}
        for c, s, n, src in candidates[:12]
    ]
    refinement["sampled_topics"] = [
        {"title": n.get("title"), "author": n.get("author"), "likes": n.get("likes")}
        for n in notes[:16]
    ]
    return refinement


def refine_query(query: str) -> dict:
    """Return the chosen keyword and the intermediate inference.

    Keys: query, keyword, tokens, intent, changed, candidates.
    """
    original = (query or "").strip()
    original = _SPACE.sub(" ", original)
    if not original:
        return {
            "query": "",
            "keyword": "",
            "tokens": [],
            "intent": None,
            "changed": False,
            "candidates": [],
        }

    raw_tokens = tokenize(original)
    core = _core_tokens(raw_tokens)
    intent = _infer_intent(original, core)
    topic = _order_topic([t for t in core if t not in INTENT_WORDS])
    # Xiaohongshu queries put the topic first and at most one intent last.
    core = topic + ([intent] if intent and intent not in topic else [])

    candidates: list[str] = []

    def add(value: str) -> None:
        value = _SPACE.sub(" ", (value or "").strip())
        if value and value not in candidates:
            candidates.append(value)

    add(_join(topic))
    add(_join(core))
    if intent and intent not in topic:
        add(_join(topic + [intent]))
    # If the input was already a short keyword, keep it in the running.
    cleaned_original = _join(_core_tokens(tokenize(_PUNCT.sub(" ", original))))
    add(cleaned_original)
    # Very short original (already a search term) should stay eligible
    # even if stopword stripping changed nothing.
    if len(re.sub(r"\s+", "", original)) <= 12:
        add(original)

    # Only attach an inferred intent when the user wrote a request
    # sentence. A ready-made keyword like "澳门咖啡店" should stay put.
    if not _is_request_sentence(original, raw_tokens):
        candidates = [c for c in candidates if not (intent and c.endswith(intent) and intent not in original and _preferred(intent) not in raw_tokens and intent not in core)]
        add(_join(topic) or original)
        add(original if len(re.sub(r"\s+", "", original)) <= 12 else "")

    scored = sorted(
        ((c, _score(c, original)) for c in candidates if c),
        key=lambda item: item[1],
        reverse=True,
    )
    keyword = scored[0][0] if scored else ( _join(topic) or original )
    # Final safety: never search with an empty string if the user typed.
    if not keyword:
        keyword = original

    # Strip official-chart modifiers from an otherwise concrete query
    # ("澳门热门咖啡店" → "澳门咖啡店") without broadening the topic.
    precise_tokens = _concrete_tokens(_core_tokens(tokenize(keyword)))
    if precise_tokens:
        stripped = _join(precise_tokens + ([intent] if intent and intent in keyword and intent not in precise_tokens else []))
        if stripped:
            keyword = stripped

    classification = classify_query(original, topic)
    if classification["mode"] == "anti_cocoon":
        keyword = _fallback_keyword(classification)
        # The live search path will replace this after sampling explore.
        return {
            "query": original,
            "keyword": keyword,
            "tokens": list(classification.get("seed") or []),
            "intent": intent,
            "changed": keyword != original,
            "candidates": [{"keyword": keyword, "score": 0, "source": "pending_explore"}],
            "mode": "anti_cocoon",
            "reason": classification["reason"],
            "needs_explore": True,
            "classification": classification,
            "principle": "Find what is hard to find: real user posts, not official trending.",
        }

    return {
        "query": original,
        "keyword": keyword,
        "tokens": precise_tokens or topic or core,
        "intent": intent,
        "changed": keyword != original,
        "candidates": [{"keyword": c, "score": round(s, 2)} for c, s in scored],
        "mode": "precise",
        "reason": classification["reason"],
        "needs_explore": False,
        "classification": classification,
        "principle": "Concrete query: search this accurately, without broadening.",
    }


def should_refine(flag: Optional[str]) -> bool:
    """False when the caller passes refine=0 / false / raw=1."""
    if flag is None:
        return True
    value = str(flag).strip().lower()
    return value not in {"0", "false", "no", "off", "raw"}


if __name__ == "__main__":
    import json
    import sys

    samples = sys.argv[1:] or [
        "帮我找一下澳门好喝的咖啡店",
        "咖啡",
        "澳门咖啡店",
        "最近澳门有什么热门咖啡店",
        "小红书最近比较热门的事情",
        "小红书有什么商机可以用",
        "反茧房看看穿搭",
        "速溶咖啡测评",
    ]
    for sample in samples:
        result = refine_query(sample)
        slim = {k: result[k] for k in ("query", "keyword", "mode", "reason", "tokens", "needs_explore") if k in result}
        print(json.dumps(slim, ensure_ascii=False))
