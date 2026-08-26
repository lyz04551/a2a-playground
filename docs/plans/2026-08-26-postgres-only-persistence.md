# Postgres 单数据库技术栈持久化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将后端业务数据和 LangGraph Agent checkpoint 全部切换到 Postgres，并通过三个 Agent 的 Direct/Auto 页面回归验证现有系统行为。

**Architecture:** Docker Compose 运行一个 Postgres 16 容器，分别创建 `playground` 和 `langgraph` 数据库。后端通过 SQLAlchemy Core 访问业务库，Agent 通过 `AsyncPostgresSaver` 访问 checkpoint 库；不提供 SQLite 或内存 checkpoint 回退。

**Tech Stack:** PostgreSQL 16、SQLAlchemy 2、psycopg 3、Alembic、LangGraph、pytest、Docker Compose、Playwright。

---

### Task 1：建立隔离的 Postgres 测试数据库

**Files:**
- Create: `tests/postgres/conftest.py`
- Create: `tests/postgres/test_database_contract.py`
- Modify: `backend/requirements.txt`

**Step 1: Write failing test**

```python
def test_postgres_fixture_is_isolated(postgres_url):
    engine = create_engine(postgres_url)
    with engine.connect() as connection:
        assert connection.execute(text("select current_database()")).scalar()
```

fixture 从 `TEST_DATABASE_URL` 创建随机数据库并在测试后删除；未配置时只跳过集成测试。

**Step 2: Verify RED**

Run: `pytest tests/postgres/test_database_contract.py -v`

Expected: FAIL，`postgres_url` fixture 不存在。

**Step 3: Implement and verify GREEN**

增加 `psycopg[binary,pool]>=3.2,<4`、`alembic>=1.14,<2`。用 `psycopg.sql.Identifier` 安全创建/删除数据库，teardown 前释放 Engine 和残留连接。

```bash
docker run --name a2a-postgres-test -e POSTGRES_PASSWORD=postgres -p 55432:5432 -d postgres:16
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/postgres/test_database_contract.py -v
git add backend/requirements.txt tests/postgres
git commit -m "test: add isolated postgres fixture"
```

### Task 2：使用 Alembic 创建业务表

**Files:**
- Create: `alembic.ini`
- Create: `backend/persistence/migrations/env.py`
- Create: `backend/persistence/migrations/script.py.mako`
- Create: `backend/persistence/migrations/versions/20260826_0001_initial.py`
- Create: `backend/persistence/migrate.py`
- Modify: `backend/persistence/models.py`
- Test: `tests/postgres/test_migrations.py`

**Step 1: Write failing test**

调用 `upgrade_database(postgres_url)`，断言 agents、conversations、messages、events、orchestration_runs、orchestration_tasks、remote_task_bindings、approvals、artifacts 全部存在；重复 upgrade 成功；事件条件唯一索引存在。

**Step 2: Verify RED**

Run: `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/postgres/test_migrations.py -v`

Expected: FAIL，迁移入口不存在。

**Step 3: Implement and verify GREEN**

通过 Alembic Config 注入 URL 并 upgrade head。初始迁移显式创建当前业务表、外键、约束和索引；不创建旧 JSON 导入使用的 migrations 业务表。

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/postgres/test_migrations.py -v
git add alembic.ini backend/persistence tests/postgres/test_migrations.py
git commit -m "feat: add postgres schema migrations"
```

### Task 3：改造 DatabaseRepository

**Files:**
- Modify: `backend/persistence/repository.py`
- Modify: `backend/persistence/__init__.py`
- Modify: `tests/backend/test_persistence.py`
- Modify: `tests/backend/test_run_repository.py`

**Step 1: Write failing tests**

改用 `DatabaseRepository(postgres_url)`；把 WAL 测试替换为 PostgreSQL 方言/索引测试；保留 12 条并发消息后的 message_count、审批幂等、事件序号和任务树约束测试。

**Step 2: Verify RED**

Run: `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/backend/test_persistence.py tests/backend/test_run_repository.py -v`

Expected: FAIL，`DatabaseRepository` 不存在。

**Step 3: Minimal implementation**

- 只接受 PostgreSQL URL。
- 删除文件路径、PRAGMA、运行时 ALTER TABLE 和 legacy upgrade。
- upsert 使用 PostgreSQL insert。
- add_message 在一个事务中 `SELECT ... FOR UPDATE` 会话行，再更新 JSON count/timestamp。
- 事件 sequence 分配锁定对应 Run。
- 保持公共方法签名及返回结构。

**Step 4: Verify and commit**

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/backend/test_persistence.py tests/backend/test_run_repository.py -v
git add backend/persistence tests/backend/test_persistence.py tests/backend/test_run_repository.py
git commit -m "feat: move backend repository to postgres"
```

