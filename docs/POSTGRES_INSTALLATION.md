# PostgreSQL Installation Guide for macOS
**Quick reference for setting up PostgreSQL + PostGIS**

---

## Installation Steps

### 1. Download Postgres.app
- Visit: https://postgresapp.com
- Click "Download" to get the latest version
- Open the downloaded `.dmg` file

### 2. Install Application
- Drag **Postgres.app** to your Applications folder
- Open Postgres.app from Applications
- Click **"Initialize"** to create the default server
- Verify the server shows a green indicator (running)

### 3. Add PostgreSQL to PATH
Open Terminal and run:
```bash
export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"
```

Make it permanent:
```bash
echo 'export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 4. Verify Installation
```bash
psql --version
```
Expected output: `psql (PostgreSQL) 16.x` (or 15.x)

### 5. Create Project Database
```bash
createdb healthcare_accessibility
```

Verify database was created:
```bash
psql -l | grep healthcare
```

### 6. Install Python Dependencies
```bash
pip install SQLAlchemy psycopg2-binary GeoAlchemy2 PyYAML
```

---

## What Was Installed

- **PostgreSQL 16** - Relational database server
- **PostGIS** - Spatial/geographic extension (included with Postgres.app)
- **Command-line tools** - `psql`, `createdb`, `pg_dump`, etc.

---

## Configuration

**Server Location:** localhost  
**Port:** 5432 (default)  
**Installed Path:** `/Applications/Postgres.app/`  
**Data Directory:** `~/Library/Application Support/Postgres/`  
**Databases Created:** `postgres`, `template1`, `healthcare_accessibility`

---

## Managing PostgreSQL

**Start Server:**  
Open Postgres.app (server starts automatically)

**Stop Server:**  
Quit Postgres.app

**Access Database Shell:**
```bash
psql healthcare_accessibility
```

**Common Commands (inside psql):**
- `\l` - List all databases
- `\dt` - List tables in current database
- `\q` - Exit psql

---

## Next Steps

After installation, initialize the project database:
```bash
make db-setup
```

This will:
- Create database schema (tables, indices, functions)
- Load shapefiles into PostGIS
- Calculate distance matrix
- Verify data integrity

---

## Troubleshooting

**"command not found: psql"**  
PostgreSQL not in PATH. Re-run Step 3.

**"could not connect to server"**  
Postgres.app not running. Open the application.

**"database does not exist"**  
Run Step 5 to create the database.

---

**Installation Time:** ~10 minutes  
**Disk Space Required:** ~200 MB (application + data)  
**Version Installed:** PostgreSQL 16.x with PostGIS 3.4
