#!/usr/bin/env python3
"""
Data Cleanup Script for MLentory ETL Pipeline

This script deletes old execution folders from the ETL data directories
based on platform, date threshold, and pipeline stage.

Usage:
    python scripts/cleanup_old_data.py --platform hf --date 2025-12-01 --stage 1_raw
    python scripts/cleanup_old_data.py --platform openml --date 2025-11-15 --stage all
    python scripts/cleanup_old_data.py --platform hf --date 2025-11-01 --stage 3_rdf --no-confirm
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


# Folder name pattern: YYYY-MM-DD_HH-MM-SS_<hash>
FOLDER_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}_[a-f0-9]{8}$')

# Valid pipeline stages
VALID_STAGES = ['1_raw', '2_normalized', '3_rdf', 'all']


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Clean up old execution files from ETL data directories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview deletion of HuggingFace raw data before Dec 1, 2025
  sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-12-01 --stage 1_raw

  # Delete from all stages with confirmation
  sudo python3 scripts/cleanup_old_data.py --platform openml --date 2025-11-15 --stage all

  # Auto-confirm deletion without prompt
  sudo python3 scripts/cleanup_old_data.py --platform hf --date 2025-11-01 --stage 3_rdf --no-confirm
        """
    )
    
    parser.add_argument(
        '--platform',
        required=True,
        help='Platform name (e.g., hf, openml, ai4life)'
    )
    
    parser.add_argument(
        '--date',
        required=True,
        help='Date threshold in YYYY-MM-DD format (delete files before this date, exclusive)'
    )
    
    parser.add_argument(
        '--stage',
        required=True,
        choices=VALID_STAGES,
        help='Pipeline stage: 1_raw, 2_normalized, 3_rdf, or all'
    )
    
    parser.add_argument(
        '--no-confirm',
        action='store_true',
        help='Skip confirmation prompt and delete immediately'
    )
    
    parser.add_argument(
        '--data-dir',
        default='/mnt/mlentory_volume/mlentory_etl_backend/data',
        help='Custom data directory path (default: /mnt/mlentory_volume/mlentory_etl_backend/data)'
    )
    
    return parser.parse_args()


def validate_date(date_str: str) -> datetime:
    """
    Validate and parse date string.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        datetime object
        
    Raises:
        ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")


def parse_folder_date(folder_name: str) -> datetime | None:
    """
    Extract date from folder name.
    
    Args:
        folder_name: Folder name in format YYYY-MM-DD_HH-MM-SS_<hash>
        
    Returns:
        datetime object if folder name matches pattern, None otherwise
    """
    match = FOLDER_PATTERN.match(folder_name)
    if match:
        date_str = match.group(1)
        return datetime.strptime(date_str, '%Y-%m-%d')
    return None


def get_folder_size(folder_path: Path) -> int:
    """
    Calculate total size of a folder in bytes.
    
    Args:
        folder_path: Path to folder
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for item in folder_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not calculate size for {folder_path}: {e}", file=sys.stderr)
    return total_size


