from pathlib import Path
import re
from typing import Dict, List, Set
from datetime import datetime

MAX_INPUT_VARS = 5 # 2 switches per variable (see README section 2.1)

def _tokenize_file(input_file: Path) -> List[List[str]]:
    """
    Helper function that goes through every line of input text,
    cleans it up, and returns list of tokens.

    Example:
    X = 1
    X = A + B
    Y = B + C
    [[X, 1], [X, A, B, +], [Y, B, C, +], ..]
    """
    tokens_per_line = []
    # using regex to split line
    LINE_PATTERN = re.compile(
        r"^(?P<lhs>[a-zA-Z_]\w*)\s*=\s*(?:"
        r"(?P<op1>[a-zA-Z_]\w*)\s*(?P<op>[+\-*])\s*(?P<op2>[a-zA-Z_]\w*)"
        r"|"
        r"(?P<val>\d+)"
        r")$"
    )

    # read lines and convert them into proper list format
    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # tokenize --> make sure it conforms to correct line pattern
            match = LINE_PATTERN.fullmatch(line)
            if not match:
                raise ValueError(f"Invalid statement syntax: '{line}'")
            # adding lines
            if match.group("op"):
                tokens_per_line.append([match.group("lhs"), match.group("op1"), match.group("op2"), match.group("op")]) # real ops
            else:
                if int(match.group("val")) > 3:
                    raise ValueError(f"Invalid hard-coded assignment. Integer must be between 0-3: '{line}'")
                tokens_per_line.append([match.group("lhs"), match.group("val")]) # hard-coded assignment

    if len(tokens_per_line) > 20:
        raise ValueError(f"Lines in file exceeds maximum of 20: {len(tokens_per_line)} lines total")

    return tokens_per_line

def text2SSA(input_file: Path) -> List[List[str]]:
    """
    Takes in input text file, parses it, converts it to SSA
    example:
    input_file -> [[X, A, B, +], [X, C, D, *]] -> [[X_0, A_0, B_0, +], [X_1, C_0, D_0, *]]
    """
    # step 1. parse equations
    eqnList = _tokenize_file(input_file)

    # step 2. convert to SSA format
    write_var_seen = {}  # var name --> count (iterates), use to do SSA and notice WAW 

    for i, eqn in enumerate(eqnList):
        if len(eqn) == 2:
            # Hardcoded assignment: [lhs, val]
            lhs, val = eqn
            write_var_seen[lhs] = write_var_seen.get(lhs, -1) + 1
            eqnList[i] = [f"{lhs}_{write_var_seen[lhs]}", val]
            
        elif len(eqn) == 4:
            # Operation: [lhs, op1, op2, op]
            lhs, op1, op2, op = eqn
            new_op1 = f"{op1}_{write_var_seen.setdefault(op1, 0)}"
            new_op2 = f"{op2}_{write_var_seen.setdefault(op2, 0)}"
            
            write_var_seen[lhs] = write_var_seen.get(lhs, -1) + 1
            new_lhs = f"{lhs}_{write_var_seen[lhs]}"
            
            eqnList[i] = [new_lhs, new_op1, new_op2, op]

    return eqnList

def extractSSA(input_file: Path, printSSA: bool) -> List[List[str]]:
    """
    Return SSA and print out file to correct location if necessary
    """
    # Convert input file to SSA token list
    ssa_tokens = text2SSA(input_file)
    if not printSSA:
        return ssa_tokens
    
    # Format tokens back into readable text lines
    # e.g., [X_0, A_0, B_0, +] -> "X_0 = A_0 + B_0"
    lines = []
    for eqn in ssa_tokens:
        if len(eqn) == 2:
            # Hardcoded assignment: [lhs, val]
            lines.append(f"{eqn[0]} = {eqn[1]}")
        elif len(eqn) == 4:
            # Operation: [lhs, op1, op2, op]
            lines.append(f"{eqn[0]} = {eqn[1]} {eqn[3]} {eqn[2]}")

    # Determine project root and target output directory
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "output" / "metrics"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Construct unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text_file_name = input_file.stem  # e.g., "example1" from "example1.txt"
    output_file = output_dir / f"SSA_{text_file_name}_{timestamp}.txt"
    
    # Write lines to file
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8") 
    print(f"[DEBUG] SSA file successfully generated!")
    print(f"  • File Name    : {output_file.name}")
    print(f"  • Absolute Path: {output_file.resolve()}")
    return ssa_tokens

class DAG:
    """
    Data dependency graph of SSA operations. Nodes are ops, named by their idx in ssa_tokens.
    Hard-coded assignments are not nodes, since they need no functional unit.

    Example:
    [[X_0, A_0, B_0, +], [Y_0, X_0, A_0, *]] -> preds = {0: {}, 1: {0}}, succs = {0: {1}, 1: {}}
    """
    OP_RESOURCES = {"+": "adder", "-": "subtractor", "*": "multiplier"}

    def __init__(self, ssa_tokens: List[List[str]]):
        self.ssa_tokens = ssa_tokens
        self.constants: Dict[str, int] = {}  # SSA var --> hard-coded value
        self.inputs: List[str] = []          # SSA vars driven by switches, in order of first use
        self.ops: Dict[int, str] = {}        # op idx --> resource type
        self.preds: Dict[int, Set[int]] = {} # op idx --> ops it depends on
        self.succs: Dict[int, Set[int]] = {} # op idx --> ops that depend on it
        self.ssa2dag()

    def ssa2dag(self) -> None:
        """
        Constructs DAG from SSA tokens, no scheduling yet!
        SSA leaves only read-after-write dependencies, so each operand has one possible writer.
        """
        writers = {}  # SSA var --> op idx that produces it

        for idx, eqn in enumerate(self.ssa_tokens):
            if len(eqn) == 2:
                self.constants[eqn[0]] = int(eqn[1])
                continue

            lhs, op1, op2, op = eqn
            self.ops[idx] = self.OP_RESOURCES[op]
            self.preds[idx], self.succs[idx] = set(), set()
            for operand in (op1, op2):
                if operand in writers:
                    self.preds[idx].add(writers[operand])
                    self.succs[writers[operand]].add(idx)
                elif operand not in self.constants and operand not in self.inputs:
                    self.inputs.append(operand)
            writers[lhs] = idx

        # invariants
        if not self.ops:
            raise ValueError("Input file has no arithmetic operations to synthesize.")
        if len(self.inputs) > MAX_INPUT_VARS:
            raise ValueError(f"Uninitialized input variables exceeds maximum of {MAX_INPUT_VARS}: {self.inputs}")
