import os
import sys
import subprocess
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import Counter

# Directory where the current script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_batch_log(log_path: str, message: str):
    """
    Append a message to the batch-level log file.
    """
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now_str()}] {message}\n")
    except Exception:
        pass


def classify_failure(message: str) -> str:
    """
    Classify failure types based on the message content for statistics.
    """
    if "Directory does not exist" in message:
        return "missing_directory"
    if "start.py not found" in message:
        return "missing_start.py"
    if "repo_to_be_tested folder is missing" in message:
        return "missing_repo_to_be_tested"
    if "Failed to replace image tags in start.py" in message:
        return "modify_startpy_failed"
    if "Execution timed out" in message:
        return "timeout"
    if "Execution failed (exit code" in message:
        return "nonzero_exit"
    if "Unknown exception occurred" in message:
        return "unknown_exception"
    if "Fatal error occurred" in message:
        return "fatal_error"
    return "other_failure"


def run_script_in_dir(target_dir: str):
    """
    Run `python start.py` inside the given directory.

    Returns a dict like:
    {
        "directory": xxx,
        "success": True/False,
        "message": "...",
        "failure_type": "...",
        "start_time": "...",
        "end_time": "...",
        "duration_sec": 123.45,
        "log_path": "...",
    }
    """
    start_ts = time.time()
    start_time_str = now_str()

    log_path = os.path.join(target_dir, "run.log") if target_dir else "run.log"

    def build_result(success: bool, message: str, failure_type: str = None):
        end_ts = time.time()
        end_time_str = now_str()
        return {
            "directory": target_dir,
            "success": success,
            "message": message,
            "failure_type": failure_type,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "duration_sec": round(end_ts - start_ts, 2),
            "log_path": log_path
        }

    # 1. Check whether the target directory exists
    if not os.path.isdir(target_dir):
        return build_result(False, "❌ Directory does not exist", "missing_directory")

    # 2. Check whether start.py exists
    script_path = os.path.join(target_dir, "start.py")
    if not os.path.isfile(script_path):
        return build_result(False, "❌ start.py not found", "missing_start.py")

    # 3. Check whether repo_to_be_tested exists
    repo_dir = os.path.join(target_dir, "repo_to_be_tested")
    if not os.path.isdir(repo_dir):
        return build_result(False, "❌ repo_to_be_tested folder is missing", "missing_repo_to_be_tested")

    # 4. Modify start.py
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        new_content = re.sub(
            r"(golang|python|node):[a-zA-Z0-9_.-]+",
            r"\1:latest",
            content
        )

        if new_content != content:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(new_content)
    except Exception as e:
        return build_result(
            False,
            f"❌ Failed to replace image tags in start.py: {str(e)}",
            "modify_startpy_failed"
        )

    # 5. Execute start.py and write detailed logs
    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"[{now_str()}] Task started\n")
            log_file.write(f"target_dir: {target_dir}\n")
            log_file.write(f"script_path: {script_path}\n")
            log_file.write(f"repo_dir: {repo_dir}\n")
            log_file.write(f"python_executable: {sys.executable}\n")
            log_file.write(f"timeout_seconds: 10800\n")
            log_file.write("=" * 80 + "\n")
            log_file.flush()

            subprocess.run(
                [sys.executable, "start.py"],
                cwd=target_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
                timeout=10800  # 3 hours
            )

            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write(f"[{now_str()}] Task finished, exit status: success\n")

        return build_result(True, "✅ Execution succeeded", None)

    except subprocess.TimeoutExpired:
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("\n" + "=" * 80 + "\n")
                log_file.write(f"[{now_str()}] Task timed out after 3 hours and was forcefully terminated\n")
        except Exception:
            pass

        return build_result(
            False,
            f"❌ Execution timed out (exceeded 3 hours). Process was forcefully terminated. See details in {log_path}",
            "timeout"
        )

    except subprocess.CalledProcessError as e:
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("\n" + "=" * 80 + "\n")
                log_file.write(f"[{now_str()}] Task failed with exit code: {e.returncode}\n")
        except Exception:
            pass

        return build_result(
            False,
            f"❌ Execution failed (exit code {e.returncode}). See details in {log_path}",
            "nonzero_exit"
        )

    except Exception as e:
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("\n" + "=" * 80 + "\n")
                log_file.write(f"[{now_str()}] Unknown exception occurred: {str(e)}\n")
        except Exception:
            pass

        return build_result(
            False,
            f"❌ Unknown exception occurred: {str(e)}",
            "unknown_exception"
        )


