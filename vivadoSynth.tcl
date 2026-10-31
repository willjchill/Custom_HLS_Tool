#!/bin/sh
# \
if command -v vivado >/dev/null 2>&1; then \
  exec vivado -mode batch -source "$0" -notrace -tclargs "$@"; \
else \
  exec tclsh "$0" "$@"; \
fi

# ==============================================================================
# vivadoSynth.tcl
# Automated Vivado Synthesis, Implementation, Timing/Power Analysis, Bitstream,
# and Programming flow
#
# Target Part Specification:
#   Product category: All
#   Family:           Artix-7
#   Package:          csg324
#   Speed:            -1
#   Part:             xc7a100tcsg324-1 (Digilent Nexys 4 DDR)
#
# Usage:
#   vivado -mode batch -source vivadoSynth.tcl [-tclargs --output_dir <path>]
#   ./vivadoSynth.tcl [--output_dir <path>]
# ==============================================================================

if {[info script] ne ""} {
    set script_path [file normalize [info script]]
    set repo_dir [file dirname $script_path]
} else {
    set repo_dir [pwd]
}

# ------------------------------------------------------------------------------
# 1. Parse Command Line Arguments
# ------------------------------------------------------------------------------
set target_dir ""
for {set i 0} {$i < $argc} {incr i} {
    set opt [lindex $argv $i]
    if {$opt eq "--output_dir" || $opt eq "-output_dir"} {
        incr i
        if {$i < $argc} {
            set target_dir [lindex $argv $i]
        }
    }
}

if {$target_dir ne "" && [file pathtype $target_dir] eq "relative"} {
    set target_dir [file normalize [file join $repo_dir $target_dir]]
}

# ------------------------------------------------------------------------------
# 2. If no directory specified, find the most recent output run directory
# ------------------------------------------------------------------------------
proc compare_mtime {a b} {
    set ma [file mtime $a]
    set mb [file mtime $b]
    if {$ma < $mb} { return -1 }
    if {$ma > $mb} { return 1 }
    return [string compare $a $b]
}

if {$target_dir eq ""} {
    set verilog_base [file join $repo_dir "output" "verilog"]
    set candidate_dirs [glob -nocomplain -types d [file join $verilog_base "*"]]
    set valid_dirs {}
    foreach d $candidate_dirs {
        set top_files [glob -nocomplain [file join $d "top*.v"]]
        if {[llength $top_files] > 0} {
            lappend valid_dirs $d
        }
    }
    if {[llength $valid_dirs] == 0} {
        puts "ERROR: No Verilog output run directory containing top*.v found in $verilog_base"
        exit 1
    }
    set sorted_dirs [lsort -decreasing -command compare_mtime $valid_dirs]
    set target_dir [lindex $sorted_dirs 0]
    puts "INFO: No output directory specified. Using most recent directory: $target_dir"
} else {
    puts "INFO: Using specified output directory: $target_dir"
}

if {![file isdirectory $target_dir]} {
    puts "ERROR: Directory does not exist: $target_dir"
    exit 1
}

# ------------------------------------------------------------------------------
# 3. Locate Top Structural Verilog Source File
# ------------------------------------------------------------------------------
set top_files [glob -nocomplain [file join $target_dir "top*.v"]]
set valid_top {}
foreach f $top_files {
    if {![string match "tb_*" [file tail $f]]} {
        lappend valid_top $f
    }
}
if {[llength $valid_top] == 0} {
    puts "ERROR: No structural Verilog top file found in $target_dir"
    exit 1
}
set top_file [lindex $valid_top 0]
puts "INFO: Found top Verilog file: $top_file"

