# ModelSim / Questa: block contexts (several blocks in flight sharing the decoder), bit-exact vs the golden model.
#   1) cd model && python gen_qkd_session.py && python gen_session_vectors.py    (writes data/sessions_tb/*.hex)
#   2) from the PostProcessing folder:  vsim -c -do sim/run_sim_ctx.do
# USE_CTX: contexts used by the testbench (1 = old single-block behaviour), RTT_CYC: Alice's round trip in cycles.
# Prints TOTAL <blocks> in <cycles> and TB_RESULT: PASS when every attempt, key and ERRCNT matches.

if {[file exists work]} { vdel -lib work -all }
vlib work
vlog +define+DATA_DIR=\"data/sessions_tb/\" +define+USE_CTX=4 +define+RTT_CYC=10000 \
    rtl/ldpc/ldpc_sdp_ram.v \
    rtl/ldpc/qc_cyclic_shifter.v \
    rtl/ldpc/ldpc_code_rom.v \
    rtl/ldpc/ldpc_ir_decoder.v \
    rtl/top/qkd_ir_core.v \
    rtl/pa/pa_hankel_hash.v \
    rtl/top/qkd_pp_axi.v \
    tb/tb_qkd_ir_ctx.v
vsim -c tb_qkd_ir_ctx
run -all
quit -f
