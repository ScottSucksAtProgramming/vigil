# Design: Dataset Encryption and Archival (Milestone 5)

**Date:** 2026-04-12
**Status:** Approved
**GitHub Issue:** #3

---

## Problem

Vigil captures a JPEG frame every 30 seconds and stores it unencrypted on the Raspberry Pi 5's SD card. If the Pi is stolen, every image ever captured is immediately readable. There is also no off-device backup — a disk failure permanently destroys any labeled frames intended for future model fine-tuning.

---

## Solution

Two-stage archival pipeline:

- **Stage 1 (0–24 h):** Images land in `dataset/images/` unencrypted. Mom views and labels them from the gallery.
- **Stage 2 (24 h+):** An hourly timer encrypts **labeled** images older than 24 hours using `age` asymmetric encryption, verifies the output, deletes the original, and marks the log entry `image_archived: true`. Unlabeled images are skipped — they have no training value. A nightly timer rsyncs the encrypted archive to a TrueNAS NAS over Tailscale, then deletes synced `.age` files from the Pi. `log.jsonl` and `checkins.jsonl` are synced to NAS but never deleted from the Pi.

The private key lives only on the builder's machine. A stolen Pi contains only encrypted blobs.

---

## Architecture

### New modules

| Module | Entry point | Timer |
|---|---|---|
| `archiver.py` | `run_archive_cycle(config)` | hourly |
| `nas_sync.py` | `run_nas_sync(config)` | nightly at 03:00 |

Both accept injected subprocess callables for full testability without real binaries.

### Modified modules

| Module | Change |
|---|---|
| `config.py` | 4 new fields in `SecurityConfig`; `archive_dir` in `DatasetConfig`; fix `image_interval_minutes` passthrough; cross-field validation |
| `models.py` | `image_archived: bool = False` on `DatasetEntry` |
| `dataset.py` | `rewrite_log()` primitive; `patch_log_entry()` wrapper; `flock` added to `append_log_entry` |
| `web_server.py` | `/images` route serves archived placeholder; `/label` route uses `patch_log_entry` |
| `templates/dashboard.html` + `static/dashboard.js` | "Archived" badge on thumbnail and modal |
| `static/` | New `archived_placeholder.jpg` asset |
| `setup/install.sh` | Install `age`; enable/start both timers |
| `docs/INSTALL_GUIDE.md` | New section for key gen, TrueNAS user, SSH setup, dry-run test |
| `setup/systemd/` | 4 new units |

---

## Section 1: Config (`config.py`)

### `SecurityConfig` — four new fields

```python
archive_after_hours: float = 24.0
age_public_key: str = ""
nas_sync_enabled: bool = False
nas_rsync_target: str = ""
```

- All flow through the existing `_build_section()` machinery — no custom builder needed.
- `age_public_key` is safe to store in config; it can only encrypt, not decrypt.

### `DatasetConfig` — one new derived field

```python
archive_dir: str = ""  # derived as {base_dir}/archive in _build_dataset
```

`_build_dataset()` sets it to `{base_dir}/archive` if empty, following the same pattern as `images_dir`. Paths belong in `DatasetConfig`, not `SecurityConfig`.

`_build_dataset()` must also be fixed to pass `image_interval_minutes` through explicitly (pre-existing omission — YAML overrides are currently silently ignored):

```python
image_interval_minutes = int(section.get("image_interval_minutes", 5))
```

### Cross-field validation in `load_config()`

If `nas_sync_enabled` is `True`, `nas_rsync_target` must be non-empty. Use the existing `_PROVIDER_REQUIRED_SECRETS` pattern.

---

## Section 2: Models (`models.py`)

Add to `DatasetEntry`:

```python
image_archived: bool = False
```

Distinct from `image_pruned` (pruning = retention policy deleted a routine frame; archived = encryption pipeline encrypted and removed the JPEG). Default of `False` ensures old log entries deserialize cleanly.

---

## Section 3: Dataset helpers (`dataset.py`)

### Concurrency model

Three code paths write to `log.jsonl`:
1. `append_log_entry` — monitor, every 30 s
2. `patch_log_entry` — label route, on user action
3. `rewrite_log` — archiver, once per hourly run

All three must participate in the same `fcntl.flock` advisory lock protocol using a dedicated `log.jsonl.lock` sidecar file. Without this, monitor appends can be silently lost during an archiver rewrite.

### `rewrite_log(config, transform)`

The single shared log-rewrite primitive:

