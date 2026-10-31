from collections import Counter
from math import inf
from typing import Callable, Dict, List, Set
from utils.hlsParser import DAG

class Scheduler:
    """
    Assigns each DAG op to a cycle, without exceeding resource constraints.
    We assume it's 1 cycle / op for our scheduler.
    """
    def __init__(self, dag: DAG, scheduler_mode: str, constraints: Dict[str, int]):
        self.DAG = dag
        self.scheduler_mode = scheduler_mode
        self.constraints = constraints
        # after scheduling, each cycle assigned a List of operations that it does (based on idx of equation in ssa_tokens)
        # cycles  = [[1, 0, 3], [2, 4], ...]
        self.cycles: List[List[int]] = []

    def _listSchedule(self, deps: Dict[int, Set[int]], priority: Callable) -> List[List[int]]:
        """
        Fills one cycle at a time with ops whose deps are all finished.
        When a resource runs out, ops with the lowest priority value go first.
        Without constraints, every ready op fits, so this is the textbook unconstrained schedule.
        """
        cycles = []
        finished = set()

        while len(finished) < len(self.DAG.ops):
            ready = [idx for idx in self.DAG.ops if idx not in finished and deps[idx] <= finished]
            used = Counter()
            cycle = []
            for idx in sorted(ready, key=priority):
                resource = self.DAG.ops[idx]
                if used[resource] < self.constraints.get(resource, inf):
                    used[resource] += 1
                    cycle.append(idx)
            finished.update(cycle)
            cycles.append(sorted(cycle))

        return cycles

    def _criticalPaths(self) -> Dict[int, int]:
        """
        Number of cycles from each op to the end of the longest path through it.
        Ops are in topological order since SSA defines every value before reading it.
        """
        paths = {}
        for idx in sorted(self.DAG.ops, reverse=True):
            paths[idx] = 1 + max((paths[succ] for succ in self.DAG.succs[idx]), default=0)
        return paths

    def scheduler(self) -> None:
        """
        Read DAG, do scheduling
        ASAP   : forward list scheduling, earlier lines first
        ALAP   : ASAP on the reversed DAG (later lines first), then flipped back
        CUSTOM : forward list scheduling, ops on the longest path first, then ops that unblock the most successors
        """
        if self.scheduler_mode == "ASAP":
            self.cycles = self._listSchedule(self.DAG.preds, lambda idx: idx)
        elif self.scheduler_mode == "ALAP":
            self.cycles = self._listSchedule(self.DAG.succs, lambda idx: -idx)[::-1]
        elif self.scheduler_mode == "CUSTOM":
            paths = self._criticalPaths()
            self.cycles = self._listSchedule(self.DAG.preds, lambda idx: (-paths[idx], -len(self.DAG.succs[idx]), idx))
        else:
            raise ValueError(f"Invalid scheduler mode: '{self.scheduler_mode}'")
