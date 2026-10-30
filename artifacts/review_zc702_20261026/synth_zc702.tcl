# Low-memory OOC synthesis for an 8 GB host, Vivado 2020.2.
# Default: RuntimeOptimized. Optional: -tclargs quality (default synthesis directive).
# Run timing/hierarchy reports in a separate process with report_zc702.tcl.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set profile low_memory
if {[info exists argc] && $argc > 0} {
    if {$argc != 1 || [lindex $argv 0] ni {low_memory quality}} {
        error "Usage: synth_zc702.tcl ?low_memory|quality?"
    }
    set profile [lindex $argv 0]
}
set out [file join $script_dir $profile]
file mkdir $out
set_param general.maxThreads 2
set directive RuntimeOptimized
if {$profile eq "quality"} { set directive default }
puts "ZC702_PROFILE=$profile THREADS=[get_param general.maxThreads] DIRECTIVE=$directive"
foreach f {
    rtl/ldpc/ldpc_sdp_ram.v
    rtl/ldpc/qc_cyclic_shifter.v
    rtl/ldpc/ldpc_code_rom.v
    rtl/ldpc/ldpc_ir_decoder.v
    rtl/top/qkd_ir_core.v
    rtl/pa/pa_hankel_hash.v
    rtl/top/qkd_pp_axi.v
} { read_verilog [file join $root $f] }
read_xdc [file join $script_dir qkd_zc702.xdc]
synth_design -top qkd_pp_axi -part xc7z020clg484-1 -mode out_of_context \
    -directive $directive
# Save the synthesized design before generating reports. No place/route/phys_opt.
write_checkpoint -force [file join $out qkd_pp_axi_synth.dcp]
report_utilization -file [file join $out utilization_synth.rpt]
close_design
puts "ZC702_OUTPUT=$out"
puts "ZC702_REVIEW_SYNTH_DONE"
