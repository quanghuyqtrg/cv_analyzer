# CV Analyzer

AI-powered CV analysis tool. FastAPI backend, Next.js frontend, PostgreSQL database, all orchestrated with Docker Compose.

## Quick Start

```bash
# Start all services (builds on first run)
docker compose up --build

# Start in background
docker compose up -d --build

# Stop all services
docker compose down

# Stop and remove volumes (wipes DB data)
docker compose down -v
```

## Ports

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:3000       |
| Backend  | http://localhost:8000       |
| Postgres | localhost:5432              |
| Health   | http://localhost:8000/health |

## Project Structure

```
cv_analyzer/
├── docker-compose.yml
├── .env                          # DB credentials (gitignored)
├── CLAUDE.md
│
├── backend/                      # FastAPI (Python 3.12)
│   ├── Dockerfile
│   ├── requirements.txt          # Pinned dependencies
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI app instance, CORS, routes
│       └── database.py           # SQLAlchemy engine, session, Base class
│
└── frontend/                     # Next.js 15 (App Router, TypeScript)
    ├── Dockerfile
    ├── package.json
    ├── tsconfig.json
    ├── next.config.ts
    └── src/
        └── app/
            ├── layout.tsx        # Root layout
            └── page.tsx          # Home page
```

## Backend Conventions (Python / FastAPI)

### File & Directory Naming
- All Python files: `snake_case.py`
- One module per concern: `database.py`, `main.py`
- Future modules go under `backend/app/` (e.g. `models.py`, `schemas.py`, `routers/`)

### Code Style
- Functions and variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Async route handlers: `async def health_check()`
- SQLAlchemy models inherit from `Base` (defined in `database.py`)
- Use `get_db()` dependency for database sessions in route handlers

### API Routes
- Prefix-free flat routes on `app` for now (e.g. `@app.get("/health")`)
- When adding domain routes, use `APIRouter` with prefix: `/api/v1/cvs`, `/api/v1/users`
- Route naming: lowercase, plural nouns, no trailing slash

### Dependencies
- Pin exact versions in `requirements.txt`
- Use `psycopg2-binary` for dev; switch to `psycopg2` for production builds

## Frontend Conventions (TypeScript / Next.js)

### File & Directory Naming
- React components: `PascalCase` function name, but file follows Next.js App Router convention (`page.tsx`, `layout.tsx`)
- Custom components (when added): `src/components/ComponentName.tsx`
- Utilities (when added): `src/lib/utilName.ts`

### Code Style
- Components: named `export default function` (not arrow functions)
- Variables and functions: `camelCase`
- Types and interfaces: `PascalCase`
- Use TypeScript strict mode (enabled in `tsconfig.json`)

## Database

- PostgreSQL 16 (Alpine image)
- Database name: `cv_analyzer`
- SQLAlchemy ORM with `DeclarativeBase`
- Connection string built from `.env` vars, injected via `DATABASE_URL`

### Future Migrations
- When adding Alembic, init with: `alembic init backend/alembic`
- Migration files go in `backend/alembic/versions/`
- Always review auto-generated migrations before applying

## Do NOT Modify

| What | Why |
|------|-----|
| `.env` | Contains local credentials; gitignored. Never commit. Copy `.env` to `.env.example` (without real values) if sharing setup instructions. |
| `backend/alembic/versions/*` (once created) | Applied migration files are immutable history. Create new migrations to make changes. Never edit or delete applied migrations. |
| `docker-compose.yml` volume `pgdata` | Removing or renaming loses all database data. |
| `backend/app/database.py` `Base` class | All models depend on this single declarative base. Do not create a second one. |
| `frontend/src/app/layout.tsx` root structure | Next.js requires this file with the `<html>` and `<body>` tags. |

## Useful Commands

```bash
# View logs for a specific service
docker compose logs -f backend

# Rebuild a single service
docker compose up --build backend

# Run a one-off command in backend container
docker compose exec backend python -c "from app.database import engine; print(engine.url)"

# Access PostgreSQL shell
docker compose exec db psql -U postgres -d cv_analyzer

# Install a new Python package
# 1. Add to backend/requirements.txt (pinned version)
# 2. Rebuild: docker compose up --build backend

# Install a new npm package
docker compose exec frontend npm install <package>
```
