# 参与 EvoLink 的开发

欢迎提 issue 和 PR。这份文档说明几条让项目保持「能构建、好 review、能放心跑」的规矩。

## 提 PR 之前

1. **先搜已有 issue** —— bug 和需求多半已经有人提过
2. **一次 PR 只做一件事**，review 会快很多
3. **绝不提交运行时数据**。`data/` 里放着 `config.json`、SQLite 索引库和 strm 回收站，
   它在 `.gitignore` 里，必须保持这样
4. **绝不把凭据贴进 issue、日志或提交**。Cookie、API Key、Plex token 都是秘密，
   哪怕是你自己的

## 中英页面必须同步

界面是四个文件：

| 文件 | 语言 |
|---|---|
| `app/web/index.html` | 简体中文 |
| `app/web/index_en.html` | English |
| `app/web/docs.html` | 简体中文 |
| `app/web/docs_en.html` | English |

英文页是中文页的**镜像**：DOM、id、结构完全相同，只有可见文案不同。
新增控件、字段或区块时，**两个文件必须在同一个提交里一起改**。
不要只重构其中一个页面然后把另一个丢下。

## 代码约定

- **只用 Python 标准库**。EvoLink 是零第三方依赖的单容器应用，
  新的 `pip install` 需要非常充分的理由
- `server.py` 是 HTTP 层与调度器；可复用逻辑放 `app/core/`
- 来源适配层放 `app/core/sources/`，通过 `app/core/sources/lists.py` 装载
- 跟随周边风格：4 空格缩进、函数 `snake_case`、类 `PascalCase`、公开函数写简短英文注释
- 注释写**为什么**，不写**是什么**

## 提交前自检

```bash
# 语法
python3 -m compileall -q app

# 文档 lint
npm install -g markdownlint-cli
markdownlint "**/*.md" --ignore node_modules
```

然后把容器跑起来，点一遍你改过的页面：

```bash
docker compose up -d
# 打开 http://<你的NAS地址>:9191
```

**没在浏览器里点过，就不算改完。**

## 反馈 Bug

用 **Bug report** 模板，包含：

- EvoLink 版本与构建号（`/api/version`）
- 部署方式（Compose / `docker run` / 源码）
- 期望行为与实际行为
- 相关的 `docker logs evolink-domestic --tail 100` 输出（**请先去掉凭据**）

## 提需求

用 **Feature request** 模板，描述你想解决的**问题**，而不是你已经想好的实现方式。
能端到端验证的需求，合并速度会快得多。

## 安全问题

不要在公开 issue 里报告漏洞。请先私下联系维护者，并留出合理的修复窗口。

## 许可

贡献内容以 [MIT 协议](LICENSE) 接受。提交 PR 即表示你确认有权许可这部分代码。

---

> 国内版与国际版的引擎完全一致，差异只在元数据来源模块。
> 通用性改动请同时提到两个仓库，避免长期分叉。
