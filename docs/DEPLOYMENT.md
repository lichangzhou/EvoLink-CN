# 部署指南

这份文档覆盖最容易踩坑的几件事：哪些挂载是必填的、端口和媒体服务器容器怎么错开、
以及功能不符合预期时该查哪里。

---

## 一、运行要求

| 项 | 要求 |
|---|---|
| Docker | Docker Compose v2（`docker compose`，不是 `docker-compose`） |
| 网络 | host 网络 —— EvoLink 直接绑宿主机端口 |
| Python | 以源码方式运行时需 3.12+ |
| 磁盘 | 镜像约 2 GB，另需为 `.strm` 库留出空间 |
| 媒体服务器 | Emby / Plex / Jellyfin / Playable 至少一个（可选，一个都没有也能先跑起来） |

**没有任何第三方 Python 依赖**，镜像里已经全部包含。

---

## 二、部署

### 方式 A —— Compose（推荐）

```bash
git clone https://github.com/lichangzhou/EvoLink-CN.git
cd EvoLink-CN
mkdir -p data
```

修改 `compose.yml`，两个挂载是必填的：

```yaml
volumes:
  - ./data:/app/data           # EvoLink 自己的配置、索引库与回收站
  - /vol1/1000/Link:/app/Link  # 你的 .strm 库
```

然后：

```bash
docker compose up -d
docker compose logs -f --tail 100
```

### 方式 B —— `docker run`

```bash
docker run -d --name evolink-domestic \
  --network host \
  -e TZ=Asia/Shanghai \
  -e PUID=1000 -e PGID=1001 \
  -v /path/to/evolink/data:/app/data \
  -v /path/to/your/strm:/app/Link \
  -v /path/to/clouddrive:/CloudNAS:shared \
  lichangzhou/evolink-domestic:latest
```

### 方式 C —— 源码运行

```bash
cd app
python3 server.py
```

端口由 `PORT` 环境变量决定（默认 `9191`）。

---

## 三、挂载对照

| 宿主路径 | 容器路径 | 权限 | 必填 | 用途 |
|---|---|---|---|---|
| `./data` | `/app/data` | 读写 | **是** | `config.json`、`vl.db`、`tasks.json`、`strm_trash/` |
| 你的 strm 库 | `/app/Link` | 读写 | **是** | 链接同步、归档输出、去重 |
| 你的 strm 库 | `/Link` | 只读 | 反代需要 | `302` 反代读每个 `.strm` 的第一行 |
| CloudDrive2 挂载点 | `/CloudNAS` | shared | 路径型链接需要 | 网盘本地挂载 |
| Emby `data` | `/emby_data` | 只读 | 删除联动需要 | 把已删条目反查回 strm 路径 |
| Jellyfin `data` | `/jellyfin_data` | 只读 | `302` 需要 | 条目 → strm 路径换算 |
| Plex `config` | `/plex_data` | 只读 | `302` 需要 | 同上 |

> **Emby 与 Jellyfin 要挂整个 `data` 目录，不能只挂主数据库文件。**
> 两者都是 WAL 模式，只挂主文件会读到旧快照。
>
> 同一个 strm 目录**故意挂两次**：只读挂 `/Link` 给反代读写不挂 `/app/Link` 给写入方。

---

## 四、端口

| 端口 | 归属 | 在哪里改 |
|---|---|---|
| `9191` | EvoLink 面板与 API | `PORT` 环境变量 |
| `8093` | EvoLink → Emby `302` 反代 | 面板 → 302 助手 |
| `8099` | EvoLink → Jellyfin `302` 反代 | 面板 → 302 助手 |
| `32411` | EvoLink → Plex `302` 反代 | 面板 → 302 助手 |
| `8092` | Playable 服务端 | —— |

> EvoLink 使用 `network_mode: host`，`ports:` 段**完全无效**。服务直接绑宿主机端口，
> 改端口要去面板里改。
>
> Emby / Jellyfin / Plex 原生容器已经占用了各自常用端口。EvoLink 不要占用也不要改动，
> 只有上面三个反代端口属于 EvoLink。

---

## 五、首次运行

1. 打开 `http://<你的NAS地址>:9191`
2. **设置** —— 设时区，然后添加媒体服务器：
   - Emby / Jellyfin：地址 + API Key（Emby 在 `/System/Info`，Jellyfin 在 `/Users`）
   - Plex：点「登录 Plex」，不要手贴 token
   - TMDB：API Key
3. **网盘登录** —— 用 115 App 扫二维码，cookie 存在 `data/config.json`
4. **索引媒体库** —— 选一个服务器开始索引。首次跑大库比较慢，之后是增量的
5. **分类设置** —— 选一套模板并调整
6. **归档刮削** —— 生成计划，预览之后再写入

---

## 六、验收清单

```bash
# 健康检查
curl -s http://127.0.0.1:9191/api/version
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9191/

# 三个反代都能把请求转给上游
curl -s -o /dev/null -w 'emby %{http_code} -> %{redirect_url}\n' http://127.0.0.1:8093/
curl -s -o /dev/null -w 'jellyfin %{http_code}\n' http://127.0.0.1:8099/
curl -s -o /dev/null -w 'plex %{http_code}\n' http://127.0.0.1:32411/

# 一条 strm 链接能换到 302
curl -s -o /dev/null -w '%{http_code} -> %{redirect_url}\n' http://127.0.0.1:9191/api/swap115/<path>
```

---

## 七、升级

```bash
cd /path/to/EvoLink-CN
git pull
docker compose up -d
```

数据都在 `data/` 里，升级不会动它。还是建议备份：

```bash
docker run --rm -v /path/to/evolink/data:/data -v $PWD:/backup alpine \
  tar czf /backup/evolink-data-$(date +%Y%m%d).tar.gz -C /data .
```

> 重启后 30–60 秒内面板会返回 `000`/`502`，那是健康检查还没起来，不是故障。

---

## 八、故障排查

### 重启后面板访问不了

容器起来之后才会绑端口。看 `docker compose ps` 和 `docker compose logs -f`。
容器 `healthy` 但端口仍被拒绝，说明宿主机上另有进程占着 `9191`。

### 媒体库正常但播不了

反代读不到 strm 库。检查挂载：

```bash
docker exec evolink-domestic ls -l /Link | head
docker exec evolink-domestic head -1 /Link/<某个文件>.strm
```

第一行必须是一个 `http://` 开头、指回 EvoLink 自身 `swap115` 接口的 URL。

### `plex.direct` 证书对不上

自签证书是按运行 EvoLink 那台机器的局域网 IP 生成的。换了机器部署就删掉旧证书让它重建：

```bash
docker exec evolink-domestic rm -f /app/data/plex_proxy_tls/cert.pem /app/data/plex_proxy_tls/key.pem
docker restart evolink-domestic
```

要固定地址就设 `EVOLINK_HOST_IP`。

### 元数据源超时

大部分目录类接口需要出网代理。在 **设置 → HTTP 代理** 里填宿主机的局域网地址和端口。
host 网络下填 `127.0.0.1` 会指向容器自己，必然失败。

### 扫网盘太慢

优先用**本地模式**，遍历 CloudDrive2 挂载目录，零网盘请求。只有确实需要完整远程目录树
时才用接口模式。

### 磁盘占用增长

`data/strm_trash/` 保存被删除的 strm 供恢复，在面板里「清空回收站」即可。
