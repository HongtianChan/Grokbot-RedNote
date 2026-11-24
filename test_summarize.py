#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-check for the on-device search-result summarizer."""
from __future__ import annotations

import unittest

from summarize import classify_title, curate_notes, dedupe_notes, summarize_notes


GO = "http://127.0.0.1:18765/go?id=aaaaaaaaaaaaaaaaaaaaaaaa&xsec_token=TOKEN1="
GO2 = "http://127.0.0.1:18765/go?id=bbbbbbbbbbbbbbbbbbbbbbbb&xsec_token=TOKEN2="
GO3 = "http://127.0.0.1:18765/go?id=cccccccccccccccccccccccc&xsec_token=TOKEN3="
GO4 = "http://127.0.0.1:18765/go?id=dddddddddddddddddddddddd&xsec_token=TOKEN4="
GO5 = "http://127.0.0.1:18765/go?id=eeeeeeeeeeeeeeeeeeeeeeee&xsec_token=TOKEN5="


class ClassifyTests(unittest.TestCase):
    def test_pattern_rules(self) -> None:
        cases = {
            "疯狗式黄金3秒已死，现在流行猫式开头。": "猫式/软开头 vs 疯狗式黄金三秒",
            "别再死磕黄金三秒了，早就不管用了！": "「黄金三秒已死」反思",
            "“黄金三秒开头”真的要失效了！": "「黄金三秒已死」反思",
            "短视频黄金三秒已死": "「黄金三秒已死」反思",
            "爆款音效放在开头 留人巨猛❗️": "音效开头",
            "口播网感开场设计，拿下黄金前3秒": "口播开场",
            "6种口播开场方式，知识类口播必备！": "口播开场",
            "小说100种开篇": "写作/小说开头",
            "宠物带货不出单？5个爆款开头🔥直接抄": "带货开头",
            "剪辑常用三种开头": "剪辑/片头/三种编辑开头",
            "5个创意片头，让你的视频开场更抓人": "剪辑/片头/三种编辑开头",
            "5种一秒抓人注意力的视频开头": "一秒抓人/视觉片头",
            "只看开场，你能猜到这条视频多少播放吗？": "一秒抓人/视觉片头",
            "谁用谁火的七句爆款开头钩子": "七句/公式钩子口诀",
            "直接套公式❗️爆款万能钩子开头合集": "七句/公式钩子口诀",
            "开课啦‼️教你用黄金三秒钟留住观众✌🏻": "黄金三秒/前三秒教学",
            "海外MKT 爆款短视频灵感": "海外社媒灵感",
            "拾一": "其他",
        }
        for title, expected in cases.items():
            self.assertEqual(classify_title(title), expected, title)

    def test_cat_style_beats_dead_golden_three(self) -> None:
        # Contains both 猫式 and 已死; the more specific contrast wins.
        self.assertEqual(
            classify_title("疯狗式黄金3秒已死，现在流行猫式开头。"),
            "猫式/软开头 vs 疯狗式黄金三秒",
        )


