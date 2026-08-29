# 全球安防咨询情报自动化系统（security-intel-agent）

每个**工作日清晨**自动从全球公开信源采集安防情报，自动分类、分级、去重，用 LLM 翻译成中文并生成「今日态势研判」，最后以管理层可读的一站式简报推送到指定渠道。

> 当前重点：**物理安防**（部门主线）。系统已聚焦物理安防领域，按行业子类（物理安防/安防硬件/周界防护/AI安防/智能安防/安防峰会/行业动态/机器人无人机）分组，自动打上「地域 / 企业 / 产品 / 事件」四维标签，每条情报均附自包含中文总结。**每日精准精选 5-6 条**生成「海报卡片风」PDF 海报，参考你提供的样板。

## 特性

- **物理安防聚焦**：自动过滤纯网络安全（cyber）、合规监管（compliance）、公共卫生（health）类，聚焦地缘冲突 / 恐怖袭击 / 骚乱罢工 / 自然灾害 / 人身与资产安全五大物理安防领域。
- **四维标签**：每条情报自动识别「地域标签 / 企业标签（安防重点企业及产业链）/ 产品标签（视频监控、门禁、报警等）/ 事件标签（政策、技术、市场、并购、展会等）」，在简报与推送中展示。
- **安防行业信源**：接入安防垂直媒体（SecurityWorld / Security Magazine / IFSEC / SSI / SDM / Security Today 等，覆盖美/英/澳/印/拉美）、行业协会与标准组织（SIA / ASIS / ONVIF / BSIA 等）、中文安防门户与全球展会（ISC West / GSX / IFSEC / Intersec / 安博会 CPSE 等）。
- **多信源自动容错**：GDELT、ReliefWeb、USGS 地震、CISA 已知被利用漏洞、NVD、通用 RSS、外交部提醒。单个信源失败不影响整体。
- **LLM 中文研判 + 自包含总结**：走任意 OpenAI 兼容接口（DeepSeek / Kimi / Qwen / 中转），**换供应商只改 `.env`，代码零改动**；未配 key 或调用失败时自动回退规则模板生成自包含总结，系统永不因 LLM 停摆。
- **三渠道推送**：企业微信 / 钉钉 / 飞书群机器人 + 邮件 + 本地文件存档，未配置的渠道自动跳过。
- **跨天去重**：N 天内不重复上报同一事件。

## 数据源与 API key

| 采集器 | 数据源 | 需要 key？ |
| --- | --- | --- |
| `gdelt.py` | GDELT 2.0 全球新闻事件 | 否 |
| `reliefweb.py` | ReliefWeb 灾害/人道主义 | 否 |
| `usgs.py` | USGS 地震（>= M4.5） | 否 |
| `cisa.py` | CISA 已知被利用漏洞 KEV | 否 |
| `nvd.py` | NVD 近期 CVE（限流） | 可选 |
| `rss.py` | 任意 RSS/Atom 信源 | 否 |
| `mfa.py` | 外交部领事提醒（易碎） | 需自备 RSS |

**只有 LLM 需要 key**，且走 OpenAI 兼容接口。

## 安装

```bash
pip install -r requirements.txt
cp .env.example .env   # Windows 用 copy .env.example .env
```

## 使用

```bash
# 立即运行一次，采集 -> 分类分级 -> 摘要 -> 出报告 -> 推送
python -m app.main

# 进入工作日定时模式（周一~周五 SCHEDULE_TIME 运行）
python -m app.main --schedule
```

运行后在 `output/` 生成：

- `daily_brief_YYYY-MM-DD.md` —— Markdown 简报（推送正文用）
- `daily_brief_YYYY-MM-DD.html` —— HTML 版（邮件/存档）
- `daily_brief_YYYY-MM-DD.json` —— 结构化归档
- `history.json` —— 去重历史（自动维护）

## 配置（.env）

