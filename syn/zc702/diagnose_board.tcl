connect -url tcp:127.0.0.1:3121
puts [targets]
targets -set -filter {name == "APU"}
foreach address {0xf8000170 0xf8000240 0xf8000900 0xf8000008} {
    if {[catch {mrd $address} value]} { puts "PS_READ_FAILED $address $value" } else { puts "PS_READ $value" }
}
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[catch {loadhw -hw [file join $root build zc702 qkd_zc702.xsa] \
    -mem-ranges [list {0x40400000 0x4043ffff} {0x43c00000 0x43c0ffff}]} message]} { puts "LOADHW_APU $message" }
if {[catch {mrd 0x43c00000} value]} { puts "APU_QKD_FAILED $value" } else { puts "APU_QKD $value" }
targets -set -filter {name =~ "*Cortex-A9*#0"}
foreach register {pc cpsr} {
    if {[catch {rrd $register} value]} { puts "CPU_READ_FAILED $register $value" } else { puts "CPU_READ $value" }
}
puts ZC702_BOARD_DIAG_DONE
