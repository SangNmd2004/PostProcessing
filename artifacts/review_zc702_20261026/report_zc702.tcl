# Optional reports: run after synthesis, in a fresh Vivado process.
# Usage: vivado -mode batch -source report_zc702.tcl [-tclargs quality]
set script_dir [file normalize [file dirname [info script]]]
set profile low_memory
if {[info exists argc] && $argc > 0} {
    if {$argc != 1 || [lindex $argv 0] ni {low_memory quality}} {
        error "Usage: report_zc702.tcl ?low_memory|quality?"
    }
    set profile [lindex $argv 0]
}
set out [file join $script_dir $profile]
set checkpoint [file join $out qkd_pp_axi_synth.dcp]
if {![file isfile $checkpoint]} { error "Missing synthesis checkpoint: $checkpoint" }
set_param general.maxThreads 2
open_checkpoint $checkpoint
report_utilization -hierarchical -file [file join $out utilization_hier_synth.rpt]
report_timing_summary -max_paths 5 -file [file join $out timing_synth.rpt]
close_design
puts "ZC702_REVIEW_REPORTS_DONE"