# ------------------------------------------------------------------------------
# 4. Top Port -> Board Net Mapping (ports are fixed by src/utils/verilator.py)
# ------------------------------------------------------------------------------
# Each entry: {port, net name in master XDC, role}
set port_map {
    {"CLK100MHZ"  "clk100mhz"  "100 MHz clock"}
    {"CPU_RESETN" "cpu_resetn" "Reset button"}
    {"BTNC"       "btnc"       "Step button"}
    {"DP"         "dp"         "Display decimal point"}
}
for {set i 0} {$i < 5} {incr i} {
    lappend port_map [list "SW\[$i\]" "sw\[$i\]" "FU select bit $i"]
}
for {set i 5} {$i < 15} {incr i} {
    set var_idx [expr {($i - 5) / 2}]
    lappend port_map [list "SW\[$i\]" "sw\[$i\]" "Input variable $var_idx"]
}
for {set i 0} {$i < 5} {incr i} {
    lappend port_map [list "LED\[$i\]" "led\[$i\]" "Cycle number bit $i"]
}
for {set i 5} {$i < 15} {incr i} {
    lappend port_map [list "LED\[$i\]" "led\[$i\]" "Unused (off)"]
}
lappend port_map [list "LED\[15\]" "led\[15\]" "Last cycle flag"]
for {set i 0} {$i < 7} {incr i} {
    set segment [lindex {ca cb cc cd ce cf cg} $i]
    lappend port_map [list "SEG\[$i\]" $segment "Display segment"]
}
for {set i 0} {$i < 8} {incr i} {
    lappend port_map [list "AN\[$i\]" "an\[$i\]" "Display digit $i"]
}

# ------------------------------------------------------------------------------
# 5. Read FPGA Board Pins from Master XDC (Digilent Nexys 4 DDR - xc7a100tcsg324-1)
# ------------------------------------------------------------------------------
set master_xdc [file join $repo_dir "output" "verilog" "Nexys4DDR_Master.xdc"]
if {![file exists $master_xdc]} {
    puts "ERROR: Master constraints file not found: $master_xdc"
    exit 1
}

set fp [open $master_xdc r]
foreach line [split [read $fp] "\n"] {
    if {[regexp {PACKAGE_PIN\s+(\S+)\s+IOSTANDARD\s+(\S+).*Sch=(\S+)} $line -> pin iostd net]} {
        set board_pins($net) [list $pin $iostd]
    }
}
close $fp

# ------------------------------------------------------------------------------
# 6. Generate XDC Constraints File (auto_pins.xdc)
# ------------------------------------------------------------------------------
set generated_xdc [file join $target_dir "auto_pins.xdc"]
set xdc_fp [open $generated_xdc w]
puts $xdc_fp "## =============================================================================="
puts $xdc_fp "## Auto-generated constraints for [file tail $top_file]"
puts $xdc_fp "## Target: Nexys 4 DDR (xc7a100tcsg324-1)"
puts $xdc_fp "## =============================================================================="
puts $xdc_fp ""

set mapping_table {}
foreach entry $port_map {
    lassign $entry port net role
    if {![info exists board_pins($net)]} {
        puts "ERROR: Board net '$net' not found in $master_xdc"
        exit 1
    }
    lassign $board_pins($net) pin iostd
    puts $xdc_fp "set_property -dict { PACKAGE_PIN $pin IOSTANDARD $iostd } \[get_ports { $port }\]; # $role"
    lappend mapping_table [list $port $net $pin $iostd $role]
}

puts $xdc_fp ""
puts $xdc_fp "## Clock"
puts $xdc_fp "create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} \[get_ports { CLK100MHZ }\];"
puts $xdc_fp ""
puts $xdc_fp "## Datapath only moves on a debounced button press, so it has many clocks to settle"
puts $xdc_fp "set datapath_regs \[get_cells -hierarchical -filter { NAME =~ *q_reg* || NAME =~ *step_reg* }\]"
puts $xdc_fp "set_multicycle_path 8 -setup -from \$datapath_regs"
puts $xdc_fp "set_multicycle_path 7 -hold -from \$datapath_regs"
close $xdc_fp
puts "INFO: Auto-generated constraints written to: $generated_xdc"

# ------------------------------------------------------------------------------
# 7. Setup Output Report Directory & File
# ------------------------------------------------------------------------------
set ts [clock format [clock seconds] -format "%Y%m%d_%H%M%S"]
set fpga_dir [file join $repo_dir "output" "fpga"]
file mkdir $fpga_dir
set report_file [file join $fpga_dir "report_${ts}.log"]

# ------------------------------------------------------------------------------
# 8. Run Synthesis, Implementation, Bitstream & Programming
# ------------------------------------------------------------------------------
set in_vivado [expr {[llength [info commands synth_design]] > 0}]
set synth_status "NOT_RUN"
set synth_timing_status "NOT_RUN"
set synth_power_status "NOT_RUN"
set impl_status "NOT_RUN"
set impl_timing_status "NOT_RUN"
set impl_power_status "NOT_RUN"
set bit_status "NOT_RUN"
set hw_status "NOT_RUN"
set overall_status "SUCCESS"
set debug_log {}
set bitstream_file [file join $target_dir "top.bit"]
set post_synth_timing_file [file join $target_dir "post_synth_timing.rpt"]
set post_synth_power_file [file join $target_dir "post_synth_power.rpt"]
set post_impl_timing_file [file join $target_dir "post_impl_timing.rpt"]
set post_impl_power_file [file join $target_dir "post_impl_power.rpt"]

