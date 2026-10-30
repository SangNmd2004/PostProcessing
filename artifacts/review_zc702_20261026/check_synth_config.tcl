# Lightweight compatibility check only: does not elaborate or synthesize the design.
set_param general.maxThreads 2
if {[get_param general.maxThreads] != 2} { error "Thread limit was not applied" }
set check_dir [file dirname [file normalize [info script]]]
foreach check_file {synth_zc702.tcl report_zc702.tcl qkd_zc702.xdc} {
    set check_handle [open [file join $check_dir $check_file] r]
    set check_source [read $check_handle]
    close $check_handle
    if {![info complete $check_source]} { error "Incomplete Tcl: $check_file" }
}
synth_design -help
puts "ZC702_CONFIG_CHECK_DONE THREADS=[get_param general.maxThreads]"
