# Separate LAB-ONLY bootstrap test ELF; baseline binary is never replaced.
# Physical ZC702 test. This resets/programs the single connected Zynq-7020 board.
# Invoked only by the UART-capturing board runner after bundle verification.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702]
set bit [file join $out qkd_zc702.bit]
set xsa [file join $out qkd_zc702.xsa]
if {$argc != 1} { error "Usage: program_bootstrap.tcl TEST_ELF" }
set elf [file normalize [lindex $argv 0]]
set init [file join $out ps7_init.tcl]
foreach f [list $bit $xsa $elf $init] { if {![file isfile $f]} { error "Missing artifact: $f" } }
connect -url tcp:127.0.0.1:3121
set fpgas [targets -target-properties -filter {name == "xc7z020"}]
set cpus [targets -target-properties -filter {name =~ "*Cortex-A9*#0"}]
set apus [targets -target-properties -filter {name == "APU"}]
if {[llength $fpgas] != 1 || [llength $cpus] != 1 || [llength $apus] != 1} {
    error "Expected one unambiguous Zynq-7020 board/CPU/APU target"
}
set cable [dict get [lindex $fpgas 0] jtag_cable_ctx]
foreach target [concat $cpus $apus] {
    if {[dict get $target jtag_cable_ctx] ne $cable} { error "CPU/APU/FPGA targets are on different cables" }
}
set cpu [dict get [lindex $cpus 0] target_id]
targets -set [dict get [lindex $apus 0] target_id]
rst -system
after 1000
foreach core [targets -target-properties -filter {name =~ "*Cortex-A9*"}] {
    if {[dict get $core jtag_cable_ctx] eq $cable} {
        targets -set [dict get $core target_id]
        stop
    }
}
targets -set [dict get [lindex $fpgas 0] target_id]
fpga -file $bit
targets -set $cpu
rst -processor -clear-registers
loadhw -hw $xsa -mem-ranges [list {0x40400000 0x4043ffff} {0x43c00000 0x43c0ffff}]
source $init
ps7_init
ps7_post_config
set id [mrd -value 0x43c00000]
if {$id != 0x49520080} {
    error "QKD IP ID after programming is incorrect: $id"
}
puts "ZC702_PROGRAM_MMIO_PASS id=[format %08X $id]"
rst -processor -clear-registers
dow $elf
con
puts "ZC702_SMOKE_CPU_STARTED"
