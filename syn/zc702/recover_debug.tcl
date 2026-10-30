connect -url tcp:127.0.0.1:3121
puts "BEFORE_RECOVERY\n[targets]"
set dap [targets -target-properties -filter {name == "DAP" || name == "APU"}]
if {[llength $dap] == 1} {
    targets -set [dict get [lindex $dap 0] target_id]
} elseif {[llength $dap] == 0 && [regexp {(^|\n)\s*1\s+DAP} [targets]]} {
    targets -set 1
} else { error "Ambiguous DAP/APU target" }
if {[catch {rst -dap} result]} { puts "DAP_RESET_FAILED $result" } else { puts DAP_RESET_SENT }
after 500
puts "AFTER_DAP_RESET\n[targets]"
