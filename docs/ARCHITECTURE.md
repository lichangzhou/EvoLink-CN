# 架构

EvoLink 是**一个 Python 进程** + **一个 SQLite 库** + **四个 HTML 单文件页面** + **若干后台
任务**。没有消息队列，没有缓存服务，没有前端构建步骤。

```
app/
├── server.py              HTTP 服务、路由、后台调度
├── core/
│   ├── config.py          所有可调项的唯一真源
│   ├── db.py              SQLite 表结构与访问层
│   ├── matcher.py         归一化、编号提取、三级匹配
│   ├── sources/           元数据适配层（一个来源一个模块）
│   ├── emby.py            Emby 只读客户端
│   ├── jellyfin.py        Jellyfin / Playable 只读客户端
│   ├── plex_proxy.py      Plex 反向代理 + plex.direct 证书
│   ├── reverse_proxy.py   Emby / Jellyfin 反向代理
│   ├── pan115.py          115 扫码登录与目录树
│   ├── pan115_swap.py     路径型 302 签名
│   ├── pan115_downurl.py  pickcode 型直链解析
│   ├── strm_sync.py       strm 库同步引擎
│   ├── strm_classify.py   分类规则引擎
│   ├── strm_archive.py    归档计划生成与落盘
│   ├── strm_weight.py     13 维打分与洗板
│   ├── strm_lib.py        strm 库持久化模型
│   ├── strm_webhook.py    Emby 删除联动
│   ├── re0.py             资源站直连通道
│   ├── re0browser.py      CloakBrowser 管理器
│   ├── hdhub.py           兜底资源检索通道
│   ├── downurl_panel.py   115 换链面板后端
│   └── license_ops.py     免费版 / 专业版判定
├── tools/
│   ├── match.py           目标目录与库存比对
│   └── sync_emby.py       Emby 全量索引进本地库
└── web/
    ├── index.html         面板（简体中文）
    ├── index_en.html      面板（English）
    ├── docs.html          使用文档（简体中文）
    └── docs_en.html       使用文档（English）
```

---

## 数据模型

两个表承载了整个产品：

### `owned` —— 你已经有的

每个条目一行，跨四个媒体服务器合并。`src` 记录来源服务器，
`emby_id` / `tmdb_id` / `imdb_id` / `tvdb_id` 存外部标识。

```
emby_id · name · original_title · year · type · library · tmdb_id · imdb_id
tvdb_id · has_image · path · norm · av_code · updated_at · medias · src
```

### `catalog` —— 世界上存在的

每个发行候选一行，来源是各元数据适配层，比对结果回写到同一行。

```
cid · source · category · title · original_title · year · release_date · poster
tmdb_id · imdb_id · tvdb_id · rating · popularity · norm · av_code
match_status · match_emby_id · match_score · matched_at · regions · genres · lists
```

### 两张表怎么接起来

```
catalog ──match──▶ owned
   │                  │
   │  source          │  library
   ▼                  ▼
  "存在的"         "你有的"
        └──── 差额 ────┘
```

`match_status` 就是缺口比对的全部机制：每条 catalog 要么匹配上了某个 owned 条目，要么没有，
没匹配上的那些就是缺口。

### 其余表

| 表 | 用途 |
|---|---|
| `cat_count` | 按分类 / 桶 / 年份的条目数，用于给缺口列表排优先级 |
| `pan115` | 网盘目录索引缓存 |
| `meta` | 时间戳与计数（`owned_synced_at`、`owned_count` 等） |
| `strm_lib`, `strm_lib_run` | strm 库模型与运行历史 |
| `strm_webhook_log` | 删除联动审计日志 |

---

## 匹配引擎

`core/matcher.py` 负责归一化标题与提取标识；`tools/match.py` 负责套用它们。
匹配分三级，按确定性从高到低：

1. **外部 ID** —— 两边都有 TMDB / IMDb / TVDB id 即精确匹配
2. **归一化标题** —— 标题转小写、去标点、去片尾补充信息，年份按容差窗口比较
3. **目录编号** —— 对带产品编号的目录，编号归一为「前缀 + 去零数字」后精确比较。
   这一级让不同地区译名的同一作品能收敛成一个条目

每次匹配都会写入 `match_status`、`match_emby_id`、`match_score` 和 `match_how`，
所以匹配理由是可追溯的，不是黑盒。

---

## 反向代理

`302` 机制是唯一会进入播放器网络路径的部分。

```
客户端 ──▶ EvoLink 反代 :8093 ──▶ Emby API
            │
            ├─▶ 解析播放条目 → 找到它的 .strm 路径
            ├─▶ 读该 .strm 的第一行 → 拿到网盘路径
            ├─▶ 用配置的 cookie 签发直链
            └─▶ 302 Location: <已签名的直链>
```

两个细节决定它能不能真跑起来：

- **签发请求与播放请求必须使用同一个 User-Agent**，EvoLink 两边都做了固定
- **Plex 变体需要 `plex.direct` 自签证书**。Plex 客户端对 `plex.direct` 域名不校验 CA，
  自签证书就够用，但证书必须带对 SAN，所以 `plex_proxy.py` 从 `EVOLINK_HOST_IP`
  （未设置则自动探测）取宿主 IP

`core/reverse_proxy.py` 处理 Emby 与 Jellyfin；`core/plex_proxy.py` 单独处理 Plex，
因为 Plex 的 https 候选域名是它自己发布的，机制不一样。

---

## 后台任务

`server.py` 持有一个小型调度器。索引、拉目录、比对这类长任务都是**可续跑**的：
进度写进 `data/tasks.json`，容器重启后从断点继续，而不是从头再来。

> 不要开启针对网盘账号的周期性全库扫描。反复批量读取是触发网盘风控最快的方式。
> EvoLink 的本地扫描模式正是为此存在的。

---

## 配置

`core/config.py` 是唯一知道 `data/config.json` 结构的地方。写入是原子的：
先写 `.tmp` 再用 `os.replace` 移过去，容器在写入过程中被杀也不会留下半截配置。

环境变量只在首次启动时覆盖少数几项（见部署指南）。

---

## 页面

四个单文件页面，没有构建步骤、没有框架：

| 文件 | 作用 |
|---|---|
| `index.html` / `index_en.html` | 面板 —— 单页应用 |
| `docs.html` / `docs_en.html` | 使用文档 —— 新标签页打开 |

英文页是中文页的**镜像**：DOM 与 id 完全一致，只有文案不同。这是项目的硬规则，
详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---

## 扩展

### 加一个元数据来源

1. 新建 `app/core/sources/<名字>.py`，暴露一个返回 catalog 行结构的函数
2. 在 `app/core/sources/lists.py` 注册
3. 加对应的设置项、代理处理与分页逻辑

不需要动 `db.py` 和 `server.py`。

### 加一个媒体服务器

1. 在 `app/core/` 加一个只读客户端，返回库与条目
2. 在现有 `/api/sync-emby` 旁边加一个索引路由
3. 在库存合并里注册这个来源

### 加一条分类规则

规则存在 `data/config.json` 的分类段，**从上到下匹配，第一条命中即生效**。
模板支持 JSON 导入导出。
