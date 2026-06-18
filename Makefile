# Robot Eval Platform — Makefile
#
# 常用命令：
#   make up          启动所有服务
#   make down        停止所有服务
#   make build       编译前端 + 重建平台镜像
#   make fe          仅编译前端（volume 挂载，立即生效，无需重启）
#   make restart     重启平台容器（后端代码变更后用）
#   make logs        跟踪平台日志
#   make status      查看所有容器状态

COMPOSE  = docker-compose
PLATFORM = eval-platform
FE_DIR   = frontend

.PHONY: up down restart build fe be logs status db-shell clean help

# ── 服务管理 ──────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d
	@echo "✓ 已启动，访问 http://$(shell python3 -c 'import socket; s=socket.socket(); s.connect(("8.8.8.8",80)); print(s.getsockname()[0])' 2>/dev/null || echo localhost):8000"

down:
	$(COMPOSE) down

restart:
	@echo "→ 重启平台容器（加载最新后端代码）..."
	docker stop $(PLATFORM) && docker start $(PLATFORM)
	@echo "✓ 平台已重启"

# ── 构建 ──────────────────────────────────────────────────────────────────────

fe:
	@echo "→ 编译前端..."
	cd $(FE_DIR) && npm run build
	@echo "✓ 前端编译完成（volume 挂载，浏览器刷新即可）"

be: restart
	@echo "✓ 后端已重载"

build: fe
	@echo "→ 重建平台 Docker 镜像..."
	$(COMPOSE) build platform
	docker stop $(PLATFORM) && docker start $(PLATFORM)
	@echo "✓ 构建完成"

# ── 调试 ──────────────────────────────────────────────────────────────────────

logs:
	$(COMPOSE) logs -f $(PLATFORM)

logs-all:
	$(COMPOSE) logs -f

status:
	$(COMPOSE) ps

db-shell:
	docker exec -it robot-eval-db psql -U eval -d robot_eval

# ── 清理 ──────────────────────────────────────────────────────────────────────

clean:
	$(COMPOSE) down -v
	@echo "⚠ 已停止服务并删除 volumes（PostgreSQL 数据已清除）"

help:
	@echo ""
	@echo "Robot Eval Platform"
	@echo "-------------------"
	@echo "  make up        启动所有服务"
	@echo "  make down      停止所有服务"
	@echo "  make fe        编译前端（立即生效，无需重启）"
	@echo "  make be        重启后端（后端代码变更后用）"
	@echo "  make build     编译前端 + 重建镜像 + 重启"
	@echo "  make restart   重启平台容器"
	@echo "  make logs      跟踪平台日志"
	@echo "  make status    查看所有容器状态"
	@echo "  make db-shell  进入 PostgreSQL shell"
	@echo "  make clean     停止所有并清除数据（危险）"
	@echo ""
