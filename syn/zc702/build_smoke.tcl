# XSCT/Vitis 2020.2: build a standalone application from the matching final XSA.
# No target connection, reset, programming, or execution occurs in this script.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702]
set xsa [file join $out qkd_zc702.xsa]
if {![file isfile $xsa]} { error "Final implemented XSA is missing: $xsa" }
set ws [file join $out vitis]
setws $ws
set ::env(MAKEFLAGS) -j1
set generate_platform 1
if {[file isfile [file join $ws qkd_zc702_platform platform.spr]]} {
    set old_xsa [file join $ws qkd_zc702_platform hw qkd_zc702.xsa]
    if {![file isfile $old_xsa]} { error "Existing platform has no hardware handoff" }
    set a [open $xsa rb]
    set new_hardware [read $a]
    close $a
    set a [open $old_xsa rb]
    set old_hardware [read $a]
    close $a
    if {$new_hardware ne $old_hardware} {
        error "Existing BSP platform uses a different XSA. Create a fresh matching workspace before building."
    }
    platform active qkd_zc702_platform
    # Regenerate incrementally: an interrupted prior BSP build may be incomplete.
    set generate_platform 1
} else {
    platform create -name qkd_zc702_platform -hw $xsa -proc ps7_cortexa9_0 -os standalone -out $ws
}
domain active standalone_domain
bsp config stdin ps7_uart_1
bsp config stdout ps7_uart_1
if {$generate_platform} { platform generate }
if {![file isdirectory [file join $ws qkd_smoke]]} {
    app create -name qkd_smoke -platform qkd_zc702_platform -domain standalone_domain -template {Empty Application}
    importsources -name qkd_smoke -path [file join $root firmware zc702]
} else {
    foreach src [glob [file join $root firmware zc702 *.c] [file join $root firmware zc702 *.h]] {
        file copy -force $src [file join $ws qkd_smoke src [file tail $src]]
    }
}
app build -name qkd_smoke
puts "ZC702_SMOKE_BUILD_DONE"
