# Stages run in separate Vivado processes to release synthesis memory before PnR.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702]
if {$argc != 1 || [lindex $argv 0] ni {synth implement}} { error "Expected stage synth|implement" }
set stage [lindex $argv 0]
set_param general.maxThreads 2
open_project [file join $out project qkd_zc702.xpr]
if {$stage eq "synth"} {
    update_compile_order -fileset sources_1
    synth_design -top system_wrapper -part xc7z020clg484-1 -directive RuntimeOptimized
    write_checkpoint -force [file join $out system_synth.dcp]
    report_utilization -file [file join $out utilization_synth.rpt]
    puts "ZC702_SYSTEM_SYNTH_DONE"
} else {
    open_checkpoint [file join $out system_synth.dcp]
    opt_design
    place_design
    write_checkpoint -force [file join $out system_placed.dcp]
    route_design
    write_checkpoint -force [file join $out system_routed.dcp]
    report_utilization -file [file join $out utilization_routed.rpt]
    report_timing_summary -max_paths 10 -file [file join $out timing_routed.rpt]
    report_drc -file [file join $out drc_routed.rpt]
    set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {![llength $setup_path] || ![llength $hold_path]} { error "No setup/hold timing paths were found" }
    if {[get_property SLACK $setup_path] < 0 || [get_property SLACK $hold_path] < 0} {
        error "Post-route timing failed. Reports/checkpoint saved; no bitstream or deployable XSA exported."
    }
    set timing_file [open [file join $out timing_routed.rpt] r]
    set timing_text [read $timing_file]
    close $timing_file
    if {![string match {*All user specified timing constraints are met.*} $timing_text]} {
        error "Timing summary did not pass all specified constraints. No bitstream exported."
    }
    set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
    # include_bit runs Vivado bitgen and its normal DRC checks. Extract that exact
    # file afterwards; two independent bitgen calls can have different headers.
    write_hw_platform -fixed -include_bit -force -file [file join $out qkd_zc702.xsa]
    puts [exec python -E [file join $script_dir extract_bitstream.py] \
        [file join $out qkd_zc702.xsa] [file join $out qkd_zc702.bit]]
    puts "ZC702_SYSTEM_IMPLEMENT_DONE"
}
close_project
