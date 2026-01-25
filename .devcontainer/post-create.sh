#!/bin/bash

# OpenSolve Pipe - Post-Create Setup Script
# Runs after the dev container is created

set -e

echo "🚀 Starting OpenSolve Pipe post-create setup..."

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Workspace
cd /workspace || {
    print_error "Failed to change to workspace directory"
    exit 1
}

# Directory structure
print_status "Creating directory structure..."
mkdir -p apps/api/src/opensolve_pipe
mkdir -p apps/web/src

# -------------------------
# Backend (Python)
# -------------------------
if [ -f "apps/api/pyproject.toml" ]; then
    print_status "Installing Python backend dependencies..."
    cd apps/api
    pip install -e ".[dev]" || print_warning "Python deps install failed"
    cd /workspace
else
    print_warning "apps/api/pyproject.toml not found - skipping backend deps"
fi

# -------------------------
# Frontend (Node / SvelteKit)
# -------------------------
if [ -f "apps/web/package.json" ]; then
    print_status "Installing frontend dependencies..."
    cd apps/web
    pnpm install || print_warning "Frontend deps install failed"
    cd /workspace
else
    print_warning "apps/web/package.json not found - skipping frontend deps"
fi

# -------------------------
# Playwright (polished setup)
# -------------------------
if [ -f "apps/web/package.json" ] && grep -q '"@playwright/test"' apps/web/package.json; then
    print_status "Setting up Playwright (Chromium + system deps)..."
    cd apps/web

    # Install browser + Linux deps (safe to re-run)
    npx playwright install chromium --with-deps || \
        print_warning "Playwright install failed or already installed"

    # Create standard folders if missing
    mkdir -p test-results playwright-report

    cd /workspace
else
    print_warning "Playwright not detected - skipping browser install"
fi

# -------------------------
# Pre-commit
# -------------------------
if [ -f ".pre-commit-config.yaml" ]; then
    print_status "Installing pre-commit hooks..."
    pre-commit install || print_warning "Pre-commit install failed"
else
    print_warning ".pre-commit-config.yaml not found - skipping pre-commit"
fi

# -------------------------
# Env files
# -------------------------
if [ -f "apps/api/.env.example" ] && [ ! -f "apps/api/.env" ]; then
    print_status "Creating apps/api/.env from example..."
    cp apps/api/.env.example apps/api/.env
fi

if [ -f "apps/web/.env.example" ] && [ ! -f "apps/web/.env" ]; then
    print_status "Creating apps/web/.env from example..."
    cp apps/web/.env.example apps/web/.env
fi

# -------------------------
# PostgreSQL
# -------------------------
print_status "Checking for PostgreSQL..."
pg_available=false
for i in {1..10}; do
    if pg_isready -h localhost -p 5432 -U opensolve -d opensolve_pipe > /dev/null 2>&1; then
        pg_available=true
        break
    fi
    echo "Waiting for PostgreSQL... ($i/10)"
    sleep 2
done

[ "$pg_available" = true ] && print_status "PostgreSQL is ready!" \
    || print_warning "PostgreSQL not available"

# -------------------------
# Redis
# -------------------------
print_status "Checking for Redis..."
redis_available=false
for i in {1..10}; do
    if redis-cli -h localhost -p 6379 ping > /dev/null 2>&1; then
        redis_available=true
        break
    fi
    echo "Waiting for Redis... ($i/10)"
    sleep 2
done

[ "$redis_available" = true ] && print_status "Redis is ready!" \
    || print_warning "Redis not available"

# -------------------------
# Summary
# -------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎉 OpenSolve Pipe development environment is ready!"
echo ""
echo "Frontend (SvelteKit):"
echo "  cd apps/web && pnpm dev"
echo "  → http://localhost:5173"
echo ""
echo "Backend (FastAPI):"
echo "  cd apps/api && uvicorn opensolve_pipe.main:app --reload --host 0.0.0.0 --port 8000"
echo "  → http://localhost:8000"
echo ""
echo "Playwright:"
echo "  cd apps/web"
echo "  pnpm test:e2e        # headless"
echo "  pnpm test:e2e:ui     # interactive UI"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