1. Open `log.jsonl.lock` and acquire `flock(LOCK_EX)`
2. Read full `log.jsonl` into a list of dicts (handle missing or empty file gracefully)
3. Apply `transform(rows) -> rows`
4. Write to `tempfile.NamedTemporaryFile(dir=log_path.parent, delete=False)` — same directory ensures same filesystem for atomic rename
5. `Path.rename()` atomically replaces `log.jsonl`
6. Release lock

### `patch_log_entry(config, timestamp, updates)`

Thin wrapper over `rewrite_log`:
- Finds the row where `row["timestamp"] == timestamp` (timestamp is the unique per-cycle identifier, already used by the label route)
- Merges `updates` dict into that row
- If no match: logs warning, returns without writing

### `append_log_entry` change

Must acquire `flock(LOCK_EX)` on `log.jsonl.lock` before opening and writing. Releases after the write completes.

### Label route refactor

`/label/<entry_id>` in `web_server.py` must be refactored to call `patch_log_entry` instead of its current bespoke read-modify-write. This eliminates the second non-atomic rewrite code path.

---

## Section 4: `archiver.py`

### Entry point: `run_archive_cycle(config)`

```
1. Skip if age_public_key is empty — log warning, return
2. Check shutil.which("age") — log error, return if not found
3. Read log.jsonl once to build {filename: label} map
   - Key: Path(entry["image_path"]).name
   - Skip entries where image_path is "" (save_image=False cycles)
4. Scan dataset/images/ for .jpg files
5. Determine file age by parsing the filename timestamp (2026-04-09_03-00-00.jpg)
   - More robust than mtime, which changes on copies or restores
6. Filter: only files older than archive_after_hours WITH a non-empty label
7. Ensure archive_dir exists (create if needed)
8. For each eligible file:
   a. Encrypt: age -r <age_public_key> -o <archive_dir>/<filename>.age <input>
   b. Verify: .age file exists and size > 0
   c. Delete original JPEG only after verification passes
   d. If verification fails: log error, skip deletion, continue to next file
9. Single rewrite_log() call — batch-mark all successfully archived entries
   image_archived=True
```

### Subprocess injection

```python
def run_archive_cycle(config, *, _run=subprocess.run):
    ...
```

`_run` defaults to `subprocess.run`; tests inject a fake.

---

## Section 5: `nas_sync.py`

### Entry point: `run_nas_sync(config)`

```
1. Skip if nas_sync_enabled is False — log warning, return
2. Skip if nas_rsync_target is empty — log warning, return
3. rsync dataset/archive/ to nas_rsync_target (rsync -avz, no --remove-source-files)
4. On exit code 0: delete .age files from dataset/archive/ that were synced
   On non-zero: log error, leave .age files intact, return
5. rsync log.jsonl and checkins.jsonl to nas_rsync_target (no deletion)
6. Log success/failure
```

### Why two-phase delete (not `--remove-source-files`)

`--remove-source-files` deletes each source file immediately after transfer. A network interruption mid-run leaves a partial state where some `.age` files are gone from the Pi but may not have reached the NAS. The two-phase approach confirms the full transfer succeeded (exit 0) before any local deletion.

### Subprocess injection

```python
def run_nas_sync(config, *, _run=subprocess.run):
    ...
```

---

## Section 6: Dashboard changes

### `GET /images/<filename>` route

The route must distinguish archived files from genuinely missing ones:

1. If JPEG exists → serve it (current behavior)
2. If JPEG missing AND `<archive_dir>/<filename>.age` exists → serve `static/archived_placeholder.jpg` (200)
3. If neither exists → 404 (current werkzeug behavior)

This prevents the placeholder from swallowing legitimate missing-file errors or path traversal rejections.

### Gallery frontend

When `image_archived: true` in a gallery entry:
- **Thumbnail**: shows `archived_placeholder.jpg` as the `<img src>` + "Archived" badge overlay
- **Modal** (on tap): shows `archived_placeholder.jpg` + "Archived" label

### New static asset

`static/archived_placeholder.jpg` — a simple placeholder image (can be a gray rectangle or text image).

---

## Section 7: Systemd units

Four new files in `setup/systemd/`:

**`archiver.service`**
```ini
[Unit]
Description=Vigil dataset archiver
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/pi/eldercare
ExecStart=/home/pi/eldercare/venv/bin/python archiver.py
User=pi
```

