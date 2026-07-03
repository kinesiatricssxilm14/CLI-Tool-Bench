import os
import zipfile
from pathlib import Path

def create_clean_zip(source_dir, output_zip, excluded_repos):
    """
    Zips a results directory (e.g. openhands_results) but excludes the 6 problematic repos.
    Also excludes bloated/unnecessary artifacts if needed (like __pycache__).
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"Warning: {source_dir} not found. Skipping.")
        return

    print(f"Packaging {source_dir} into {output_zip}...")
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_path):
            current_path = Path(root)
            
            # Prune __pycache__ and git objects to save space if desired
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')

            # Check if this path contains one of the excluded repos
            # The structure is usually run_differential_test_<model>/repo/<owner>/<repo>/
            # We can check if any excluded_repo is a substring of the path
            is_excluded = False
            for ex_repo in excluded_repos:
                # normalize path separators
                if ex_repo in str(current_path.as_posix()):
                    is_excluded = True
                    break
            
            if is_excluded:
                continue

            for file in files:
                file_path = current_path / file
                # Double check the file path just in case
                is_file_excluded = False
                for ex_repo in excluded_repos:
                    if ex_repo in str(file_path.as_posix()):
                        is_file_excluded = True
                        break
                
                if not is_file_excluded:
                    arcname = file_path.relative_to(source_path)
                    zipf.write(file_path, arcname)

    print(f"Successfully created {output_zip} ({os.path.getsize(output_zip) / 1024 / 1024:.2f} MB)")

if __name__ == "__main__":
    from excluded_repos import EXCLUDED_REPOS

    # The raw data is in the old repo folder
    old_repo_dir = "/Users/freed/论文/ICSE 2027/CLI_Tool_Bench/CLI-Tool-Bench_repo"
    new_repo_dir = "/Users/freed/论文/ICSE 2027/CLI_Tool_Bench/CLI-Tool-Bench"

    print(f"Excluding the following {len(EXCLUDED_REPOS)} repositories:")
    for r in EXCLUDED_REPOS:
        print(f" - {r}")
    print()

    out_dir = Path(new_repo_dir) / "drive_uploads_package"
    out_dir.mkdir(exist_ok=True)

    create_clean_zip(
        os.path.join(old_repo_dir, "openhands_results"),
        out_dir / "openhands_generated_repos_clean.zip",
        EXCLUDED_REPOS
    )

    create_clean_zip(
        os.path.join(old_repo_dir, "mini_swe_agent_results"),
        out_dir / "mini_swe_agent_generated_repos_clean.zip",
        EXCLUDED_REPOS
    )

    print("\nNext steps:")
    print("1. Upload the zip files in `drive_uploads_package/` to your Google Drive.")
    print("2. Update the links in `docs/DATA_ACCESS.md` and `README.md` to point to the new files.")
