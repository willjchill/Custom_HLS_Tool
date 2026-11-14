# 1.1 Background

High-level synthesis (HLS) tools are essentially an abstraction above RTL. We can have high-level representations of operations (A = B + C) and do many different techniques to essentially synthesize them directly, potentially skipping RTL altogether. Very useful if you don't want to pull your hair out dealing with Verilog and want to continue working with C-like syntax, such as with SystemC library. We will test all of the different stages of HLS in this project.

# 1.2 Objectives

Designing our own constrained high-level synthesis (HLS) tool. This will be able to do single-static assignment (SSA), DAG construction, scheduling (ALAP/ASAP) with resource constraints, binding, and converting this into a Verilog format with various pre-built modules. Since we need a MUX/register-based design during synthesis of control paths and standard operations (e.g. 32-bit unsigned addition, subtraction and multiplication in input text files), we need to make sure we have all the modules necessary for "synthesis".

Here are the tangible features of this HLS tool:
- Print out intermediary SSA text file upon command
- Create Verilog file which acts as the end-point of this synthesis tool
- Take advantage of real-world FPGA and automate deployment for easy testing

# 2.1 Input Text File Supported By Our HLS

We will have a text-format that allows for the following rules:

1. Only these arithmetic operations are allowed: (+, -, *)

2. Only one equation per line

3. Each equation will consist of two arguments

4. OPTIONAL: Assignments for initial values are possible (e.g. hard-coded values). We can have X = 2, for instance at the beginning of the text file lines. If not specified, these initial values will all be converted to switches.

For example,

```
X = 2
X = A + B
Y = X + A
Z = X - B
Q = B * Z
```

There are two important assumptions:

1. We can assume maximum of 20 lines in input text file.

2. We can assume that output results are always positive.

This is helpful since we do not have to worry about negative number outputs on seven segment display or excessively using input switches to choose line number in text file for debug output!

Note that since there is a maximum of 16 switches on our target Artix-7 FPGA, we will use the 20-line constraint to help adjust what the maximum bit-width of our uninitialized input variables are. To support 20-line maximum, we need 5 bits (e.g. 5 switches to specify functional unit in a single cycle, since worst-case is 20 functional units in a single cycle). Therefore, we have 11 switches available to us to input variables. For simplicity, we assume 2-bit variable values; therefore, 2 switches per variable, with a maximum of 5 input variables.

Therefore, we have implicit assumption (3) - (4)

3. Input variables are 2-bit unsigned integers (e.g. hard-coded values are between 0 and 3).

4. We can assume maximum uninitialized input variables of 5. 

# 3.1 Using HLS tool in Python

Make sure you have Python 3.9+ installed beforehand. You only need Vivado for the FPGA part (x86 preferred), and note that Vivado does not run on Mac, so use a Windows or Linux computer for that. Useful to have a Artix-7 FPGA compatible with this project (we use the Nexys 4 DDR).

In order to run this HLS tool, first do

`python3 src/synth.py <test file> --export-ssa --scheduler <mode> --constraints adders=X multipliers=X subtractors=X`

For example: `python3 src/synth.py testcases/example1.txt --export-ssa --scheduler ASAP --constraints adders=1 multipliers=1`

If you include the `--export-ssa` flag, an output file with the intermediary SSA text file will be printed for debugging. Regardless, each run of synth.py will generate a debug scheduler output that specifies all the functional units (and their corresponding index) for each "cycle" within the datapath. This will help with debugging and using the input switches on the FPGA after synthesizing the resulting Verilog later.

If you include `--scheduler` flag, you can run different modes:
- **ASAP**: as soon as possible scheduler. Constraints can be specified by user.
- **ALAP**: as late as possible scheduler. Constraints can be specified by user.
- **CUSTOM**: Our own scheduler. Works like ASAP, but when there are not enough units, the operations on the longest chain go first. Constraints can be specified by user.

`--constraints` is optional. If a resource is not listed, we assume unlimited.

Main HLS synthesis script will also automatically generate verilog and testbenches that are ready-to-use for Artix-7 FPGA. 

# 3.2 Simulating the Verilog (no board needed)

The generated testbench goes through every cycle for 3 sets of input values and checks every functional unit. It prints `PASS` or `FAIL` at the end.

```bash
# Mac: brew install icarus-verilog
iverilog -g2012 -o sim output/verilog/<test file name>_<timestamp>/top_<timestamp>.v output/verilog/<test file name>_<timestamp>/tb_top_<timestamp>.v
vvp sim
```

# 3.3 Synthesizing Verilog output

