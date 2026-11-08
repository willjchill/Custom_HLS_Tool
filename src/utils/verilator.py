from pathlib import Path
from typing import Dict, List
from utils.binding import DATA_WIDTH, Mux, SynthScheduler, inputSwitches

# using synthesized scheduler --> convert to verilog + testbench
# output file order: pre-built modules, hls_core (datapath + FSM), top (board I/O)

FU_MODULES = {"adder": "fu_add", "subtractor": "fu_sub", "multiplier": "fu_mul"}
INPUT_MAX = 3 # 2-bit unsigned input variables
TEST_VECTORS = [[3, 3, 3, 3, 3], [1, 2, 3, 1, 2], [3, 1, 2, 2, 1]] # input variable values, by position
VERILOG_LIB = Path(__file__).resolve().parents[1] / "verilog" # hand-written modules (adder, mux, ...)

def _library() -> str:
    """
    Reads all the pre-built modules (adder, mux, etc) in src/verilog
    """
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(VERILOG_LIB.glob("*.v")))

def _checkWidth(synth: SynthScheduler) -> None:
    """
    Warns if the worst-case value of any variable does not fit in our datapath
    """
    bounds = dict(synth.DAG.constants)
    bounds.update({var: INPUT_MAX for var in synth.DAG.inputs})

    for idx in synth.DAG.ops:
        lhs, op1, op2, op = synth.DAG.ssa_tokens[idx]
        a, b = bounds[op1], bounds[op2]
        bounds[lhs] = {"+": a + b, "-": a, "*": a * b}[op]
        if bounds[lhs] >= 2 ** DATA_WIDTH:
            print(f"[WARNING] {lhs} can overflow {DATA_WIDTH} bits, display will show truncated value.")

def _evaluate(synth: SynthScheduler, vector: List[int]) -> Dict[str, int]:
    """
    Python version of the input equations for the testbench, wraps around like hardware
    """
    values = dict(synth.DAG.constants)
    values.update(zip(synth.DAG.inputs, vector))

    for idx in synth.DAG.ops:
        lhs, op1, op2, op = synth.DAG.ssa_tokens[idx]
        a, b = values[op1], values[op2]
        values[lhs] = {"+": a + b, "-": a - b, "*": a * b}[op] % 2 ** DATA_WIDTH

    return values

def _generateMux(mux: Mux) -> str:
    """
    Single-source muxes become plain wires. Concatenation lists highest idx first.
    """
    if len(mux.sources) == 1:
        return f"    assign {mux.dest} = {mux.sources[0]};"

    sources = ", ".join(reversed(mux.sources))
    return f"    mux #(.WIDTH(WIDTH), .INPUTS({len(mux.sources)})) mux_{mux.dest} (.in({{{sources}}}), .sel({mux.dest}_sel), .out({mux.dest}));"

def _generateControl(synth: SynthScheduler) -> List[str]:
    """
    Control signals only depend on the current step: mux selects, register enables, active FUs
    """
    lines = []

    for mux in synth.muxes.values():
        if len(mux.sources) > 1:
            lines.append(f"    wire [{(len(mux.sources) - 1).bit_length() - 1}:0] {mux.dest}_sel =")
            lines += [f"        (step == {c}) ? {sel} :" for c, sel in mux.selects.items() if sel != 0]
            lines.append("        0;")

    for reg in range(synth.numRegs):
        steps = " || ".join(f"step == {c}" for c in synth.muxes[f"reg_{reg}_d"].selects)
        lines.append(f"    wire reg_{reg}_we = {steps};")

    lines.append(f"    wire [{len(synth.fuTypes) - 1}:0] fu_active;")
    for fu in range(len(synth.fuTypes)):
        steps = " || ".join(f"step == {c}" for c, cycle in enumerate(synth.cycles) if fu in map(synth.opBinding.get, cycle))
        lines.append(f"    assign fu_active[{fu}] = {steps};")

    return lines

