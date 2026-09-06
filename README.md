# 🍁 Maple Pipeline · CI 质量门禁流水线平台

一个前后端分离的 CI/CD 质量门禁平台：可视化编排 DAG 流水线，测试指标不达标自动拦截部署，DeepSeek AI 智能归因失败与生成执行报告。**测试左移 + DevOps + AI** 的完整落地。

![tech](https://img.shields.io/badge/FastAPI-0.115-009488) ![tech](https://img.shields.io/badge/Vue3-3.5-42b883) ![tech](https://img.shields.io/badge/AntV_X6-2.18-8656d8) ![tech](https://img.shields.io/badge/MySQL-8.0-4479A1) ![tech](https://img.shields.io/badge/DeepSeek-AI-4D6BFE)

## 界面预览

| 登录（9 张枫叶背景轮播） | 仪表盘 |
|:---:|:---:|
| ![登录](docs/login.png) | ![仪表盘](docs/dashboard.png) |

| DAG 可视化编排 | 执行详情（实时日志 + 门禁） |
|:---:|:---:|
| ![编排器](docs/editor.png) | ![执行详情](docs/run-detail.png) |

| AI 助手 |
|:---:|
| ![AI 助手](docs/ai-assistant.png) |

## 核心特性

| 模块 | 能力 |
|---|---|
| 用户认证 | JWT 登录态 + bcrypt 密码哈希；账户存 **MySQL**（用户库与业务库分离），业务 API 全量鉴权，WS 握手 token 校验 |
| DAG 流水线引擎 | Kahn 拓扑排序分层调度、同层节点并行执行、成环检测、失败节点下游自动阻断 |
| 质量门禁 | 单测通过率 / 覆盖率阈值卡点，指标不达标即拦截部署（测试全绿但覆盖率不足也会被拦） |
| 代码检出 | 真实 `git clone` 拉取 GitHub 仓库（支持代理兜底）；或上传本地 zip 压缩包真实解压检出 |
| 实时日志 | WebSocket 逐行推送 + JSONL 落盘，断线重连回放历史，REST 轮询双通道兜底 |
| 可视化编排 | AntV X6 画布：拖拽添加节点、port 连线、属性面板、环检测、画布平移缩放自适应 |
| DeepSeek 智能化 | ① 失败日志归因与修复建议 ② 自然语言生成流水线 DAG ③ 门禁阈值智能推荐 ④ 执行报告自动生成 ⑤ 节点命令 AI 生成 |
| 仪表盘 | 成功率/耗时统计、7 天执行趋势、失败热点节点排行 |
| 报告中心 | AI 执行报告与失败归因统一归档，Markdown 渲染阅读 |
| 故障演练 | 一键注入「节点失败」或「覆盖率不达标」场景，演示门禁拦截链路 |

## 技术架构

```
┌─────────────────────────── 前端 Vue3 + Vite ───────────────────────────┐
│  登录/注册   仪表盘(ECharts)   流水线列表   X6 编排器   执行详情   AI 助手  │
└──────────────┬────────────────────────────────────────────┬───────────┘
        REST /api/* (Bearer JWT)                  WebSocket /ws/runs/{id}?token= + SSE
┌──────────────┴────────────────────────────────────────────┴───────────┐
│                          后端 FastAPI                                  │
│  routers: auth(JWT签发) / pipelines / runs / ai / dashboard / reports  │
│  engine:  DagRunner(Kahn分层+并行调度) → NodeExecutor(真实检出+高仿真) → Gate │
│  services: bcrypt密码哈希 · DeepSeek客户端 · WS连接管理 · LogStore      │
└──────────────┬──────────────────────────────┬─────────────────────────┘
   用户库 MySQL(maple_auth)   业务库 SQLite        httpx → DeepSeek API
```

## 快速启动

### 环境要求

- Python 3.10+、Node 18+、MySQL 8.x（本机已启动）

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env     # Windows（Linux/macOS 用 cp）
# 编辑 .env，填入以下配置：
#   DEEPSEEK_API_KEY   DeepSeek API 密钥
#   MYSQL_URL          mysql+pymysql://root:你的密码@127.0.0.1:3306/maple_auth?charset=utf8mb4
#   JWT_SECRET         随机长字符串（python -c "import secrets; print(secrets.token_hex(32))"）
python -m uvicorn app.main:app --port 8800
```

> MySQL 库 `maple_auth` 与用户表会在首次启动时**自动创建**，无需手工建库。
> 业务数据（流水线/执行记录）存 SQLite，零配置。

### 2. 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5273
```

首次启动自动初始化演示数据：示例流水线 + 历史执行记录。注册任意账户登录即可体验（账户存 MySQL，bcrypt 加密）。

Windows 可直接双击 `start.bat` 一键启动前后端。

## 演示剧本

1. **正常发布**：流水线页 → mall-api → 立即运行（不注入故障）→ 详情页看日志实时滚动、节点逐个变绿、门禁通过。
2. **门禁拦截**（招牌场景）：运行时故障演练选「单元/接口测试」+「覆盖率不达标」→ 测试节点全绿，但覆盖率 76.8% < 80% 阈值 → 质量门禁红色 FAIL，部署节点灰色「被阻断」。
3. **AI 失败归因**：失败 run 详情页 →「✦ AI 失败归因」→ DeepSeek 流式输出根因分析、修复建议、防回归用例建议。
4. **AI 生成流水线**：AI 助手页输入一句话（如「前端项目：构建、E2E 测试、门禁、发布生产」）→ 生成 DAG → 一键创建进入编排器。
5. **AI 执行报告**：run 详情页 →「📄 AI 执行报告」→ 5 章节结构化报告（执行摘要/节点明细/指标分析/问题风险/改进建议），自动归档到报告中心。
6. **真实代码检出**：新建流水线时选择 Git 仓库（真实 clone）或上传本地 zip（真实解压），检出节点展示真实文件列表与 commit 信息。

## 目录结构

```
maple-pipeline/
├── backend/
│   ├── app/
│   │   ├── auth_db.py       # MySQL 用户库（自动建库建表）
│   │   ├── engine/          # DAG 调度、节点执行器、质量门禁评估
│   │   ├── routers/         # auth / pipelines / runs / ai / dashboard / reports / uploads
│   │   ├── services/        # security(bcrypt+JWT) / DeepSeek 客户端 / WS 管理 / 日志存储
│   │   └── main.py
│   ├── seed.py              # 演示数据初始化
│   ├── requirements.txt
│   └── .env.example         # 环境变量模板（.env 已 gitignore）
└── frontend/
    ├── public/bg/           # 登录页轮播背景
    └── src/
        ├── views/           # Login / Dashboard / PipelineList / Editor(X6) / RunDetail / Reports / AI助手
        ├── components/      # 枫叶 Logo
        └── api.js           # REST / SSE / WebSocket 封装（自动附带 JWT）
```

## 技术亮点（面试可讲）

- **认证架构**：用户库（MySQL）与业务库（SQLite）分离的双数据源设计；bcrypt 成本因子哈希防彩虹表；JWT 24h 过期 + 前端路由守卫；WS 握手走 query token（浏览器 WS 不支持 Authorization header 的工程细节）
- **自研 DAG 调度器**：Kahn 算法拓扑分层，asyncio.gather 同层并行；失败传播用后代闭包计算阻断集合
- **门禁口径设计**：通过率 = passed/(passed+failed)，与 skipped 解耦，避免「跳过用例拉低通过率」的口径事故
- **实时日志双通道**：WebSocket 推送为主（内存 buffer + JSONL 落盘支持回放），REST 轮询兜底，前端按事件指纹去重
- **AI 工程化**：DeepSeek OpenAI 兼容接口，SSE 流式打字机输出，json_mode 结构化生成 DAG 并做 schema 兜底解析
- **真实检出链路**：git clone 真实执行（失败自动探测本地代理端口重试）、zip 解压做路径穿越（Zip Slip）防护
- **演示环境执行器**：高仿真模拟执行（pytest/bandit/docker/kubectl 风格日志），真实环境可平滑替换为 subprocess 执行 command

## License

MIT
