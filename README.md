<div align="center">

# ⚡ Crypto Alert Bot

**Telegram 加密货币价格提醒机器人** —— 用户选择币种、设定阈值,价格穿越阈值时自动推送提醒。

A Telegram bot for crypto price alerts: pick a coin, set a threshold, get notified the moment the price crosses.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-22.x-2CA5E0)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![Data Source](https://img.shields.io/badge/Data%20Source-Gate.io-2B6CB0)
![Status](https://img.shields.io/badge/Status-MVP-yellowgreen)

</div>

---

## 目录

- [简介](#简介)
- [功能特性](#功能特性)
- [工作原理](#工作原理)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [配置项说明](#配置项说明)
- [部署注意事项](#部署注意事项)
- [测试](#测试)
- [路线图](#路线图)
- [常见问题 FAQ](#常见问题-faq)
- [免责声明](#免责声明)
- [请我喝咖啡](#请我喝咖啡)
- [许可证](#许可证)

---

## 简介

Crypto Alert Bot 是一个自托管的 Telegram 机器人,用于监控加密货币价格并在价格**穿越**用户设定的阈值时推送提醒。它围绕"**纵向切片 MVP**"的理念设计:第一期只做「加密货币价格提醒」这一个类别,但架构(数据源适配器 `Source` 接口)为后续扩展**更多信息类别**(巨鲸转账、新闻、GitHub 动态、学术论文等)预留了统一入口。

数据源使用 **Gate.io 公开行情 API**,无需注册或 API Key,轮询间隔可配置。

## 功能特性

- 🪙 **多币种价格提醒**:BTC / ETH / SOL / BNB / DOGE / XRP / ADA / LTC(可在 `ui.py` 中扩展)
- 🐋 **巨鲸转账监控**:≥ $100 万大额链上转账提醒(WhaleAlert,配置 `WHALEALERT_API_KEY` 后启用),支持全部币种或指定币种
- 📰 **RSS 订阅**:粘贴任意 RSS/Atom 链接(兼容 RSSHub / GitHub / arXiv 等),可选关键词过滤,新内容自动推送
- 📈📉 **双向阈值**:价格「高于」或「低于」设定值时触发
- 🚦 **穿越检测 + 冷却**:仅在「未满足 → 满足」的穿越瞬间触发一次,冷却期内不重复轰炸,价格回落撤销条件后重新上膛
- 📋 **订阅管理**:内联键盘添加 / 查看 / 删除提醒,无感交互
- 🧪 **离线演练模式**(`DRY_RUN`):不连接 Telegram 也能跑通拉取、过滤、去重全流程,适合开发调试
- 🔌 **适配器架构**:`sources/` 下新增一个模块即可接入新数据源,核心引擎零改动
- 🗄️ **零外部依赖存储**:SQLite,无需数据库服务

## 工作原理

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
│  用户 Telegram  │   │    UI 层      │   │   引擎 Engine   │   │  数据源 Source    │
│  /start /myalerts│──▶│ 内联键盘/回调 │──▶│ 轮询+穿越检测   │──▶│ Gate.io 行情      │
└─────────────┘   └──────────────┘   │ 冷却+去重      │   └──────────────────┘
                                     └──────┬───────┘
                                            │ 触发
                                     ┌──────▼───────┐
                                     │   notify      │
                                     │ Telegram 推送  │
                                     │ 或 DRY_RUN 日志 │
                                     └──────────────┘
```

- **数据层**:`sources/price_gateio.py` 每次轮询拉取 Gate.io 全量现货 ticker,本地按订阅币种过滤、按资产去重(只保留 USDT 计价对)
- **判定层**:`engine.py` 对每个活跃订阅做**穿越检测**(仅「上一轮未满足 → 本轮满足」触发),触发后进入冷却期(默认 30 分钟)
- **通知层**:`notify.py` 在 `DRY_RUN=1` 时打印控制台并写入 `alerts.log`,否则推送 Telegram 消息(含快捷删除按钮)

## 项目结构

```
crypto-alert-bot/
├── main.py                 # 入口:PTB Application + JobQueue 定时轮询接线
├── config.py               # 集中配置(.env / 环境变量)
├── db.py                   # SQLite:users / subscriptions 建表 + CRUD
├── engine.py               # 告警引擎:轮询 → 穿越检测 → 冷却 → 触发
├── notify.py               # 通知:DRY_RUN 控制台日志 / Telegram 推送
├── ui.py                   # Telegram 交互:命令 + 内联键盘 + 回调
├── sources/
│   ├── base.py             # Source 抽象接口:fetch() -> list[AlertItem]
│   ├── price_gateio.py     # Gate.io 现货行情适配器(无需 key)
│   ├── whale_alert.py      # WhaleAlert 巨鲸转账适配器(需 key,无 key 时优雅降级)
│   └── rss_feed.py         # 通用 RSS/Atom 订阅适配器(feedparser,首轮基线+增量)
├── tests/
│   ├── seed_test.py        # 造测试数据(供 DRY_RUN 演示)
│   └── test_engine.py      # 断言测试:穿越/去重/冷却/低于方向
├── requirements.txt
├── .env.example            # 配置模板
└── README.md
```

## 快速开始

### 前置条件

- **Python 3.12+**
- 一个 **Telegram Bot Token**(通过 [@BotFather](https://t.me/BotFather) 创建,`/newbot` 获取)
- **网络要求**:本机需能访问 `api.telegram.org`(见 [部署注意事项](#部署注意事项))

### 安装

```bash
# 1. 克隆或进入项目目录
cd crypto-alert-bot

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# Linux / macOS
.venv/bin/pip install -r requirements.txt

# 国内网络可换清华镜像加速:
# .venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env`:

```ini
# 必填:从 @BotFather 获取
BOT_TOKEN=123456:ABC-DEF...your_token

# 可选:通过代理访问 Telegram 时填写
# HTTPS_PROXY=http://127.0.0.1:33210
```

### 启动

```bash
# 正常模式(连接 Telegram,接收真实用户)
.venv\Scripts\python main.py
# Linux/macOS:
# .venv/bin/python main.py

# 离线演练模式(不连 Telegram,跑 3 轮看触发/去重效果)
DRY_RUN=1 .venv\Scripts\python main.py
```

### 测试

```bash
PYTHONPATH=. .venv\Scripts\python tests\test_engine.py
# Linux/macOS:
# PYTHONPATH=. .venv/bin/python tests/test_engine.py
```

## 使用指南

在 Telegram 中与机器人对话:

| 命令 / 操作 | 说明 |
|---|---|
| `/start` | 开始使用,显示类别菜单(🪙 价格 / 🐋 巨鲸 / 📰 RSS) |
| `/myalerts` | 查看我的全部提醒,可逐条删除 |
| ➕ 添加提醒 | 价格:选币种 → 选方向(高于/低于)→ 输入阈值 → 保存 |
| ➕ 添加 RSS | 选「📰 RSS 订阅」→ 粘贴 RSS/Atom 链接 → 可选关键词(或 `/skip`)→ 保存 |
| 🗑️ 删除 | 从「我的提醒」列表或推送消息中一键删除 |

示例交互流程:

```
用户:  /start
Bot:   欢迎使用 ⚡ 加密价格提醒 …
       [🪙 加密货币价格提醒]
用户:  点击「🪙 加密货币价格提醒」
Bot:   选择要监控的币种:
       [BTC] [ETH] [SOL] [BNB]
       [DOGE] [XRP] [ADA] [LTC]
用户:  点击「BTC」
Bot:   BTC: 价格达到什么条件时提醒?
       [📈 高于阈值] [📉 低于阈值]
用户:  点击「📈 高于阈值」
Bot:   请输入阈值价格(数字,如 65000)
用户:  65000
Bot:   ✅ 已添加提醒
       BTC 高于 $65,000.00
       (订阅 #1)
```

当 BTC 价格穿越 $65,000 时,机器人推送:

```
🚀 突破 BTC 高于 $65,000.00
当前价格 $65,120.00
(订阅 #1)              [🗑️ 删除 #1]
```

## 配置项说明

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Telegram Bot Token(@BotFather 获取) |
| `HTTPS_PROXY` | — | 空 | 访问 Telegram 的代理地址;留空则直连 |
| `WHALEALERT_API_KEY` | — | 空 | WhaleAlert API key([whale-alert.io](https://whale-alert.io) 免费注册),填了才启用巨鲸类别 |
| `DRY_RUN` | — | `0` | `1` 时离线演练,不连接 Telegram,告警打印控制台 |
| `POLL_INTERVAL` | — | `60` | 行情轮询间隔(秒) |
| `COOLDOWN_SECONDS` | — | `1800` | 触发后冷却(秒),防震荡重复轰炸 |
| `DB_PATH` | — | `./alerts.db` | SQLite 数据库路径 |
| `LOG_FILE` | — | `./alerts.log` | DRY_RUN 模式的告警日志路径 |

## 部署注意事项

> ⚠️ **重要**:机器人必须能连接 `api.telegram.org` 才能收发消息。部分网络环境(如中国大陆)直连会被阻断。

- **方案一(推荐)· 海外 VPS**:将代码部署到一台 24h 在线的海外服务器上运行,7x24 稳定在线,无需代理
- **方案二 · 本地 + 代理**:配置 `HTTPS_PROXY` 指向本地代理(如 Clash/v2ray),机器人通过代理连接 Telegram

代码层面已做以下处理:

- `trust_env=False`:**不**继承操作系统/环境变量里的系统代理,避免被不可用的全局代理隧道劫持;仅当显式配置 `HTTPS_PROXY` 时才走代理
- 数据源 Gate.io 在部分被限制的网络下仍可直连,但 Telegram API 需要代理或境外网络
- 验证网络连通性:应能返回 `200`

```bash
curl -x http://127.0.0.1:33210 https://api.telegram.org
```

## 测试

`tests/test_engine.py` 使用**假数据源**(不联网)断言核心逻辑:

- ✅ 穿越检测:未达标不触发,向上穿越触发一次
- ✅ 去重:持续达标不重复触发
- ✅ 回落重置:价格回落撤销条件后,再次穿越可重新触发
- ✅ 冷却:冷却期内再次穿越不触发
- ✅ 低于方向:`lt` 方向判定正确
- ✅ 删除越权保护:只能删除自己的订阅

## 路线图

- [x] **MVP**:加密货币价格提醒(Gate.io,双向阈值,穿越检测 + 冷却)
- [x] **巨鲸转账**:接入 WhaleAlert API(同一 `Source` 接口),监控大额链上转账(需 `WHALEALERT_API_KEY`)
- [x] **多类别 / RSS 订阅**:通用 RSS/Atom 订阅(任意链接 + 关键词过滤,兼容 RSSHub / GitHub / arXiv),顶层类别选择
- [ ] **变现**:接入 Telegram Stars 订阅档(免费档限量,付费解锁更多币种/类别),`createInvoiceLink` 收款

## 常见问题 FAQ

**Q: 机器人启动后收不到提醒?**
A: 优先检查网络:本机能否连通 `api.telegram.org`(见部署注意事项)。其次确认 `DRY_RUN` 未被设置为 `1`。

**Q: 价格一直高于阈值,为什么只收到一次提醒?**
A: 这是有意的设计 —— 穿越检测只在你设定的条件**首次满足**时提醒一次,之后进入冷却期,避免价格波动造成消息轰炸。价格回落撤销条件后,再次穿越会重新提醒。

**Q: 想监控更多币种怎么办?**
A: 编辑 `ui.py` 中的 `SUPPORTED_ASSETS` 列表即可;只要 Gate.io 有该币种的 USDT 现货对,即可生效。

**Q: 如何新增一个信息类别(如 GitHub 动态)?**
A: 在 `sources/` 下新增一个模块实现 `Source.fetch()` 接口(参考 `price_gateio.py`),`engine` 无需任何改动 —— 这正是适配器架构的设计目的。

## 免责声明

- 本项目基于第三方公开数据源(Gate.io)构建,数据源可用性与数据准确性不受本项目控制,可能随时变化或不可用
- 本项目仅供学习研究使用,不构成任何投资建议。加密货币价格波动剧烈,请注意风险
- 部署者需遵守所在地区法律法规,并自行承担使用本项目的相关责任

## ☕ 请我喝咖啡

如果这个机器人帮你**躲过一次暴跌**、**抓住一次暴涨**……那多半是玄学,与作者无关。
但如果实在想表达感谢,作者本人对咖啡的抵抗力为零:

- ☕ **一杯美式** —— 续命,继续修 bug
- 🧋 **一杯奶茶** —— 心理暗示式加速开发新类别(无实际契约,纯属图个乐)
- 🍜 **一碗兰州拉面** —— 顺手把 README 翻成英文

> 🧾 **正经声明**:本项目完全免费,功能对所有用户一视同仁。
> 打赏**纯属自愿**,不影响任何功能 —— 本项目没有"付费解锁"这种东西(至少现在没有)。
> 若你哪天在路边看到作者捡瓶子,记得来杯咖啡救急 🙏

![微信收款码](assets/donate_wechat.png)

## 许可证

本项目基于 **[MIT License](LICENSE)** 开源。