class DedupeAndRankTests(unittest.TestCase):
    def test_dedupe_by_id_keeps_higher_likes_and_go_url(self) -> None:
        notes = [
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "A", "author": "Ann", "likes_count": 10, "url": "https://www.xiaohongshu.com/explore/aaaaaaaaaaaaaaaaaaaaaaaa"},
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "A", "author": "Ann", "likes": "1.2万", "url": GO},
        ]
        unique = dedupe_notes(notes)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["likes_count"], 12000)
        self.assertEqual(unique[0]["url"], GO)

    def test_summarize_groups_rank_and_example(self) -> None:
        notes = [
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "只看开场，你能猜到这条视频多少播放吗？", "author": "影视飓风", "likes_count": 41200, "url": GO},
            {"id": "bbbbbbbbbbbbbbbbbbbbbbbb", "title": "疯狗式黄金3秒已死，现在流行猫式开头。", "author": "一款雷雷", "likes_count": 35100, "url": GO2},
            {"id": "cccccccccccccccccccccccc", "title": "谁用谁火的七句爆款开头钩子", "author": "编导然然", "likes_count": 12500, "url": GO3},
            # Duplicate of the swipe-file note, should not inflate count.
            {"id": "cccccccccccccccccccccccc", "title": "谁用谁火的七句爆款开头钩子", "author": "编导然然", "likes_count": 12500, "url": GO3},
            {"id": "dddddddddddddddddddddddd", "title": "剪辑常用三种开头", "author": "土豆教剪辑（收徒）", "likes_count": 7378, "url": GO4},
            {"id": "eeeeeeeeeeeeeeeeeeeeeeee", "title": "10类钩子开头", "author": "大姝在进步", "likes_count": 5493, "url": GO5},
            # High-like untitled/account note should not outrank named patterns.
            {"id": "ffffffffffffffffffffffff", "title": "拾一", "author": "拾一", "likes_count": 23200, "url": ""},
        ]
        summary = summarize_notes(notes)
        self.assertEqual(summary["total"], 7)
        self.assertEqual(summary["unique"], 6)
        names = [g["name"] for g in summary["groups"]]
        self.assertEqual(
            names,
            [
                "一秒抓人/视觉片头",
                "猫式/软开头 vs 疯狗式黄金三秒",
                "七句/公式钩子口诀",
                "剪辑/片头/三种编辑开头",
                "其他",
            ],
        )
        self.assertEqual(summary["groups"][-1]["name"], "其他")
        self.assertEqual(summary["groups"][-1]["example"]["likes_count"], 23200)
        # Swipe-file group has two unique notes; example is the higher-like one.
        swipe = summary["groups"][2]
        self.assertEqual(swipe["count"], 2)
        self.assertEqual(swipe["example"]["title"], "谁用谁火的七句爆款开头钩子")
        self.assertEqual(swipe["example"]["author"], "编导然然")
        self.assertEqual(swipe["example"]["likes_count"], 12500)
        self.assertEqual(swipe["example"]["url"], GO3)
        # Do not invent tokens for a note that has no url.
        bare = summarize_notes([{"id": "ffffffffffffffffffffffff", "title": "拾一", "author": "拾一", "likes_count": 1}])
        self.assertEqual(bare["groups"][0]["example"]["url"], "")

    def test_empty(self) -> None:
        summary = summarize_notes([])
        self.assertEqual(summary, {"groups": [], "total": 0, "unique": 0})