def format_size(size_bytes: int) -> str:
    """
    Format size in bytes to human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def find_folders_to_delete(
    platform_dir: Path,
    threshold_date: datetime
) -> List[Tuple[Path, datetime]]:
    """
    Find all folders that should be deleted based on date threshold.
    
    Args:
        platform_dir: Path to platform directory
        threshold_date: Date threshold (delete folders before this date)
        
    Returns:
        List of tuples (folder_path, folder_date)
    """
    folders_to_delete = []
    
    if not platform_dir.exists():
        return folders_to_delete
    
    for folder in platform_dir.iterdir():
        if not folder.is_dir():
            continue
            
        folder_date = parse_folder_date(folder.name)
        if folder_date and folder_date < threshold_date:
            folders_to_delete.append((folder, folder_date))
    
    # Sort by date for better display
    folders_to_delete.sort(key=lambda x: x[1])
    
    return folders_to_delete


def display_preview(
    stage: str,
    platform: str,
    folders: List[Tuple[Path, datetime]],
    threshold_date: datetime
) -> int:
    """
    Display preview of folders to be deleted.
    
    Args:
        stage: Pipeline stage name
        platform: Platform name
        folders: List of tuples (folder_path, folder_date)
        threshold_date: Date threshold
        
    Returns:
        Total size in bytes
    """
    if not folders:
        print(f"\n[{stage}] No folders found for platform '{platform}' before {threshold_date.strftime('%Y-%m-%d')}")
        return 0
    
    print(f"\n{'='*80}")
    print(f"Stage: {stage}")
    print(f"Platform: {platform}")
    print(f"Date threshold: {threshold_date.strftime('%Y-%m-%d')} (exclusive)")
    print(f"{'='*80}")
    
    total_size = 0
    date_range = []
    
    print(f"\nFolders to be deleted ({len(folders)}):")
    print(f"{'Folder Name':<50} {'Date':<12} {'Size':<12}")
    print(f"{'-'*80}")
    
    for folder_path, folder_date in folders:
        size = get_folder_size(folder_path)
        total_size += size
        date_range.append(folder_date)
        
        print(f"{folder_path.name:<50} {folder_date.strftime('%Y-%m-%d'):<12} {format_size(size):<12}")
    
    print(f"{'-'*80}")
    print(f"\nSummary:")
    print(f"  Total folders: {len(folders)}")
    if date_range:
        print(f"  Date range: {min(date_range).strftime('%Y-%m-%d')} to {max(date_range).strftime('%Y-%m-%d')}")
    print(f"  Total size: {format_size(total_size)}")
    
    return total_size


def delete_folders(folders: List[Tuple[Path, datetime]]) -> Tuple[int, int]:
    """
    Delete folders and return statistics.
    
    Args:
        folders: List of tuples (folder_path, folder_date)
        
    Returns:
        Tuple of (successful_deletions, failed_deletions)
    """
    successful = 0
    failed = 0
    
    for folder_path, _ in folders:
        try:
            shutil.rmtree(folder_path)
            successful += 1
            print(f"✓ Deleted: {folder_path.name}")
        except (OSError, PermissionError) as e:
            failed += 1
            print(f"✗ Failed to delete {folder_path.name}: {e}", file=sys.stderr)
    
    return successful, failed


def confirm_deletion() -> bool:
    """
    Prompt user for confirmation.
    
    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input("\nProceed with deletion? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("Please enter 'yes' or 'no'")


def process_stage(
    data_dir: Path,
    stage: str,
    platform: str,
    threshold_date: datetime,
    no_confirm: bool
) -> Tuple[int, int, int]:
    """
    Process a single stage.
    
    Args:
        data_dir: Base data directory
        stage: Pipeline stage name
        platform: Platform name
        threshold_date: Date threshold
        no_confirm: Skip confirmation if True
        
    Returns:
        Tuple of (folders_found, successful_deletions, failed_deletions)
    """
    platform_dir = data_dir / stage / platform
    
    # Find folders to delete
    folders = find_folders_to_delete(platform_dir, threshold_date)
    
    if not folders:
        display_preview(stage, platform, folders, threshold_date)
        return 0, 0, 0
    
    # Display preview
    display_preview(stage, platform, folders, threshold_date)
    
    # Confirm deletion
    if not no_confirm:
        if not confirm_deletion():
            print(f"\n[{stage}] Deletion cancelled by user")
            return len(folders), 0, 0
    
    # Delete folders
    print(f"\n[{stage}] Deleting folders...")
    successful, failed = delete_folders(folders)
    
    print(f"\n[{stage}] Deletion complete: {successful} successful, {failed} failed")
    
    return len(folders), successful, failed


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Validate date
    try:
        threshold_date = validate_date(args.date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate data directory
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Determine stages to process
    stages = ['1_raw', '2_normalized', '3_rdf'] if args.stage == 'all' else [args.stage]
    
    # Process each stage
    total_found = 0
    total_successful = 0
    total_failed = 0
    
    print(f"\nMLentory ETL Data Cleanup")
    print(f"Platform: {args.platform}")
    print(f"Date threshold: {threshold_date.strftime('%Y-%m-%d')} (exclusive)")
    print(f"Stages: {', '.join(stages)}")
    print(f"Data directory: {data_dir}")
    
    for stage in stages:
        found, successful, failed = process_stage(
            data_dir,
            stage,
            args.platform,
            threshold_date,
            args.no_confirm
        )
        total_found += found
        total_successful += successful
        total_failed += failed
    
    # Final summary
    print(f"\n{'='*80}")
    print(f"FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Total folders found: {total_found}")
    print(f"Successfully deleted: {total_successful}")
    print(f"Failed to delete: {total_failed}")
    
    if total_failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()

