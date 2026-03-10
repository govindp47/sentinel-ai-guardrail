# 08_BACKUP_AND_RECOVERY.md

# SentinelAI Guardrail — Backup & Recovery

---

## 1. Backup Architecture Overview

SentinelAI Guardrail's backup scope is determined by which data is persistent and irreproducible:

| Component | Persistent? | Backup Required? | Rationale |
|---|---|---|---|
| SQLite / PostgreSQL database | Yes | Yes | Audit records, KB metadata, policy configs, analytics |
| FAISS index files | Yes | Yes | Index rebuild from DB is possible but slow; backup avoids re-embedding |
| Uploaded document files | Yes | Yes | Raw documents cannot be recovered if lost |
| Embedding model weights | Yes | No | Re-downloadable from HuggingFace on startup |
| detoxify model weights | Yes | No | Re-downloadable from package registry |
| Ollama model weights | Yes | No | Re-pullable via `ollama pull` |
| Application code | Version-controlled | No | Git is the source of truth |
| Environment variables / secrets | External | No | Managed by platform or CI secrets |

**MVP backup scope:** Database file + FAISS index directory + uploaded document directory.

---

## 2. Backup File Structure

All backup artifacts are stored in a structured directory with the following layout:

```
backups/
└── {YYYY-MM-DD}/
    └── {YYYY-MM-DDTHH-MM-SSZ}/     ← ISO 8601 timestamp (UTC)
        ├── MANIFEST.json            ← Backup manifest (metadata + integrity hashes)
        ├── database/
        │   ├── sentinel.db          ← SQLite database file (or pg_dump output for PostgreSQL)
        │   └── sentinel.db.sha256   ← SHA-256 checksum of the database file
        ├── faiss_indexes/
        │   ├── {kb_id_1}.faiss
        │   ├── {kb_id_1}_id_map.json
        │   ├── {kb_id_2}.faiss
        │   ├── {kb_id_2}_id_map.json
        │   └── faiss_indexes.sha256  ← SHA-256 of concatenated index file checksums
        └── documents/
            ├── {session_id_1}/
            │   ├── {doc_uuid_1}_{filename}
            │   └── {doc_uuid_2}_{filename}
            └── documents.sha256      ← SHA-256 of tar archive of documents directory
```

### 2.1 MANIFEST.json Schema

```json
{
  "backup_version": "1.0",
  "backup_id": "bk_20240315T120000Z",
  "created_at": "2024-03-15T12:00:00Z",
  "schema_version": "0001",
  "app_version": "1.0.0",
  "components": {
    "database": {
      "type": "sqlite",
      "filename": "database/sentinel.db",
      "size_bytes": 2097152,
      "sha256": "abc123...",
      "row_counts": {
        "sessions": 42,
        "requests": 387,
        "kb_documents": 8,
        "kb_chunks": 1204
      }
    },
    "faiss_indexes": {
      "count": 3,
      "total_size_bytes": 5242880,
      "sha256": "def456...",
      "indexes": [
        {"kb_id": "...", "vector_count": 402, "dimension": 384}
      ]
    },
    "documents": {
      "count": 8,
      "total_size_bytes": 3145728,
      "sha256": "ghi789..."
    }
  },
  "integrity_verified": true,
  "host": "sentinel-prod-01",
  "notes": ""
}
```

---

## 3. Backup Mechanisms

### 3.1 SQLite Backup (MVP)

SQLite's online backup API is used to create a consistent snapshot without locking the database for writes during the backup:

```python
# scripts/backup.py

import sqlite3
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone

def backup_sqlite(source_path: str, dest_dir: Path) -> dict:
    dest_path = dest_dir / "sentinel.db"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Use SQLite's built-in online backup API (no write lock required)
    source_conn = sqlite3.connect(source_path)
    dest_conn = sqlite3.connect(str(dest_path))

    with dest_conn:
        source_conn.backup(dest_conn, pages=100, progress=_backup_progress_callback)

    source_conn.close()
    dest_conn.close()

    # Compute SHA-256 of backup file
    sha256 = compute_sha256(dest_path)
    checksum_path = dest_dir / "sentinel.db.sha256"
    checksum_path.write_text(sha256)

    return {
        "filename": "database/sentinel.db",
        "size_bytes": dest_path.stat().st_size,
        "sha256": sha256,
        "row_counts": get_row_counts(str(dest_path))
    }

def _backup_progress_callback(status, remaining, total):
    pass  # Can be connected to a progress logger

def get_row_counts(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    tables = ["sessions", "requests", "kb_documents", "kb_chunks",
              "pipeline_traces", "request_claims", "analytics_counters"]
    counts = {}
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]
    conn.close()
    return counts
```

