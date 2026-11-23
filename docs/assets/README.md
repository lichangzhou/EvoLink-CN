# 截图素材

本目录所有图片都采集自**本地的脱敏实例**（`tools/shoot_clean.py`），不是线上部署。

| | 说明 |
|---|---|
| 采集对象 | 本地实例，`data/` 目录为空 |
| 真实媒体库数据 | 无（计数为 0） |
| 凭据 / Cookie | 无 |
| 设备指纹 / 激活码 | 无 |
| 授权验证服务器地址 | 无 |

## 刻意不放进这些图里的东西

- 115 Cookie、Emby / Plex / TMDB API Key
- 设备指纹（`data/.device_id`）
- 激活码与授权验证服务器地址
- 仅线上可见的界面（采集时会自动移除授权面板）

> 直接访问线上 NAS 实例截的图**包含设备指纹与授权验证地址**，
> 这正是它们被排除在仓库之外的原因。

## 文件清单

| 文件 | 界面 |
|---|---|
| `01-dashboard.png` | 仪表盘 —— 发行状态计数、任务队列 |
| `02-media-library.png` | 媒体库 —— 四个库合并浏览 |
| `03-index-libraries.png` | 索引媒体库 —— 添加与索引 Emby / Plex / Jellyfin / Playable |
| `05-start-compare.png` | 开始比对 |
| `06-cloud-drive-login.png` | 网盘登录与目录访问 |
| `07-302-assistant.png` | 302 助手 —— 反代端口与链接设置 |
| `08-archive-scrape.png` | 归档刮削 —— 源目录、输出目录与命名模板 |
| `09-weighted-dedup.png` | 权重洗板 —— 13 个打分维度 |
| `10-category-settings.png` | 分类设置 —— 目录规则引擎 |
| `11-delete-linkage.png` | 删除联动 —— Emby webhook |
| `12-settings.png` | 设置 |

## 图片授权

截图里是个人媒体库的界面，与仓库其余部分同样以 MIT 协议发布。
如果你 fork 了本项目，建议换成你自己的截图 —— 那更有说服力。
