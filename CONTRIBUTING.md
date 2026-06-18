# Contributing To Argus Reputation Intelligence

Thanks for helping improve Argus. This project combines a Flask backend, a Next.js/Vercel AI SDK frontend, Weibo data preparation, and a restored BettaFish multi-engine analysis chain. Please keep changes focused and easy to review.

感谢你改进 Argus。本项目包含 Flask 后端、Next.js/Vercel AI SDK 前端、微博数据准备路径，以及恢复后的 BettaFish 多引擎分析链路。请保持改动聚焦、易审阅。

## Before You Start / 开始之前

- Open an issue or discussion for large behavior changes.
- Keep product logic changes separate from documentation-only changes.
- Do not commit secrets, `.env`, raw crawl outputs, runtime databases, logs, caches, or private local paths.
- Preserve BettaFish attribution and GPLv2 license notices.

- 大的行为改动请先开 issue 或 discussion。
- 产品逻辑改动和纯文档改动尽量分开提交。
- 不要提交 secrets、`.env`、原始爬取输出、运行时数据库、日志、缓存或本地私有路径。
- 保留 BettaFish 归属说明和 GPLv2 许可证声明。

## Development Setup / 开发环境

Backend:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
```

Frontend:

```bash
cd apps/argus-saas
pnpm install
```

Copy `.env.example` to `.env` and fill in your own local provider keys. Never commit `.env`.

复制 `.env.example` 为 `.env`，填入你自己的本地 provider 配置。不要提交 `.env`。

## Pull Requests / 提交 PR

1. Create a focused branch, for example `feature/report-rendering` or `fix/weibo-data-prep`.
2. Make the smallest sufficient change.
3. Add or update tests when behavior changes.
4. Run the relevant checks and list them in the PR.
5. Confirm no raw data, secrets, or private paths were added.

1. 创建聚焦的分支，例如 `feature/report-rendering` 或 `fix/weibo-data-prep`。
2. 使用足够简单的实现，不做无关重构。
3. 行为变化时补充或更新测试。
4. 运行相关检查，并在 PR 中列出。
5. 确认没有加入原始数据、secrets 或本地私有路径。

## Useful Checks / 常用检查

Backend:

```bash
PYTHONPATH="$(pwd)/ReportEngine/utils:${PYTHONPATH:-}" TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q
```

Frontend:

```bash
cd apps/argus-saas
TMPDIR=/tmp TMP=/tmp TEMP=/tmp pnpm exec tsc --noEmit
```

Repository hygiene:

```bash
git diff --check
git status --short --branch
```

## Sample Reports / 样例报告

`sample_reports/` contains sanitized examples only. Do not add raw TikHub responses, raw comments, runtime state, or local logs. If you add a new sample, include a short README that explains the scenario and data boundary.

`sample_reports/` 只放已脱敏样例。不要加入 TikHub 原始响应、原始评论、运行时状态或本地日志。新增样例时，请包含简短 README，说明场景和数据边界。
