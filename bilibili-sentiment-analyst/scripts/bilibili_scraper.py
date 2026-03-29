#!/usr/bin/env python3
"""
Bilibili Scraper - 通过B站公开Web API采集视频评论与弹幕

无需API Key，大部分接口可直接调用。

用法:
    from bilibili_scraper import BilibiliScraper
    scraper = BilibiliScraper()
    info = scraper.get_video_info("BV1xx411c7mD")
    comments = scraper.fetch_comments("BV1xx411c7mD")
    danmakus = scraper.fetch_danmaku(cid=info["cid"])
"""

import os
import re
import time
import json
import struct
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

# ── .env loader ─────────────────────────────────────────────────────────
def _load_dotenv():
    """Load .env from skill root into os.environ (real env vars take precedence)."""
    for candidate in [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
    ]:
        if candidate.exists():
            with open(candidate, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key, value = key.strip(), value.strip()
                        if key and key not in os.environ:
                            os.environ[key] = value
            break

_load_dotenv()


class BilibiliScraper:
    """B站视频评论与弹幕采集器，基于公开Web API。"""

    # ── API 端点 ──
    VIDEO_INFO_URL = "https://api.bilibili.com/x/web-interface/view"
    COMMENT_URL = "https://api.bilibili.com/x/v2/reply"
    COMMENT_REPLY_URL = "https://api.bilibili.com/x/v2/reply/reply"
    DANMAKU_URL = "https://api.bilibili.com/x/v1/dm/list.so"
    DANMAKU_PB_URL = "https://api.bilibili.com/x/v2/dm/web/seg.so"
    USER_VIDEOS_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
    USER_INFO_URL = "https://api.bilibili.com/x/space/acc/info"
    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"

    def __init__(self, cookie=None, request_delay=0.6, max_retries=3):
        """
        Args:
            cookie: B站登录Cookie（可选，从 .env 的 BILIBILI_COOKIE 加载）
            request_delay: 请求间隔（秒）
            max_retries: 失败重试次数
        """
        self.cookie = cookie or os.environ.get("BILIBILI_COOKIE", "")
        self.delay = request_delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    # ── 工具方法 ──

    @staticmethod
    def parse_video_id(url_or_id):
        """从B站视频链接或ID中提取BV号和aid。

        支持格式:
            - BV号: "BV1xx411c7mD"
            - av号: "av170001" 或 170001
            - 完整URL: "https://www.bilibili.com/video/BV1xx411c7mD"
        
        Returns:
            dict: {"bvid": str or None, "aid": int or None}
        """
        s = str(url_or_id).strip()

        # URL中提取
        bv_match = re.search(r"(BV[\w]{10})", s, re.IGNORECASE)
        if bv_match:
            return {"bvid": bv_match.group(1), "aid": None}

        av_match = re.search(r"av(\d+)", s, re.IGNORECASE)
        if av_match:
            return {"bvid": None, "aid": int(av_match.group(1))}

        # 纯BV号
        if re.match(r"^BV[\w]{10}$", s, re.IGNORECASE):
            return {"bvid": s, "aid": None}

        # 纯数字 → aid
        if s.isdigit():
            return {"bvid": None, "aid": int(s)}

        raise ValueError(
            f"无法解析视频ID: {s}\n"
            f"请提供BV号、av号或B站视频链接"
        )

    def _request_with_retry(self, url, params=None, is_binary=False):
        """带重试和退避的HTTP请求。"""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    if is_binary:
                        return resp.content
                    return resp.json()
                elif resp.status_code in (412, 429, 503):
                    wait = (attempt + 1) * 3
                    print(f"  [Rate limited] HTTP {resp.status_code}, "
                          f"等待{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    print(f"  [Error] HTTP {resp.status_code}")
                    return None
            except requests.RequestException as e:
                print(f"  [Network error] {e}, 重试 {attempt + 1}/{self.max_retries}")
                time.sleep((attempt + 1) * 2)
        return None

    # ── 视频信息 ──

    def get_video_info(self, video_id):
        """获取视频基础信息（播放量、三连数据、UP主等）。

        Returns:
            dict: 视频详情，包含title, owner, stat, cid, duration等
            None: 请求失败
        """
        parsed = self.parse_video_id(video_id)
        params = {}
        if parsed["bvid"]:
            params["bvid"] = parsed["bvid"]
        else:
            params["aid"] = parsed["aid"]

        data = self._request_with_retry(self.VIDEO_INFO_URL, params=params)
        if not data or data.get("code") != 0:
            print(f"[Error] 获取视频信息失败: {data}")
            return None

        d = data["data"]
        stat = d.get("stat", {})
        owner = d.get("owner", {})

        return {
            "aid": d.get("aid"),
            "bvid": d.get("bvid"),
            "cid": d.get("cid"),                # 第一个分P的cid
            "cid_list": [p["cid"] for p in d.get("pages", [])],  # 所有分P
            "title": d.get("title"),
            "description": d.get("desc", ""),
            "duration": d.get("duration"),        # 秒
            "pubdate": d.get("pubdate"),          # Unix时间戳
            "owner_mid": owner.get("mid"),
            "owner_name": owner.get("name"),
            "view": stat.get("view", 0),          # 播放
            "like": stat.get("like", 0),           # 点赞
            "coin": stat.get("coin", 0),           # 投币
            "favorite": stat.get("favorite", 0),   # 收藏
            "share": stat.get("share", 0),         # 分享
            "danmaku": stat.get("danmaku", 0),     # 弹幕数
            "reply": stat.get("reply", 0),         # 评论数
        }

    # ── 评论采集 ──

    def fetch_comments(self, video_id, sort=2, max_pages=None,
                       fetch_replies=True, max_replies_per_comment=10):
        """采集视频评论。

        Args:
            video_id: BV号、av号或链接
            sort: 排序方式 0=按时间, 1=按点赞数, 2=按回复数
            max_pages: 最大页数，None=全量（每页20条）
            fetch_replies: 是否拉取楼中楼回复
            max_replies_per_comment: 每条评论最多拉取回复数

        Returns:
            dict: {
                "video_id": str,
                "comments": [list of comment dicts],
                "fetch_time": str,
                "total_fetched": int,
            }
        """
        parsed = self.parse_video_id(video_id)

        # 需要aid来调用评论接口
        if parsed["aid"]:
            oid = parsed["aid"]
        else:
            # 通过video_info获取aid
            info = self.get_video_info(video_id)
            if not info:
                return {"video_id": str(video_id), "comments": [],
                        "fetch_time": "", "total_fetched": 0}
            oid = info["aid"]

        all_comments = []
        page = 1

        print(f"[Scraper] 开始采集评论, oid={oid}, sort={sort}")

        while True:
            if max_pages and page > max_pages:
                break

            params = {
                "type": 1,           # 1=视频评论
                "oid": oid,
                "sort": sort,
                "pn": page,
                "ps": 20,           # 每页条数（最大20）
                "nohot": 0,
            }

            data = self._request_with_retry(self.COMMENT_URL, params=params)
            if not data or data.get("code") != 0:
                print(f"  [Error] 评论接口返回异常: {data}")
                break

            reply_data = data.get("data", {})
            replies = reply_data.get("replies") or []

            if not replies:
                print(f"  [Done] 无更多评论，共采集 {len(all_comments)} 条")
                break

            for reply in replies:
                member = reply.get("member", {})
                content = reply.get("content", {})
                up_action = reply.get("up_action", {})

                comment = {
                    "rpid": reply.get("rpid"),
                    "message": content.get("message", ""),
                    "like": reply.get("like", 0),
                    "rcount": reply.get("rcount", 0),       # 回复数
                    "ctime": reply.get("ctime"),              # Unix时间戳
                    "mid": member.get("mid"),
                    "uname": member.get("uname", ""),
                    "level_info": member.get("level_info", {}).get("current_level", 0),
                    "up_reply": bool(up_action.get("reply")),  # UP主是否回复
                    "up_like": bool(up_action.get("like")),    # UP主是否点赞
                    "is_top": reply.get("type") == 1,          # 是否置顶
                    "sub_replies": [],
                }

                # 拉取楼中楼回复
                if fetch_replies and reply.get("rcount", 0) > 0:
                    sub = self._fetch_sub_replies(
                        oid, reply["rpid"], max_replies_per_comment
                    )
                    comment["sub_replies"] = sub

                all_comments.append(comment)

            print(f"  [Page {page}] 本页{len(replies)}条, "
                  f"累计{len(all_comments)}条评论")
            page += 1
            time.sleep(self.delay)

        return {
            "video_id": str(video_id),
            "oid": oid,
            "comments": all_comments,
            "fetch_time": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
            "total_fetched": len(all_comments),
        }

    def _fetch_sub_replies(self, oid, root_rpid, max_count=10):
        """拉取楼中楼回复。"""
        params = {
            "type": 1,
            "oid": oid,
            "root": root_rpid,
            "ps": min(max_count, 20),
            "pn": 1,
        }
        data = self._request_with_retry(self.COMMENT_REPLY_URL, params=params)
        if not data or data.get("code") != 0:
            return []

        replies = data.get("data", {}).get("replies") or []
        result = []
        for r in replies[:max_count]:
            member = r.get("member", {})
            content = r.get("content", {})
            result.append({
                "rpid": r.get("rpid"),
                "message": content.get("message", ""),
                "like": r.get("like", 0),
                "ctime": r.get("ctime"),
                "uname": member.get("uname", ""),
                "mid": member.get("mid"),
            })
        return result

    # ── 弹幕采集 ──

    def fetch_danmaku(self, cid, segment_index=None):
        """采集视频弹幕。

        使用XML接口（兼容性更好，无需protobuf依赖）。

        Args:
            cid: 视频cid（从get_video_info获取）
            segment_index: 分段索引（用于长视频），None=全部

        Returns:
            dict: {
                "cid": int,
                "danmakus": [list of danmaku dicts],
                "fetch_time": str,
                "total_fetched": int,
            }
        """
        print(f"[Scraper] 开始采集弹幕, cid={cid}")

        url = self.DANMAKU_URL
        params = {"oid": cid}

        content = self._request_with_retry(url, params=params, is_binary=True)
        if not content:
            return {"cid": cid, "danmakus": [],
                    "fetch_time": "", "total_fetched": 0}

        # 解析XML弹幕
        danmakus = self._parse_danmaku_xml(content)

        print(f"  [Done] 共采集 {len(danmakus)} 条弹幕")

        return {
            "cid": cid,
            "danmakus": danmakus,
            "fetch_time": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
            "total_fetched": len(danmakus),
        }

    def _parse_danmaku_xml(self, xml_bytes):
        """解析B站XML格式弹幕。

        XML中每条弹幕格式:
        <d p="进度(秒),模式,字号,颜色,时间戳,弹幕池,用户hash,弹幕ID">弹幕内容</d>

        模式: 1/2/3=滚动, 4=底部, 5=顶部, 6=逆向, 7=精准定位, 8=高级
        """
        import xml.etree.ElementTree as ET

        try:
            # B站XML弹幕可能有编码问题，尝试解码
            try:
                import zlib
                xml_text = zlib.decompress(xml_bytes, -zlib.MAX_WBITS).decode("utf-8")
            except Exception:
                xml_text = xml_bytes.decode("utf-8", errors="ignore")

            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"  [Error] 弹幕XML解析失败: {e}")
            return []

        danmakus = []
        for d in root.findall(".//d"):
            p = d.get("p", "")
            text = d.text or ""
            parts = p.split(",")
            if len(parts) < 8:
                continue

            try:
                danmakus.append({
                    "progress": float(parts[0]),       # 出现时间（秒）
                    "mode": int(parts[1]),              # 弹幕模式
                    "fontsize": int(parts[2]),           # 字号
                    "color": int(parts[3]),              # 颜色（十进制）
                    "ctime": int(parts[4]),              # 发送时间（Unix时间戳）
                    "pool": int(parts[5]),               # 弹幕池 0=普通 1=字幕 2=特殊
                    "user_hash": parts[6],               # 用户hash
                    "dmid": parts[7],                    # 弹幕ID
                    "text": text.strip(),
                })
            except (ValueError, IndexError):
                continue

        return danmakus

    # ── 关键词搜索视频 ──

    def search_videos(self, keyword, max_pages=2, order="totalrank",
                      duration=0, tids=0):
        """按关键词搜索B站视频。

        Args:
            keyword: 搜索关键词（如"鸣潮1.4"、"原神深渊"）
            max_pages: 最大翻页数（每页20条，默认2页=40条）
            order: 排序方式
                - "totalrank": 综合排序（默认）
                - "click": 最多播放
                - "pubdate": 最新发布
                - "dm": 最多弹幕
                - "stow": 最多收藏
                - "scores": 最多评论
            duration: 时长筛选 0=全部, 1=0-10分钟, 2=10-30分钟,
                      3=30-60分钟, 4=60+分钟
            tids: 分区ID 0=全部, 4=游戏区, 17=单机游戏,
                  171=电子竞技, 172=手机游戏, 65=网络游戏

        Returns:
            dict: {
                "keyword": str,
                "order": str,
                "videos": [list of video dicts],
                "total_results": int,   # B站返回的总结果数
                "total_fetched": int,   # 实际拉取数量
                "fetch_time": str,
            }
        """
        print(f"[Scraper] 搜索B站视频, 关键词='{keyword}', 排序={order}")

        all_videos = []
        total_results = 0

        for page in range(1, max_pages + 1):
            params = {
                "search_type": "video",
                "keyword": keyword,
                "order": order,
                "page": page,
                "duration": duration,
                "tids": tids,
            }

            data = self._request_with_retry(self.SEARCH_URL, params=params)
            if not data or data.get("code") != 0:
                print(f"  [Error] 搜索接口返回异常: {data}")
                break

            result = data.get("data", {})
            if page == 1:
                total_results = result.get("numResults", 0)
                print(f"  [Info] 共找到 {total_results} 条结果")

            video_list = result.get("result") or []
            if not video_list:
                break

            for v in video_list:
                # 清理标题中的高亮标签 <em class="keyword">xxx</em>
                title = re.sub(r"<[^>]+>", "", v.get("title", ""))
                all_videos.append({
                    "aid": v.get("aid"),
                    "bvid": v.get("bvid"),
                    "title": title,
                    "description": v.get("description", ""),
                    "author": v.get("author", ""),
                    "mid": v.get("mid"),
                    "pubdate": v.get("pubdate"),          # Unix时间戳
                    "duration": v.get("duration", ""),     # "HH:MM:SS"格式
                    "play": v.get("play", 0),
                    "danmaku": v.get("video_review", 0),   # 弹幕数
                    "favorites": v.get("favorites", 0),
                    "review": v.get("review", 0),          # 评论数
                    "tag": v.get("tag", ""),               # 标签（逗号分隔）
                    "arcurl": v.get("arcurl", ""),         # 视频链接
                })

            print(f"  [Page {page}] 本页{len(video_list)}条, "
                  f"累计{len(all_videos)}条")
            time.sleep(self.delay)

        return {
            "keyword": keyword,
            "order": order,
            "videos": all_videos,
            "total_results": total_results,
            "total_fetched": len(all_videos),
            "fetch_time": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        }

    def search_and_collect(self, keyword, top_n=10, max_search_pages=2,
                           search_order="totalrank", tids=0,
                           comment_pages=3, fetch_danmaku=True):
        """搜索关键词 → 批量拉取Top N视频的评论+弹幕。

        这是"话题分析"的一站式入口方法。

        Args:
            keyword: 搜索关键词
            top_n: 从搜索结果中取前N个视频深入分析
            max_search_pages: 搜索最大翻页数
            search_order: 搜索排序（同 search_videos）
            tids: 分区ID（0=全部, 4=游戏区）
            comment_pages: 每个视频拉取的评论页数
            fetch_danmaku: 是否拉取弹幕

        Returns:
            dict: {
                "keyword": str,
                "videos": [list of {
                    "video_info": dict,
                    "comments": dict,
                    "danmaku": dict or None,
                }],
                "total_videos_analyzed": int,
                "total_comments": int,
                "total_danmakus": int,
                "fetch_time": str,
            }
        """
        # Step 1: 搜索
        search_result = self.search_videos(
            keyword, max_pages=max_search_pages,
            order=search_order, tids=tids
        )
        candidates = search_result["videos"][:top_n]

        if not candidates:
            print(f"[Warning] 关键词'{keyword}'无搜索结果")
            return {
                "keyword": keyword, "videos": [],
                "total_videos_analyzed": 0,
                "total_comments": 0, "total_danmakus": 0,
                "fetch_time": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
            }

        print(f"\n[Scraper] 将对Top {len(candidates)}个视频批量采集评论"
              f"{'+弹幕' if fetch_danmaku else ''}")

        # Step 2: 逐个采集
        collected = []
        total_comments = 0
        total_danmakus = 0

        for i, v in enumerate(candidates, 1):
            bvid = v["bvid"]
            print(f"\n── [{i}/{len(candidates)}] {v['title']} ({bvid}) ──")

            # 获取视频详情（含cid）
            video_info = self.get_video_info(bvid)
            if not video_info:
                print(f"  [Skip] 无法获取视频信息")
                continue

            # 拉取评论
            comments = self.fetch_comments(
                bvid, max_pages=comment_pages, sort=2
            )
            total_comments += comments["total_fetched"]

            # 拉取弹幕
            danmaku = None
            if fetch_danmaku and video_info.get("cid"):
                danmaku = self.fetch_danmaku(video_info["cid"])
                total_danmakus += danmaku["total_fetched"]

            collected.append({
                "video_info": video_info,
                "comments": comments,
                "danmaku": danmaku,
                "search_meta": {  # 保留搜索时的元信息
                    "search_rank": i,
                    "search_play": v["play"],
                    "search_tag": v["tag"],
                },
            })

        print(f"\n[Done] 共分析{len(collected)}个视频, "
              f"{total_comments}条评论, {total_danmakus}条弹幕")

        return {
            "keyword": keyword,
            "videos": collected,
            "total_videos_analyzed": len(collected),
            "total_comments": total_comments,
            "total_danmakus": total_danmakus,
            "fetch_time": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        }

    # ── UP主视频列表 ──

    def fetch_user_videos(self, mid, max_pages=5, order="pubdate",
                          keyword=None):
        """获取UP主视频列表。

        Args:
            mid: UP主UID
            max_pages: 最大页数（每页30条）
            order: 排序 "pubdate"=最新发布, "click"=最多播放, "stow"=最多收藏
            keyword: 搜索关键词（在UP主视频中搜索）

        Returns:
            dict: {
                "mid": int,
                "videos": [list of video dicts],
                "total_fetched": int,
            }
        """
        print(f"[Scraper] 获取UP主视频列表, mid={mid}")

        all_videos = []
        for page in range(1, max_pages + 1):
            params = {
                "mid": mid,
                "ps": 30,
                "pn": page,
                "order": order,
            }
            if keyword:
                params["keyword"] = keyword

            data = self._request_with_retry(self.USER_VIDEOS_URL, params=params)
            if not data or data.get("code") != 0:
                break

            vlist = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break

            for v in vlist:
                all_videos.append({
                    "aid": v.get("aid"),
                    "bvid": v.get("bvid"),
                    "title": v.get("title"),
                    "description": v.get("description", ""),
                    "created": v.get("created"),          # Unix时间戳
                    "length": v.get("length"),             # "MM:SS"格式
                    "play": v.get("play", 0),
                    "comment": v.get("comment", 0),
                    "video_review": v.get("video_review", 0),  # 弹幕数
                })

            print(f"  [Page {page}] 本页{len(vlist)}条, 累计{len(all_videos)}条")
            time.sleep(self.delay)

        return {
            "mid": mid,
            "videos": all_videos,
            "total_fetched": len(all_videos),
        }

    # ── DataFrame 转换 ──

    def comments_to_dataframe(self, comments_data):
        """将评论数据转为DataFrame。

        Returns:
            pd.DataFrame: 评论数据（含楼中楼展开为独立行）
        """
        rows = []
        for c in comments_data.get("comments", []):
            rows.append({
                "rpid": c["rpid"],
                "message": c["message"],
                "like": c["like"],
                "rcount": c["rcount"],
                "ctime": c["ctime"],
                "uname": c["uname"],
                "mid": c["mid"],
                "level": c.get("level_info", 0),
                "up_reply": c.get("up_reply", False),
                "up_like": c.get("up_like", False),
                "is_top": c.get("is_top", False),
                "is_sub_reply": False,
                "parent_rpid": None,
            })
            # 展开楼中楼
            for sub in c.get("sub_replies", []):
                rows.append({
                    "rpid": sub["rpid"],
                    "message": sub["message"],
                    "like": sub["like"],
                    "rcount": 0,
                    "ctime": sub["ctime"],
                    "uname": sub["uname"],
                    "mid": sub["mid"],
                    "level": 0,
                    "up_reply": False,
                    "up_like": False,
                    "is_top": False,
                    "is_sub_reply": True,
                    "parent_rpid": c["rpid"],
                })

        df = pd.DataFrame(rows)
        if "ctime" in df.columns and not df.empty:
            df["ctime"] = pd.to_datetime(df["ctime"], unit="s", utc=True)
            df["ctime"] = df["ctime"].dt.tz_convert("Asia/Shanghai")
        return df

    def danmaku_to_dataframe(self, danmaku_data):
        """将弹幕数据转为DataFrame。"""
        df = pd.DataFrame(danmaku_data.get("danmakus", []))
        if "ctime" in df.columns and not df.empty:
            df["ctime"] = pd.to_datetime(df["ctime"], unit="s", utc=True)
            df["ctime"] = df["ctime"].dt.tz_convert("Asia/Shanghai")
        return df


if __name__ == "__main__":
    import sys

    scraper = BilibiliScraper()

    if len(sys.argv) > 1:
        target = sys.argv[1]
        info = scraper.get_video_info(target)
        if info:
            print(f"\n📋 {info['title']}")
            print(f"   BV号: {info['bvid']}")
            print(f"   UP主: {info['owner_name']}")
            print(f"   播放: {info['view']:,}")
            print(f"   三连: 👍{info['like']:,} / 💰{info['coin']:,} / ⭐{info['favorite']:,}")
            print(f"   评论: {info['reply']:,} / 弹幕: {info['danmaku']:,}")

            # 演示：拉取前2页评论
            comments = scraper.fetch_comments(target, max_pages=2)
            print(f"\n评论采集: {comments['total_fetched']} 条")

            # 演示：拉取弹幕
            dm = scraper.fetch_danmaku(info["cid"])
            print(f"弹幕采集: {dm['total_fetched']} 条")
    else:
        print("用法: python bilibili_scraper.py <BV号或视频链接>")
        print("示例: python bilibili_scraper.py BV1xx411c7mD")
        print("      python bilibili_scraper.py https://www.bilibili.com/video/BV1xx411c7mD")
