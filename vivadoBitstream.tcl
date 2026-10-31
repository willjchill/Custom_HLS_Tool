#!/bin/sh
# \
if command -v vivado >/dev/null 2>&1; then \
  exec vivado -mode batch -source "$0" -notrace -tclargs "$@"; \
else \
  exec tclsh "$0" "$@"; \
fi

# ==============================================================================
# vivadoBitstream.tcl
# Fast FPGA Bitstream Programming Flow (Skips Synthesis & Implementation)
#
# Target Part: xc7a100tcsg324-1 (Digilent Nexys 4 DDR)
#
# Usage:
#   vivado -mode batch -source vivadoBitstream.tcl [-tclargs --output_dir <dir>]
#   vivado -mode batch -source vivadoBitstream.tcl [-tclargs --bitstream <path/to/top.bit>]
#   ./vivadoBitstream.tcl [--output_dir <dir> | --bitstream <path>]
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
set bitstream_file ""

for {set i 0} {$i < $argc} {incr i} {
    set opt [lindex $argv $i]
    if {$opt eq "--output_dir" || $opt eq "-output_dir"} {
        incr i
        if {$i < $argc} {
            set target_dir [lindex $argv $i]
        }
    } elseif {$opt eq "--bitstream" || $opt eq "-bitstream"} {
        incr i
        if {$i < $argc} {
            set bitstream_file [lindex $argv $i]
        }
    }
}

if {$target_dir ne "" && [file pathtype $target_dir] eq "relative"} {
    set target_dir [file normalize [file join $repo_dir $target_dir]]
}
if {$bitstream_file ne "" && [file pathtype $bitstream_file] eq "relative"} {
    set bitstream_file [file normalize [file join $repo_dir $bitstream_file]]
}

# ------------------------------------------------------------------------------
# 2. Locate Target Bitstream File
# ------------------------------------------------------------------------------
proc compare_mtime {a b} {
    set ma [file mtime $a]
    set mb [file mtime $b]
    if {$ma < $mb} { return -1 }
    if {$ma > $mb} { return 1 }
    return [string compare $a $b]
}

if {$bitstream_file eq ""} {
    if {$target_dir ne ""} {
        # Check inside specified directory
        set bits [glob -nocomplain [file join $target_dir "*.bit"]]
        if {[llength $bits] > 0} {
            set sorted_bits [lsort -decreasing -command compare_mtime $bits]
            set bitstream_file [lindex $sorted_bits 0]
        } else {
            puts "ERROR: No .bit file found in specified directory: $target_dir"
            exit 1
        }
    } else {
        # Search all output/verilog subdirectories for the most recent .bit file
        set verilog_base [file join $repo_dir "output" "verilog"]
        set bits [glob -nocomplain [file join $verilog_base "*" "*.bit"]]
        if {[llength $bits] > 0} {
            set sorted_bits [lsort -decreasing -command compare_mtime $bits]
            set bitstream_file [lindex $sorted_bits 0]
            puts "INFO: No bitstream or directory specified. Using most recently generated bitstream:"
            puts "      $bitstream_file"
        } else {
            puts "ERROR: No generated bitstream (.bit) found in $verilog_base."
            puts "       Run vivadoSynth.tcl first to synthesize and generate a bitstream:"
            puts "       vivado -mode batch -source vivadoSynth.tcl"
            exit 1
        }
    }
}

if {![file exists $bitstream_file]} {
    puts "ERROR: Bitstream file does not exist: $bitstream_file"
    exit 1
}

puts "INFO: Target Bitstream: $bitstream_file"
puts "INFO: Bitstream Size:   [file size $bitstream_file] bytes"
puts "INFO: Last Modified:    [clock format [file mtime $bitstream_file] -format "%Y-%m-%d %H:%M:%S"]"

# ------------------------------------------------------------------------------
# 3. Setup Output Report Directory & File
# ------------------------------------------------------------------------------
set ts [clock format [clock seconds] -format "%Y%m%d_%H%M%S"]
set fpga_dir [file join $repo_dir "output" "fpga"]
file mkdir $fpga_dir
set report_file [file join $fpga_dir "program_${ts}.log"]

# ------------------------------------------------------------------------------
# 4. Program FPGA via Vivado Hardware Manager
# ------------------------------------------------------------------------------
set in_vivado [expr {[llength [info commands open_hw_manager]] > 0}]
set prog_status "NOT_RUN"
set prog_msg ""
set device_name "xc7a100tcsg324-1"

if {$in_vivado} {
    puts "================================================================================"
    puts "CONNECTING TO HARDWARE MANAGER & PROGRAMMING FPGA"
    puts "================================================================================"
    if {[catch {
        open_hw_manager
        connect_hw_server -allow_non_jtag
        open_hw_target
        set hw_devices [get_hw_devices]
        if {[llength $hw_devices] == 0} {
            error "No hardware devices detected on JTAG chain. Make sure your Nexys 4 DDR is powered on and plugged in via USB."
        }
        set target_device [lindex $hw_devices 0]
        foreach dev $hw_devices {
            set dev_part [get_property PART $dev]
            if {[string match "*7a100t*" $dev_part] || [string match "*xc7a100t*" $dev_part]} {
                set target_device $dev
                break
            }
        }
        set device_name [get_property PART $target_device]
        puts "INFO: Target FPGA device found: $device_name"
        current_hw_device $target_device
        refresh_hw_device -update_hw_probes false $target_device
        
        puts "INFO: Sending bitstream to $device_name..."
        set_property PROGRAM.FILE $bitstream_file $target_device
        program_hw_devices $target_device
        refresh_hw_device $target_device
        
        set prog_status "SUCCESS"
        set prog_msg "Successfully programmed FPGA ($device_name) with $bitstream_file"
        puts "SUCCESS: $prog_msg"
    } err]} {
        set prog_status "FAILED"
        set prog_msg $err
        puts "ERROR: $prog_msg"
    }
} else {
    set prog_status "NOT_RUN (Tclsh mode)"
    set prog_msg "Script executed in Tclsh mode. Run in Vivado batch mode to program FPGA hardware:"
    puts "INFO: $prog_msg"
    puts "      vivado -mode batch -source vivadoBitstream.tcl -tclargs --bitstream $bitstream_file"
}

# ------------------------------------------------------------------------------
# 5. Write Execution Log
# ------------------------------------------------------------------------------
set rpt [open $report_file w]
puts $rpt "================================================================================"
puts $rpt "                     VIVADO FPGA PROGRAMMING REPORT                             "
puts $rpt "================================================================================"
puts $rpt "Timestamp:       [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]"
puts $rpt "Status:          $prog_status"
puts $rpt "Target Part:     xc7a100tcsg324-1"
puts $rpt "Detected Device: $device_name"
puts $rpt "Bitstream File:  $bitstream_file"
puts $rpt "Bitstream Size:  [file size $bitstream_file] bytes"
puts $rpt ""
puts $rpt "--- PROGRAMMING LOG ---"
puts $rpt "  $prog_msg"
puts $rpt "================================================================================"
close $rpt

puts "Program log written to: $report_file"