class CurateTests(unittest.TestCase):
    def test_prefers_named_groups_and_caps_at_ten(self) -> None:
        notes = [
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "只看开场，你能猜到这条视频多少播放吗？", "author": "影视飓风", "likes_count": 41200, "url": GO},
            {"id": "bbbbbbbbbbbbbbbbbbbbbbbb", "title": "疯狗式黄金3秒已死，现在流行猫式开头。", "author": "一款雷雷", "likes_count": 35100, "url": GO2},
            {"id": "cccccccccccccccccccccccc", "title": "谁用谁火的七句爆款开头钩子", "author": "编导然然", "likes_count": 12500, "url": GO3},
            {"id": "dddddddddddddddddddddddd", "title": "剪辑常用三种开头", "author": "土豆教剪辑（收徒）", "likes_count": 7378, "url": GO4},
            {"id": "eeeeeeeeeeeeeeeeeeeeeeee", "title": "10类钩子开头", "author": "大姝在进步", "likes_count": 5493, "url": GO5},
            {"id": "111111111111111111111111", "title": "口播网感开场设计，拿下黄金前3秒", "author": "Z嗯", "likes_count": 4458, "url": GO},
            {"id": "222222222222222222222222", "title": "别再死磕黄金三秒了，早就不管用了！", "author": "阿文校长", "likes_count": 3927, "url": GO2},
            {"id": "333333333333333333333333", "title": "宠物带货不出单？5个爆款开头🔥直接抄", "author": "桃总", "likes_count": 2839, "url": GO3},
            {"id": "444444444444444444444444", "title": "爆款音效放在开头 留人巨猛❗️", "author": "小歪再努力.", "likes_count": 885, "url": GO4},
            {"id": "555555555555555555555555", "title": "开课啦‼️教你用黄金三秒钟留住观众✌🏻", "author": "Ms Chloris小课堂", "likes_count": 1058, "url": GO5},
            {"id": "666666666666666666666666", "title": "海外MKT 爆款短视频灵感", "author": "Luna Green", "likes_count": 6916, "url": GO},
            # 11th quality group would be skipped by the cap if we had more;
            # skipped buckets must not appear even with huge like counts.
            {"id": "ffffffffffffffffffffffff", "title": "拾一", "author": "拾一", "likes_count": 23200, "url": GO},
            {"id": "999999999999999999999999", "title": "小说100种开篇", "author": "耶鲁猫猫", "likes_count": 1379, "url": GO2},
        ]
        curated = curate_notes(notes)
        self.assertGreaterEqual(len(curated), 5)
        self.assertLessEqual(len(curated), 10)
        titles = [item["title"] for item in curated]
        self.assertNotIn("拾一", titles)
        self.assertNotIn("小说100种开篇", titles)
        self.assertEqual(titles[0], "只看开场，你能猜到这条视频多少播放吗？")
        self.assertEqual(titles[1], "疯狗式黄金3秒已死，现在流行猫式开头。")
        self.assertEqual(curated[0]["url"], GO)
        self.assertEqual(curated[0]["likes_count"], 41200)
        self.assertEqual(curated[0]["group"], "一秒抓人/视觉片头")
        # One note per group first: 编导然然 beats 大姝 even though both are swipe files.
        self.assertIn("谁用谁火的七句爆款开头钩子", titles)
        # Second swipe-file note can fill remaining slots after one-per-group.
        self.assertEqual(len(titles), len(set(titles)))

    def test_fills_to_at_least_five_from_quality_notes(self) -> None:
        notes = [
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "只看开场，你能猜到这条视频多少播放吗？", "author": "影视飓风", "likes_count": 100, "url": GO},
            {"id": "bbbbbbbbbbbbbbbbbbbbbbbb", "title": "视觉失焦练习2", "author": "甲", "likes_count": 80, "url": GO2},
            {"id": "cccccccccccccccccccccccc", "title": "5种一秒抓人注意力的视频开头", "author": "乙", "likes_count": 70, "url": GO3},
            {"id": "dddddddddddddddddddddddd", "title": "剪辑常用三种开头", "author": "丙", "likes_count": 60, "url": GO4},
            {"id": "eeeeeeeeeeeeeeeeeeeeeeee", "title": "5个创意片头，让你的视频开场更抓人", "author": "丁", "likes_count": 50, "url": GO5},
        ]
        curated = curate_notes(notes)
        self.assertEqual(len(curated), 5)
        # First pass takes one per group (visual, 剪辑), then fills by likes.
        self.assertEqual(curated[0]["title"], "只看开场，你能猜到这条视频多少播放吗？")
        self.assertEqual(curated[1]["title"], "剪辑常用三种开头")
        self.assertEqual(curated[2]["title"], "视觉失焦练习2")

    def test_uses_skip_groups_only_to_reach_minimum(self) -> None:
        notes = [
            {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "title": "只看开场，你能猜到这条视频多少播放吗？", "author": "影视飓风", "likes_count": 100, "url": GO},
            {"id": "bbbbbbbbbbbbbbbbbbbbbbbb", "title": "剪辑常用三种开头", "author": "土豆", "likes_count": 90, "url": GO2},
            {"id": "ffffffffffffffffffffffff", "title": "拾一", "author": "拾一", "likes_count": 800, "url": GO3},
            {"id": "999999999999999999999999", "title": "小说100种开篇", "author": "耶鲁猫猫", "likes_count": 700, "url": GO4},
            {"id": "888888888888888888888888", "title": "曲奇の饼🍪", "author": "曲奇の饼🍪", "likes_count": 600, "url": GO5},
        ]
        curated = curate_notes(notes)
        self.assertEqual(len(curated), 5)
        self.assertEqual(curated[0]["title"], "只看开场，你能猜到这条视频多少播放吗？")
        self.assertEqual(curated[1]["title"], "剪辑常用三种开头")
        # Quality notes first; skipped buckets only pad to 5.
        self.assertEqual([item["title"] for item in curated[2:]], ["拾一", "小说100种开篇", "曲奇の饼🍪"])

    def test_empty_curation(self) -> None:
        self.assertEqual(curate_notes([]), [])


if __name__ == "__main__":
    unittest.main()
