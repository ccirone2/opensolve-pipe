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

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if we're in the workspace directory
cd /workspace || {
    print_error "Failed to change to workspace directory"
    exit 1
}

# Create apps directories if they don't exist
print_status "Creating directory structure..."
mkdir -p apps/api/src/opensolve_pipe
mkdir -p apps/web/src

# Backend setup
if [ -f "apps/api/pyproject.toml" ]; then
    print_status "Installing Python backend dependencies..."
    cd apps/api
    pip install -e ".[dev]" || print_warning "Failed to install Python dependencies (may not be set up yet)"
    cd /workspace
else
    print_warning "apps/api/pyproject.toml not found - skipping Python dependency installation"
fi

# Frontend setup
if [ -f "apps/web/package.json" ]; then
    print_status "Installing frontend dependencies..."
    cd apps/web
    pnpm install || print_warning "Failed to install frontend dependencies (may not be set up yet)"
    cd /workspace
else
    print_warning "apps/web/package.json not found - skipping frontend dependency installation"
fi

# Install pre-commit hooks
if [ -f ".pre-commit-config.yaml" ]; then
    print_status "Installing pre-commit hooks..."
    pre-commit install || print_warning "Failed to install pre-commit hooks"
else
    print_warning ".pre-commit-config.yaml not found - skipping pre-commit setup"
fi

# Create .env files from .env.example if they exist and .env doesn't
if [ -f "apps/api/.env.example" ] && [ ! -f "apps/api/.env" ]; then
    print_status "Creating apps/api/.env from .env.example..."
    cp apps/api/.env.example apps/api/.env
fi

if [ -f "apps/web/.env.example" ] && [ ! -f "apps/web/.env" ]; then
    print_status "Creating apps/web/.env from .env.example..."
    cp apps/web/.env.example apps/web/.env
fi

# Wait for PostgreSQL to be ready (optional - don't fail if not available)
print_status "Checking for PostgreSQL..."
max_attempts=10
attempt=0
pg_available=false
while [ $attempt -lt $max_attempts ]; do
    if pg_isready -h localhost -p 5432 -U opensolve -d opensolve_pipe > /dev/null 2>&1; then
        pg_available=true
        break
    fi
    attempt=$((attempt + 1))
    echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ "$pg_available" = true ]; then
    print_status "PostgreSQL is ready!"
else
    print_warning "PostgreSQL not available - skipping database checks"
fi

# Wait for Redis to be ready (optional - don't fail if not available)
print_status "Checking for Redis..."
max_attempts=10
attempt=0
redis_available=false
while [ $attempt -lt $max_attempts ]; do
    if redis-cli -h localhost -p 6379 ping > /dev/null 2>&1; then
        redis_available=true
        break
    fi
    attempt=$((attempt + 1))
    echo "Waiting for Redis... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ "$redis_available" = true ]; then
    print_status "Redis is ready!"
else
    print_warning "Redis not available - this is optional for development"
fi

# Run database migrations (if migration system exists)
# Uncomment when migrations are set up
# if [ -f "apps/api/alembic.ini" ]; then
#     print_status "Running database migrations..."
#     cd apps/api
#     alembic upgrade head || print_warning "Failed to run migrations"
#     cd /workspace
# fi

# Display helpful information
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎉 OpenSolve Pipe development environment is ready!"
echo ""
echo "📚 Quick Start:"
echo ""
echo "  Frontend (SvelteKit):"
echo "    cd apps/web && pnpm dev"
echo "    → http://localhost:5173"
echo ""
echo "  Backend (FastAPI):"
echo "    cd apps/api && uvicorn opensolve_pipe.main:app --reload --host 0.0.0.0 --port 8000"
echo "    → http://localhost:8000"
echo "    → http://localhost:8000/docs (API docs)"
echo ""
if [ "$pg_available" = true ]; then
echo "  Database:"
echo "    PostgreSQL: localhost:5432"
echo "    User: opensolve | Password: devpassword | DB: opensolve_pipe"
echo ""
fi
if [ "$redis_available" = true ]; then
echo "  Redis:"
echo "    localhost:6379"
echo ""
fi
echo "📖 Documentation:"
echo "    - CLAUDE.md - Project overview and context"
echo "    - docs/DEVELOPMENT_PLAN.md - Phased development plan"
echo "    - docs/PRD.md, SDD.md, TSD.md - Complete specifications"
echo ""
echo "🔧 Development Tools:"
echo "    - Pre-commit hooks: automatically run linting and formatting"
echo "    - Ruff: Python linting and formatting"
echo "    - ESLint + Prettier: TypeScript/Svelte formatting"
if [ "$pg_available" = true ]; then
echo "    - SQLTools: Database management in VS Code"
fi
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