复制 `.env.example` 为 `.env` 后按需修改，关键项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ENABLE_LLM` | `1` | 是否启用 LLM（0=纯模板研判） |
| `LLM_API_BASE` | `https://api.deepseek.com` | OpenAI 兼容 base_url |
| `LLM_API_KEY` | 空 | LLM key（留空自动回退模板） |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `ENABLE_GDELT/RELIEFWEB/USGS/CISA/NVD/MFA` | `1/1/1/1/0/0` | 各信源开关 |
| `RSS_FEEDS` | 15 个默认源 | `URL\|领域`，逗号分隔，可自行增删（含安防行业信源） |
| `TOP_N` | `8` | 每日最终上报条数（5-15 条，行业事件优先 + 突发事件限量） |
| `DEDUP_DAYS` | `7` | 去重窗口（天） |
| `SEVERITY_HIGHLIGHT` | `4` | 「重点关注」阈值 |
| `WECOM_WEBHOOK` | 空 | 企业微信机器人完整地址 |
| `DINGTALK_WEBHOOK` / `DINGTALK_SECRET` | 空 | 钉钉机器人地址 / 加签密钥 |
| `FEISHU_WEBHOOK` | 空 | 飞书机器人完整地址 |
| `SMTP_HOST` 等 | 空 | 邮件配置 |
| `PROXY_HTTP` / `PROXY_HTTPS` | 空 | 代理地址（国内 IP 访问境外源用，SMTP 不走代理） |
| `SCHEDULE_TIME` | `07:30` | 工作日定时时刻 |

## 推送渠道接入

- **企业微信**：群机器人 -> 复制 Webhook 地址填入 `WECOM_WEBHOOK`。
- **钉钉**：群机器人 -> 复制 Webhook 填入 `DINGTALK_WEBHOOK`；若启用了「加签」，把密钥填 `DINGTALK_SECRET`。
- **飞书**：群机器人 -> 复制 Webhook 填入 `FEISHU_WEBHOOK`。
- **邮件**：填 `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS`/`EMAIL_TO`（465 端口走 SSL，其他端口走 STARTTLS）。

各渠道内容长度有限（企微 4096 字节、钉钉/飞书有字符上限），超长会自动截断。

## 国内 IP 访问境外源与代理

数据源按「国内是否可达」分两类：

| 国内可达（无需代理） | 国内被墙（需代理） |
| --- | --- |
| GDELT、USGS、CISA、NVD、ReliefWeb、Krebs、BleepingComputer、TheHackersNews | BBC、The Guardian、Al Jazeera |

- **国内 IP 直连**：上面「国内可达」的源照常工作，GDELT 本身就聚合全球冲突/恐袭/骚乱，可作为全球新闻兜底。此时 BBC/Guardian/Al Jazeera 会抓取失败（已做容错，静默跳过、不影响整体）。
- **想取全境外新闻**：在 `.env` 填 `PROXY_HTTPS`（如 `http://127.0.0.1:7890`，端口按你的代理软件），HTTP(S) 采集会自动走代理；邮件（SMTP）仍走直连、**不受影响**。
- **不想用代理**：删掉 `RSS_FEEDS` 里的 BBC / Al Jazeera / The Guardian 三条即可，其余不受影响。

> 说明：`PROXY_HTTP`/`PROXY_HTTPS` 只作用于 HTTP(S) 采集与 Webhook 推送，**不影响 SMTP 邮件**（发邮件走 `smtplib`，不读代理）。

## 扩展新信源

1. 继承 [app/collectors/base.py](app/collectors/base.py) 的 `BaseCollector`，实现 `collect()` 返回 `List[SecurityEvent]`。
2. 在 [app/main.py](app/main.py) 的 `build_agent()` 里把采集器加进 `collectors` 列表即可，去重/分类/分级/摘要/报告/推送逻辑无需改动。

   - 最简单的方式：直接往 `.env` 的 `RSS_FEEDS` 里加一条 `URL|领域`，零代码接入新 RSS 信源。

## 物理安防聚焦与四维标签

- **聚焦过滤**：`app/services/classifier.py` 的 `PHYSICAL_SECURITY_CATEGORIES` 定义物理安防保留领域（geopolitical / terror / unrest / disaster / personnel）；`BriefAgent.run_daily()` 会用 `Classifier.is_physical_security()` 自动过滤掉 cyber / compliance / health 类事件。如需调整聚焦范围，改这个集合即可。
- **行业子类**：`app/services/sector.py` 把事件归入 9 个行业子类（物理安防/安防硬件/周界防护/AI安防/智能安防/安防峰会/行业动态/安防机器人/无人机/突发事件），简报与海报按子类分组。
- **精准精选**：`BriefAgent._select_top()` 优先高严重度的行业事件，突发事件（地缘/恐袭/灾害等）限量补充（至多总量的 1/3、不超过 3 条），总量控制在 `TOP_N`（默认 8，可配 5-15）。
- **相似事件去重**：同主题事件（地震/袭击/火灾/并购等，按 `_similarity_key` 判定）最多推 2 条，**不限制国家**，只减少同质事件堆叠。
- **USGS 源头降采样**：`USGSCollector` 默认每国家/地区最多 1 条，避免推送里堆砌一堆同区域小震。
- **四维打标**：`app/services/tagger.py` 用规则关键词识别「地域 / 企业 / 产品 / 事件」四维标签，存入 `SecurityEvent.tags` 并在简报、HTML、海报中展示。企业、产品、事件关键词表可在 `tagger.py` 顶部按需扩充。
- **自包含总结**：`app/services/summarizer.py` 在 LLM 摘要基础上，对失败/未命中的条目用 `_template_summary()` 生成「地点 + 事件 + 等级」的自包含中文总结，确保收件人不点链接也能看懂。
- **海报卡片风 PDF**：`app/services/report.py` 用 HTML/CSS 生成海报（深蓝渐变标题、统计徽章、彩色分类卡片、严重度色块、行业标签），再通过本地 Edge / Chrome 无头打印成 PDF（reportlab 兜底）。需要系统已安装 Edge 或 Chrome；未安装时自动回退到 reportlab 的简洁版 PDF。

