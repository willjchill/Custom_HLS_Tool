from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
from utils.hlsParser import DAG
from utils.scheduling import Scheduler

DATA_WIDTH = 32 # matches the 8 hex digits on seven segment display
FU_SELECT_SWITCHES = "SW[4:0]"
FIRST_INPUT_SWITCH = 5 # input variables take 2 switches each, starting after FU select

@dataclass
class Mux:
    """
    Mux insertion in front of a net. A single-source mux is just a wire.
    Example: Mux("fu_0_a", ["in_A_0", "reg_1_q"], {0: 0, 2: 1}) reads reg_1_q in cycle 2
    """
    dest: str
    sources: List[str] = field(default_factory=list)
    selects: Dict[int, int] = field(default_factory=dict)  # cycle --> idx in sources

def inputSwitches(position: int) -> str:
    """
    Switches that drive the input variable at given position in DAG.inputs
    """
    low = FIRST_INPUT_SWITCH + 2 * position
    return f"SW[{low + 1}:{low}]"

# inherits from scheduler --> has its own binding ops for MUX / register w/ constraints
class SynthScheduler(Scheduler):
    def __init__(self, dag: DAG, scheduler_mode: str, constraints: Dict[str, int]):
        super().__init__(dag, scheduler_mode, constraints)
        self.fuTypes: List[str] = []         # FU idx --> resource type
        self.opBinding: Dict[int, int] = {}  # op idx --> FU idx
        self.regBinding: Dict[str, int] = {} # SSA var --> register idx
        self.numRegs = 0
        self.muxes: Dict[str, Mux] = {}      # dest net --> mux in front of it

    def bind(self) -> None:
        """
        Must run after scheduling. Binding order matters, since muxes depend on the other two.
        """
        self._bindFunctionalUnits()
        self._bindRegisters()
        self._insertMuxes()

    def _bindFunctionalUnits(self) -> None:
        """
        Ops in the same cycle get different FUs, and ops in different cycles share them.
        We end up with the minimum FU count for the schedule, which satisfies the constraints.
        """
        fus = defaultdict(list)  # resource type --> FU idxs

        for cycle in self.cycles:
            used = Counter()
            for idx in cycle:
                resource = self.DAG.ops[idx]
                if used[resource] == len(fus[resource]):
                    fus[resource].append(len(self.fuTypes))
                    self.fuTypes.append(resource)
                self.opBinding[idx] = fus[resource][used[resource]]
                used[resource] += 1

    def _bindRegisters(self) -> None:
        """
        Left-edge algorithm. Value is latched at the end of its op's cycle and held until its last read.
        A register can be reused in the same cycle as its last read, since the write happens at the clock edge.
        Values nobody reads need no register: they can be seen at the FU output in their cycle.
        """
        opCycles = {idx: c for c, cycle in enumerate(self.cycles) for idx in cycle}
        lifetimes = []
        for idx, succs in self.DAG.succs.items():
            if succs:
                lifetimes.append((opCycles[idx], max(opCycles[succ] for succ in succs), self.DAG.ssa_tokens[idx][0]))

        lastReads = []  # register idx --> cycle where its current value is last read
        for start, end, var in sorted(lifetimes):
            reg = next((r for r, lastRead in enumerate(lastReads) if lastRead <= start), len(lastReads))
            lastReads[reg:reg + 1] = [end]
            self.regBinding[var] = reg

        self.numRegs = len(lastReads)

    def _sourceNet(self, var: str) -> str:
        """
        Net that holds an SSA var: hard-coded literal, switches, or a register
        """
        if var in self.DAG.constants:
            return f"{DATA_WIDTH}'d{self.DAG.constants[var]}"
        if var in self.DAG.inputs:
            return f"in_{var}"
        return f"reg_{self.regBinding[var]}_q"

    def _connect(self, dest: str, source: str, cycle: int) -> None:
        mux = self.muxes.setdefault(dest, Mux(dest))
        if source not in mux.sources:
            mux.sources.append(source)
        mux.selects[cycle] = mux.sources.index(source)

    def _insertMuxes(self) -> None:
        """
        Every FU operand and register input selects its source based on current cycle
        """
        for c, cycle in enumerate(self.cycles):
            for idx in cycle:
                lhs, op1, op2, _ = self.DAG.ssa_tokens[idx]
                fu = self.opBinding[idx]
                self._connect(f"fu_{fu}_a", self._sourceNet(op1), c)
                self._connect(f"fu_{fu}_b", self._sourceNet(op2), c)
                if lhs in self.regBinding:
                    self._connect(f"reg_{self.regBinding[lhs]}_d", f"fu_{fu}_y", c)

    def exportScheduler(self, input_file: Path, timestamp: str) -> None:
        """
        Prints debug scheduler output, which is the guide for using switches on the FPGA
        """
        lines = [f"Source File : {input_file.name}",
                 f"Scheduler   : {self.scheduler_mode}",
                 f"Constraints : {self.constraints or 'none'}",
                 f"Cycles      : {len(self.cycles)}",
                 f"FUs         : {len(self.fuTypes)}",
                 f"Registers   : {self.numRegs}",
                 f"Muxes       : {sum(len(mux.sources) > 1 for mux in self.muxes.values())}",
                 "",
                 "Input Switches"]
        lines += [f"  {var} : {inputSwitches(i)}" for i, var in enumerate(self.DAG.inputs)]
        lines += [f"  {var} : hard-coded {val}" for var, val in self.DAG.constants.items()]

        lines += ["", f"Functional Units (select with {FU_SELECT_SWITCHES})"]
        for c, cycle in enumerate(self.cycles):
            lines.append(f"Cycle {c + 1}")
            for idx in sorted(cycle, key=self.opBinding.get):
                lhs, op1, op2, op = self.DAG.ssa_tokens[idx]
                fu = self.opBinding[idx]
                reg = f" -> R{self.regBinding[lhs]}" if lhs in self.regBinding else ""
                lines.append(f"  FU {fu:<2} ({self.fuTypes[fu]}) : {lhs} = {op1} {op} {op2}{reg}")

        # Determine project root and target output directory
        output_dir = Path(__file__).resolve().parents[2] / "output" / "metrics"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"scheduler_{input_file.stem}_{timestamp}.txt"

        output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[DEBUG] Scheduler file successfully generated!")
        print(f"  • File Name    : {output_file.name}")
        print(f"  • Absolute Path: {output_file.resolve()}")
