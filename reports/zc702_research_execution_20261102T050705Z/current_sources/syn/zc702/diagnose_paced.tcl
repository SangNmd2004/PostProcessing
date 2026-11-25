# Called only after a failed timed test, before immutable baseline restore.
connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "*Cortex-A9*#0"}
if {[catch {stop} err] && ![string match "*Already stopped*" $err]} {error $err}
puts "PACED_FAILED_CPU_REGISTERS"
puts [rrd]
if {$argc == 1} {
    puts "PACED_DEBUG_DDR"
    puts [mrd [lindex $argv 0] 12]
}