**`archiver.timer`**
```ini
[Unit]
Description=Run vigil archiver hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

**`nas_sync.service`**
```ini
[Unit]
Description=Vigil NAS sync
After=network.target tailscaled.service

[Service]
Type=oneshot
WorkingDirectory=/home/pi/eldercare
ExecStart=/home/pi/eldercare/venv/bin/python nas_sync.py
User=pi
```

**`nas_sync.timer`**
```ini
[Unit]
Description=Run vigil NAS sync nightly

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

---

## Section 8: Setup and install guide

### `setup/install.sh` additions

```bash
sudo apt install -y age
systemctl enable --now archiver.timer
systemctl enable --now nas_sync.timer
```

### `docs/INSTALL_GUIDE.md` — new section: Dataset Encryption and NAS Sync Setup

1. Generate age key pair (on builder's machine, NOT on Pi): `age-keygen -o key.txt`
2. Copy the `public key:` line from `key.txt` into `config.yaml` → `security.age_public_key`
3. Keep `key.txt` (private key) off the Pi — store it securely on the builder's machine
4. Create `vigil-sync` user on TrueNAS with restricted dataset permissions
5. Generate passphrase-less SSH key on Pi: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/vigil_nas`
6. Copy public key to TrueNAS: `ssh-copy-id -i ~/.ssh/vigil_nas.pub vigil-sync@<tailscale-ip>`
7. Set `config.yaml` → `security.nas_rsync_target: "vigil-sync@<tailscale-ip>:/mnt/pool/vigil-archive"`
8. Set `config.yaml` → `security.nas_sync_enabled: true`
9. Test with dry-run: `rsync -avz --dry-run dataset/archive/ vigil-sync@<tailscale-ip>:/mnt/pool/vigil-archive/`

---

## Section 9: Tests

### `tests/test_archiver.py` (new)

- Skip when `age_public_key` is empty
- Skip when `age` binary not found (`shutil.which` returns None)
- Skip files younger than `archive_after_hours` (determined by filename timestamp)
- Skip unlabeled files (no label in log map)
- Skip entries with empty `image_path` when building label map
- Encrypt eligible labeled file → verify → delete original
- Fail-safe: skip deletion when `.age` output is missing or zero-size
- Single batch `rewrite_log()` call for all archived entries (not once per file)
- Create `archive_dir` if it does not exist (first run)

### `tests/test_nas_sync.py` (new)

- Skip when `nas_sync_enabled` is False
- Skip when `nas_rsync_target` is empty
- Call rsync with correct arguments for archive dir and log files
- Do NOT delete `.age` files if rsync returns non-zero
- Delete `.age` files from Pi after confirmed (exit 0) rsync

### `tests/test_dataset.py` extensions

- `rewrite_log` applies transform and atomically rewrites file
- `rewrite_log` handles missing `log.jsonl` (first run)
- `rewrite_log` handles empty `log.jsonl` (0 bytes)
- `patch_log_entry` finds matching row by timestamp and updates fields
- `patch_log_entry` no-op + warning when row not found
- `patch_log_entry` preserves all other rows unchanged
- `append_log_entry` participates in the same `flock` lock protocol

### `tests/test_web_server.py` extensions

- `GET /images/<archived-file>` returns placeholder (200) when `.age` file exists in archive_dir
- `GET /images/<truly-missing-file>` returns 404 when neither JPEG nor `.age` exists
- `GET /images/<existing-file>` still returns the real JPEG
- `/label/<id>` route delegates to `patch_log_entry` (no bespoke rewrite)

---

## Out of Scope

- Decryption tooling on the builder's machine (manual `age -d` is sufficient)
- Fine-tuning pipeline or dataset preparation scripts
- Encryption of `log.jsonl` or `checkins.jsonl`
- TrueNAS dataset encryption at rest
- Retention policy for unlabeled images (future milestone)
- Dashboard UI for browsing the encrypted archive

---

## Further Notes

- `age` public keys are safe to store in `config.yaml` — they can only encrypt, not decrypt.
- Both Pi and TrueNAS are enrolled in Tailscale — all rsync traffic is encrypted without additional VPN config.
- The 24-hour active window is a deliberate usability tradeoff. The install guide should note that physical security of the Pi matters during this window.
- `rewrite_log` batches all archiver updates into one rewrite per hourly run, bounding write amplification on the Pi's SD card.
- The `log.jsonl.lock` sidecar file approach uses a separate fd for locking and the log file for data, which is the standard pattern for advisory flock on files that are also replaced atomically.
