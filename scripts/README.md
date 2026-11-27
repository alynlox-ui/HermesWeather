# scripts/ —— 辅助脚本

## archive/expand_sites_v115.py（已归档，请勿运行）

v1.14 → v1.15 的**一次性**历史迁移脚本：批量扩充官网合集条目并把 favicon
下载/转换为 `assets/site-icons/*.png`。它**不再属于主流程**，原因：

- 依赖第三方库（`PIL`、`resvg_py`），违反本项目"零依赖标准库"的约定；
- 断言写死了 v1.15 时代的版本号（`1.14.0→1.15.0`）、动态条目数（=96）、
  静态卡片数（=18）以及旧版渲染函数的逐字文本；
- 当前版本为 `1.17.1-wanna-icon`，动态条目 159 且前端已拆分为
  `static/js/*`，直接重跑必然失败，且可能误改 index.html。

保留仅为追溯图标来源与扩充方法。若将来需要再扩充官网合集，请以当前结构
重写脚本，并把 `SITE_EXTRA_SOFTWARE` 数据（`static/js/10-sites-data.js`）
作为唯一数据源，不要恢复对 index.html 的正则改写。

## 主流程脚本（仓库根目录）

- `refresh_hot_news_snapshot.py`：抓取四源热点，原子写 `hot-news.json`，
  可选上传 GitHub（由 `WANNA_NEWS_REPO` 控制）。
  依赖的环境变量：`WANNA_EDGE_PATH`（Edge）、`WANNA_GH_PATH`（gh），
  未设置时自动探测常见安装路径与 PATH。
- `run_hot_news_silent.py`：无窗口包装器，配合任务计划定时执行，
  使用 `sys.executable`，不绑死机器路径。
- `news_crawler.py` / `wanna/`：在线服务源码，见根目录 README。
