from pathlib import Path
import re
from typing import List, Optional
from datetime import datetime

def _tokenize_file(input_file: Path) -> List[List[str]]:
    """
    Helper function that goes through every line of input text,
    cleans it up, and returns list of tokens.

    Example:
    X = 1
    X = A + B
    Y = B + C
    [[X, 1], [X, A, B, +], [Y, B, C, -], ..]]
    """
    # invariant
    with input_file.open("r", encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)
    if total_lines > 20:
        raise ValueError(f"Lines in file exceeds maximum of 20: {total_lines} lines total")

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
            if not match.group("lhs").isidentifier():
                raise ValueError(f"Invalid variable name: '{line}'")
            # adding lines
            if match.group("op"):
                tokens_per_line.append([match.group("lhs"), match.group("op1"), match.group("op2"), match.group("op")]) # real ops
            else:
                if int(match.group("val")) < 0 and int(match.group("val")) > 3:
                    raise ValueError(f"Invalid hard-coded assignment. Integer must be between 0-3: '{line}'")
                tokens_per_line.append([match.group("lhs"), match.group("val")]) # hard-coded assignment

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

if __name__ == "__main__":
    print("Debug")
    test = Path("../../testcases/example2.txt") # make sure to run this test in utils
    print(extractSSA(test, True))
