# ModelSim / Questa: bit-exact check of the IR core against the golden model.
#   1) cd model && python gen_vectors.py          (writes data/tb/*.hex)
#   2) from the PostProcessing folder:  vsim -c -do sim/run_sim.do
# Prints TB_RESULT: PASS when the RTL matches the golden model.

if {[file exists work]} { vdel -lib work -all }
vlib work
vlog +define+DATA_DIR=\"data/tb/\" \
    rtl/ldpc/ldpc_sdp_ram.v \
    rtl/ldpc/qc_cyclic_shifter.v \
    rtl/ldpc/ldpc_code_rom.v \
    rtl/ldpc/ldpc_ir_decoder.v \
    rtl/top/qkd_ir_core.v \
    rtl/pa/pa_hankel_hash.v \
    rtl/top/qkd_pp_axi.v \
    tb/tb_qkd_ir.v
vsim -c tb_qkd_ir
run -all
quit -f
