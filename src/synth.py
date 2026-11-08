import argparse
import sys
from datetime import datetime
from pathlib import Path
import utils.hlsParser as hlsp
from utils.binding import SynthScheduler
from utils.verilator import synth2verilog

def parse_args() -> tuple[Path, bool, str, dict[str, int]]:
    """
    Parsing command line args
    Returns values needed for later steps:
    Input file : Path
    Export-SSA : bool
    Scheduling mode : str
    Constraints : Dictionary[str, int] (e.g. {"adder": 2})
    """
    parser = argparse.ArgumentParser(description="Main HLS synthesis script generating Verilog and testbenches for Artix-7 FPGA.")
    parser.add_argument("input_file", type=Path, help="Path to input text file with proper equation formatting.")
    parser.add_argument("--export-ssa", action="store_true", help="Export the intermediary SSA text file for debugging.")
    parser.add_argument("--scheduler", required=True, choices=["ASAP", "ALAP", "CUSTOM"], type=str.upper, help="Select the scheduling mode (ASAP, ALAP, or CUSTOM).")
    parser.add_argument("--constraints", nargs="*", metavar="RESOURCE=LIMIT", help="Specify hardware constraints, e.g. adders=2 multipliers=1. Valid resources: adder, multiplier, subtractor.")
    args = parser.parse_args()

    if not args.input_file.is_file():
        parser.error("Input file path does not exist.")

    constraints_dict = {}
    for item in args.constraints or []:
        key, _, val = item.partition("=")
        key = key.strip().lower().removesuffix("s") # adders=2 and adder=2 both work
        if key not in ("adder", "multiplier", "subtractor"):
            parser.error(f"Constraint '{item}' must match the key=value format (e.g., adder=3).")
        if not val.strip().isdigit() or int(val) < 1:
            parser.error(f"Value for '{key}' must be an integer of at least 1 (e.g., {key}=3). Got '{val.strip()}' instead.")
        constraints_dict[key] = int(val)

    return (args.input_file, args.export_ssa, args.scheduler, constraints_dict)

def main():
    # step 1: process cmd line args
    input_file, export_ssa, scheduler_mode, constraints_dict = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # step 2: parse input file, construct DAG
    try:
        ssa_tokens = hlsp.extractSSA(input_file, export_ssa)
        dag = hlsp.DAG(ssa_tokens)
    except ValueError as err:
        sys.exit(f"Error: {err}")

    # step 3: do scheduling
    synth = SynthScheduler(dag, scheduler_mode, constraints_dict)
    synth.scheduler()

    # step 4: do binding
    synth.bind()

    # step 5: convert to verilog and output debug files :)
    synth.exportScheduler(input_file, timestamp)
    synth2verilog(synth, input_file, timestamp)

if __name__ == "__main__":
    main()