def get_current_time_str():
    """
    Return current Beijing time in MMDDHHMM format.
    Example: Mar 23 15:58 -> 03231558
    """
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m%d%H%M")


def main():
    # ================= Configuration =================
    root_path = os.path.join(BASE_DIR, "repo")
    full_name_txt_path = os.path.join(BASE_DIR, "full_name.txt")
    json_output_path = os.path.join(BASE_DIR, f"run_status_{get_current_time_str()}.json")
    batch_log_path = os.path.join(BASE_DIR, "batch_run.log")
    summary_output_path = os.path.join(BASE_DIR, f"run_summary_{get_current_time_str()}.json")
    MAX_WORKERS = 8
    # =================================================

    # Initialize batch log
    append_batch_log(batch_log_path, "========== Batch job started ==========")
    append_batch_log(batch_log_path, f"BASE_DIR={BASE_DIR}")
    append_batch_log(batch_log_path, f"root_path={root_path}")
    append_batch_log(batch_log_path, f"full_name_txt_path={full_name_txt_path}")
    append_batch_log(batch_log_path, f"json_output_path={json_output_path}")
    append_batch_log(batch_log_path, f"MAX_WORKERS={MAX_WORKERS}")

    # Check root directory
    if not os.path.exists(root_path):
        msg = f"❌ Root directory does not exist: {root_path}"
        print(msg)
        append_batch_log(batch_log_path, msg)
        return

    # Check full_name.txt
    if not os.path.isfile(full_name_txt_path):
        msg = f"❌ full_name.txt does not exist: {full_name_txt_path}"
        print(msg)
        append_batch_log(batch_log_path, msg)
        return

    # Read full_name.txt and build target directories line by line
    directories = []
    try:
        with open(full_name_txt_path, "r", encoding="utf-8") as f:
            for line in f:
                full_name = line.strip()
                if not full_name:
                    continue
                target_dir = os.path.join(root_path, full_name)
                directories.append(target_dir)
    except Exception as e:
        msg = f"❌ Failed to read full_name.txt: {e}"
        print(msg)
        append_batch_log(batch_log_path, msg)
        return

    # Remove duplicates while preserving order
    directories = list(dict.fromkeys(directories))

    print(f"🚀 Start processing. Total directories: {len(directories)}, max workers: {MAX_WORKERS}\n")
    append_batch_log(batch_log_path, f"Number of directories to process: {len(directories)}")

    success_count = 0
    fail_count = 0
    error_count = 0

    # Failure type statistics
    failure_counter = Counter()

    # Store status for each directory
    status_dict = {}

    # Load existing output JSON if present
    if os.path.exists(json_output_path):
        try:
            with open(json_output_path, "r", encoding="utf-8") as f:
                status_dict = json.load(f)
            append_batch_log(batch_log_path, "Existing status file loaded successfully. Resume is supported.")
        except Exception as e:
            append_batch_log(batch_log_path, f"Failed to load existing status file: {e}")

    total_start_ts = time.time()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_dir = {executor.submit(run_script_in_dir, d): d for d in directories}

        for idx, future in enumerate(as_completed(future_to_dir), start=1):
            target_dir = future_to_dir[future]

            try:
                result = future.result()

                directory = result["directory"]
                is_success = result["success"]
                message = result["message"]
                failure_type = result["failure_type"]
                start_time = result["start_time"]
                end_time = result["end_time"]
                duration_sec = result["duration_sec"]
                log_path = result["log_path"]

                status_dict[directory] = {
                    "status": "success" if is_success else "failed",
                    "message": message,
                    "failure_type": failure_type,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_sec": duration_sec,
                    "log_path": log_path
                }

                if is_success:
                    success_count += 1
                    print(f"[SUCCESS] {directory} | Duration: {duration_sec}s")
                    append_batch_log(
                        batch_log_path,
                        f"[{idx}/{len(directories)}] SUCCESS: {directory} | Duration: {duration_sec}s"
                    )
                else:
                    fail_count += 1
                    failure_counter[failure_type or classify_failure(message)] += 1
                    print(f"[FAILED] {directory}")
                    print(f"         Type: {failure_type}")
                    print(f"         Reason: {message}")
                    print(f"         Duration: {duration_sec}s")
                    print(f"         Log: {log_path}")

                    append_batch_log(
                        batch_log_path,
                        f"[{idx}/{len(directories)}] FAILED: {directory} | Type: {failure_type} | "
                        f"Duration: {duration_sec}s | Reason: {message} | Log: {log_path}"
                    )

            except Exception as exc:
                fail_count += 1
                error_count += 1
                error_msg = f"Fatal error occurred: {exc}"
                failure_counter["fatal_error"] += 1

                print(f"[ERROR] Directory {target_dir} | {error_msg}")
                append_batch_log(batch_log_path, f"[ERROR] Directory {target_dir} | {error_msg}")

                status_dict[target_dir] = {
                    "status": "error",
                    "message": error_msg,
                    "failure_type": "fatal_error"
                }

            # Save status after each completed task
            try:
                with open(json_output_path, "w", encoding="utf-8") as f:
                    json.dump(status_dict, f, indent=4, ensure_ascii=False)
            except Exception as e:
                warn_msg = f"⚠️ Failed to save status JSON: {e}"
                print(warn_msg)
                append_batch_log(batch_log_path, warn_msg)

    total_duration = round(time.time() - total_start_ts, 2)

    # Count missing file-related failures
    missing_file_count = (
        failure_counter["missing_start.py"] +
        failure_counter["missing_repo_to_be_tested"] +
        failure_counter["missing_directory"]
    )

    # Summary info
    summary = {
        "total": len(directories),
        "success": success_count,
        "failed": fail_count,
        "error": error_count,
        "total_duration_sec": total_duration,
        "failure_statistics": {
            "timeout": failure_counter["timeout"],
            "missing_files_total": missing_file_count,
            "missing_directory": failure_counter["missing_directory"],
            "missing_start.py": failure_counter["missing_start.py"],
            "missing_repo_to_be_tested": failure_counter["missing_repo_to_be_tested"],
            "nonzero_exit": failure_counter["nonzero_exit"],
            "modify_startpy_failed": failure_counter["modify_startpy_failed"],
            "unknown_exception": failure_counter["unknown_exception"],
            "fatal_error": failure_counter["fatal_error"],
            "other_failure": failure_counter["other_failure"],
        }
    }

    # Save summary
    try:
        with open(summary_output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
    except Exception as e:
        append_batch_log(batch_log_path, f"Failed to save summary JSON: {e}")

    print("\n" + "=" * 60)
    print("🎉 All tasks have finished!")
    print(f"📊 Total: {len(directories)}")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print(f"⏱️ Timeout: {failure_counter['timeout']}")
    print(f"📁 Missing file-related failures: {missing_file_count}")
    print(f"   - Missing directory: {failure_counter['missing_directory']}")
    print(f"   - Missing start.py: {failure_counter['missing_start.py']}")
    print(f"   - Missing repo_to_be_tested: {failure_counter['missing_repo_to_be_tested']}")
    print(f"🚫 Non-zero exit failures: {failure_counter['nonzero_exit']}")
    print(f"🛠️ start.py modification failures: {failure_counter['modify_startpy_failed']}")
    print(f"❓ Unknown exceptions: {failure_counter['unknown_exception']}")
    print(f"💥 Fatal errors: {failure_counter['fatal_error']}")
    print(f"📝 Status file: {json_output_path}")
    print(f"📈 Summary file: {summary_output_path}")
    print(f"📚 Batch log: {batch_log_path}")
    print("=" * 60)

    append_batch_log(batch_log_path, "========== Batch job finished ==========")
    append_batch_log(batch_log_path, f"Total duration: {total_duration}s")
    append_batch_log(batch_log_path, f"Summary: {json.dumps(summary, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
