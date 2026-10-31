import argparse
from datetime import datetime
from pathlib import Path
import utils.hlsParser as hlsp
from utils.binding import SynthScheduler
from utils.verilator import synth2verilog

def parse_args() -> tuple[Path, bool, str, dict[str, int]]:
    """
        Parsing command line args
        Returns list of values needed for later steps: 
        Export-SSA : bool
        Scheduling mode : str, 
        Constraints : Dictionary[str, int], 
    """
    # creating parser
    parser = argparse.ArgumentParser(description="Main HLS synthesis script generating Verilog and testbenches for Artix-7 FPGA.")
    parser.add_argument("input_file", type=Path, help="Path to input text file with proper equation formatting.")
    parser.add_argument("--export-ssa", action="store_true", help="Export the intermediary SSA text file for debugging.")
    parser.add_argument("--scheduler", required=True, choices=["ASAP", "ALAP", "CUSTOM"], type=str.upper, help="Select the scheduling mode (ASAP, ALAP, or CUSTOM).")
    parser.add_argument("--constraints", nargs="*", metavar="RESOURCE=LIMIT", help="Specify hardware constraints. Valid resources: adder, multiplier, subtractor.")
    args = parser.parse_args()

    # important invariant 
    if args.constraints and not args.scheduler:
        parser.error("Constraints can only be specified if a --scheduler mode is selected.")
    if not args.input_file.is_file():
        parser.error("Input file path does not exist.")

    # parse constraints
    constraints_dict = {}
    if args.constraints:
        CONSTRAINTS = {"adder", "multiplier", "subtractor"}
        for item in args.constraints:
            if '=' not in item:
                raise argparse.ArgumentTypeError(f"Constraint '{item}' must match the key=value format (e.g., adder=3).")

            key, val = item.split('=', 1)
            key = key.strip().lower().removesuffix("s") # adders=2 and adder=2 both work

            if key not in CONSTRAINTS:
                raise argparse.ArgumentTypeError(f"Invalid resource '{key}'.")

            try:
                constraints_dict[key] = int(val.strip()) # convert str to int
            except ValueError:
                raise argparse.ArgumentTypeError(f"Value for '{key}' must be an integer (e.g., {key}=3). Got '{val.strip()}' instead.")

            if constraints_dict[key] < 1:
                raise argparse.ArgumentTypeError(f"Value for '{key}' must be at least 1.")

    return (args.input_file, args.export_ssa, args.scheduler, constraints_dict)

def main():
    # step 1: process cmd line args
    input_file, export_ssa, scheduler_mode, constraints_dict = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # step 2: parse input file, construct DAG
    ssa_tokens = hlsp.extractSSA(input_file, export_ssa)
    dag = hlsp.DAG(ssa_tokens)

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