### Task 4：完整后端测试迁移到 Postgres

**Files:**
- Create: `tests/backend/conftest.py`
- Create: `tests/backend/test_postgres_only_contract.py`
- Modify: 所有直接构造 `SQLiteRepository` 的 `tests/backend/*.py`
- Delete: `tests/backend/test_json_migration.py`

**Step 1: Write failing contract**

扫描生产代码，断言不存在 `SQLiteRepository`、`PLAYGROUND_DB_PATH`、`sqlite_insert`、SQLite PRAGMA、`import_legacy_json`。

**Step 2: Verify RED**

Run: `pytest tests/backend/test_postgres_only_contract.py -v`

Expected: FAIL 并列出残留文件。

**Step 3: Implement and verify**

提供每测试独立的真实 Postgres repository fixture。Service/App helper 接收 repository，不再接收 tmp_path；不得 mock Repository。

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/backend -v
git add tests/backend
git commit -m "test: run backend suite on postgres"
```

### Task 5：后端强制 DATABASE_URL

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/main.py`
- Modify: `backend/settings.py`
- Delete: `backend/persistence/migrate_json.py`
- Test: `tests/backend/test_database_startup.py`

**Step 1: Write failing tests**

缺少 `DATABASE_URL` 时抛出 `RuntimeError("DATABASE_URL is required")`；SQLite URL 抛出包含 PostgreSQL 的 `ValueError`。

**Step 2: Verify RED**

Run: `pytest tests/backend/test_database_startup.py -v`

Expected: FAIL，仍读取 `PLAYGROUND_DB_PATH`。

**Step 3: Implement and verify**

database facade 只创建 `DatabaseRepository`；删除数据目录/JSON 导入。Web 启动验证连接及 Alembic revision，迁移由部署入口执行。

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/a2a_test pytest tests/backend -v
git add backend tests/backend/test_database_startup.py
git commit -m "feat: require postgres for backend startup"
```

### Task 6：Agent 使用 AsyncPostgresSaver

**Files:**
- Modify: `agents/shared-runtime/pyproject.toml`
- Modify: `agents/shared-runtime/a2a_runtime/agent.py`
- Create: `agents/shared-runtime/a2a_runtime/checkpoint_migrate.py`
- Create: `tests/runtime/test_postgres_checkpointer.py`
- Modify: `tests/runtime/test_approval_resume.py`

**Step 1: Write failing tests**

第一个 RuntimeMCPAgent 向稳定 thread_id 写状态并关闭；第二个实例通过 `aget_state` 读到历史。另测 thread 隔离、缺少/不可达 URL、重复 shutdown、degraded readiness。

**Step 2: Verify RED**

Run: `TEST_CHECKPOINT_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/a2a_checkpoint_test pytest tests/runtime/test_postgres_checkpointer.py tests/runtime/test_approval_resume.py -v`

Expected: FAIL，仍使用 MemorySaver/get_state。

**Step 3: Implement**

增加 checkpoint-postgres/psycopg 依赖。URL 来自构造参数或 `AGENT_CHECKPOINT_DATABASE_URL`，缺失不回退。ensure_ready 打开一次 saver 上下文；改用 `await aget_state`；shutdown 幂等；失败初始化释放资源。迁移模块执行 `await setup()`。

**Step 4: Verify and commit**

```bash
TEST_CHECKPOINT_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/a2a_checkpoint_test pytest tests/runtime -v
git add agents/shared-runtime tests/runtime
git commit -m "feat: persist agent checkpoints in postgres"
```

### Task 7：Docker Compose Postgres-only 启动链路

**Files:**
- Modify: `docker-compose.yml`
- Create: `deploy/postgres/init/01-create-langgraph.sql`
- Modify: `.env.example`
- Modify: `backend/Dockerfile`
- Modify: 三个 Agent Dockerfile
- Modify: `tests/smoke/test_compose_config.py`
- Modify: `tests/backend/test_deployment_decoupling.py`

**Step 1: Write failing contract**

断言 Postgres 16、pg_isready、postgres_data、langgraph init SQL、backend-migrate、checkpoint-migrate 存在；业务服务等待迁移完成；不存在 PLAYGROUND_DB_PATH/backend_data。

**Step 2: Verify RED**

Run: `pytest tests/smoke/test_compose_config.py tests/backend/test_deployment_decoupling.py -v`

Expected: FAIL。

**Step 3: Implement**

本地默认开发账号为 a2a/a2a_dev_password。backend URL 指向 playground，三个 Agent URL 指向 langgraph；设置 `LANGGRAPH_STRICT_MSGPACK=true`。一次性迁移服务成功退出后才启动业务服务。

**Step 4: Verify and commit**

```bash
pytest tests/smoke/test_compose_config.py tests/backend/test_deployment_decoupling.py -v
docker compose config --quiet
docker compose up -d --build
docker compose ps
git add docker-compose.yml deploy .env.example backend/Dockerfile agents tests/smoke tests/backend/test_deployment_decoupling.py
git commit -m "feat: run full stack on postgres"
```

Expected: Postgres、backend、frontend、三个 Agent healthy，迁移服务 exit 0。

### Task 8：跨重启持久化回归

**Files:**
- Create: `tests/integration/test_postgres_restart.py`
- Create: `scripts/verify-postgres-persistence.sh`

**Step 1: Write failing test**

API 注册三个 Agent、创建会话/消息并记录 ID；重启 backend 后读取同一数据。向稳定 Agent thread 写 checkpoint，重启 Agent 后验证上下文。只用只读请求或确定性测试替身。

**Step 2: Verify RED**

Run: `pytest tests/integration/test_postgres_restart.py -v`

Expected: 持久化链路完整前 FAIL。

**Step 3: Implement diagnostics and verify**

健康等待使用截止时间轮询。失败输出 compose ps 和脱敏日志。

```bash
pytest tests/integration/test_postgres_restart.py -v
git add tests/integration scripts/verify-postgres-persistence.sh
git commit -m "test: verify postgres persistence across restarts"
```

### Task 9：三个 Agent 页面回归

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright.config.js`
- Create: `frontend/e2e/postgres-workspace.spec.js`
- Modify: 相关前端组件（仅在需要稳定定位或发现真实缺陷时）