set post_synth_timing_rpt ""
set post_synth_power_rpt ""
set post_impl_timing_rpt ""
set post_impl_power_rpt ""

if {$in_vivado} {
    puts "================================================================================"
    puts "RUNNING VIVADO SYNTHESIS FLOW (xc7a100tcsg324-1)"
    puts "================================================================================"

    # Step 8.1: Synthesis
    if {[catch {
        set_part "xc7a100tcsg324-1"
        read_verilog $top_file
        read_xdc $generated_xdc
        synth_design -top top -part "xc7a100tcsg324-1"
        set synth_status "SUCCESS"
        lappend debug_log "synth_design completed successfully."
    } err]} {
        set synth_status "FAILED"
        set overall_status "FAILED"
        lappend debug_log "synth_design error: $err"
    }

    # Step 8.1.1: Post-Synthesis Timing and Power Reports
    if {$synth_status eq "SUCCESS"} {
        puts "INFO: Generating post-synthesis timing report..."
        if {[catch {
            report_timing_summary -file $post_synth_timing_file -report_unconstrained -max_paths 10
            if {[file exists $post_synth_timing_file]} {
                set fp [open $post_synth_timing_file r]
                set post_synth_timing_rpt [read $fp]
                close $fp
                set synth_timing_status "SUCCESS"
                lappend debug_log "Post-synthesis timing report generated: $post_synth_timing_file"
            } else {
                set post_synth_timing_rpt "Report file not created."
                set synth_timing_status "FAILED (File not found)"
            }
        } err]} {
            set synth_timing_status "FAILED"
            set post_synth_timing_rpt "Error generating post-synthesis timing report: $err"
            lappend debug_log "Post-synthesis timing error: $err"
        }

        puts "INFO: Generating post-synthesis power report..."
        if {[catch {
            report_power -file $post_synth_power_file
            if {[file exists $post_synth_power_file]} {
                set fp [open $post_synth_power_file r]
                set post_synth_power_rpt [read $fp]
                close $fp
                set synth_power_status "SUCCESS"
                lappend debug_log "Post-synthesis power report generated: $post_synth_power_file"
            } else {
                set post_synth_power_rpt "Report file not created."
                set synth_power_status "FAILED (File not found)"
            }
        } err]} {
            set synth_power_status "FAILED"
            set post_synth_power_rpt "Error generating post-synthesis power report: $err"
            lappend debug_log "Post-synthesis power error: $err"
        }
    } else {
        set synth_timing_status "SKIPPED"
        set synth_power_status "SKIPPED"
        set post_synth_timing_rpt "Post-synthesis timing report skipped due to synthesis failure."
        set post_synth_power_rpt "Post-synthesis power report skipped due to synthesis failure."
    }

    # Step 8.2: Implementation
    if {$synth_status eq "SUCCESS"} {
        if {[catch {
            opt_design
            place_design
            route_design
            set impl_status "SUCCESS"
            lappend debug_log "Implementation (opt, place, route) completed successfully."
        } err]} {
            set impl_status "FAILED"
            set overall_status "FAILED"
            lappend debug_log "Implementation error: $err"
        }
    } else {
        set impl_status "SKIPPED"
    }

    # Step 8.2.1: Post-Implementation Timing and Power Reports
    if {$impl_status eq "SUCCESS"} {
        puts "INFO: Generating post-implementation timing report..."
        if {[catch {
            report_timing_summary -file $post_impl_timing_file -report_unconstrained -max_paths 10
            if {[file exists $post_impl_timing_file]} {
                set fp [open $post_impl_timing_file r]
                set post_impl_timing_rpt [read $fp]
                close $fp
                set impl_timing_status "SUCCESS"
                lappend debug_log "Post-implementation timing report generated: $post_impl_timing_file"
            } else {
                set post_impl_timing_rpt "Report file not created."
                set impl_timing_status "FAILED (File not found)"
            }
        } err]} {
            set impl_timing_status "FAILED"
            set post_impl_timing_rpt "Error generating post-implementation timing report: $err"
            lappend debug_log "Post-implementation timing error: $err"
        }

        puts "INFO: Generating post-implementation power report..."
        if {[catch {
            report_power -file $post_impl_power_file
            if {[file exists $post_impl_power_file]} {
                set fp [open $post_impl_power_file r]
                set post_impl_power_rpt [read $fp]
                close $fp
                set impl_power_status "SUCCESS"
                lappend debug_log "Post-implementation power report generated: $post_impl_power_file"
            } else {
                set post_impl_power_rpt "Report file not created."
                set impl_power_status "FAILED (File not found)"
            }
        } err]} {
            set impl_power_status "FAILED"
            set post_impl_power_rpt "Error generating post-implementation power report: $err"
            lappend debug_log "Post-implementation power error: $err"
        }
    } else {
        set impl_timing_status "SKIPPED"
        set impl_power_status "SKIPPED"
        set post_impl_timing_rpt "Post-implementation timing report skipped ($impl_status)."
        set post_impl_power_rpt "Post-implementation power report skipped ($impl_status)."
    }

    # Step 8.3: Write Bitstream
    if {$impl_status eq "SUCCESS"} {
        if {[catch {
            write_bitstream -force $bitstream_file
            set bit_status "SUCCESS"
            lappend debug_log "Bitstream generated: $bitstream_file"
        } err]} {
            set bit_status "FAILED"
            set overall_status "FAILED"
            lappend debug_log "write_bitstream error: $err"
        }
    } else {
        set bit_status "SKIPPED"
    }

    # Step 8.4: Hardware Manager & FPGA Programming
    if {$bit_status eq "SUCCESS"} {
        puts "================================================================================"
        puts "PROGRAMMING TARGET FPGA (xc7a100tcsg324-1)"
        puts "================================================================================"
        if {[catch {
            open_hw_manager
            connect_hw_server -allow_non_jtag
            open_hw_target
            set hw_devices [get_hw_devices]
            if {[llength $hw_devices] == 0} {
                error "No hardware devices detected on JTAG chain."
            }
            set target_device [lindex $hw_devices 0]
            foreach dev $hw_devices {
                set dev_part [get_property PART $dev]
                if {[string match "*7a100t*" $dev_part] || [string match "*xc7a100t*" $dev_part]} {
                    set target_device $dev
                    break
                }
            }
            current_hw_device $target_device
            refresh_hw_device -update_hw_probes false $target_device
            set_property PROGRAM.FILE $bitstream_file $target_device
            program_hw_devices $target_device
            refresh_hw_device $target_device
            set hw_status "SUCCESS"
            lappend debug_log "Device successfully programmed: [get_property PART $target_device]"
        } err]} {
            set hw_status "NOT_CONNECTED / SKIPPED"
            lappend debug_log "Hardware Manager note: $err"
        }
    } else {
        set hw_status "SKIPPED"
    }
} else {
    # Plain Tclsh environment (pre-synthesis / verification mode)
    set synth_status "NOT_RUN (Tclsh mode)"
    set synth_timing_status "NOT_RUN (Tclsh mode)"
    set synth_power_status "NOT_RUN (Tclsh mode)"
    set impl_status "NOT_RUN (Tclsh mode)"
    set impl_timing_status "NOT_RUN (Tclsh mode)"
    set impl_power_status "NOT_RUN (Tclsh mode)"
    set bit_status "NOT_RUN (Tclsh mode)"
    set hw_status "NOT_RUN (Tclsh mode)"
    set overall_status "CONSTRAINTS GENERATED (READY FOR VIVADO)"
    set post_synth_timing_rpt "Report not generated in Tclsh pre-synthesis mode.\nRun in Vivado batch mode to synthesize and generate timing reports:\n    vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir $target_dir"
    set post_synth_power_rpt "Report not generated in Tclsh pre-synthesis mode.\nRun in Vivado batch mode to synthesize and generate power reports:\n    vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir $target_dir"
    set post_impl_timing_rpt "Report not generated in Tclsh pre-synthesis mode.\nRun in Vivado batch mode to implement and generate timing reports:\n    vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir $target_dir"
    set post_impl_power_rpt "Report not generated in Tclsh pre-synthesis mode.\nRun in Vivado batch mode to implement and generate power reports:\n    vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir $target_dir"
    lappend debug_log "Script executed in Tclsh mode. Pin constraints generated successfully."
    lappend debug_log "To execute full synthesis, implementation, and bitstream generation in Vivado, run:"
    lappend debug_log "    vivado -mode batch -source vivadoSynth.tcl -tclargs --output_dir $target_dir"
}

