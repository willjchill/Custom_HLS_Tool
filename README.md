# 1.1 Background

High-level synthesis (HLS) tools are essentially an abstraction above RTL. We can have high-level representations of operations (A = B + C) and do many different techniques to essentially synthesize them directly, potentially skipping RTL altogether. Very useful if you don't want to pull your hair out dealing with Verilog and want to continue working with C-like syntax, such as with SystemC library. We will test all of the different stages of HLS in this project.

# 1.2 Objectives

Designing our own constrained high-level synthesis (HLS) tool. This will be able to do single-static assignment (SSA), DAG construction, scheduling (ALAP/ASAP) with resource constraints, binding, and converting this into a Verilog format with various pre-built modules. Since we need a MUX/register-based design during synthesis of control paths and standard operations (e.g. 32-bit floating point addition in input text files), we need to make sure we have all the modules necessary for "synthesis". 

Here are the tangible features of this HLS tool:
- Print out intermediary SSA text file upon command
- Create Verilog file which acts as the end-point of this synthesis tool
- Take advantage of real-world FPGA and automate deployment for easy testing

# 2.1 Input Text File Supported By Our HLS

We will have a text-format that allows for the following rules:

1. Only these arithmetic operations are allowed: (+, -, *)

2. Only one equation per line

3. Each equation will consist of two arguments

4. OPTIONAL: Assignments for initial values are possible (e.g. hard-coded values). We can have X = 4, for instance at the beginning of the text file lines. If not specified, these initial values will all be converted to switches.

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

Note that since there is a maximum of 16 switches on our target Artix-7 FPGA, we will use the 20-line constraint to help adjust what the maximum bit-width of our uninitialized input variables are. To support 20-line maximum, we need 5 bits (e.g. 5 switches to specify functional unit in a single cycle, since worst-case is 20 functional units in a single cycle). Therefore, we have 11 switches availabe to us to output functional unit output. For simplicity, we assume 2-bit variable values; therefore, 2 switches per variable, with a maximum of 5 input variables.

Therefore, we have implicit assumption (3) - (4)

3. Input variables are 2-bit unsigned integers (e.g. hard-coded values are between 0 and 3).

4. We can assume maximum uninitialized input variables of 5. 

# 3.1 Using HLS tool in Python

Make sure you have Vivado and Python installed beforehand (x86 preferred). Useful to have a Artix-7 FPGA compatible with this project.

In order to run this HLS tool, first do

`python3 src/synth.py <test file> --export-ssa --scheduler <mode> --constraints <adders=X> <multipliers=X> <subtractors=X>`

If you include the `--export-ssa` flag, an output file with the intermediary SSA text file will be printed for debugging. Regardless, each run of synth.py will generate a debug scheduler output that specifies all the functional units (and their corresponding index) for each "cycle" within the datapath. This will help with debugging and using the input switches on the FPGA after synthesizing the resulting Verilog later.

If you include `--scheduler` flag, you can run different modes:
- **ASAP**: as soon as possible scheduler. Constraints can be specified by user.
- **ALAP**: as late as possible scheduler. Constraints can be specified by user.
- **CUSTOM**: Our own custom experimental scheduler with various heuristics. Can include constraints if specified by user.

Main HLS synthesis script will also automatically generate verilog and testbenches that are ready-to-use for Artix-7 FPGA. 

# 3.2 Synthesizing Verilog output

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

### 3.3. Fast Bitstream Programming (Skipping Synthesis)

Since synthesis and implementation can take several minutes, use `vivadoBitstream.tcl` to quickly send an already-generated bitstream directly to the FPGA hardware:

```bash
# Automatically finds and sends the most recently generated bitstream:
vivado -mode batch -source vivadoBitstream.tcl

# Or specify a specific directory or bitstream:
vivado -mode batch -source vivadoBitstream.tcl -tclargs --output_dir output/verilog/<model>_<timestamp>
vivado -mode batch -source vivadoBitstream.tcl -tclargs --bitstream output/verilog/<model>_<timestamp>/top.bit
```

### 4. Project Hierarchy

```
.
├── README.md
├── .gitignore
├── vivadoSynth.tcl
├── vivadoBitstream.tcl
├── output
│   ├── fpga
│   │   ├── report_<timestamp>.log
│   │   └── program_<timestamp>.log
│   ├── metrics
│   │   ├── SSA_<test file name>_<timestamp>.txt
│   │   └── scheduler_<test file name>_<timestamp>.txt
│   └── verilog
│       ├── Nexys4DDR_Master.xdc
│       └── <test file name>_<timestamp>
│           ├── auto_pins.xdc
│           ├── top_<timestamp>.v
│           ├── tb_top_<timestamp>.v
│           └── top.bit (generated by Vivado)
├── src
│   ├── synth.py
│   └── utils
│       ├── hlsParser.py
│       ├── scheduling.py
│       ├── binding.py
│       └── verilator.py
└── testcases
    ├── example1.txt
    └── example2.txt
```

Note that "metrics" contains any debug output from main Python program. hlsParser converts text file and creates SSA. It also contains the DAG object definition, which will be used for scheduling and binding operations in their respective files. A generic Scheduler object which has-a DAG object and has-a List which specifies MUX/Register insertions in scheduled DAG. The final, populated Scheduler after binding and resource-constrained scheduling methods should be enough information to convert into standard Verilog file. This conversion is specified in verilator. 

------------

Last updated 1/1/2026
William Desueza
