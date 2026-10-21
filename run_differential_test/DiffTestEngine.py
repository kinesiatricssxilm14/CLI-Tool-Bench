import docker
import json
import os
import time
import traceback
import tarfile
import io
from BaseRepoAdapter import BaseRepoAdapter, TestCase


class DiffTestEngine:
    ENABLE_FS_DIFF = True
    SAVE_EVERY_N_CASES = 50
    WRITE_JSONL = True
    KEEP_FULL_DETAILS_FOR_MATCHED = True
    DIFF_CONTENT_LIMIT = 2000

    def __init__(self, adapter: BaseRepoAdapter, agent_local_path: str):
        self.adapter = adapter
        self.agent_local_path = os.path.abspath(agent_local_path)
        self.client = docker.from_env()

        self.oracle_image_tag = f"diff_oracle_{id(self)}:latest"
        self.agent_image_tag = f"diff_agent_{id(self)}:latest"

        self.work_repo_dir = self.adapter.work_repo_dir
        self.snapshot_repo_dir = self.adapter.snapshot_repo_dir
        self.repo_root_dir = self.adapter.repo_root_dir
        self.snapshot_root_dir = self.adapter.snapshot_root_dir
        self.test_data_dir = self.adapter.test_data_dir

        self.oracle_container = None
        self.agent_container = None

    def _escape_shell_cmd(self, cmd: str) -> str:
        return cmd.replace("'", "'\\''")

    def _safe_exec(self, container, cmd: str):
        safe_cmd = self._escape_shell_cmd(cmd)
        return container.exec_run(f"sh -c '{safe_cmd}'")

    def _decode_output(self, output) -> str:
        if output is None:
            return ""
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return str(output)

    def _truncate_content(self, content: str, limit: int = 2000) -> str:
        if len(content) > limit:
            return content[:limit] + "\n...[TRUNCATED]"
        return content

    def _build_baselines(self):
        print("Building Oracle baseline image...")
        c_oracle = self.client.containers.run(
            self.adapter.base_image,
            "sleep infinity",
            detach=True
        )
        try:
            self.adapter.install_oracle(c_oracle)
            self._normalize_repo_layout_inside_container(c_oracle, side="oracle")
            self._create_repo_snapshot(c_oracle)
            c_oracle.commit(repository=self.oracle_image_tag)
        finally:
            try:
                c_oracle.kill()
            except Exception:
                pass
            try:
                c_oracle.remove()
            except Exception:
                pass

        print("Building Agent baseline image...")
        c_agent = self.client.containers.run(
            self.adapter.base_image,
            "sleep infinity",
            detach=True
        )
        try:
            self.adapter.install_agent(c_agent, self.agent_local_path)
            self._normalize_repo_layout_inside_container(c_agent, side="agent")
            self._create_repo_snapshot(c_agent)
            c_agent.commit(repository=self.agent_image_tag)
        finally:
            try:
                c_agent.kill()
            except Exception:
                pass
            try:
                c_agent.remove()
            except Exception:
                pass

    def _normalize_repo_layout_inside_container(self, container, side: str):
        work_repo_dir = self.work_repo_dir
        repo_root_dir = self.repo_root_dir

        check_res = self._safe_exec(container, f"test -d '{work_repo_dir}'")
        if check_res.exit_code == 0:
            return

        list_cmd = (
            f"find '{repo_root_dir}' -mindepth 1 -maxdepth 1 -type d "
            f"! -name '{os.path.basename(work_repo_dir)}' "
            f"! -name '{os.path.basename(self.snapshot_root_dir)}' "
            f"| sort"
        )
        res = self._safe_exec(container, list_cmd)
        if res.exit_code != 0:
            raise Exception(f"[{side}] Failed to inspect repo root dir: {self._decode_output(res.output)}")

        candidates = [
            line.strip()
            for line in self._decode_output(res.output).splitlines()
            if line.strip()
        ]

        if len(candidates) == 1:
            src = candidates[0]
            move_cmd = f"rm -rf '{work_repo_dir}' && mv '{src}' '{work_repo_dir}'"
            move_res = self._safe_exec(container, move_cmd)
            if move_res.exit_code != 0:
                raise Exception(
                    f"[{side}] Failed to normalize repo dir from {src} to {work_repo_dir}: "
                    f"{self._decode_output(move_res.output)}"
                )
            print(f"[{side}] Normalized repo dir: {src} -> {work_repo_dir}")
            return

        raise Exception(
            f"[{side}] Cannot uniquely determine installed repo directory under {repo_root_dir}. "
            f"Candidates: {candidates}. "
            f"Please ensure adapter installs the target repo under {work_repo_dir} "
            f"or leaves exactly one repo directory under {repo_root_dir}."
        )

    def _create_repo_snapshot(self, container):
        cmd = (
            f"mkdir -p '{self.snapshot_root_dir}' && "
            f"rm -rf '{self.snapshot_repo_dir}' && "
            f"cp -a '{self.work_repo_dir}' '{self.snapshot_repo_dir}'"
        )
        res = self._safe_exec(container, cmd)
        if res.exit_code != 0:
            raise Exception(
                f"Failed to create repo snapshot: {self._decode_output(res.output)}"
            )

    def _start_persistent_containers(self):
        print("Starting persistent Oracle container...")
        self.oracle_container = self.client.containers.run(
            self.oracle_image_tag,
            "sleep infinity",
            detach=True
        )

        print("Starting persistent Agent container...")
        self.agent_container = self.client.containers.run(
            self.agent_image_tag,
            "sleep infinity",
            detach=True
        )

    def _stop_persistent_containers(self):
        for c in [self.oracle_container, self.agent_container]:
            if c is None:
                continue
            try:
                c.kill()
            except Exception:
                pass
            try:
                c.remove()
            except Exception:
                pass

        self.oracle_container = None
        self.agent_container = None

    def _restore_container_state(self, container):
        cmd = (
            f"rm -rf '{self.test_data_dir}' && mkdir -p '{self.test_data_dir}' && "
            f"rm -rf '{self.work_repo_dir}' && "
            f"cp -a '{self.snapshot_repo_dir}' '{self.work_repo_dir}'"
        )
        res = self._safe_exec(container, cmd)
        if res.exit_code != 0:
            raise Exception(
                f"Failed to restore container state: {self._decode_output(res.output)}"
            )

    def _put_files_to_test_data(self, container, mount_files):
        mount_files = mount_files or {}
        if not mount_files:
            return

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for target_path, content in mount_files.items():
                relative_path = target_path.strip("/")
                data = content.encode("utf-8")

                tar_info = tarfile.TarInfo(name=relative_path)
                tar_info.size = len(data)
                tar_info.mtime = int(time.time())
                tar_info.mode = 0o644

                tar.addfile(tarinfo=tar_info, fileobj=io.BytesIO(data))

        tar_stream.seek(0)
        ok = container.put_archive(self.test_data_dir, tar_stream.getvalue())
        if not ok:
            raise Exception(f"put_archive failed when writing mount_files into {self.test_data_dir}")

    def _build_find_prune_expr(self):
        ignore_names = self.adapter.workspace_diff_ignore_dir_names or []
        if not ignore_names:
            return ""

        parts = []
        for name in ignore_names:
            parts.append(f"-name '{name}'")
        joined = " -o ".join(parts)
        return f"\\( {joined} \\) -prune -o"

    def _build_workspace_manifest_shell_script(self):
        prune_expr = self._build_find_prune_expr()

        # ouput format：logical_path<TAB>size<TAB>cksum
        # logical_path：
        #   <REPO>/...
        #   <TEST_DATA>/...
        script = f"""
set -eu

TMP="/tmp/ws_manifest_$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

PRUNE_EXPR='{prune_expr}'

emit_manifest_for_base() {{
  PHYSICAL_BASE="$1"
  LOGICAL_PREFIX="$2"

  if [ ! -d "$PHYSICAL_BASE" ]; then
    return 0
  fi

  cd "$PHYSICAL_BASE"

  find . {prune_expr} -type f -print | sort | while IFS= read -r rel; do
    clean_rel="$(printf "%s" "$rel" | sed 's#^\\./##')"

    if [ ! -f "$clean_rel" ]; then
      continue
    fi

    size="$(wc -c < "$clean_rel" | tr -d ' ')"
    sum="$(cksum < "$clean_rel" | awk '{{print $1}}')"

    printf "%s/%s\\t%s\\t%s\\n" "$LOGICAL_PREFIX" "$clean_rel" "$size" "$sum"
  done
}}

emit_manifest_for_base "{self.work_repo_dir}" "<REPO>"
emit_manifest_for_base "{self.test_data_dir}" "<TEST_DATA>"
"""
        return script

    def _get_workspace_manifest(self, container):
        script = self._build_workspace_manifest_shell_script()
        res = self._safe_exec(container, script)
        if res.exit_code != 0:
            raise Exception(f"Workspace manifest script failed: {self._decode_output(res.output)}")

        raw = self._decode_output(res.output)
        manifest = {}

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) != 3:
                continue

            path, size, checksum = parts
            manifest[path] = {
                "size": size,
                "checksum": checksum
            }

        return manifest

    def _read_file_content_by_logical_path(self, container, logical_path: str) -> str:
        if logical_path.startswith("<REPO>/"):
            physical_path = f"{self.work_repo_dir}/{logical_path[len('<REPO>/'):]}"
        elif logical_path.startswith("<TEST_DATA>/"):
            physical_path = f"{self.test_data_dir}/{logical_path[len('<TEST_DATA>/'):]}"
        else:
            return "[UNABLE TO READ]"

        res = self._safe_exec(container, f"cat '{physical_path}'")
        if res.exit_code != 0:
            return "[UNABLE TO READ]"

        return self._truncate_content(self._decode_output(res.output), self.DIFF_CONTENT_LIMIT)

    def _build_workspace_diff_from_manifests(self, before_manifest: dict, after_manifest: dict, container):
        changes = {}
        all_paths = sorted(set(before_manifest.keys()) | set(after_manifest.keys()))

        for logical_path in all_paths:
            before = before_manifest.get(logical_path)
            after = after_manifest.get(logical_path)

            if before is None and after is not None:
                changes[logical_path] = {
                    "type": "ADD",
                    "content": self._read_file_content_by_logical_path(container, logical_path)
                }
            elif before is not None and after is None:
                changes[logical_path] = {
                    "type": "DEL",
                    "content": "N/A"
                }
            else:
                if (
                    before["size"] != after["size"]
                    or before["checksum"] != after["checksum"]
                ):
                    changes[logical_path] = {
                        "type": "MOD",
                        "content": self._read_file_content_by_logical_path(container, logical_path)
                    }

        return changes

    def _run_in_persistent_container(self, container, test_case: TestCase):
        restore_start = time.time()
        self._restore_container_state(container)
        restore_cost = time.time() - restore_start

        copy_cost = 0.0
        prep_cost = 0.0
        before_snapshot_cost = 0.0
        diff_cost = 0.0

        copy_start = time.time()
        self._put_files_to_test_data(container, test_case.mount_files)
        copy_cost = time.time() - copy_start

        if test_case.prep_script:
            prep_start = time.time()
            prep_res = self._safe_exec(container, test_case.prep_script)
            prep_cost = time.time() - prep_start
            if prep_res.exit_code != 0:
                raise Exception(
                    f"Prep script failed: {self._decode_output(prep_res.output)}"
                )

        before_manifest = {}
        if self.ENABLE_FS_DIFF:
            before_snapshot_start = time.time()
            before_manifest = self._get_workspace_manifest(container)
            before_snapshot_cost = time.time() - before_snapshot_start

        exec_start = time.time()
        exec_res = self._safe_exec(container, test_case.command)
        exec_duration = time.time() - exec_start

        raw_stdout = self._decode_output(exec_res.output)
        clean_stdout = self.adapter.sanitize_stdout(raw_stdout)

        fs_diff = {}
        if self.ENABLE_FS_DIFF:
            diff_start = time.time()
            after_manifest = self._get_workspace_manifest(container)
            fs_diff = self._build_workspace_diff_from_manifests(
                before_manifest=before_manifest,
                after_manifest=after_manifest,
                container=container
            )
            diff_cost = time.time() - diff_start

        return {
            "duration_seconds": round(exec_duration, 4),
            "exit_code": exec_res.exit_code,
            "stdout": clean_stdout,
            "stderr": "",
            "fs_diff": fs_diff,
            "perf": {
                "restore_seconds": round(restore_cost, 4),
                "copy_testdata_seconds": round(copy_cost, 4),
                "prep_seconds": round(prep_cost, 4),
                "before_snapshot_seconds": round(before_snapshot_cost, 4),
                "exec_seconds": round(exec_duration, 4),
                "diff_seconds": round(diff_cost, 4)
            }
        }

    def _is_result_matched(self, oracle_res: dict, agent_res: dict) -> bool:
        return (
            oracle_res.get("exit_code") == agent_res.get("exit_code")
            and oracle_res.get("stdout") == agent_res.get("stdout")
            and oracle_res.get("stderr") == agent_res.get("stderr")
            and oracle_res.get("fs_diff") == agent_res.get("fs_diff")
        )

    def _build_preparation_brief(self, tc: TestCase):
        mount_files = tc.mount_files or {}
        return {
            "script": tc.prep_script,
            "mounted_file_count": len(mount_files)
        }

    def _build_preparation_full(self, tc: TestCase):
        mount_files = tc.mount_files or {}
        return {
            "script": tc.prep_script,
            "mounted_files": [
                {"path": f"{self.test_data_dir}/{k.strip('/')}", "content": v}
                for k, v in mount_files.items()
            ]
        }

    def _append_jsonl(self, jsonl_path: str, item: dict):
        try:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to append JSONL {jsonl_path}: {e}")

    def _save_full_results(self, output_json_path: str, results: list):
        try:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save results to {output_json_path}: {e}")

    def run(self, output_json_path: str):
        total_start = time.time()
        results = []
        jsonl_path = output_json_path + "l" if self.WRITE_JSONL else None

        success_count = 0
        framework_error_count = 0
        mismatch_count = 0

        try:
            self._build_baselines()
            self._start_persistent_containers()
            test_cases = self.adapter.generate_test_cases()

            print(f"\nStarting test execution. Total cases: {len(test_cases)}")

            for idx, tc in enumerate(test_cases):
                case_start = time.time()
                print(f"[Test {idx + 1}/{len(test_cases)} | {tc.category}] {tc.command}")

                try:
                    oracle_res = self._run_in_persistent_container(self.oracle_container, tc)
                    agent_res = self._run_in_persistent_container(self.agent_container, tc)

                    matched = self._is_result_matched(oracle_res, agent_res)
                    if not matched:
                        mismatch_count += 1

                    oracle_duration = oracle_res.get("duration_seconds")
                    agent_duration = agent_res.get("duration_seconds")
                    case_wall_time = round(time.time() - case_start, 4)

                    if matched and not self.KEEP_FULL_DETAILS_FOR_MATCHED:
                        case_result = {
                            "test_id": idx + 1,
                            "category": tc.category,
                            "status": "SUCCESS",
                            "matched": True,
                            "command": tc.command,
                            "oracle_duration": oracle_duration,
                            "agent_duration": agent_duration,
                            "case_wall_time_seconds": case_wall_time,
                            "oracle_exit_code": oracle_res.get("exit_code"),
                            "agent_exit_code": agent_res.get("exit_code"),
                            "preparation": self._build_preparation_brief(tc),
                            "oracle_perf": oracle_res.get("perf", {}),
                            "agent_perf": agent_res.get("perf", {})
                        }
                    else:
                        case_result = {
                            "test_id": idx + 1,
                            "category": tc.category,
                            "status": "SUCCESS",
                            "matched": matched,
                            "command": tc.command,
                            "oracle_duration": oracle_duration,
                            "agent_duration": agent_duration,
                            "case_wall_time_seconds": case_wall_time,
                            "preparation": self._build_preparation_full(tc),
                            "oracle_result": oracle_res,
                            "agent_result": agent_res,
                            "oracle_perf": oracle_res.get("perf", {}),
                            "agent_perf": agent_res.get("perf", {})
                        }

                    results.append(case_result)
                    success_count += 1

                    if self.WRITE_JSONL:
                        self._append_jsonl(jsonl_path, case_result)

                except Exception:
                    framework_error_count += 1
                    error_msg = traceback.format_exc()
                    case_wall_time = round(time.time() - case_start, 4)
                    print("Framework execution error, skipped and recorded.")

                    case_result = {
                        "test_id": idx + 1,
                        "category": tc.category,
                        "status": "FRAMEWORK_ERROR",
                        "error_message": error_msg,
                        "command": tc.command,
                        "case_wall_time_seconds": case_wall_time,
                        "preparation": self._build_preparation_brief(tc)
                    }
                    results.append(case_result)

                    if self.WRITE_JSONL:
                        self._append_jsonl(jsonl_path, case_result)

                finally:
                    if (idx + 1) % self.SAVE_EVERY_N_CASES == 0:
                        self._save_full_results(output_json_path, results)

        finally:
            self._save_full_results(output_json_path, results)
            self._stop_persistent_containers()

            try:
                self.client.images.remove(self.oracle_image_tag, force=True)
            except Exception:
                pass

            try:
                self.client.images.remove(self.agent_image_tag, force=True)
            except Exception:
                pass

        total_cost = time.time() - total_start
        print(f"\nTest execution finished. Final report saved to {output_json_path}")
        print(f"Total wall time: {total_cost:.2f}s")
        print(f"Success cases: {success_count}")
        print(f"Mismatched cases: {mismatch_count}")
        print(f"Framework error cases: {framework_error_count}")