**Step 1: Write E2E tests**

验证三个 Agent 可见；逐个 Direct 只读聊天；消息/工具活动/终态正常；Auto 显示 Host 决策、三个任务卡和最终输出；刷新保留历史；重启后继续同一会话。

**Step 2: Verify RED**

Run: `cd frontend && npm run test:e2e`

Expected: FAIL，配置/定位尚不存在。

**Step 3: Implement**

增加 `@playwright/test` 和 script。优先语义定位，必要时加 data-testid；失败保留 screenshot/trace/video。自动化使用确定性 LLM/MCP Compose override，之后再用用户真实配置执行非破坏性回归。

**Step 4: Verify and commit**

```bash
cd frontend
npm test
npm run build
npm run test:e2e
git add package.json package-lock.json playwright.config.js e2e src
git commit -m "test: cover postgres workspace in browser"
```

### Task 10：清理 SQLite 并全量验证

**Files:**
- Delete: 被 Git 跟踪的旧 SQLite/legacy JSON 数据资产
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `guide.md`
- Modify: `docs/CODE_WALKTHROUGH_ZH.md`
- Modify: `tests/backend/test_postgres_only_contract.py`

**Step 1: Verify remaining RED**

Run: `pytest tests/backend/test_postgres_only_contract.py -v`

Expected: 任何生产路径残留 SQLite/MemorySaver 均失败。

**Step 2: Cleanup and document**

删除残留。中文文档说明首次启动、变量、两个数据库职责、迁移、健康检查、测试、备份，以及删除 volume 会永久清空数据。

**Step 3: Full verification**

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres TEST_CHECKPOINT_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/a2a_checkpoint_test pytest -v
cd frontend && npm test && npm run build && npm run test:e2e
cd .. && docker compose config --quiet
docker compose ps
rg -n "SQLiteRepository|MemorySaver|PLAYGROUND_DB_PATH|sqlite_insert|PRAGMA journal_mode|import_legacy_json" backend agents docker-compose.yml
```

Expected: 所有测试通过，Compose 服务 healthy，最后 rg 无输出。

**Step 4: Commit**

```bash
git add -A
git commit -m "docs: finalize postgres-only runtime"
```

## 最终人工验收记录

交付时记录三个 Agent ID、三次 Direct conversation ID/终态、Auto conversation ID/run ID/终态、刷新结果、backend/Agent 重启恢复结果、外部 LLM/MCP 未覆盖项，以及实际测试命令和通过数量。