For PHO115 lab computers, use C:\Xilinx\Vivado\2024.1\bin\vivado.bat instead of vivado in Windows Powershell to avoid alias or PATH issues.

```bash
# Run with Vivado in batch mode (automatically picks the most recent Verilog run directory):
vivado -mode batch -source vivadoSynth.tcl

# Or specify a specific output directory:
vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir output/verilog/<model>_<timestamp>

# Or directly execute the script:
./vivadoSynth.tcl [--output_dir <path>]
```

Features:
- **Automatic I/O Mapping**: Check debug scheduler text output to see what functional units exist in each cycle number, and which switches drive each input variable. Functional unit numbers are the same across all cycles. Set input switches right after reset, since registers keep results that were already latched.

| Board I/O | Function |
| --- | --- |
| `SW[4:0]` | Functional unit number to show on 7 segment display |
| `SW[14:5]` | 2-bit input variables, in order of first use (first variable is `SW[6:5]`) |
| 7 segment display | Functional unit output in current cycle, as 8 hex digits. Dashes mean that unit is idle this cycle |
| `BTNC` | Step to next cycle (e.g. "clocking"), stops at last cycle |
| `CPU_RESETN` | Reset back to first cycle |
| `LED[4:0]` | Current cycle number |
| `LED[15]` | On during last cycle |

- **Target Part**: `xc7a100tcsg324-1` (Artix-7, Package `csg324`, Speed `-1`).
- **Constraints**: Generates `auto_pins.xdc` inside the Verilog run directory referencing board pins from `output/verilog/Nexys4DDR_Master.xdc`.
- **Hardware Programming**: Connects to the Vivado Hardware Manager and automatically programs connected FPGA hardware.
- **Reporting**: Logs full execution status, debug details, FPGA I/O pin mappings, post-synthesis timing & power reports, and post-implementation timing & power reports to `output/fpga/report_<timestamp>.log`.

### 3.4. Fast Bitstream Programming (Skipping Synthesis)

Since synthesis and implementation can take several minutes, use `vivadoBitstream.tcl` to quickly send an already-generated bitstream directly to the FPGA hardware:

```bash
# Automatically finds and sends the most recently generated bitstream:
vivado -mode batch -source vivadoBitstream.tcl

# Or specify a specific directory or bitstream:
vivado -mode batch -source vivadoBitstream.tcl -tclargs --output_dir output/verilog/<model>_<timestamp>
vivado -mode batch -source vivadoBitstream.tcl -tclargs --bitstream output/verilog/<model>_<timestamp>/top.bit
```

# 4. Tool Architecture

```
text file --> SSA --> DAG --> scheduling --> binding --> Verilog + testbench
          hlsParser.py        scheduling.py   binding.py   verilator.py
```

1. **SSA** (`hlsParser.py`): every time a variable is written it gets a new name (writing `X` twice gives `X_0` and `X_1`). Variables that are read before they are written are the input variables (like `A_0`).
2. **DAG** (`hlsParser.py`): each operation is a node, and an edge means one operation uses the result of another.
3. **Scheduling** (`scheduling.py`): gives each operation a cycle (1 cycle per operation) without going over the adder / subtractor / multiplier limits. ASAP and CUSTOM start from the inputs, ALAP starts from the end.
4. **Binding** (`binding.py`): picks the hardware for each operation.
   - Functional units: operations in the same cycle need different units, but operations in different cycles can share one. So we end up with the minimum number of units for the schedule.
   - Registers: a result that is used in a later cycle gets saved in a register at the end of its cycle. After its last use, the register can be reused (left-edge algorithm).
   - Muxes: every unit input and register input has a mux to choose its source in each cycle. If there is only one source it is just a wire.
5. **Verilog** (`verilator.py`): writes `hls_core` (FSM, muxes, registers, functional units) and `top` (debouncers, switches, LEDs, 7 segment display). The pre-built modules like adder and mux are in `src/verilog`. Everything is put in one `top_<timestamp>.v` file so Vivado only needs to read that one.

The FSM is just a step counter. Mux selects, register write enables and which units are active all depend on the current step, and the step goes up every time `BTNC` is pressed. Registers only get written when the step changes, so the results stay on the display until the next press.

# 5. Project Hierarchy

