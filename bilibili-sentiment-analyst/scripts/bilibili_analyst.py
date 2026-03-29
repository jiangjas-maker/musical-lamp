#!/usr/bin/env python3
"""
Bilibili Analyst - 评论与弹幕数据的多维度分析引擎

功能:
    - LDA主题聚类
    - 弹幕密度峰值分析（B站独有）
    - 三连互动分析（B站独有）
    - 评论趋势分析
    - 关键词声量份额(Share of Voice)统计
    - 代表性评论/弹幕提取

用法:
    from bilibili_analyst import BilibiliAnalyst
    analyst = BilibiliAnalyst()
"""

import re
import os
import numpy as np
import pandas as pd
import jieba
from pathlib import Path
from collections import Counter
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation

try:
    import nltk
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", quiet=True)

# 停用词路径
SKILL_DIR = Path(__file__).resolve().parent.parent
STOPWORDS_DIR = SKILL_DIR / "assets" / "stopwords_extended"


class BilibiliAnalyst:
    """B站评论与弹幕多维度分析引擎。"""

    def __init__(self):
        self._stopwords_cache = {}

    def _load_stopwords(self, lang="zh"):
        """加载停用词表。"""
        if lang in self._stopwords_cache:
            return self._stopwords_cache[lang]

        stopwords = set()

        custom_file = STOPWORDS_DIR / f"stopwords_{lang}.txt"
        if custom_file.exists():
            with open(custom_file, "r", encoding="utf-8") as f:
                stopwords.update(line.strip() for line in f if line.strip())

        if lang == "en":
            try:
                from nltk.corpus import stopwords as nltk_sw
                stopwords.update(nltk_sw.words("english"))
            except Exception:
                pass

        # B站特有过滤词
        stopwords.update([
            "br", "nbsp", "http", "https", "www", "com",
            "bilibili", "哔哩哔哩", "视频", "up", "up主",
        ])

        self._stopwords_cache[lang] = stopwords
        return stopwords

    def _tokenize(self, text, lang="zh"):
        """对文本进行jieba分词和清洗。"""
        text = str(text).lower().strip()
        # 移除URL
        text = re.sub(r"http\S+", "", text)
        # 移除B站特有格式
        text = re.sub(r"\[.*?\]", "", text)       # [表情]
        text = re.sub(r"@[\w]+", "", text)          # @用户
        text = re.sub(r"#[\w]+#", "", text)         # #话题#
        # 移除特殊字符（保留中日韩和字母数字）
        text = re.sub(
            r"[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]",
            " ", text
        )

        stopwords = self._load_stopwords(lang)

        if lang == "zh":
            tokens = jieba.cut(text)
            tokens = [t for t in tokens if len(t) > 1 and t not in stopwords]
        else:
            tokens = text.split()
            tokens = [t for t in tokens if len(t) > 2 and t not in stopwords]

        return " ".join(tokens)

    def load_data(self, comments_data, danmaku_data=None):
        """从scraper返回的原始数据加载为DataFrame。

        Args:
            comments_data: fetch_comments() 的返回值（或已转换的DataFrame）
            danmaku_data: fetch_danmaku() 的返回值（或已转换的DataFrame）

        Returns:
            tuple: (df_comments, df_danmaku)
        """
        # 处理评论
        if isinstance(comments_data, pd.DataFrame):
            df_comments = comments_data
        elif isinstance(comments_data, dict) and "comments" in comments_data:
            from bilibili_scraper import BilibiliScraper
            scraper = BilibiliScraper.__new__(BilibiliScraper)
            df_comments = scraper.comments_to_dataframe(comments_data)
        else:
            df_comments = pd.DataFrame()

        # 处理弹幕
        if danmaku_data is None:
            df_danmaku = pd.DataFrame()
        elif isinstance(danmaku_data, pd.DataFrame):
            df_danmaku = danmaku_data
        elif isinstance(danmaku_data, dict) and "danmakus" in danmaku_data:
            from bilibili_scraper import BilibiliScraper
            scraper = BilibiliScraper.__new__(BilibiliScraper)
            df_danmaku = scraper.danmaku_to_dataframe(danmaku_data)
        else:
            df_danmaku = pd.DataFrame()

        return df_comments, df_danmaku

    # ──────────────────────────────────────────────────────
    #  LDA 主题聚类
    # ──────────────────────────────────────────────────────

    def run_lda(self, df_comments, language="zh", n_topics="auto",
                max_features=2000, topic_range=None):
        """运行LDA主题模型（基于评论文本）。

        Args:
            df_comments: 评论DataFrame（需含"message"列）
            language: 分析语言，默认"zh"
            n_topics: 主题数，"auto"自动优化，或指定int
            max_features: 最大特征词数量
            topic_range: 自动优化时的候选主题数列表

        Returns:
            dict: {
                "lda_model": LDA模型对象,
                "vectorizer": CountVectorizer对象,
                "dtm": 文档-词矩阵,
                "n_topics": int,
                "topics": [{id, keywords, weight}, ...],
                "language": str,
                "df_with_topics": 带主题标注的评论DataFrame,
            }
        """
        if df_comments.empty or "message" not in df_comments.columns:
            print("[LDA] 无评论数据")
            return None

        df = df_comments.copy()
        print(f"[LDA] 分析语言: {language}, 评论数: {len(df)}")

        # 分词
        print("[LDA] 分词中...")
        df["tokens"] = df["message"].apply(
            lambda x: self._tokenize(x, language)
        )

        # 过滤空文本
        valid_mask = df["tokens"].str.strip().str.len() > 0
        if valid_mask.sum() < 10:
            print("[LDA] 有效文本不足，无法进行主题分析")
            return None

        # 构建词频矩阵
        vectorizer = CountVectorizer(
            max_df=0.85,
            min_df=max(3, valid_mask.sum() // 200),
            max_features=max_features,
        )
        dtm = vectorizer.fit_transform(df.loc[valid_mask, "tokens"])

        # 确定主题数
        if n_topics == "auto":
            topic_range = topic_range or [3, 5, 7, 10]
            lda_model, best_n = self._find_optimal_topics(dtm, topic_range)
        else:
            best_n = n_topics
            lda_model = LatentDirichletAllocation(
                n_components=best_n, random_state=42, n_jobs=-1
            )
            lda_model.fit(dtm)

        # 提取主题关键词
        feature_names = vectorizer.get_feature_names_out()
        topics = []
        for idx, topic_vec in enumerate(lda_model.components_):
            top_indices = topic_vec.argsort()[:-11:-1]
            keywords = [feature_names[i] for i in top_indices]
            weight = topic_vec.sum() / lda_model.components_.sum()
            topics.append({
                "id": idx,
                "keywords": keywords,
                "weight": round(weight, 4),
            })

        topics.sort(key=lambda t: t["weight"], reverse=True)

        # 为每条评论标注主题
        doc_topic_dist = lda_model.transform(dtm)
        df.loc[valid_mask, "topic_id"] = doc_topic_dist.argmax(axis=1)
        df.loc[valid_mask, "topic_confidence"] = doc_topic_dist.max(axis=1)
        df["topic_id"] = df["topic_id"].fillna(-1).astype(int)
        df["topic_confidence"] = df["topic_confidence"].fillna(0)

        print(f"[LDA] 完成，共 {best_n} 个主题")
        return {
            "lda_model": lda_model,
            "vectorizer": vectorizer,
            "dtm": dtm,
            "n_topics": best_n,
            "topics": topics,
            "language": language,
            "df_with_topics": df,
        }

    def _find_optimal_topics(self, dtm, topic_range):
        """通过困惑度选择最优主题数。"""
        print(f"[LDA] 优化主题数，候选: {topic_range}")
        best_lda = None
        best_perplexity = float("inf")
        best_n = topic_range[0]

        for n in topic_range:
            lda = LatentDirichletAllocation(
                n_components=n, random_state=42, n_jobs=-1
            )
            lda.fit(dtm)
            perplexity = lda.perplexity(dtm)
            print(f"  n={n}, Perplexity={perplexity:.2f}")
            if perplexity < best_perplexity:
                best_perplexity = perplexity
                best_lda = lda
                best_n = n

        print(f"[LDA] 最优主题数: {best_n}")
        return best_lda, best_n

    # ──────────────────────────────────────────────────────
    #  弹幕密度峰值分析（B站独有）
    # ──────────────────────────────────────────────────────

    def analyze_danmaku_density(self, df_danmaku, video_duration,
                                window_seconds=30, top_n=5):
        """分析弹幕时间线密度，找出情绪爆发的峰值时刻。

        这是B站独有的分析能力——通过弹幕出现时间，定位视频中
        引发最强观众反应的具体画面。

        Args:
            df_danmaku: 弹幕DataFrame（需含"progress"列，单位秒）
            video_duration: 视频总时长（秒）
            window_seconds: 统计窗口大小（秒）
            top_n: 返回前N个密度峰值

        Returns:
            dict: {
                "timeline": [{start, end, count, density}, ...],
                "peaks": [{
                    start, end, count, density,
                    top_texts, sample_texts
                }, ...],
                "total_danmaku": int,
                "avg_density": float,
                "insight": str,
            }
        """
        if df_danmaku.empty or "progress" not in df_danmaku.columns:
            return {
                "timeline": [], "peaks": [],
                "total_danmaku": 0, "avg_density": 0,
                "insight": "无弹幕数据"
            }

        total = len(df_danmaku)
        n_windows = max(1, int(video_duration / window_seconds))
        avg_density = total / n_windows

        # 按时间窗口统计弹幕密度
        timeline = []
        for i in range(n_windows):
            start = i * window_seconds
            end = min((i + 1) * window_seconds, video_duration)
            mask = (df_danmaku["progress"] >= start) & (df_danmaku["progress"] < end)
            window_dm = df_danmaku[mask]
            count = len(window_dm)

            segment = {
                "start": start,
                "end": end,
                "start_fmt": f"{int(start//60):02d}:{int(start%60):02d}",
                "end_fmt": f"{int(end//60):02d}:{int(end%60):02d}",
                "count": count,
                "density": round(count / window_seconds, 2),
            }

            # 该窗口内的弹幕文本
            if count > 0:
                texts = window_dm["text"].tolist()
                # 高频弹幕
                text_counts = Counter(texts)
                segment["top_texts"] = [
                    {"text": t, "count": c}
                    for t, c in text_counts.most_common(5)
                ]
                segment["sample_texts"] = texts[:10]
            else:
                segment["top_texts"] = []
                segment["sample_texts"] = []

            timeline.append(segment)

        # 找出密度峰值
        timeline_sorted = sorted(timeline, key=lambda x: x["count"], reverse=True)
        peaks = timeline_sorted[:top_n]

        # 生成洞察
        insight = ""
        if peaks and peaks[0]["count"] > 0:
            top = peaks[0]
            ratio = top["count"] / avg_density if avg_density > 0 else 0
            insight = (
                f"弹幕密度最高峰出现在 {top['start_fmt']}-{top['end_fmt']}，"
                f"共{top['count']}条弹幕（是平均密度的{ratio:.1f}倍）"
            )
            if top["top_texts"]:
                top_text = top["top_texts"][0]["text"]
                insight += f"，最高频弹幕为「{top_text}」"

        return {
            "timeline": timeline,
            "peaks": peaks,
            "total_danmaku": total,
            "avg_density": round(avg_density, 2),
            "insight": insight,
        }

    # ──────────────────────────────────────────────────────
    #  三连互动分析（B站独有）
    # ──────────────────────────────────────────────────────

    def analyze_engagement(self, video_info):
        """分析视频三连互动数据，评估互动质量。

        B站独有的三连体系（点赞/投币/收藏）可以区分不同层级的
        用户认可度，比单纯的Like/Dislike信息量更大。

        Args:
            video_info: get_video_info()的返回值

        Returns:
            dict: {
                "raw": {view, like, coin, favorite, share, danmaku, reply},
                "ratios": {
                    "like_rate": 点赞率 (like/view),
                    "coin_rate": 投币率 (coin/view),
                    "fav_rate": 收藏率 (favorite/view),
                    "share_rate": 分享率 (share/view),
                    "danmaku_rate": 弹幕率 (danmaku/view),
                    "reply_rate": 评论率 (reply/view),
                    "coin_like_ratio": 投币/点赞比（越高=越有质量）,
                    "fav_like_ratio": 收藏/点赞比（越高=越有长期价值）,
                },
                "quality_assessment": str,
                "insight": str,
            }
        """
        if not video_info:
            return {"raw": {}, "ratios": {}, "quality_assessment": "", "insight": ""}

        view = max(video_info.get("view", 1), 1)
        like = video_info.get("like", 0)
        coin = video_info.get("coin", 0)
        fav = video_info.get("favorite", 0)
        share = video_info.get("share", 0)
        danmaku = video_info.get("danmaku", 0)
        reply = video_info.get("reply", 0)

        ratios = {
            "like_rate": round(like / view, 4),
            "coin_rate": round(coin / view, 4),
            "fav_rate": round(fav / view, 4),
            "share_rate": round(share / view, 4),
            "danmaku_rate": round(danmaku / view, 4),
            "reply_rate": round(reply / view, 4),
            "coin_like_ratio": round(coin / max(like, 1), 4),
            "fav_like_ratio": round(fav / max(like, 1), 4),
        }

        # 互动质量判定
        # 基准参考值（游戏区大致基准，非绝对标准）
        quality = []
        if ratios["like_rate"] > 0.04:
            quality.append("点赞率优秀(>4%)")
        elif ratios["like_rate"] < 0.01:
            quality.append("点赞率偏低(<1%)")

        if ratios["coin_like_ratio"] > 0.4:
            quality.append("投币/点赞比高——观众认可度强，愿意付出B币")
        elif ratios["coin_like_ratio"] < 0.1:
            quality.append("投币/点赞比低——'路过点赞'居多，深度认可不足")

        if ratios["fav_like_ratio"] > 0.5:
            quality.append("收藏/点赞比高——内容被认为有长期回看价值")
        elif ratios["fav_like_ratio"] < 0.15:
            quality.append("收藏/点赞比低——一次性消费内容，回看价值低")

        assessment = "；".join(quality) if quality else "互动数据处于正常范围"

        # 生成洞察
        insight = (
            f"播放{view:,}，点赞率{ratios['like_rate']:.1%}，"
            f"投币/点赞比{ratios['coin_like_ratio']:.0%}，"
            f"收藏/点赞比{ratios['fav_like_ratio']:.0%}"
        )

        return {
            "raw": {
                "view": view, "like": like, "coin": coin,
                "favorite": fav, "share": share,
                "danmaku": danmaku, "reply": reply,
            },
            "ratios": ratios,
            "quality_assessment": assessment,
            "insight": insight,
        }

    # ──────────────────────────────────────────────────────
    #  评论趋势
    # ──────────────────────────────────────────────────────

    def comment_trend(self, df_comments, time_col="ctime", freq="D"):
        """按时间段统计评论量趋势。

        Args:
            df_comments: 评论DataFrame
            time_col: 时间列名
            freq: "D"=日, "W"=周, "H"=时

        Returns:
            pd.DataFrame: period, total_comments, avg_likes
        """
        if df_comments.empty or time_col not in df_comments.columns:
            return pd.DataFrame()

        df = df_comments.copy()
        df["period"] = df[time_col].dt.to_period(freq)

        trend = df.groupby("period").agg(
            total_comments=("message", "count"),
            avg_likes=("like", "mean"),
        ).reset_index()

        trend["avg_likes"] = trend["avg_likes"].round(1)
        trend["period"] = trend["period"].astype(str)
        return trend

    # ──────────────────────────────────────────────────────
    #  关键词声量份额
    # ──────────────────────────────────────────────────────

    def share_of_voice(self, df_comments, df_danmaku=None, keywords=None):
        """统计关键词在评论和弹幕中的声量份额。

        Args:
            df_comments: 评论DataFrame
            df_danmaku: 弹幕DataFrame（可选）
            keywords: {主题名: [关键词列表]}

        Returns:
            pd.DataFrame: topic, mention_comments, mention_danmaku,
                          total_mentions, mention_rate
        """
        if keywords is None:
            return pd.DataFrame()

        total_comments = len(df_comments) if not df_comments.empty else 0
        total_danmaku = len(df_danmaku) if df_danmaku is not None and not df_danmaku.empty else 0
        total_docs = total_comments + total_danmaku

        rows = []
        for topic_name, kw_list in keywords.items():
            pattern = "|".join(re.escape(kw) for kw in kw_list)

            # 评论中搜索
            c_matches = 0
            if not df_comments.empty and "message" in df_comments.columns:
                c_matches = df_comments["message"].str.contains(
                    pattern, case=False, na=False
                ).sum()

            # 弹幕中搜索
            d_matches = 0
            if df_danmaku is not None and not df_danmaku.empty and "text" in df_danmaku.columns:
                d_matches = df_danmaku["text"].str.contains(
                    pattern, case=False, na=False
                ).sum()

            total = c_matches + d_matches
            rows.append({
                "topic": topic_name,
                "keywords": ", ".join(kw_list),
                "mention_comments": int(c_matches),
                "mention_danmaku": int(d_matches),
                "total_mentions": int(total),
                "mention_rate": round(total / total_docs, 4) if total_docs > 0 else 0,
            })

        result = pd.DataFrame(rows)
        result.sort_values("total_mentions", ascending=False, inplace=True)
        return result.reset_index(drop=True)

    # ──────────────────────────────────────────────────────
    #  代表性评论提取
    # ──────────────────────────────────────────────────────

    def get_representative_comments(self, df_comments, lda_result, n=3,
                                    weight_by_likes=True):
        """提取每个主题最具代表性的评论。

        Args:
            df_comments: 评论DataFrame
            lda_result: run_lda()的返回值
            n: 每个主题提取数量
            weight_by_likes: 是否考虑点赞数加权

        Returns:
            dict: {topic_id: [{message, like, rcount, uname, ctime}, ...]}
        """
        if lda_result is None:
            return {}

        lda_model = lda_result["lda_model"]
        dtm = lda_result["dtm"]
        topic_df = lda_result["df_with_topics"]

        doc_topic_dist = lda_model.transform(dtm)
        valid_mask = topic_df["topic_id"] >= 0
        result = {}

        for topic in lda_result["topics"]:
            tid = topic["id"]
            scores = doc_topic_dist[:, tid].copy()

            if weight_by_likes and "like" in topic_df.columns:
                valid_likes = topic_df.loc[valid_mask, "like"].values.astype(float)
                like_weights = np.log1p(np.maximum(valid_likes, 0))
                scores = scores * (1 + like_weights * 0.3)

            top_indices = scores.argsort()[:-n - 1:-1]
            comments = []
            valid_indices = topic_df.index[valid_mask]
            for idx in top_indices:
                if idx >= len(valid_indices):
                    continue
                row = topic_df.iloc[valid_indices[idx]]
                comments.append({
                    "message": str(row.get("message", ""))[:500],
                    "like": int(row.get("like", 0)),
                    "rcount": int(row.get("rcount", 0)),
                    "uname": str(row.get("uname", "")),
                    "up_reply": bool(row.get("up_reply", False)),
                })
            result[tid] = comments

        return result

    # ──────────────────────────────────────────────────────
    #  高赞评论 / 热门弹幕
    # ──────────────────────────────────────────────────────

    def get_top_comments(self, df_comments, n=10):
        """提取最高赞评论。"""
        if df_comments.empty or "like" not in df_comments.columns:
            return []
        cols = ["message", "like", "rcount", "uname", "up_reply", "ctime"]
        available = [c for c in cols if c in df_comments.columns]
        return df_comments.nlargest(n, "like")[available].to_dict("records")

    def get_top_danmaku(self, df_danmaku, n=20):
        """提取最高频弹幕。"""
        if df_danmaku.empty or "text" not in df_danmaku.columns:
            return []
        counts = df_danmaku["text"].value_counts().head(n)
        return [{"text": t, "count": int(c)} for t, c in counts.items()]

    # ──────────────────────────────────────────────────────
    #  导出
    # ──────────────────────────────────────────────────────

    def export_to_excel(self, df_comments, df_danmaku, filepath,
                        lda_result=None, video_info=None):
        """导出分析结果到Excel（多Sheet）。

        Args:
            df_comments: 评论DataFrame
            df_danmaku: 弹幕DataFrame
            filepath: 输出路径
            lda_result: LDA结果（可选）
            video_info: 视频信息（可选）
        """
        export_comments = df_comments.copy()
        export_danmaku = df_danmaku.copy() if not df_danmaku.empty else pd.DataFrame()

        # 合并LDA主题标注
        if lda_result and "df_with_topics" in lda_result:
            topic_df = lda_result["df_with_topics"]
            if "topic_id" in topic_df.columns:
                export_comments["topic_id"] = topic_df["topic_id"].values
                export_comments["topic_confidence"] = topic_df["topic_confidence"].values

        # 清理不适合Excel的列
        for col in ["tokens"]:
            if col in export_comments.columns:
                export_comments.drop(columns=[col], inplace=True)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # 视频信息Sheet
            if video_info:
                info_df = pd.DataFrame([video_info])
                info_df.to_excel(writer, sheet_name="视频信息", index=False)

            export_comments.to_excel(writer, sheet_name="评论", index=False)

            if not export_danmaku.empty:
                export_danmaku.to_excel(writer, sheet_name="弹幕", index=False)

        total = len(export_comments) + len(export_danmaku)
        print(f"[Export] 已保存到 {filepath} "
              f"({len(export_comments)} 评论 + {len(export_danmaku)} 弹幕)")
