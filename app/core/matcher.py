"""标题归一化 + 三级匹配。

设计依据（2026-10-18 实测抽样）：
- 电影/剧集/纪录片/演唱会：Tmdb ID 覆盖近乎 100%，优先用 ID 精确匹配。
- 动画/综艺等：标题 + 年份兜底。
国内版仅保留常规影视分类的匹配逻辑。
"""
import re
import unicodedata

# 常见繁→简 高频字（只覆盖影响匹配的字，不求完整；完整转换交给 zhconv/opencc 若可用）
_FJ = str.maketrans(
    "國與為這個來時說會對後發現點麼樣開關無線視聽聲畫專題記億萬歲東車馬長門問題"
    "學愛戀願歡樂懼驚險殺戰鬥爭奪圖書館寫讀譯藝術戲劇綜兒童觀眾熱門經典續集"
    "級別總體統計數據資訊網絡結構團隊製作發行動漫創作者導演演員配音員鏡頭",
    "国与为这个来时说会对后发现点么样开关无线视听声画专题记亿万岁东车马长门问题"
    "学爱恋愿欢乐惧惊险杀战斗争夺图书馆写读译艺术戏剧综儿童观众热门经典续集"
    "级别总体统计数据资讯网络结构团队制作发行动漫创作者导演演员配音员镜头",
)

ARTICLES = re.compile(r"^(the|a|an)\s+", re.I)
SEASON = re.compile(r"\s*(第[一二三四五六七八九十\d]+季|season\s*\d+|s\d{1,2})$", re.I)
BRACKETS = re.compile(r"[\(\[【（][^\)\]】）]{0,40}[\)\]】）]")
NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+", re.U)


def normalize(text):
    """标题归一化：繁→简、全角→半角、去标点、去冠词、去季集后缀。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    t = t.translate(_FJ)
    t = BRACKETS.sub(" ", t)
    t = SEASON.sub("", t.strip())
    t = t.lower().strip()
    t = ARTICLES.sub("", t)
    t = NON_WORD.sub("", t)
    return t


# 115/PT 的发布名专用清理：先砍掉年份、分辨率、编码等噪音再归一化，
# 否则 "沙丘2.2023.2160p.WEB-DL.mkv" 会归一成 "沙丘220232160pwebdl"，跟发行片永远对不上。
_JUNK = re.compile(
    r"(?i)[\.\s_\-\[\]]+(?:2160p|1080p|720p|480p|4k|8k|web[\-.]?dl|webrip|web|bluray|blu\-ray|"
    r"bdrip|hdtv|dvdrip|remux|x264|x265|h\.?264|h\.?265|hevc|avc|aac|ac3|eac3|dts[\-.](?:hd|ma)?|"
    r"truehd|atmos|hdr10\+?|hdr|dovi|dv|10bit|8bit|proper|repack|complete|internal)\b")
_YEAR_IN = re.compile(r"(?:^|[\.\s_\(\[])((?:19|20)\d{2})(?:[\.\s_\)\]]|$)")
_EPISODE = re.compile(r"(?i)[\.\s_\-]*s\d{1,2}(?:e\d{1,3})?")


def media_norm(name):
    """把网盘/PT 的发布名归一成可用于比对的标题。"""
    if not name:
        return ""
    t = str(name)
    t = re.sub(r"\.[A-Za-z0-9]{2,4}$", " ", t)          # 去扩展名
    t = BRACKETS.sub(" ", t)                             # 去 [xxx] (xxx)
    m = _YEAR_IN.search(t)
    if m:
        t = t[:m.start()]
    t = _JUNK.sub(" ", t)
    t = _EPISODE.sub(" ", t)
    return normalize(t)


def year_of(item):
    y = item.get("year") or item.get("ProductionYear")
    if y:
        try:
            return int(str(y)[:4])
        except ValueError:
            pass
    d = item.get("premiere") or item.get("PremiereDate") or item.get("release_date") or ""
    m = re.match(r"(\d{4})", str(d))
    return int(m.group(1)) if m else None


def score_pair(cat, own):
    """给一条目标 vs 一条库存打分。0 表示不可能，>=1 表示确定。"""
    score = 0.0
    ct, ot = cat.get("tmdb_id"), own.get("tmdb_id")
    if ct and ot and str(ct) == str(ot):
        return 100.0
    ci, oi = cat.get("imdb_id"), own.get("imdb_id")
    if ci and oi and str(ci).lower() == str(oi).lower():
        return 100.0
    cv, ov = cat.get("tvdb_id"), own.get("tvdb_id")
    if cv and ov and str(cv) == str(ov):
        return 100.0

    cy, oy = year_of(cat), year_of(own)
    yr_ok = bool(cy and oy and abs(cy - oy) <= 1)
    if cy and oy and abs(cy - oy) > 2:
        return 0.0

    cn, on = cat.get("norm") or normalize(cat.get("title")), own.get("norm") or normalize(own.get("name"))
    co = normalize(cat.get("original_title"))
    oo = normalize(own.get("original_title"))

    if cn and on and cn == on:
        score = 70.0
        if not (cy and oy):
            # 双方都没有年份（短剧等常见）→ 无矛盾信息，视为确定
            score = 88.0 if (not cy and not oy) else 80.0
    elif cn and on and (cn in on or on in cn) and min(len(cn), len(on)) >= 4:
        score = 55.0
    elif co and oo and co == oo:
        score = 65.0
    elif co and on and co == on:
        score = 60.0
    elif cn and oo and cn == oo:
        score = 60.0

    if score and yr_ok:
        score += 25
    elif score and cy and oy:
        score -= 15
    return score


def classify(cat, candidates):
    """三级判定：owned(确定) / likely(疑似) / missing(缺) / unmatchable(无法比对)。

    阈值说明：85 分对应"标题完全相等 + 双方均无年份"，这类应算确定；
    50~85 是包含关系或单边年份，交给人工确认。
    """
    best, best_id = 0.0, None
    for own in candidates:
        s = score_pair(cat, own)
        if s > best:
            best, best_id = s, own.get("emby_id")
    if best >= 85:
        return "owned", best_id, best
    if best >= 50:
        return "likely", best_id, best
    return "missing", None, best or None


def is_unmatchable(item):
    """名字归一化后为空（如 "[FemdomEmpire.com] -"），无法参与标题比对。"""
    return not (item.get("norm") or normalize(item.get("title") or item.get("name")))