def _generateCore(synth: SynthScheduler) -> str:
    """
    Generated part: FSM, muxes, registers and functional units.
    Inputs are the variables and a step pulse, output is the FU we are looking at.
    """
    numFUs = len(synth.fuTypes)
    lastStep = len(synth.cycles) - 1
    wires = lambda nets: f"    wire [WIDTH-1:0] {', '.join(nets)};"

    lines = ["module hls_core #(parameter WIDTH = 32) (",
             "    input  wire             clk,",
             "    input  wire             rst,",
             "    input  wire             step_pulse,   // go to next cycle",
             "    input  wire [4:0]       fu_sel,       // which FU to look at"]
    lines += [f"    input  wire [WIDTH-1:0] in_{var}," for var in synth.DAG.inputs]
    lines += ["    output wire [4:0]       cycle,        // current cycle (starts at 1)",
              "    output wire             last_cycle,",
              "    output wire [WIDTH-1:0] fu_value,     // output of selected FU",
              "    output wire             fu_valid      // selected FU is used in this cycle",
              ");",
              f"    localparam LAST_STEP = {lastStep};",
              "",
              "    // FSM: step counter, stops at last cycle",
              f"    reg [{max(lastStep.bit_length(), 1) - 1}:0] step = 0;",
              "    wire advance = step_pulse && (step != LAST_STEP);",
              "    always @(posedge clk) begin",
              "        if (rst)          step <= 0;",
              "        else if (advance) step <= step + 1;",
              "    end",
              "    assign cycle = 5'd1 + step;",
              "    assign last_cycle = (step == LAST_STEP);",
              "",
              "    // datapath nets",
              wires(f"fu_{fu}_{port}" for fu in range(numFUs) for port in "aby")]
    if synth.numRegs:
        lines.append(wires(f"reg_{reg}_{port}" for reg in range(synth.numRegs) for port in "dq"))

    lines += ["", "    // control", *_generateControl(synth), "", "    // functional units"]
    for fu, resource in enumerate(synth.fuTypes):
        lines.append(f"    {FU_MODULES[resource]} #(.WIDTH(WIDTH)) fu_{fu} (.a(fu_{fu}_a), .b(fu_{fu}_b), .y(fu_{fu}_y));")

    lines += ["", "    // muxes"]
    lines += [_generateMux(mux) for mux in synth.muxes.values()]

    lines += ["", "    // registers"]
    for reg in range(synth.numRegs):
        lines.append(f"    register #(.WIDTH(WIDTH)) reg_{reg} (.clk(clk), .rst(rst), .en(reg_{reg}_we && advance), .d(reg_{reg}_d), .q(reg_{reg}_q));")

    lines += ["", "    // pick which FU to show. shift gives 0 if fu_sel is bigger than last FU",
              f"    wire [WIDTH-1:0] fu_out [0:{numFUs - 1}];"]
    lines += [f"    assign fu_out[{fu}] = fu_{fu}_y;" for fu in range(numFUs)]
    lines += ["    assign fu_value = fu_out[fu_sel];",
              "    assign fu_valid = fu_active >> fu_sel;",
              "endmodule",
              ""]
    return "\n".join(lines)

def _generateTop(synth: SynthScheduler) -> str:
    """
    Top module with buttons, switches, LEDs and 7 segment display. Ports match the board nets mapped in vivadoSynth.tcl
    """
    lines = ["module top #(parameter DEBOUNCE_CYCLES = 1000000) (",
             "    input  wire        CLK100MHZ,",
             "    input  wire        CPU_RESETN,",
             "    input  wire        BTNC,",
             "    input  wire [14:0] SW,",
             "    output wire [15:0] LED,",
             "    output wire [6:0]  SEG,",
             "    output wire        DP,",
             "    output wire [7:0]  AN",
             ");",
             f"    localparam WIDTH = {DATA_WIDTH};",
             "",
             "    // BTNC = step, CPU_RESETN is active low",
             "    wire rst, step_pulse;",
             "    debouncer #(.CYCLES(DEBOUNCE_CYCLES)) debounce_reset (.clk(CLK100MHZ), .btn(~CPU_RESETN), .level(rst), .pulse());",
             "    debouncer #(.CYCLES(DEBOUNCE_CYCLES)) debounce_step (.clk(CLK100MHZ), .btn(BTNC), .level(), .pulse(step_pulse));",
             "",
             "    wire [4:0] cycle;",
             "    wire last_cycle;",
             "    wire [WIDTH-1:0] display_value;",
             "    wire display_valid;",
             "",
             "    hls_core #(.WIDTH(WIDTH)) core (",
             "        .clk(CLK100MHZ), .rst(rst), .step_pulse(step_pulse), .fu_sel(SW[4:0]),"]
    lines += [f"        .in_{var}({{{DATA_WIDTH - 2}'d0, {inputSwitches(i)}}})," for i, var in enumerate(synth.DAG.inputs)]
    lines += ["        .cycle(cycle), .last_cycle(last_cycle), .fu_value(display_value), .fu_valid(display_valid)",
              "    );",
              "",
              "    // 7 segment display shows selected FU, dashes if it is idle",
              "    seven_seg display (.clk(CLK100MHZ), .valid(display_valid), .value(display_value), .an(AN), .seg(SEG));",
              "    assign DP = 1;",
              "",
              "    // LED[4:0] = cycle number from scheduler file, LED[15] = last cycle",
              "    assign LED = {last_cycle, 10'd0, cycle};",
              "endmodule",
              ""]
    return "\n".join(lines)

