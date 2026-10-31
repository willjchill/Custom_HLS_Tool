class Scheduler:
    def __init__(self):
        self.DAG = None
        self.scheduler_mode = None
        self.constraints = None
        # contains original ssa tokens list
        self.ssa_tokens = None
        # after scheduling, each cycle assigned a List of operations that it does (based on idx of equation in ssa_tokens)
        # cycles  = [[1, 0, 3], [2, 4], ...] 
        self.cycles = []
        # for now, we assume it's 1 cycle / op for our scheduler
        self.opNumCycles = {"adder": 1, "multiplier": 1, "subtractor": 1}

    def scheduler(self):
        # read DAG, do scheduling
        if self.scheduler_mode == "ASAP":
            pass

class DAG:
    def __init__(self):
        pass

    # helps construct SSA to dag, no scheduling yet! 
    def ssa2dag(self):
        pass