## 无人值守部署（Windows）

`--schedule` 需要进程常驻。真正无人值守建议用 **任务计划程序（Task Scheduler）**。项目已提供 `run_daily.bat`（调用 `python -m app.main --once`，并把日志追加到同目录 `run_log.txt`）。

**方式一（已注册）**：本机已创建计划任务 `SecurityIntelDailyBrief`，每周一至周五 07:30 自动运行 `run_daily.bat`，可在「任务计划程序」里查看/修改。

**方式二（手动/重装）**：命令行注册（PowerShell / cmd）：

```bat
schtasks /Create /TN "SecurityIntelDailyBrief" /TR "\"C:\vscode project\security-intel-agent\run_daily.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /F
```

> **注意 1**：默认以「只在用户登录时运行」创建；如需「不管用户是否登录都运行」，在任务计划程序里勾选该选项并输入 Windows 密码，或改用 `/RU SYSTEM`。
>
> **注意 2（代理依赖）**：脚本按 `.env` 里的 `PROXY_HTTP/PROXY_HTTPS` 访问境外源——当前配了全局代理 `127.0.0.1:7897`，**若代理软件（如 Clash）未运行，所有境外采集都会失败**。请确保代理软件「开机自启」。若想降低对代理的依赖，可清空 `PROXY_HTTP/PROXY_HTTPS`，此时国内可达源（GDELT/USGS/CISA/Krebs）直连可用，仅 BBC/Guardian/Al Jazeera 取不到。

## 云端无人值守部署（GitHub Actions，关机也能跑）

如果不想依赖本机开机（笔记本关机就收不到日报），推荐把定时任务搬到云端，用 GitHub Actions 免费跑。云端 runner 在美国，能直连 GDELT/USGS/BBC 等境外源，**连代理都省了**。

已提供 [.github/workflows/daily-brief.yml](.github/workflows/daily-brief.yml)，默认**周一~周五 08:30（北京时间）**运行，并支持在 GitHub 网页上手动触发。部署步骤：

1. 把代码推到 GitHub 仓库（建议用 **private**，因为代码含业务逻辑；`.env` 已被 `.gitignore` 排除，不会上传）。
2. 在仓库 **Settings → Secrets and variables → Actions → New repository secret** 添加 4 个密钥：

   | 名称 | 值 |
   | --- | --- |
   | `LLM_API_KEY` | 你的 DeepSeek key |
   | `SMTP_USER` | 发件邮箱，如 `3414125031@qq.com` |
   | `SMTP_PASS` | QQ 邮箱授权码（不是登录密码） |
   | `EMAIL_TO` | 收件人，逗号分隔 |

3. 回到 **Actions** 页签，选 `Security Intel Daily Brief` → **Run workflow** 手动跑一次验证；或等下一个工作日 08:30 自动触发。

注意事项：

- **海报 PDF**：云端无 Edge/Chrome，会自动回退 reportlab 生成简洁版 PDF（内容完整，仅样式简单些）。
- **跨天去重**：通过 Actions 缓存持久化 `history.json`，云端也能「N 天内不重复上报」。
- **改运行频率**：编辑工作流里的 `cron`；想每天（含周末）跑就把 `1-5` 改成 `*`。
- **免费额度**：public 仓库 Actions 免费不限量；private 仓库每月 2000 分钟（每天约 2-3 分钟，够用）。
- 每次运行会把当日 md/html/json/pdf 打包成 artifact，可在 Actions 运行详情里下载核对。

## 测试

```bash
python -m pytest tests/
```

单元测试只覆盖分类/分级规则，不依赖网络。