**SQLite WAL mode interaction:** The application runs SQLite in WAL mode (`PRAGMA journal_mode = WAL`). SQLite's backup API correctly handles WAL mode by checkpointing the WAL before backing up. The `pages=100` parameter causes the backup to proceed in chunks, yielding between chunks so that concurrent reads/writes are not blocked.

### 3.2 PostgreSQL Backup (Production)

When PostgreSQL is in use, `pg_dump` produces the backup in custom format (compressed, supports partial restore):

```bash
pg_dump \
  --format=custom \
  --compress=9 \
  --file="${BACKUP_DIR}/database/sentinel.pgdump" \
  --no-password \
  "${DATABASE_URL}"
```

The `pg_dump` custom format supports:

- Table-level restore (`pg_restore --table=requests`)
- Schema-only restore (`pg_restore --schema-only`)
- Data-only restore (`pg_restore --data-only`)

A SHA-256 checksum is computed on the `.pgdump` file after creation.

### 3.3 FAISS Index Backup

```python
def backup_faiss_indexes(faiss_dir: Path, dest_dir: Path) -> dict:
    dest_faiss_dir = dest_dir / "faiss_indexes"
    dest_faiss_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    combined_hash = hashlib.sha256()

    for faiss_file in faiss_dir.glob("*.faiss"):
        kb_id = faiss_file.stem
        id_map_file = faiss_dir / f"{kb_id}_id_map.json"

        # Copy index file
        dest_index = dest_faiss_dir / faiss_file.name
        shutil.copy2(faiss_file, dest_index)

        # Copy id_map if it exists
        if id_map_file.exists():
            shutil.copy2(id_map_file, dest_faiss_dir / id_map_file.name)

        # Load index to get vector count and dimension
        index = faiss.read_index(str(faiss_file))
        file_hash = compute_sha256(dest_index)
        combined_hash.update(file_hash.encode())

        backed_up.append({
            "kb_id": kb_id,
            "vector_count": index.ntotal,
            "dimension": index.d
        })

    combined_sha256 = combined_hash.hexdigest()
    (dest_faiss_dir / "faiss_indexes.sha256").write_text(combined_sha256)

    return {
        "count": len(backed_up),
        "total_size_bytes": sum(f.stat().st_size for f in dest_faiss_dir.glob("*.faiss")),
        "sha256": combined_sha256,
        "indexes": backed_up
    }
```

**FAISS index backup timing:** FAISS indexes are backed up after the database backup completes, so that the `faiss_vector_id` values in `kb_chunks` are consistent with the backed-up index state.

### 3.4 Document File Backup

```python
def backup_documents(upload_dir: Path, dest_dir: Path) -> dict:
    dest_docs_dir = dest_dir / "documents"

    # Use tar to preserve directory structure and file metadata
    tar_path = dest_dir / "documents.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(upload_dir, arcname="documents")

    sha256 = compute_sha256(tar_path)
    (dest_dir / "documents.sha256").write_text(sha256)

    # Extract to final location for individual file access during restore
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(dest_dir)

    tar_path.unlink()  # Remove tar after extraction; individual files are the artifact

    file_count = sum(1 for _ in dest_docs_dir.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in dest_docs_dir.rglob("*") if f.is_file())

    return {
        "count": file_count,
        "total_size_bytes": total_size,
        "sha256": sha256
    }
```

---

## 4. Integrity Verification

### 4.1 Per-Component Verification

