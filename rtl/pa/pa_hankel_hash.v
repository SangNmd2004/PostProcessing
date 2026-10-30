`timescale 1ns / 1ps

// Privacy amplification: streaming Hankel (Toeplitz-type) universal hash. Bit-exact reference: model/pa_model.py
//
//   y[j] = XOR_{i < n_in} x[i] AND s[i + j],   j = 0 .. L_OUT-1
//
// x arrives on s_axis_x (32 bit per beat, bit 0 first), the TRNG seed s on s_axis_seed (32 bit per beat, bit 0
// first). The core keeps a window W = s[p .. p + W_LEN - 1] for the current input position p. For each group of
// B_STEP = 8 input bits:   y ^= XOR_t x[p+t] ? W[t +: L_OUT] : 0,   then W shifts down by 8 and 8 new seed bits
// enter at the top. One 32-bit input word + one 32-bit seed word are consumed together every 4 cycles
// (8 bit / cycle, 800 Mbit/s at 100 MHz).
//
// Seed length: PRELOAD (= W_LEN / 32 = 33) words before the first input word, then 1 word per input word,
// i.e. (n_words + 33) * 32 bits; only s[0 .. n_in + L_OUT - 2] influence y.
// Output: L_OUT / 64 = 16 words of 64 bit on m_axis_y (y[0] = bit 0 of the first word), tlast on the last.
//
// Cost (L_OUT = 1024): y 1024 FF + W 1056 FF + 1024 x (8 AND + 9-input XOR) - a few thousand LUTs.
module pa_hankel_hash #(
    parameter L_OUT = 1024,               // output bits per pass (multiple of 64)
    parameter NW_W  = 20                  // width of the input-word counter (up to 2^20 words = 32 Mbit)
)(
    input                clk,
    input                rst,

    input                start,           // pulse: begin a pass (seed preload, then n_words input words)
    input  [NW_W-1:0]    n_words,         // input length in 32-bit words (>= 1)
    output               busy,
    output reg           done,            // 1-cycle pulse after the last output word

    input      [31:0]    s_axis_x_tdata,
    input                s_axis_x_tvalid,
    output               s_axis_x_tready,

    input      [31:0]    s_axis_seed_tdata,
    input                s_axis_seed_tvalid,
    output               s_axis_seed_tready,

    output     [63:0]    m_axis_y_tdata,
    output               m_axis_y_tvalid,
    input                m_axis_y_tready,
    output               m_axis_y_tlast
);

    localparam W_LEN   = L_OUT + 32;      // window: >= L_OUT + 7, rounded to whole seed words
    localparam PRELOAD = W_LEN / 32;      // seed words before the first input word (33)
    localparam NOUT    = L_OUT / 64;      // output words (16)

    localparam P_IDLE = 2'd0, P_PRE = 2'd1, P_RUN = 2'd2, P_OUT = 2'd3;
    reg  [1:0]       state;
    reg  [W_LEN-1:0] win;                 // seed window s[p .. p + W_LEN - 1]
    reg  [L_OUT-1:0] acc;                 // hash accumulator y
    reg  [31:0]      xw, sw;              // current input word / seed word
    reg              have;                // xw / sw hold a word being processed
    reg  [1:0]       sub;                 // 8-bit group inside the word (0..3)
    reg  [NW_W-1:0]  nw_q, words;         // requested / consumed input words
    reg  [5:0]       pre_cnt;
    reg  [4:0]       out_cnt;

    assign busy = (state != P_IDLE);

    // ---- stream handshakes
    // preload: seed only. run: an input word and a seed word are taken together, when no word is pending or the
    // pending one is in its last 8-bit group (so the core never stalls between words).
    wire take_ok   = (state == P_RUN) && (words != nw_q) && (!have || sub == 2'd3);
    wire run_fire  = take_ok && s_axis_x_tvalid && s_axis_seed_tvalid;
    wire pre_fire  = (state == P_PRE) && s_axis_seed_tvalid;
    assign s_axis_x_tready    = take_ok && s_axis_seed_tvalid;
    assign s_axis_seed_tready = (state == P_PRE) || (take_ok && s_axis_x_tvalid);

    // ---- one 8-bit step: acc ^= XOR_t x8[t] ? win[t +: L_OUT]
    wire [7:0]       x8 = xw[sub*8 +: 8];
    wire [7:0]       s8 = sw[sub*8 +: 8];
    reg  [L_OUT-1:0] step_xor;
    integer t;
    always @(*) begin
        step_xor = {L_OUT{1'b0}};
        for (t = 0; t < 8; t = t + 1)
            if (x8[t]) step_xor = step_xor ^ win[t +: L_OUT];
    end

    // ---- output
    assign m_axis_y_tdata  = acc[out_cnt*64 +: 64];
    assign m_axis_y_tvalid = (state == P_OUT);
    assign m_axis_y_tlast  = (state == P_OUT) && (out_cnt == NOUT - 1);

    always @(posedge clk) begin
        if (rst) begin
            state <= P_IDLE; done <= 1'b0; have <= 1'b0; sub <= 2'd0;
            words <= {NW_W{1'b0}}; nw_q <= {NW_W{1'b0}}; pre_cnt <= 6'd0; out_cnt <= 5'd0;
        end else begin
            done <= 1'b0;
            case (state)
                P_IDLE: begin
                    if (start) begin
                        nw_q    <= (n_words == {NW_W{1'b0}}) ? {{(NW_W-1){1'b0}}, 1'b1} : n_words;
                        words   <= {NW_W{1'b0}};
                        acc     <= {L_OUT{1'b0}};
                        have    <= 1'b0;
                        sub     <= 2'd0;
                        pre_cnt <= 6'd0;
                        state   <= P_PRE;
                    end
                end
                P_PRE: begin
                    // the first seed word ends at win[31:0] after PRELOAD shifts
                    if (pre_fire) begin
                        win     <= {s_axis_seed_tdata, win[W_LEN-1:32]};
                        pre_cnt <= pre_cnt + 6'd1;
                        if (pre_cnt == PRELOAD - 1) state <= P_RUN;
                    end
                end
                P_RUN: begin
                    if (have) begin
                        acc <= acc ^ step_xor;
                        win <= {s8, win[W_LEN-1:8]};
                        sub <= sub + 2'd1;
                    end
                    if (run_fire) begin
                        xw    <= s_axis_x_tdata;
                        sw    <= s_axis_seed_tdata;
                        have  <= 1'b1;
                        sub   <= 2'd0;
                        words <= words + {{(NW_W-1){1'b0}}, 1'b1};
                    end else if (have && sub == 2'd3) begin
                        have <= 1'b0;
                        if (words == nw_q) begin
                            out_cnt <= 5'd0;
                            state   <= P_OUT;
                        end
                    end
                end
                P_OUT: begin
                    if (m_axis_y_tready) begin
                        if (out_cnt == NOUT - 1) begin
                            done  <= 1'b1;
                            state <= P_IDLE;
                        end else begin
                            out_cnt <= out_cnt + 5'd1;
                        end
                    end
                end
            endcase
        end
    end

endmodule