```
.
├── README.md
├── .gitignore
├── vivadoSynth.tcl
├── vivadoBitstream.tcl
├── sample_output
│   └── example1/example2: _ssa.txt, _schedule.txt, _top.v, _tb.v (copies of generated files)
├── output
│   ├── fpga
│   │   ├── report_<timestamp>.log
│   │   └── program_<timestamp>.log
│   ├── metrics
│   │   ├── SSA_<test file name>_<timestamp>.txt
│   │   └── scheduler_<test file name>_<timestamp>.txt
│   └── verilog
│       ├── Nexys4DDR_Master.xdc
│       └── <test file name>_<timestamp>
│           ├── auto_pins.xdc
│           ├── top_<timestamp>.v
│           ├── tb_top_<timestamp>.v
│           └── top.bit (generated by Vivado)
├── src
│   ├── synth.py
│   ├── utils
│   │   ├── hlsParser.py
│   │   ├── scheduling.py
│   │   ├── binding.py
│   │   └── verilator.py
│   └── verilog
│       ├── fu_add.v
│       ├── fu_sub.v
│       ├── fu_mul.v
│       ├── mux.v
│       ├── register.v
│       ├── debouncer.v
│       └── seven_seg.v
└── testcases
    ├── example1.txt
    └── example2.txt
```

Note that "metrics" contains any debug output from main Python program. hlsParser converts text file and creates SSA. It also contains the DAG object definition, which will be used for scheduling and binding operations in their respective files. A generic Scheduler object which has-a DAG object and has-a List which specifies MUX/Register insertions in scheduled DAG. The final, populated Scheduler after binding and resource-constrained scheduling methods should be enough information to convert into standard Verilog file. This conversion is specified in verilator. 

`sample_output` has the generated files for `example1.txt` and `example2.txt` (ASAP with 1 adder, 1 subtractor, 1 multiplier), so you can look at them without running anything.

# 6. 30-Minute Demo Plan

Note that Vivado time depends on the computer, so check how long it takes when practicing and change the live run times if needed.

Before the demo starts:
- Board plugged in, Vivado open on a Windows/Linux computer, terminal open in the repo folder.
- Run `example1.txt` through Vivado beforehand so we have a `top.bit` as backup.
- Test the Python tool and `iverilog` (or Vivado simulator) on this computer.

| Time | What we do | What we show |
| --- | --- | --- |
| 0:00 - 3:00 | Explain the flow from section 4 and our assumptions (max 20 lines, positive results, 2-bit inputs, max 5 uninitialized inputs, 1 cycle per operation) | Architecture |
| 3:00 - 8:00 | Run `example1.txt` or `example2.txt`  with `--export-ssa` and open the SSA file. Then run ASAP, ALAP and CUSTOM, with and without `--constraints adders=1`, and compare the scheduler files | SSA, DAG, all schedulers, constraints, binding |
| 8:00 - 10:00 | Open the generated `top_<timestamp>.v` (either `example1.txt` or `example2.txt`)  and go through `hls_core` and `top`. | Generated Verilog, testbench |
| 10:00 - 12:00 | Program the backup bitstream for the examples (again either works). Press reset, set `SW[6:5]` and `SW[8:7]`, step with `BTNC`. Change `SW[4:0]` to look at each unit | Button clocking, unit select switches, reset, LEDs, dashes on idle units |
| 12:00 - 27:00 | Three live runs with equations from the professor, 5 minutes each (see below) | Whole flow on new input |
| 27:00 - 30:00 | Summary, what we could improve (more input bits, better schedulers), questions | |

Each live run:
1. Professor writes the equations in a new text file and picks the scheduler and constraints.
2. Run `python3 src/synth.py <file> --export-ssa --scheduler <mode> --constraints ...` and open the scheduler file. It says which switches are the inputs and which unit does what in each cycle.
3. Start `vivado -mode batch -source vivadoSynth.tcl` right away. While it runs, simulate the testbench with `iverilog` and work out the expected values by hand for the switch values the professor picks.
4. Once the board is programmed: reset, set the input switches, press `BTNC` and compare each unit output with the hand-calculated values.

If the professor has no preference for the three runs:
- Run 1: ASAP, no constraints.
- Run 2: ASAP or CUSTOM with `adders=1 multipliers=1`, to show the extra cycles and the shared registers / muxes.
- Run 3: ALAP, with a variable that is assigned twice (SSA renaming).

Backup plans:
- If Vivado takes too long, keep explaining the scheduler file and testbench while it runs. We still have the `example1.txt` bitstream to show on the board.
- If the input breaks a rule (more than 5 inputs, more than 20 lines, value above 3), the tool stops and prints which rule it broke.
- If the board does not work, show the testbench simulation and the scheduler file instead.

AI Disclosure:
AI was used to help understand and debugging the codes as well as tcl files for ease of launch, testing and demo purposes. All works and plans are our own.

------------

Last updated 11/13/2026
Thinh 
