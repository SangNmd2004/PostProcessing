# ==============================================================================
# Floorplanning and Physical Placement Constraints for Xilinx ZC702 (Zynq-7000)
# Target Part: xc7z020clg484-1
# Reference: Work Item R07, Vivado Design Suite User Guide: Implementation (UG904)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Timing Constraints (Baseline 50 MHz and Prospective Optimization Target)
# ------------------------------------------------------------------------------
# Primary system clock from PS FCLK0
create_clock -period 20.000 -name clk_50mhz [get_ports clk]

# Asynchronous Reset False Paths
set_false_path -through [get_ports rst_n]

# False paths on quasi-static configuration registers
set_false_path -to [get_cells -hierarchical -filter {NAME =~ *cfg_reg[*]}]
set_false_path -to [get_cells -hierarchical -filter {NAME =~ *reg_et_patience[*]}]

# ------------------------------------------------------------------------------
# 2. Pblock: QC-LDPC Information Reconciliation Core (qkd_ir_core)
# ------------------------------------------------------------------------------
# Constrains the 128-lane cyclic shifter and check-node processing tree to
# adjacent SLICE columns in Clock Region X0Y1 to minimize inter-bank routing latency.
create_pblock pblock_ldpc_core
add_cells_to_pblock [get_pblocks pblock_ldpc_core] [get_cells -hierarchical -filter {NAME =~ *u_qkd_ir_core*}]
resize_pblock [get_pblocks pblock_ldpc_core] -add {SLICE_X24Y50:SLICE_X55Y99}
resize_pblock [get_pblocks pblock_ldpc_core] -add {RAMB36_X1Y10:RAMB36_X2Y19}
set_property IS_SOFT FALSE [get_pblocks pblock_ldpc_core]

# ------------------------------------------------------------------------------
# 3. Pblock: Hankel / NTT Privacy Amplification Engine (pa_hankel_hash)
# ------------------------------------------------------------------------------
# Places the streaming Hankel hash accumulator into Clock Region X0Y0 close to
# DMA S2MM channels.
create_pblock pblock_pa_engine
add_cells_to_pblock [get_pblocks pblock_pa_engine] [get_cells -hierarchical -filter {NAME =~ *u_pa_hankel_hash*}]
resize_pblock [get_pblocks pblock_pa_engine] -add {SLICE_X0Y0:SLICE_X23Y49}
resize_pblock [get_pblocks pblock_pa_engine] -add {RAMB36_X0Y0:RAMB36_X0Y9}
set_property IS_SOFT FALSE [get_pblocks pblock_pa_engine]

# ------------------------------------------------------------------------------
# 4. Pblock: AXI DMA and Interconnect Infrastructure
# ------------------------------------------------------------------------------
# Keeps Simple DMA channels adjacent to the PS HP and GP AXI boundary
create_pblock pblock_axi_dma
add_cells_to_pblock [get_pblocks pblock_axi_dma] [get_cells -hierarchical -filter {NAME =~ *axi_dma*}]
resize_pblock [get_pblocks pblock_axi_dma] -add {SLICE_X0Y50:SLICE_X23Y99}
set_property IS_SOFT TRUE [get_pblocks pblock_axi_dma]

# ------------------------------------------------------------------------------
# 5. Routing Optimization Directives
# ------------------------------------------------------------------------------
set_property BLOCK_SYNTH.RETIMING 1 [get_cells -hierarchical -filter {NAME =~ *u_shifter*}]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
