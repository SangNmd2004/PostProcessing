# Reproducible ZC702 system: PS7 + QKD IP + four simple-mode AXI DMAs.
# All PL logic uses PS FCLK0 at 50 MHz. No board programming occurs here.
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir ../..]]
set out [file join $root build zc702]
set project_dir [file join $out project]
if {[file exists [file join $project_dir qkd_zc702.xpr]]} {
    error "Project already exists. Use run_system.ps1 -Stage synth or implement; do not overwrite it."
}
file mkdir $out
set_param general.maxThreads 2
create_project qkd_zc702 $project_dir -part xc7z020clg484-1
set boards [lsort -dictionary [get_board_parts -quiet xilinx.com:zc702:part0:*]]
if {[llength $boards] == 0} { error "Installed ZC702 board preset not found" }
set_property board_part [lindex $boards end] [current_project]
set_property target_language Verilog [current_project]
foreach f {
    rtl/ldpc/ldpc_sdp_ram.v rtl/ldpc/qc_cyclic_shifter.v rtl/ldpc/ldpc_code_rom.v
    rtl/ldpc/ldpc_ir_decoder.v rtl/top/qkd_ir_core.v rtl/pa/pa_hankel_hash.v
    rtl/top/qkd_pp_axi.v rtl/top/qkd_pp_zc702.v
} { add_files -norecurse [file join $root $f] }
update_compile_order -fileset sources_1
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1"} $ps
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {50} CONFIG.PCW_USE_FABRIC_INTERRUPT {1} \
    CONFIG.PCW_IRQ_F2P_INTR {1}] $ps

set qkd [create_bd_cell -type module -reference qkd_pp_zc702 qkd]
set control [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 control]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {5}] $control
set memory [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory]
set_property -dict [list CONFIG.NUM_SI {6} CONFIG.NUM_MI {1}] $memory
set reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset]
# Reset polarity is propagated from PS7/FCLK_RESET0_N by IP Integrator.
set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one]
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] $one
set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero]
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] $zero
set concat [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 interrupts]
set_property CONFIG.NUM_PORTS {16} $concat

foreach {name receive} {dma_ch 1 dma_syn 0 dma_pa 1 dma_seed 0} {
    set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 $name]
    set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_sg_include_stscntrl_strm {0} \
        CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm $receive \
        CONFIG.c_addr_width {32} CONFIG.c_sg_length_width {26} \
        CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axis_mm2s_tdata_width {32} \
        CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0} \
        CONFIG.c_mm2s_burst_size {16} CONFIG.c_s2mm_burst_size {16}] $dma
    if {$receive} {
        set_property -dict [list CONFIG.c_m_axi_s2mm_data_width {64} CONFIG.c_s_axis_s2mm_tdata_width {64}] $dma
    }
}

connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins control/S00_AXI]
foreach {index target} {0 qkd/s_axi 1 dma_ch/S_AXI_LITE 2 dma_syn/S_AXI_LITE 3 dma_pa/S_AXI_LITE 4 dma_seed/S_AXI_LITE} {
    connect_bd_intf_net [get_bd_intf_pins [format "control/M%02d_AXI" $index]] [get_bd_intf_pins $target]
}
set index 0
foreach name {dma_ch dma_syn dma_pa dma_seed} {
    foreach iface {M_AXI_MM2S M_AXI_S2MM} {
        set pin [get_bd_intf_pins -quiet $name/$iface]
        if {[llength $pin]} {
            connect_bd_intf_net $pin [get_bd_intf_pins [format "memory/S%02d_AXI" $index]]
            incr index
        }
    }
}
if {$index != 6} { error "Expected six DDR AXI masters, got $index" }
connect_bd_intf_net [get_bd_intf_pins memory/M00_AXI] [get_bd_intf_pins ps7/S_AXI_HP0]
foreach {source sink} {
    dma_ch/M_AXIS_MM2S qkd/s_axis_ch
    dma_syn/M_AXIS_MM2S qkd/s_axis_syn
    dma_pa/M_AXIS_MM2S qkd/s_axis_pa_x
    dma_seed/M_AXIS_MM2S qkd/s_axis_pa_seed
    qkd/m_axis_key dma_ch/S_AXIS_S2MM
    qkd/m_axis_pa_y dma_pa/S_AXIS_S2MM
} { connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $sink] }

connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK] \
    [get_bd_pins ps7/S_AXI_HP0_ACLK] [get_bd_pins reset/slowest_sync_clk] [get_bd_pins qkd/s_axi_aclk]
foreach name {control memory dma_ch dma_syn dma_pa dma_seed} {
    foreach pin [get_bd_pins -of_objects [get_bd_cells $name] -filter {TYPE == clk}] {
        connect_bd_net [get_bd_pins ps7/FCLK_CLK0] $pin
    }
}
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins reset/ext_reset_in]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked] [get_bd_pins reset/aux_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset/mb_debug_sys_rst]
connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins qkd/s_axi_aresetn]
foreach name {dma_ch dma_syn dma_pa dma_seed} {
    connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins $name/axi_resetn]
}
foreach name {control memory} {
    foreach pin [get_bd_pins -of_objects [get_bd_cells $name] -filter {TYPE == rst}] {
        connect_bd_net [get_bd_pins reset/interconnect_aresetn] $pin
    }
}
foreach {index pin} {0 qkd/irq 1 dma_ch/mm2s_introut 2 dma_ch/s2mm_introut 3 dma_syn/mm2s_introut 4 dma_pa/mm2s_introut 5 dma_pa/s2mm_introut 6 dma_seed/mm2s_introut} {
    connect_bd_net [get_bd_pins $pin] [get_bd_pins interrupts/In$index]
}
for {set index 7} {$index < 16} {incr index} {
    connect_bd_net [get_bd_pins zero/dout] [get_bd_pins interrupts/In$index]
}
connect_bd_net [get_bd_pins interrupts/dout] [get_bd_pins ps7/IRQ_F2P]

foreach {cell offset} {qkd 0x43C00000 dma_ch 0x40400000 dma_syn 0x40410000 dma_pa 0x40420000 dma_seed 0x40430000} {
    set iface S_AXI_LITE
    if {$cell eq "qkd"} { set iface s_axi }
    set seg [get_bd_addr_segs -of_objects [get_bd_intf_pins $cell/$iface]]
    if {[llength $seg] != 1} { error "Expected one control address segment for $cell; got $seg" }
    assign_bd_address -target_address_space [get_bd_addr_spaces ps7/Data] -offset $offset -range 64K $seg
}
assign_bd_address
validate_bd_design
if {[get_property CONFIG.C_EXT_RESET_HIGH $reset] != 0} { error "PS reset polarity did not propagate as active-low" }
if {[get_property CONFIG.C_AUX_RESET_HIGH $reset] != 0} { error "Aux reset must be active-low when tied high" }
save_bd_design
set bd [get_files */system.bd]
# One synthesis process for the system; no concurrent IP OOC synthesis jobs.
set_property synth_checkpoint_mode None $bd
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl -force [file join $out system_recreate.tcl]
write_hw_platform -fixed -force -file [file join $out qkd_zc702_pre_synth.xsa]
puts "ZC702_BD_VALIDATE_DONE"
close_project