# ------------------------------------------------------------------------------
# 9. Format and Write Execution & I/O Report
# ------------------------------------------------------------------------------
set rpt [open $report_file w]
puts $rpt "================================================================================"
puts $rpt "                     VIVADO FPGA SYNTHESIS & I/O REPORT                         "
puts $rpt "================================================================================"
puts $rpt "Timestamp:       [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]"
puts $rpt "Overall Status:  $overall_status"
puts $rpt ""
puts $rpt "--- TARGET DEVICE SPECIFICATION ---"
puts $rpt "Product Category: All"
puts $rpt "Family:           Artix-7"
puts $rpt "Package:          csg324"
puts $rpt "Speed Grade:      -1"
puts $rpt "Target Part:      xc7a100tcsg324-1"
puts $rpt "Board:            Digilent Nexys 4 DDR Rev. C"
puts $rpt ""
puts $rpt "--- DESIGN SOURCES & ARTIFACTS ---"
puts $rpt "Source Directory:   $target_dir"
puts $rpt "Verilog File:       $top_file"
puts $rpt "Generated XDC:      $generated_xdc"
if {$bit_status eq "SUCCESS"} {
    puts $rpt "Bitstream File:     $bitstream_file"
}
if {[file exists $post_synth_timing_file]} {
    puts $rpt "Post-Synth Timing:  $post_synth_timing_file"
}
if {[file exists $post_synth_power_file]} {
    puts $rpt "Post-Synth Power:   $post_synth_power_file"
}
if {[file exists $post_impl_timing_file]} {
    puts $rpt "Post-Impl Timing:   $post_impl_timing_file"
}
if {[file exists $post_impl_power_file]} {
    puts $rpt "Post-Impl Power:    $post_impl_power_file"
}
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                          REAL FPGA I/O PIN MAPPING                             "
puts $rpt "================================================================================"
puts $rpt [format "%-12s | %-12s | %-12s | %-10s | %s" "PORT NAME" "BOARD NET" "PACKAGE PIN" "IOSTANDARD" "ROLE"]
puts $rpt "-------------+--------------+--------------+------------+----------------------"
foreach m $mapping_table {
    lassign $m port net pin iostd role
    puts $rpt [format "%-12s | %-12s | %-12s | %-10s | %s" $port $net $pin $iostd $role]
}
puts $rpt "================================================================================"
puts $rpt ""
puts $rpt "--- FLOW EXECUTION SUMMARY ---"
puts $rpt [format "%-24s %s" "Synthesis:" $synth_status]
puts $rpt [format "%-24s %s" "Post-Synth Timing:" $synth_timing_status]
puts $rpt [format "%-24s %s" "Post-Synth Power:" $synth_power_status]
puts $rpt [format "%-24s %s" "Implementation:" $impl_status]
puts $rpt [format "%-24s %s" "Post-Impl Timing:" $impl_timing_status]
puts $rpt [format "%-24s %s" "Post-Impl Power:" $impl_power_status]
puts $rpt [format "%-24s %s" "Bitstream:" $bit_status]
puts $rpt [format "%-24s %s" "FPGA Program:" $hw_status]
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                    POST-SYNTHESIS TIMING REPORT                                "
puts $rpt "================================================================================"
puts $rpt [string trim $post_synth_timing_rpt]
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                     POST-SYNTHESIS POWER REPORT                                "
puts $rpt "================================================================================"
puts $rpt [string trim $post_synth_power_rpt]
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                  POST-IMPLEMENTATION TIMING REPORT                             "
puts $rpt "================================================================================"
puts $rpt [string trim $post_impl_timing_rpt]
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                   POST-IMPLEMENTATION POWER REPORT                             "
puts $rpt "================================================================================"
puts $rpt [string trim $post_impl_power_rpt]
puts $rpt ""
puts $rpt "================================================================================"
puts $rpt "                        DEBUG & EXECUTION LOG                                   "
puts $rpt "================================================================================"
if {[llength $debug_log] > 0} {
    foreach d $debug_log {
        puts $rpt "  $d"
    }
} else {
    puts $rpt "  No errors or warnings recorded."
}
puts $rpt "================================================================================"
close $rpt

# Also print report to stdout
set rpt_view [open $report_file r]
puts [read $rpt_view]
close $rpt_view

puts "Report written to: $report_file"
