# Read-only timing experiment on the existing 50-MHz routed checkpoint.
# Changes constraints in memory only. No routing, bitstream export or programming.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702 timing_trials]
file mkdir $out
set_param general.maxThreads 2
open_checkpoint [file join $root build zc702 system_routed.dcp]
set clocks [get_clocks -quiet clk_fpga_0]
if {[llength $clocks]!=1} {error "Expected one clk_fpga_0"}
set sources [get_property SOURCE_PINS $clocks]
set pins [get_pins -quiet $sources]
if {[llength $pins]!=1} {error "Expected one primary clock source pin; found $sources"}
set report [open [file join $out existing_route_frequency_sweep.csv] w]
puts $report "frequency_mhz,period_ns,setup_wns_ns,hold_whs_ns,scope"
foreach mhz {50 55 60 70} {
    set period [expr {1000.0/$mhz}]
    create_clock -name clk_fpga_0 -period $period $pins
    report_timing_summary -max_paths 3 -file [file join $out "sta_${mhz}mhz.rpt"]
    set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {![llength $setup]||![llength $hold]} {error "Missing timing paths"}
    set wns [get_property SLACK $setup]
    set whs [get_property SLACK $hold]
    puts $report "$mhz,$period,$wns,$whs,existing_route_constraint_trial_only"
    puts "ZC702_STA_TRIAL frequency=$mhz WNS=$wns WHS=$whs"
}
close $report
close_design
puts "ZC702_EXISTING_ROUTE_STA_TRIAL_DONE"
