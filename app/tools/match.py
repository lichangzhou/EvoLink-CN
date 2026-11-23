"""把目标目录与 Emby 库存做匹配，写回 catalog 的 match_* 字段。

比对分成两条轨，按「确定性」从高到低走：
1. ID 轨       —— tmdb / imdb / tvdb 精确相等
2. 标题轨      —— 电影/剧集等按归一化标题 + 年份
国内版仅保留常规影视分类的匹配逻辑。

比对范围（1022 修正）：默认**严格按分类勾选的库**——「剧集」只跟剧集各桶勾选的库比，
没勾的库一律不参与。设置里打开「跨库兜底」(match_all_libs) 才回到旧行为：片子放在任何库都算「已在库」。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, db, matcher


def _build_index(rows, allow=None):
    """把 owned 行建成一套索引。

    allow        —— 允许参与的文件所属库集合；None 表示不限（跨库兜底）
    """
    by_tmdb, by_imdb, by_tvdb, by_norm = {}, {}, {}, {}
    for d in rows:
        lib = d.get("library") or ""
        if allow is not None and lib not in allow:
            continue
        if d.get("tmdb_id"):
            by_tmdb.setdefault(str(d["tmdb_id"]), d)
        if d.get("imdb_id"):
            by_imdb.setdefault(str(d["imdb_id"]).lower(), d)
        if d.get("tvdb_id"):
            by_tvdb.setdefault(str(d["tvdb_id"]), d)
        if d.get("norm"):
            by_norm.setdefault(d["norm"], []).append(d)
    return {"tmdb": by_tmdb, "imdb": by_imdb, "tvdb": by_tvdb, "norm": by_norm}


def load_owned_index(c, only_libs=None):
    """按分类建索引：每个分类只收「该分类勾选的库」里的本地条目。

    严格模式（默认）下，每个分类的索引里只有该分类桶勾选的库，
    所以没勾的库（短剧、演唱会……）永远不会被比对到。
    打开「跨库兜底」后共用一套全库索引，恢复旧行为。

    only_libs：用户在「比对」面板里勾选的 Emby 库。非空时每个分类的索引
    再与该集合取交集 —— 只勾「欧美电影」就只拿它的库存去比电影清单。
    """
    cfg = config.load()
    cross = bool(cfg.get("match_all_libs", False))
    rows = [dict(r) for r in c.execute("SELECT * FROM owned")]
    only = {l for l in (only_libs or []) if l}

    if cross and not only:
        all_idx = _build_index(rows, None)
        return {cat: all_idx for cat in db.CAT_BUCKETS}

    per = {}
    for cat in db.CAT_BUCKETS:
        allow = set(db.libs_for_cat(cat))
        if only:
            allow &= only
            if not allow:
                per[cat] = _build_index([], set())
                continue
        per[cat] = _build_index(rows, allow)
    return per


def full_index(c):
    """兜底：catalog 里出现未知分类时用的全库索引。"""
    rows = [dict(r) for r in c.execute("SELECT * FROM owned")]
    return _build_index(rows, None)


def libs_to_cats(libs):
    """勾选的 Emby 库 → 要比对的 catalog 分类集合。"""
    from tools import sync_emby          # 延迟导入：避免与 core 包循环
    cats = set()
    for l in (libs or []):
        if not l:
            continue
        cats.add(sync_emby.category_of(l))
    return cats


def match_all(verbose=True, only_cat=None, rescan=True, only_libs=None, progress=None):
    """重跑比对。rescan=True 时连「已入库」的也重算（换了匹配算法必须重算）。

    only_libs：只比对勾选的 Emby 库（并集语义一次算清，避免多库互相覆盖）。
        catalog 取这些库所属分类的并集，owned 索引只收这些库的条目。
    progress：可选回调 progress(done, total, cur_cat)，每 500 行 + 末行触发，
        供「比对」面板画每个库的进度条。
    """
    t0 = time.time()
    c = db.init()
    only = [l for l in (only_libs or []) if l]
    idxmap = load_owned_index(c, only)
    if only_cat:
        rows = c.execute("SELECT * FROM catalog WHERE category=?", (only_cat,)).fetchall()
    elif only:
        cats = sorted(libs_to_cats(only))
        qs = ",".join("?" * len(cats))
        rows = c.execute(f"SELECT * FROM catalog WHERE category IN ({qs})", cats).fetchall()
    elif rescan:
        rows = c.execute("SELECT * FROM catalog").fetchall()
    else:
        rows = c.execute("SELECT * FROM catalog WHERE match_status IS NULL OR match_status='missing'").fetchall()
        if not rows:
            rows = c.execute("SELECT * FROM catalog").fetchall()
    counts = {"owned": 0, "likely": 0, "missing": 0, "unmatchable": 0}
    how = {}
    upd = []
    n_total = len(rows)
    for i, r in enumerate(rows):
        d = dict(r)
        cat = (d.get("category") or "").strip()
        if cat in idxmap:
            idx = idxmap[cat]
        else:
            idx = idxmap.get("*")
            if idx is None:
                idx = idxmap["*"] = full_index(c)
        status, eid, score, why = "missing", None, 0.0, ""

        # 1) ID 精确轨
        if status == "missing":
            for key, field in (("tmdb", "tmdb_id"), ("imdb", "imdb_id"), ("tvdb", "tvdb_id")):
                v = d.get(field)
                if not v:
                    continue
                v = str(v).lower() if key == "imdb" else str(v)
                hit = idx[key].get(v)
                if hit:
                    status, eid, score, why = "owned", hit["emby_id"], 100.0, key.upper()
                    break

        # 2) 标题轨（同 norm 下再比年份）
        if status == "missing":
            if matcher.is_unmatchable(d):
                status, eid, score = "unmatchable", None, 0.0
            else:
                cands = idx["norm"].get(d["norm"] or "", [])
                st, e_id, sc = matcher.classify(d, cands)
                status, eid, score = st, e_id, sc or 0.0
                if st in ("owned", "likely"):
                    why = "标题"

        counts[status] += 1
        if why:
            # 「同厂牌同标题（本地 JUR135）」这类按前缀归并，否则依据统计会被几十条明细刷屏
            k = why.split("（")[0]
            how[k] = how.get(k, 0) + 1
        upd.append((status, eid, score, why, db.now(), d["cid"]))
        if progress is not None and (i % 500 == 0 or i == n_total - 1):
            try:
                progress(i + 1, n_total, cat)
            except Exception:
                pass

    c.executemany("UPDATE catalog SET match_status=?, match_emby_id=?, match_score=?, "
                  "match_how=?, matched_at=? WHERE cid=?", upd)
    c.commit()
    # 大量 UPDATE 之后把 WAL 压回主库：否则 -wal 涨到近百 MB，
    # 之后每个读查询都要先合并 WAL，stats / 仪表盘会被拖到十几秒。
    try:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    if verbose:
        total = sum(counts.values())
        print(f"匹配完成 {total} 条，耗时 {time.time()-t0:.1f}s")
        for k, v in counts.items():
            print(f"  {k:8s} {v:6d}  ({v/max(total,1)*100:.1f}%)")
        if how:
            print("  依据：" + "　".join(f"{k} {v}" for k, v in sorted(how.items(), key=lambda x: -x[1])))
    if not only_cat:
        db.set_meta("matched_at", db.now())
    return counts


if __name__ == "__main__":
    match_all()
