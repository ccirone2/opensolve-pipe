# OpenSolve Pipe - Development Container

This directory contains the VS Code development container configuration for OpenSolve Pipe.

## What's Included

- **Python 3.11** - Backend development
- **Node.js 20 LTS** - Frontend development
- **PostgreSQL 16** - Database
- **Redis 7** - Cache and task queue

## Quick Start

1. Install **Docker Desktop** and **VS Code**
2. Install **Dev Containers extension** in VS Code
3. Open this project in VS Code
4. Click "Reopen in Container" when prompted
5. Wait for setup to complete (~5 minutes first time)

## Services

All services start automatically:

- **Frontend:** http://localhost:5173 (SvelteKit)
- **Backend:** http://localhost:8000 (FastAPI)
- **Database:** localhost:5432 (PostgreSQL)
- **Redis:** localhost:6379

## File Structure

```
.devcontainer/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Multi-service orchestration
├── devcontainer.json       # VS Code configuration
├── post-create.sh          # Post-creation setup script
└── README.md               # This file
```

## Development Workflow

### Start Services

```bash
# Frontend
cd apps/web && pnpm dev

# Backend
cd apps/api && uvicorn opensolve_pipe.main:app --reload --port 8000
```

### Database Access

```bash
# Using psql
psql -h localhost -U opensolve -d opensolve_pipe
# Password: devpassword

# Using SQLTools extension in VS Code
# Connection is pre-configured
```

### Redis Access

```bash
# Using redis-cli
redis-cli -h localhost -p 6379
```

## VS Code Extensions

Pre-installed extensions:

**Python:**
- Python
- Pylance
- Ruff (linting & formatting)

**TypeScript/Svelte:**
- Svelte for VS Code
- ESLint
- Prettier

**Database:**
- SQLTools
- PostgreSQL driver

**General:**
- Tailwind CSS IntelliSense
- GitLens
- Error Lens

## Customization

### Add Python Packages

Edit `apps/api/pyproject.toml` and rebuild:

```bash
# In container
pip install -e ".[dev]"
```

### Add Node Packages

```bash
cd apps/web
pnpm add <package-name>
```

### Modify Container

Edit `.devcontainer/Dockerfile` and rebuild container:

1. Command Palette → "Dev Containers: Rebuild Container"
2. Wait for rebuild

## Troubleshooting

### Container Won't Start

```bash
# Rebuild without cache
docker-compose -f .devcontainer/docker-compose.yml build --no-cache

# Check logs
docker-compose -f .devcontainer/docker-compose.yml logs
```

### PostgreSQL Connection Failed

```bash
# Check if PostgreSQL is running
docker-compose -f .devcontainer/docker-compose.yml ps

# Restart PostgreSQL
docker-compose -f .devcontainer/docker-compose.yml restart postgres
```

### Redis Connection Failed

```bash
# Check if Redis is running
docker-compose -f .devcontainer/docker-compose.yml ps

# Restart Redis
docker-compose -f .devcontainer/docker-compose.yml restart redis
```

### Port Already in Use

Stop other services using the same ports:

```bash
# Check what's using port 5432
sudo lsof -i :5432

# Kill the process
kill <PID>
```

## Performance Optimization

### WSL 2 (Windows)

1. Store project in WSL filesystem (`/home/user/...`)
2. Do NOT use Windows filesystem (`/mnt/c/...`)
3. This improves performance by 10-20x

### Docker Resource Limits

Adjust in Docker Desktop settings:

- **Memory:** 4 GB minimum, 8 GB recommended
- **CPUs:** 2 minimum, 4 recommended
- **Swap:** 1 GB

## Environment Variables

Default environment variables (see `docker-compose.yml`):

```bash
DATABASE_URL=postgresql://opensolve:devpassword@localhost:5432/opensolve_pipe
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
NODE_ENV=development
```

To override, create `.env` files:

```bash
# apps/api/.env
DATABASE_URL=postgresql://custom:password@localhost:5432/custom_db

# apps/web/.env
PUBLIC_API_URL=http://localhost:8000
```

## Cleanup

### Remove Containers and Volumes

```bash
# Stop and remove containers
docker-compose -f .devcontainer/docker-compose.yml down

# Remove volumes (WARNING: deletes data)
docker-compose -f .devcontainer/docker-compose.yml down -v
```

### Remove Images

```bash
docker images | grep opensolve-pipe
docker rmi <image-id>
```

## Additional Resources

- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [Docker Compose](https://docs.docker.com/compose/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Redis Docker](https://hub.docker.com/_/redis)
