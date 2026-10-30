# Recover/repeat packaging from the routed checkpoint without repeating PnR.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702]
set_param general.maxThreads 2
open_project [file join $out project qkd_zc702.xpr]
open_checkpoint [file join $out system_routed.dcp]
set timing_file [open [file join $out timing_routed.rpt] r]
set text [read $timing_file]
close $timing_file
if {![string match {*All user specified timing constraints are met.*} $text]} { error "Routed timing has not passed" }
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
write_hw_platform -fixed -include_bit -force -file [file join $out qkd_zc702.xsa]
puts [exec python -E [file join $script_dir extract_bitstream.py] \
    [file join $out qkd_zc702.xsa] [file join $out qkd_zc702.bit]]
puts ZC702_SYSTEM_IMPLEMENT_DONE
close_project
