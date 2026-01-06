# MLentory ETL Scripts

This directory contains utility scripts for managing the MLentory ETL pipeline.

## cleanup_old_data.py

A command-line tool to clean up old execution files from the ETL data directories.

### Features

- Delete old execution folders based on date threshold
- Support for multiple platforms (hf, openml, ai4life, etc.)
- Support for specific pipeline stages or all stages at once
- Preview mode with size calculations before deletion
- Confirmation prompt for safety (can be skipped with `--no-confirm`)

### Usage

```bash
# Preview deletion of HuggingFace raw data before Dec 1, 2025
sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-12-01 --stage 1_raw

# Delete from all stages with confirmation
sudo python3 scripts/cleanup_old_data.py --platform openml --date 2025-11-15 --stage all

# Auto-confirm deletion without prompt
sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-11-01 --stage 3_rdf --no-confirm

# Use custom data directory
sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-12-01 --stage all --data-dir /path/to/data
```

### Arguments

- `--platform` (required): Platform name (e.g., hf, openml, ai4life)
- `--date` (required): Date threshold in YYYY-MM-DD format (deletes files **before** this date, exclusive)
- `--stage` (required): Pipeline stage - one of:
  - `1_raw`: Raw extracted data
  - `2_normalized`: Normalized/transformed data
  - `3_rdf`: RDF output files
  - `all`: Process all three stages
- `--no-confirm` (optional): Skip confirmation prompt and delete immediately
- `--data-dir` (optional): Custom data directory path (default: `/mnt/mlentory_volume/mlentory_etl_backend/data`)

### How It Works

1. **Folder Detection**: Scans for folders matching the pattern `YYYY-MM-DD_HH-MM-SS_<hash>`
2. **Date Filtering**: Compares folder dates with the threshold date (exclusive)
3. **Preview**: Shows all matching folders with:
   - Folder names and dates
   - Individual and total sizes
   - Date range summary
4. **Confirmation**: Prompts for user confirmation (unless `--no-confirm` is used)
5. **Deletion**: Recursively deletes confirmed folders and reports results

### Examples

#### Clean up old HuggingFace data before November 2025

```bash
sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-11-01 --stage all
```

This will:
- Find all HuggingFace folders dated before 2025-11-01
- Show preview with sizes
- Ask for confirmation
- Delete from all three stages (1_raw, 2_normalized, 3_rdf)

#### Quick cleanup with auto-confirm

```bash
sudo python3 scripts/cleanup_old_data.py --platform openml --date 2025-12-01 --stage 1_raw --no-confirm
```

This will immediately delete OpenML raw data folders before December 1, 2025 without asking for confirmation.

### Safety Features

- **Dry-run preview**: Always shows what will be deleted before proceeding
- **Confirmation prompt**: Requires explicit "yes" to proceed (unless `--no-confirm`)
- **Pattern matching**: Only deletes folders matching the exact naming pattern
- **Error handling**: Gracefully handles permission errors and missing directories
- **Detailed output**: Shows exactly what was deleted or failed

### Notes

- The date threshold is **exclusive** - folders from the specified date are NOT deleted
- If you get permission errors, you may need to run with appropriate permissions
- The script will skip stages where the platform directory doesn't exist
- Empty folders (0 bytes) are also deleted if they match the date criteria