```python
def verify_backup(backup_dir: Path) -> VerificationResult:
    manifest_path = backup_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return VerificationResult(valid=False, error="MANIFEST.json not found")

    manifest = json.loads(manifest_path.read_text())
    errors = []

    # Verify database
    db_component = manifest["components"]["database"]
    db_path = backup_dir / db_component["filename"]
    if not db_path.exists():
        errors.append(f"Database file missing: {db_path}")
    else:
        actual_sha256 = compute_sha256(db_path)
        if actual_sha256 != db_component["sha256"]:
            errors.append(f"Database checksum mismatch: expected {db_component['sha256']}, got {actual_sha256}")
        else:
            # Structural validation: open DB and verify row counts
            actual_counts = get_row_counts(str(db_path))
            for table, expected_count in db_component["row_counts"].items():
                if actual_counts.get(table) != expected_count:
                    errors.append(f"Row count mismatch for {table}: expected {expected_count}, got {actual_counts.get(table)}")

    # Verify FAISS indexes
    faiss_sha256_path = backup_dir / "faiss_indexes" / "faiss_indexes.sha256"
    if faiss_sha256_path.exists():
        stored_sha256 = faiss_sha256_path.read_text().strip()
        combined_hash = hashlib.sha256()
        for faiss_file in sorted((backup_dir / "faiss_indexes").glob("*.faiss")):
            combined_hash.update(compute_sha256(faiss_file).encode())
        actual_combined = combined_hash.hexdigest()
        if actual_combined != stored_sha256:
            errors.append("FAISS index checksum mismatch")

    # Verify documents
    docs_sha256_path = backup_dir / "documents.sha256"
    if docs_sha256_path.exists():
        # Re-compute tar hash of documents directory for comparison
        temp_tar = backup_dir / "_verify_docs.tar.gz"
        with tarfile.open(temp_tar, "w:gz") as tar:
            tar.add(backup_dir / "documents", arcname="documents")
        actual_sha256 = compute_sha256(temp_tar)
        temp_tar.unlink()
        stored_sha256 = docs_sha256_path.read_text().strip()
        if actual_sha256 != stored_sha256:
            errors.append("Document files checksum mismatch")

    return VerificationResult(
        valid=len(errors) == 0,
        errors=errors,
        manifest=manifest
    )
```

### 4.2 Automated Verification on Backup Completion

The backup script always runs `verify_backup()` immediately after creating the backup. If verification fails:

1. The backup directory is renamed to `{timestamp}_FAILED`.
2. An error is logged at CRITICAL level.
3. The previous successful backup is retained (not overwritten).

---

## 5. Scheduled Backup Mechanisms

### 5.1 Backup Schedule

| Environment | Frequency | Retention | Method |
|---|---|---|---|
| Local development | Manual only | N/A | `scripts/backup.py` |
| MVP (free hosting) | Daily (00:00 UTC) | Last 7 backups | Cron job in container or platform scheduler |
| Production | Daily + on-deploy | Last 30 daily, last 4 weekly | Platform cron + pre-deploy hook |

### 5.2 Container-Based Scheduling (MVP)

For deployments without a platform cron scheduler, a lightweight cron is embedded in the application container using `supercronic` (a Docker-friendly cron daemon):

```dockerfile
# Dockerfile.backend
RUN apt-get install -y supercronic
COPY docker/crontab /etc/crontab

# /etc/crontab:
# 0 0 * * * python /app/scripts/backup.py >> /var/log/backup.log 2>&1
```

### 5.3 Backup Rotation

```python
def rotate_backups(backup_root: Path, keep_days: int = 7) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for date_dir in backup_root.iterdir():
        for timestamp_dir in date_dir.iterdir():
            try:
                ts = datetime.fromisoformat(timestamp_dir.name.replace("T", " ").replace("Z", "+00:00"))
                if ts < cutoff:
                    shutil.rmtree(timestamp_dir)
                    log.info("Rotated backup", path=str(timestamp_dir))
            except (ValueError, OSError) as e:
                log.warning("Could not rotate backup dir", path=str(timestamp_dir), error=str(e))
        # Remove empty date directories
        if not any(date_dir.iterdir()):
            date_dir.rmdir()
```

---

## 6. Restore Validation Logic

### 6.1 Full Restore Procedure