def _generateTestbench(synth: SynthScheduler) -> str:
    """
    Testbench: goes through every cycle for each test vector and checks every FU
    against the Python version
    """
    numFUs = len(synth.fuTypes)
    lines = ["`timescale 1ns / 1ps",
             "",
             "module tb_top;",
             "    reg clk = 0, resetn = 1, btn = 0;",
             "    reg [14:0] sw = 0;",
             "    wire [15:0] led;",
             "    wire [6:0] seg;",
             "    wire [7:0] an;",
             "    wire dp;",
             "    integer errors = 0;",
             "",
             "    top #(.DEBOUNCE_CYCLES(2)) dut (.CLK100MHZ(clk), .CPU_RESETN(resetn), .BTNC(btn), .SW(sw), .LED(led), .SEG(seg), .DP(dp), .AN(an));",
             "    always #5 clk = ~clk;",
             "",
             "    task press_step;",
             "        begin",
             "            btn = 1; repeat (8) @(posedge clk);",
             "            btn = 0; repeat (8) @(posedge clk);",
             "        end",
             "    endtask",
             "",
             "    task press_reset;",
             "        begin",
             "            resetn = 0; repeat (8) @(posedge clk);",
             "            resetn = 1; repeat (8) @(posedge clk);",
             "        end",
             "    endtask",
             "",
             "    task check_cycle(input [4:0] cycle);",
             "        if (led[4:0] !== cycle) begin",
             "            $display(\"FAIL: LED shows cycle %0d, expected %0d\", led[4:0], cycle);",
             "            errors = errors + 1;",
             "        end",
             "    endtask",
             "",
             "    task check_fu(input [4:0] fu, input [31:0] expected);",
             "        begin",
             "            sw[4:0] = fu; #1;",
             "            if (dut.display_valid !== 1'b1 || dut.display_value !== expected) begin",
             "                $display(\"FAIL: FU %0d shows %0d, expected %0d\", fu, dut.display_value, expected);",
             "                errors = errors + 1;",
             "            end",
             "        end",
             "    endtask",
             "",
             "    task check_idle(input [4:0] fu);",
             "        begin",
             "            sw[4:0] = fu; #1;",
             "            if (dut.display_valid !== 1'b0) begin",
             "                $display(\"FAIL: FU %0d should be idle\", fu);",
             "                errors = errors + 1;",
             "            end",
             "        end",
             "    endtask",
             "",
             "    initial begin"]

    for vector in TEST_VECTORS:
        values = _evaluate(synth, vector)
        lines.append("        press_reset;")
        lines += [f"        {inputSwitches(i).lower()} = {vector[i]};" for i in range(len(synth.DAG.inputs))]

        for c, cycle in enumerate(synth.cycles):
            active = {synth.opBinding[idx]: idx for idx in cycle}
            lines.append(f"        check_cycle({c + 1});")
            for fu in range(min(numFUs + 1, 32)): # one extra FU to check that unused select shows dashes
                if fu in active:
                    lines.append(f"        check_fu({fu}, {values[synth.DAG.ssa_tokens[active[fu]][0]]});")
                else:
                    lines.append(f"        check_idle({fu});")
            lines.append("        press_step;")

    lines += ["        if (errors == 0) $display(\"PASS\");",
              "        else $display(\"FAIL: %0d errors\", errors);",
              "        $finish;",
              "    end",
              "endmodule",
              ""]
    return "\n".join(lines)

def synth2verilog(synth: SynthScheduler, input_file: Path, timestamp: str) -> None:
    """
    Converts bound schedule to Verilog and its testbench, in a new run directory
    """
    _checkWidth(synth)

    # Determine project root and target output directory
    output_dir = Path(__file__).resolve().parents[2] / "output" / "verilog" / f"{input_file.stem}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    top_file = output_dir / f"top_{timestamp}.v"
    top_file.write_text(_library() + "\n" + _generateCore(synth) + "\n" + _generateTop(synth), encoding="utf-8")
    (output_dir / f"tb_top_{timestamp}.v").write_text(_generateTestbench(synth), encoding="utf-8")

    print(f"[DEBUG] Verilog successfully generated!")
    print(f"  • File Name    : {top_file.name}")
    print(f"  • Absolute Path: {top_file.resolve()}")
