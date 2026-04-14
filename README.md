# ExceptionOps Lite

一个面向企业运营场景的规则优先异常处理 Agent，用于跨系统数据冲突的证据聚合、语义解释、SOP 建议与人工审核闭环。

这个 demo 的核心不是“让模型自己判断”，而是把职责拆清楚：

- 规则引擎先识别金额、数量、状态、关键字段、更新时间异常
- 跨系统证据快照负责可追溯性
- 语义层只做摘要、根因整理、SOP 建议和风险表达
- 高风险动作由人工在自有案例页确认

## Stack

- Frontend: React 19 + Vite + TypeScript
- Backend: FastAPI + SQLite + SQLAlchemy + httpx
- AI orchestration: Dify Workflow API, with local fallback when Dify env is not configured

## Project Layout

- `frontend/`: Create Case 和 Case Detail 两个页面
- `backend/`: FastAPI API、规则引擎、SQLite、审计日志、Dify 适配层
- `seed/`: mock 跨系统记录、SOP 文档、知识库清单
- `dify/`: 工作流蓝图、Prompt、Code Node 参考实现
- `docs/`: 架构说明、Prompt 规则、演示脚本、面试讲稿
- `scripts/`: 本地启动和初始化脚本

## Run Locally

### 1. Backend

```bash
cd /root/dev/exceptionops-lite/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -i https://pypi.org/simple -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend

```bash
cd /root/dev/exceptionops-lite/frontend
npm install
npm run dev
```

默认地址：

- Frontend: `http://localhost:4174`
- Backend: `http://localhost:8000`
- API health: `http://localhost:8000/api/health`

## Dify Integration

如果没有配置 Dify 环境变量，后端会自动走本地 fallback 分析，保证项目开箱可演示。

配置真实 Dify 时使用：

```bash
export DIFY_API_URL="https://<your-dify-host>"
export DIFY_API_KEY="<your-api-key>"
export DIFY_WORKFLOW_ID="<your-workflow-id>"
```

## Demo Path

推荐直接使用默认案例：

- `external_ref`: `PO-2026-004`
- 这是一条金额、数量、状态、关键字段同时存在风险的组合异常
- 提交后可直接在详情页演示：
  - 证据快照
  - 规则命中
  - AI 解释
  - 人工确认
  - 审计时间线

## API Summary

- `POST /api/cases`
- `GET /api/cases/{case_id}`
- `GET /api/cases/{case_id}/context`
- `POST /api/cases/{case_id}/analyze`
- `POST /api/cases/{case_id}/review`
- `GET /api/mock/records/{external_ref}`

## Why This Demo Works In Interviews

- 它不是泛滥的聊天机器人壳子
- 它强调规则优先与可解释性，而不是盲目追求“自动化判断”
- 它体现了企业里真正关键的事情：证据链、风险边界、状态留痕、人工兜底
- 它把 Dify 放在合适的位置：AI 编排层，而不是主业务状态中心