```bash
# Step 1: Stop the application
docker compose stop app

# Step 2: Verify backup integrity
python scripts/verify_backup.py --backup-dir backups/2024-03-15/2024-03-15T00-00-00Z

# Step 3: Restore database
# For SQLite:
cp backups/2024-03-15/.../database/sentinel.db ./sentinel.db
# For PostgreSQL:
pg_restore --clean --if-exists --dbname "${DATABASE_URL}" \
  backups/2024-03-15/.../database/sentinel.pgdump

# Step 4: Restore FAISS indexes
rm -rf ./data/faiss_indexes/*
cp backups/2024-03-15/.../faiss_indexes/* ./data/faiss_indexes/

# Step 5: Restore document files
rm -rf ./data/uploads/*
cp -r backups/2024-03-15/.../documents/* ./data/uploads/

# Step 6: Run Alembic migration check (in case schema changed since backup)
alembic upgrade head

# Step 7: Validate restore
python scripts/validate_restore.py

# Step 8: Start application
docker compose start app
```

### 6.2 `validate_restore.py` — Post-Restore Checks

```python
def validate_restore() -> ValidationReport:
    checks = []

    # 1. Database connectivity
    engine = create_engine(config.database_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    checks.append(Check("database_connectivity", passed=True))

    # 2. Row count sanity (non-zero where expected)
    with engine.connect() as conn:
        session_count = conn.execute(text("SELECT COUNT(*) FROM sessions")).scalar()
        checks.append(Check("sessions_non_empty", passed=session_count > 0,
                           detail=f"{session_count} sessions"))

    # 3. FAISS index consistency with database
    kb_docs = get_ready_kb_documents()
    for doc in kb_docs:
        index_path = Path(config.faiss_index_dir) / f"{doc.kb_id}.faiss"
        if not index_path.exists():
            checks.append(Check(f"faiss_index_{doc.kb_id}", passed=False,
                               detail="Index file missing"))
            continue
        index = faiss.read_index(str(index_path))
        db_chunk_count = get_chunk_count(doc.id)
        checks.append(Check(f"faiss_vector_count_{doc.kb_id}",
                           passed=abs(index.ntotal - db_chunk_count) <= 2,
                           detail=f"FAISS:{index.ntotal} DB:{db_chunk_count}"))

    # 4. Document file presence
    doc_records = get_all_kb_documents()
    for doc in doc_records:
        exists = os.path.exists(doc.storage_path)
        checks.append(Check(f"document_file_{doc.id[:8]}",
                           passed=exists,
                           detail=doc.storage_path if not exists else "OK"))

    # 5. FAISS search smoke test
    if kb_docs:
        test_vector = np.random.rand(1, 384).astype(np.float32)
        faiss.normalize_L2(test_vector)
        index = faiss.read_index(str(Path(config.faiss_index_dir) / f"{kb_docs[0].kb_id}.faiss"))
        distances, ids = index.search(test_vector, k=1)
        checks.append(Check("faiss_search_smoke_test", passed=ids[0][0] >= 0))

    failed = [c for c in checks if not c.passed]
    return ValidationReport(checks=checks, success=len(failed) == 0, failed=failed)
```

---

## 7. Partial Restore Strategy

### 7.1 Database Only (Documents Lost)

Scenario: filesystem containing document files and FAISS indexes is lost, but the database is intact.

```
1. Restore database from backup
2. Mark all kb_documents as status='failed', error_message='Document file lost during incident'
3. Mark all kb_chunks.faiss_vector_id = NULL
4. Notify users (via UI state): "Knowledge base documents were lost. Please re-upload."
5. Request audit records are intact (claim evidence references kb_chunk_id; chunks still exist in DB)
   → The claim_evidence table references still resolve but chunk_text is available
   → Evidence display in Request Explorer still works from the DB record
6. FAISS indexes need to be rebuilt from chunk text in the database:
   python scripts/rebuild_faiss_indexes.py  ← re-embeds all chunks from DB text
```

### 7.2 FAISS Indexes Only (Database Intact)

Scenario: FAISS index files are corrupted or lost, but the database is intact and document files exist.

```
1. Run rebuild_faiss_indexes.py to re-embed all kb_chunks.chunk_text from the database
2. This operation takes: N_chunks × 8ms embedding time
   Example: 10,000 chunks × 8ms = ~80 seconds on CPU
3. No data loss; the chunk_text is the source of truth
4. Mark all kb_documents with status='indexing' during rebuild; set to 'ready' on completion
```

`rebuild_faiss_indexes.py`:

```python
async def rebuild_all_indexes():
    documents = await kb_repo.get_all_ready_documents()
    for doc in documents:
        chunks = await chunk_repo.get_by_document(doc.id)
        texts = [c.chunk_text for c in chunks]
        vectors = embedding_adapter.embed_batch(texts)
        faiss.normalize_L2(vectors)

        index = faiss.IndexIDMap(faiss.IndexFlatL2(vectors.shape[1]))
        faiss_ids = np.array([c.chunk_index for c in chunks], dtype=np.int64)
        index.add_with_ids(vectors, faiss_ids)
        faiss.write_index(index, str(Path(config.faiss_index_dir) / f"{doc.kb_id}.faiss"))

        id_map = {str(c.chunk_index): c.id for c in chunks}
        (Path(config.faiss_index_dir) / f"{doc.kb_id}_id_map.json").write_text(json.dumps(id_map))

        await chunk_repo.update_faiss_ids(doc.id, {c.chunk_index: c.chunk_index for c in chunks})
        await kb_repo.update_status(doc.id, 'ready')
```

### 7.3 Single Table Restore (PostgreSQL Only)

For PostgreSQL deployments, a single table can be restored from a `pg_dump` custom format backup without restoring the entire database:

```bash
# Restore only the requests table (e.g., after accidental mass deletion)
pg_restore \
  --data-only \
  --table=requests \
  --dbname="${DATABASE_URL}" \
  backups/2024-03-15/.../database/sentinel.pgdump
```

**Caution:** Restoring `requests` without restoring its child tables (`pipeline_traces`, `request_claims`, etc.) leaves orphaned parent rows. Always restore the full dependency chain: `requests → pipeline_traces, request_claims, claim_evidence, safety_filter_results`.

---

## 8. Compatibility with Schema Migrations

### 8.1 Schema Version Tagging

Every backup records the Alembic schema version at the time of backup in `MANIFEST.json`:

```python
# In backup.py
def get_schema_version(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        return row[0] if row else "unknown"
    finally:
        conn.close()
```

### 8.2 Restore to a Different Schema Version

**Case 1: Backup schema == current schema**
Standard restore procedure. No migration needed.

**Case 2: Backup schema is older than current schema (backup is stale)**

```
1. Restore backup (older schema)
2. Run: alembic upgrade head
   → Applies all pending migrations to the restored database
   → New columns get their DEFAULT values; no data loss
3. FAISS indexes and document files are unaffected by schema migrations
4. Run validate_restore.py
```

**Case 3: Backup schema is newer than current code (rollback scenario)**

```
1. Roll back application code to the version matching the backup's schema version
2. Restore backup
3. Do NOT run alembic upgrade (the schema is already at the correct version)
4. If code rollback is not possible:
   → Run: alembic downgrade {backup_schema_version}
   → This is a destructive operation if the migration dropped columns
   → Prevention: migrations are additive-only (Rule 1 in migration strategy)
```

### 8.3 Migration Safety for Backup Compatibility

The additive-only migration rule (no DROP COLUMN in a single migration) is critical for backup compatibility. A backup made before a column was dropped can still be restored to a schema that has the column (the column just has no data). A backup made before a column was added is restored and then migrated forward (the column appears with its DEFAULT value).

---

## 9. External Backup Storage (Phase 3)

For MVP, backups are stored on the local filesystem of the deployment host. For Phase 3:

- **S3-compatible object storage** (AWS S3, Cloudflare R2, Backblaze B2): Daily backups are uploaded to a configured bucket after local backup completes.
- Upload is performed by `scripts/backup.py` using `boto3` or the S3-compatible API.
- Bucket lifecycle rule: transition backups older than 7 days to Glacier/cold tier; delete after 90 days.
- Backup files are encrypted at rest by the storage provider (SSE-S3).

```python
# Phase 3 addition to backup.py
def upload_to_s3(backup_dir: Path, s3_bucket: str, s3_prefix: str) -> None:
    import boto3
    s3 = boto3.client('s3')
    for file_path in backup_dir.rglob("*"):
        if file_path.is_file():
            key = f"{s3_prefix}/{file_path.relative_to(backup_dir.parent)}"
            s3.upload_file(str(file_path), s3_bucket, key)
    log.info("Backup uploaded to S3", bucket=s3_bucket, prefix=s3_prefix)
```
