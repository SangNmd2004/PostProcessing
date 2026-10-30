`timescale 1ns / 1ps

// Logarithmic cyclic shifter for QC-LDPC: out[j] = in[(j + shift_amt) mod ZC].
// Rotations compose additively mod ZC, so ceil(log2(ZC)) stages of 2:1 muxes
// (stage k rotates by 2^k mod ZC) replace the ZC:1 mux per element of a naive shifter.
// Cost: SHIFT_W * ZC * WORD_W 2:1 muxes (7 * 128 * 8 = 7168 for ZC = 128).
//
// PIPE_AT > 0 inserts a register after stage PIPE_AT (latency 1): shift_amt is sampled together with
// data_in, the bits used after the register are delayed internally.
module qc_cyclic_shifter #(
    parameter ZC      = 96,
    parameter WORD_W  = 8,
    parameter SHIFT_W = 7,
    parameter NGRP    = 1,      // number of replicated copies of shift_amt (lane j uses copy j*NGRP/ZC)
    parameter PIPE_AT = 0       // 0: combinational
)(
    input                       clk,
    input  [ZC*WORD_W-1:0]      data_in,
    input  [NGRP*SHIFT_W-1:0]   shift_amt,   // NGRP identical copies, each < ZC
    output [ZC*WORD_W-1:0]      data_out
);

    wire [ZC*WORD_W-1:0] stage [0:SHIFT_W];
    reg  [ZC*WORD_W-1:0] mid_q;
    reg  [NGRP*SHIFT_W-1:0] amt_q;

    always @(posedge clk) begin
        mid_q <= stage[PIPE_AT];
        amt_q <= shift_amt;
    end

    assign stage[0] = data_in;

    genvar k, j;
    generate
        for (k = 0; k < SHIFT_W; k = k + 1) begin : g_stage
            localparam integer ROT = (1 << k) % ZC;
            wire [ZC*WORD_W-1:0] src = (PIPE_AT > 0 && k == PIPE_AT) ? mid_q : stage[k];
            wire [NGRP*SHIFT_W-1:0] amt = (PIPE_AT > 0 && k >= PIPE_AT) ? amt_q : shift_amt;
            for (j = 0; j < ZC; j = j + 1) begin : g_lane
                localparam integer SRC = (j + ROT) % ZC;
                localparam integer GRP = j * NGRP / ZC;
                assign stage[k+1][j*WORD_W +: WORD_W] = amt[GRP*SHIFT_W + k] ? src[SRC*WORD_W +: WORD_W]
                                                                             : src[j*WORD_W +: WORD_W];
            end
        end
    endgenerate

    assign data_out = stage[SHIFT_W];

endmodule
