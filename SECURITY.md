# Security Policy

## Reporting Security Issues

Please report security issues privately through the repository owner's preferred private channel. Do not open a public issue containing secrets, exploit details, private data, or raw provider outputs.

If this repository is public, use GitHub's private vulnerability reporting when it is enabled. Otherwise, contact the maintainer through a non-public channel.

## Secret Handling

Do not commit:

- `.env` files
- API keys or bearer tokens
- provider credentials
- raw provider responses
- raw TikHub crawl outputs
- runtime databases
- generated report dumps outside curated samples
- logs and caches
- local machine paths

If a secret is committed, revoke and rotate the affected credential immediately before continuing development. Do not rely on deleting the file from the latest commit; assume the exposed value is compromised.

## Data Handling

Sample reports in `sample_reports/` are sanitized examples. They must not include raw crawl JSON, raw comments, private datasets, database state, or local workflow logs.

When sharing debugging artifacts, strip provider keys, local paths, user identifiers that are not already public in the source material, and any raw data that is not necessary for reproduction.

## 中文说明

请不要在公开 issue 中提交 secrets、漏洞利用细节、私有数据或 provider 原始输出。

禁止提交 `.env`、API key、原始 TikHub 爬取结果、运行时数据库、日志、缓存、本地路径，以及未脱敏的报告产物。如果 secret 曾经进入仓库，请立即吊销并轮换，不要只依赖删除文件。
