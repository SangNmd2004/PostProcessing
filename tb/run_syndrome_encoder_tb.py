#!/usr/bin/env python3
"""
run_syndrome_encoder_tb.py
Compiles and simulates RTL ldpc_syndrome_encoder against golden ir_model syndromes
using Vivado xsim. Verifies all 4 code rates (r12, r23, r34, r56) bit-by-bit.
"""

import sys
import os
import subprocess
import pathlib
import numpy as np

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR / "model"))
import ir_model

TB_DIR = ROOT_DIR / "tb"
RTL_DIR = ROOT_DIR / "rtl" / "ldpc"
VIVADO_BIN = pathlib.Path("D:/Xilinx/Vivado/2020.2/bin")

def main():
    print("=== STARTING RTL SYNDROME ENCODER VERIFICATION ===")
    zc = 128
    codes = ir_model.load_codes(zc)

    # 1. Generate test key (3072 bits)
    rng = np.random.default_rng(20261027)
    key_bits = rng.integers(0, 2, size=(1, 24, zc))

    words_32 = []
    for c in range(24):
        col_bits = key_bits[0, c]
        for w in range(4):
            chunk = col_bits[w*32 : (w+1)*32]
            val = 0
            for i, b in enumerate(chunk):
                val |= (int(b) << i)
            words_32.append(val)

    key_hex_file = TB_DIR / "test_key.hex"
    with open(key_hex_file, "w") as f:
        for w in words_32:
            f.write(f"{w:08x}\n")
    print(f"Wrote test key: {key_hex_file} (96 words)")

    # 2. Generate golden syndromes for each code rate
    rate_names = ["r12", "r23", "r34", "r56"]
    for rate_idx, rate in enumerate(rate_names):
        base = codes[rate]
        syn = ir_model.syndrome(base, key_bits, zc)
        mb = len(base)
        syn_words = []
        for l in range(mb):
            layer_bits = syn[0, l]
            for w in range(4):
                chunk = layer_bits[w*32 : (w+1)*32]
                val = 0
                for i, b in enumerate(chunk):
                    val |= (int(b) << i)
                syn_words.append(val)
        hex_file = TB_DIR / f"gold_syn_{rate}.hex"
        with open(hex_file, "w") as f:
            for w in syn_words:
                f.write(f"{w:08x}\n")
        print(f"Wrote golden syndrome for {rate}: {hex_file} ({len(syn_words)} words)")

    # 3. Create tb_ldpc_syndrome_encoder.v
    tb_v = TB_DIR / "tb_ldpc_syndrome_encoder.v"
    tb_content = """`timescale 1ns / 1ps

module tb_ldpc_syndrome_encoder;

    reg clk;
    reg rst_n;
    reg start;
    reg [1:0] code_rate;
    wire busy;
    wire done;

    reg [31:0]  s_axis_key_tdata;
    reg         s_axis_key_tvalid;
    wire        s_axis_key_tready;

    wire [31:0] m_axis_syn_tdata;
    wire        m_axis_syn_tvalid;
    reg         m_axis_syn_tready;

    ldpc_syndrome_encoder #(
        .ZC(128),
        .SHIFT_W(7),
        .NB_COLS(24),
        .MB_MAX(12)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .code_rate(code_rate),
        .busy(busy),
        .done(done),
        .s_axis_key_tdata(s_axis_key_tdata),
        .s_axis_key_tvalid(s_axis_key_tvalid),
        .s_axis_key_tready(s_axis_key_tready),
        .m_axis_syn_tdata(m_axis_syn_tdata),
        .m_axis_syn_tvalid(m_axis_syn_tvalid),
        .m_axis_syn_tready(m_axis_syn_tready)
    );

    // Clock generator: 50 MHz (20 ns period)
    always #10 clk = ~clk;

    reg [31:0] key_mem [0:95];
    reg [31:0] gold_r12 [0:47];
    reg [31:0] gold_r23 [0:31];
    reg [31:0] gold_r34 [0:23];
    reg [31:0] gold_r56 [0:15];

    integer errors;
    integer total_checked;

    task test_rate(input [1:0] r, input integer num_words, input [32*8-1:0] name);
        integer i;
        reg [31:0] exp_word;
        begin
            $display("--- Testing Rate %0s (%0d words) ---", name, num_words);
            code_rate = r;
            start = 1;
            @(posedge clk);
            start = 0;

            // Wait for dut to become busy
            while (!busy) @(posedge clk);

            // Feed key words: exactly 96 words accepted
            s_axis_key_tvalid = 1;
            for (i = 0; i < 96; i = i + 1) begin
                s_axis_key_tdata = key_mem[i];
                @(posedge clk);
            end
            s_axis_key_tvalid = 0;

            // Collect syndrome outputs
            m_axis_syn_tready = 1;
            for (i = 0; i < num_words; i = i + 1) begin
                while (!m_axis_syn_tvalid) @(posedge clk);
                case (r)
                    2'd0: exp_word = gold_r12[i];
                    2'd1: exp_word = gold_r23[i];
                    2'd2: exp_word = gold_r34[i];
                    2'd3: exp_word = gold_r56[i];
                endcase
                if (m_axis_syn_tdata !== exp_word) begin
                    $display("ERROR [%0s] Word %0d mismatch: got 0x%08x, expected 0x%08x", name, i, m_axis_syn_tdata, exp_word);
                    errors = errors + 1;
                end
                total_checked = total_checked + 1;
                @(posedge clk);
            end
            m_axis_syn_tready = 0;

            // Wait for done
            while (!done) @(posedge clk);
            @(posedge clk);
            $display("Finished Rate %0s. Current errors: %0d", name, errors);
        end
    endtask

    initial begin
        $readmemh("tb/test_key.hex", key_mem);
        $readmemh("tb/gold_syn_r12.hex", gold_r12);
        $readmemh("tb/gold_syn_r23.hex", gold_r23);
        $readmemh("tb/gold_syn_r34.hex", gold_r34);
        $readmemh("tb/gold_syn_r56.hex", gold_r56);

        clk = 0;
        rst_n = 0;
        start = 0;
        code_rate = 0;
        s_axis_key_tdata = 0;
        s_axis_key_tvalid = 0;
        m_axis_syn_tready = 0;
        errors = 0;
        total_checked = 0;

        #100;
        rst_n = 1;
        #40;

        test_rate(2'd0, 48, "r12");
        #100;
        test_rate(2'd1, 32, "r23");
        #100;
        test_rate(2'd2, 24, "r34");
        #100;
        test_rate(2'd3, 16, "r56");

        #100;
        $display("==================================================");
        $display("RTL SYNDROME ENCODER TEST SUMMARY: Checked %0d words, Errors = %0d", total_checked, errors);
        if (errors == 0 && total_checked == 120) begin
            $display("RESULT: ALL RATES PASSED 100% BIT-EXACT!");
        end else begin
            $display("RESULT: TEST FAILED!");
        end
        $display("==================================================");
        $finish;
    end

endmodule
"""
    with open(tb_v, "w", encoding="utf-8") as f:
        f.write(tb_content)
    print(f"Created testbench: {tb_v}")

    # 4. Compile with xvlog
    print("\nRunning xvlog...")
    xvlog_cmd = [
        str(VIVADO_BIN / "xvlog.bat"),
        str(RTL_DIR / "qc_cyclic_shifter.v"),
        str(RTL_DIR / "ldpc_code_rom.v"),
        str(RTL_DIR / "ldpc_syndrome_encoder.v"),
        str(tb_v)
    ]
    res = subprocess.run(xvlog_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print("xvlog failed:\n", res.stderr or res.stdout)
        return 1
    print("xvlog SUCCESS")

    # 5. Elaborate with xelab
    print("Running xelab...")
    xelab_cmd = [
        str(VIVADO_BIN / "xelab.bat"),
        "-top", "tb_ldpc_syndrome_encoder",
        "-snapshot", "ldpc_syn_enc_snap"
    ]
    res = subprocess.run(xelab_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print("xelab failed:\n", res.stderr or res.stdout)
        return 1
    print("xelab SUCCESS")

    # 6. Simulate with xsim
    print("Running xsim...")
    xsim_cmd = [
        str(VIVADO_BIN / "xsim.bat"),
        "ldpc_syn_enc_snap",
        "-R"
    ]
    res = subprocess.run(xsim_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0 or "RESULT: ALL RATES PASSED 100% BIT-EXACT!" not in res.stdout:
        print("xsim failed or simulation mismatches detected!")
        return 1

    print("=== RTL SYNDROME ENCODER VERIFICATION COMPLETED WITH 0 ERRORS! ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
