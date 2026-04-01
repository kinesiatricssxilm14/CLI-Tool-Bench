import os
import sys
import re
import random
import json
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the core, non-interactive commands of the backing-tracks tool.
    We focus on 'export' and 'strudel' as they process an input file and produce an output,
    which is ideal for differential testing. The 'play' command is interactive and not suitable.
    We also test the combination with the global '--soundfont' option.
    """
    EXPORT_BASIC = "backing-tracks export <file.btml> <outfile.mid>"
    EXPORT_WITH_SOUNDFONT = "backing-tracks --soundfont <font> export <file.btml> <outfile.mid>"
    STRUDEL_BASIC = "backing-tracks strudel <file.btml> <outfile.js>"
    STRUDEL_WITH_SOUNDFONT = "backing-tracks --soundfont <font> strudel <file.btml> <outfile.js>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    """
    Adapter for the 'backing-tracks' CLI tool.
    """
    # --- Static lists for generating valid BTML content ---
    VALID_KEYS = ['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb',
                  'Am', 'Em', 'Bm', 'F#m', 'C#m', 'G#m', 'D#m', 'A#m', 'Dm', 'Gm', 'Cm', 'Fm', 'Bbm', 'Ebm', 'Abm']
    VALID_STYLES = ['rock', 'blues', 'jazz', 'folk', 'funk', 'ska', 'reggae', 'country', 'disco', 'motown', 'flamenco', 'edm', 'trap', 'ragtime', 'stride', 'boogie']
    VALID_CHORDS = ['C', 'G', 'Am', 'F', 'C7', 'G7', 'Am7', 'Fmaj7', 'Dm', 'E7', 'Csus4', 'D5']
    VALID_BASS_STYLES = ['root', 'root_fifth', 'walking', 'swing_walking', 'stride', 'boogie']
    VALID_DRUM_STYLES = ['rock_beat', 'shuffle', 'jazz_swing', 'kick_only']
    VALID_RHYTHM_STYLES = ['whole', 'half', 'quarter', 'eighth', 'sixteenth', 'funk_16th', 'shuffle_strum', 'travis', 'fingerpick', 'arpeggio_up']

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Install dependencies and then the oracle version of the tool."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ako/backing-tracks.git && cd backing-tracks && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Install dependencies and then the agent version of the tool."""
        # dep_cmd = "apt-get update && apt-get install -y fluidsynth fluid-soundfont-gm"
        # if container.exec_run(dep_cmd).exit_code != 0:
        #     raise Exception("Agent dependency installation failed")
        
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize output by removing volatile information like file paths and line numbers.
        """
        sanitized = re.sub(r'file ".*?"', 'file "[FILEPATH]"', raw_stdout)
        sanitized = re.sub(r"[/a-zA-Z0-9_.-]+\.btml", "[FILEPATH].btml", sanitized)
        sanitized = re.sub(r'line \d+', 'line [LINE]', sanitized)
        sanitized = re.sub(r'column \d+', 'column [COL]', sanitized)
        return super().sanitize_stdout(sanitized)

    @staticmethod
    def _generate_btml_content(is_edge_case: bool) -> str:
        """
        Helper method to generate content for a .btml file.
        Generates valid-ish content for normal cases and malformed/boundary content for edge cases.
        """
        def yml_string(s):
            return json.dumps(s)

        try:
            if is_edge_case:
                if random.random() < 0.3:
                    return FuzzHelper.get_evil_string()

                track_data = {
                    "title": yml_string(FuzzHelper.get_string(1, 50)),
                    "key": yml_string(FuzzHelper.get_string(1, 5)),
                    "tempo": FuzzHelper.get_int(-100, 10) if random.random() > 0.5 else yml_string(FuzzHelper.get_evil_string()),
                    "style": yml_string(FuzzHelper.get_string(1, 10))
                }
                progression_data = {
                    "pattern": yml_string(" ".join(FuzzHelper.get_string(1, 4) for _ in range(4))),
                    "bars_per_chord": FuzzHelper.get_int(-2, 0)
                }
                bass_data = {"style": yml_string(FuzzHelper.get_string(1, 10))}
                drum_data = {"style": yml_string(FuzzHelper.get_string(1, 10))}
            else:
                track_data = {
                    "title": yml_string(f"Fuzz Song {FuzzHelper.get_int(1, 100)}"),
                    "key": random.choice(MyAdapter.VALID_KEYS),
                    "tempo": FuzzHelper.get_int(40, 240),
                    "style": random.choice(MyAdapter.VALID_STYLES)
                }
                progression_data = {
                    "pattern": yml_string(" ".join(random.choices(MyAdapter.VALID_CHORDS, k=random.randint(4, 12)))),
                    "bars_per_chord": random.choice([1, 2, 4])
                }
                bass_data = {"style": random.choice(MyAdapter.VALID_BASS_STYLES)}
                drum_data = {"style": random.choice(MyAdapter.VALID_DRUM_STYLES)}

            return f"""
track:
  title: {track_data['title']}
  key: {track_data['key']}
  tempo: {track_data['tempo']}
  style: {track_data['style']}
chord_progression:
  pattern: {progression_data['pattern']}
  bars_per_chord: {progression_data['bars_per_chord']}
bass:
  style: {bass_data['style']}
drums:
  style: {drum_data['style']}
"""
        except Exception:
            return "track:\n  title: 'fallback case'\n  key: C\n  tempo: 120\nchord_progression:\n  pattern: 'C G Am F'"

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generate a list of TestCase objects for the 'backing-tracks' tool.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        DEFAULT_SOUNDFONT_PATH = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)

                btml_filename = f"fuzz_{category.name.lower()}_{i}.btml"
                btml_content = self._generate_btml_content(is_edge_case)
                
                cmd_parts = ["backing-tracks"]
                
                if category in [CmdCategory.EXPORT_WITH_SOUNDFONT, CmdCategory.STRUDEL_WITH_SOUNDFONT]:
                    soundfont_path = FuzzHelper.get_filepath(ext=".sf2") if is_edge_case else DEFAULT_SOUNDFONT_PATH
                    cmd_parts.extend(["--soundfont", soundfont_path])

                if category in [CmdCategory.EXPORT_BASIC, CmdCategory.EXPORT_WITH_SOUNDFONT]:
                    subcommand = "export"
                    output_filename = f"output_{i}.mid"
                else: # STRUDEL
                    subcommand = "strudel"
                    output_filename = f"output_{i}.strudel.js"
                cmd_parts.append(subcommand)

                input_path = f"/test_data/{btml_filename}"
                output_path = f"/test_data/{output_filename}"
                
                if is_edge_case and random.random() < 0.3:
                    output_path = FuzzHelper.get_filepath(ext=".mid" if subcommand == "export" else ".js")

                cmd_parts.append(input_path)
                cmd_parts.append(output_path)

                command = " ".join(cmd_parts)

                cases.append(TestCase(
                    command=command,
                    category=category.value,
                    mount_files={btml_filename: btml_content},
                ))
        return cases


# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))