`timescale 1ns / 1ps

// Syndrome-based layered min-sum QC-LDPC decoder (normalized x0.75 or offset) for blind reconciliation.
// Bit-exact reference: model/ir_model.py (decode_attempt).
//
// Datapath (derived from the 2026-10 ldpc_opt decoder): one non-zero circulant per cycle, ZC lanes wide,
// serial min1/min2 CNU per lane, C2V stored per edge in the check-node domain, one shared cyclic shifter
// (forward shift of the APP on read, inverse shift of c2v_new - c2v_old on write), all bulk storage in BSRAM.
// The write phase rebuilds app_new = app_old + inv_shift(c2v_new - c2v_old) (= v2c + c2v_new), so only the
// V2C signs are buffered between the phases (1 bit instead of 8 bit per lane and edge).
//
// New in this version:
//   * 4 mother codes selected by `code` (ldpc_code_rom.v, generated from model/codes.json), row degree up to 31.
//   * Channel RAM holds a 2-bit type per variable node: 00 key bit, 01 punctured, 10 shortened, 11 key bit with
//     inverted channel sign (set by post-processing, cleared when an attempt starts with fresh = 1).
//   * Shortened nodes are frozen: APP = +-63 (reserved codes, other APPs saturate to +-62), V2C = +-127.
//   * Strict convergence: all layer parities hold AND no APP sign changed during the iteration. A decode that
//     reaches iter_max is still accepted when its hard decision satisfies the syndrome (n_usc == 0).
//   * Trapping-set post-processing: after a failed decode the unsatisfied checks (USC) of the hard decision are
//     computed (n_usc). If n_usc <= pp_max_usc and rounds are left, every key bit touching >= pp_min_usc USCs gets
//     its channel sign inverted and the block is decoded again.
//   * Early termination (et_patience): every iteration counts the unsatisfied checks seen at read time; when the
//     count has not improved for et_patience iterations the decode stops as failed (see S_LEND).
//   * 2026-10-11: check-node magnitude selectable (cn_nms). Normalized min-sum min - (min >> 2) (alpha = 0.75,
//     Zhu et al. JLT 2022 use 0.70-0.79) needs 25-45 % fewer iterations than offset min-sum on all 4 codes at
//     equal or lower f (results/exp_cn.txt); offset min-sum kept for comparison.
//
// ------------------------------------------------------------------------------------------------------------
// Number formats (two's complement)                                    value range         special codes
//   channel LLR of a key bit   lq (5 bit, CSR)                         1 .. 31 (use 8)
//   APP   (7 bit)  posterior LLR, variable-node domain                 -62 .. +62          +63 / -63 frozen
//   C2V   (6 bit)  check-to-variable message, stored per edge          -32 .. +31
//   V2C   (8 bit)  app - c2v (check domain, read pipeline only)        -93 .. +94          +127 / -127 frozen
//   delta (8 bit)  c2v_new - c2v_old (write phase)                     -63 .. +63
//   min1/min2 (7 bit) |v2c| in the serial CNU (MAG_MAX = 127); m1s/m2s (6 bit) <= 32:
//                      NMS min - (min >> 2)  |  OMS max(min - offset, 0)
//   unsat_acc / unsat_best (12 bit) read-time unsatisfied checks per iteration, <= mb * ZC = 1536
//
// Memories (all BSRAM, simple dual port, 1-cycle read latency)        width x depth
//   CH   {type1, type0, bit} planes per variable node                  3*ZC  x 32 per context (rows 0..23)
//   APP                                                                 7*ZC  x 24
//   C2V  one word per edge of the active code (address e_g)            6*ZC  x 128
//   SGN  V2C sign of each edge of the current layer (address e)        ZC    x 32
//   SYN  syndrome rows (0..15) + unsatisfied-check rows (16..31)       ZC    x 32 per context
//   CH and SYN have one bank per block context (2^CTX_W, 2026-10-23): attempts of different blocks share the
//   decoder; only CH (channel types / bits incl. reveals) and SYN survive between attempts of a block.
//
// Control flow (state):
//   S_IDLE -> S_LOAD (24 rows: CH -> initial APP; fresh: clear key-flip marks)
//          -> per layer: S_RD (deg read issues) -> S_WR (deg write issues) -> S_RD of the next layer, overlapped
//             with the write drain; after the last layer of an iteration: -> S_CHK x2 -> S_LEND (all writes and
//             the sign-change flag settle before the convergence / ET decision)
//          -> converged: done | failed: S_USC/S_UEND/S_UP1/S_UP2 per layer -> S_UFIN (n_usc)
//          -> post-processing: S_CNT/S_CFLIP per column -> S_LOAD (no fresh) -> decode again
//
// Pipeline (one edge per cycle; a = issue register stage, RAM addresses come from a_* flip-flops):
//   read   a -> r0 (RAM output register) -> r1 (RAM data, shifter 1st half) -> r1x (2nd half) -> r1b (v2c)
//          -> r2 (CNU update, SGN write)
//   write  a -> w0 (c2v_new; SGN data) -> w1 (delta = c2v_new - c2v_old; C2V / APP data) -> w2 (C2V write, shifter
//          1st half) -> w2b (2nd half) -> w2c (sum) -> w2d (saturate) -> APP write; sign-change check at w3 (+1)
//          and flip_grp (+2)
//   APP and C2V RAMs have an output register (latency 2), CH / SGN / SYN latency 1 (2026-10-24, timing).
//   count  a -> u1 (USC row, shifter 1st half) -> u2 (per-node counters)
//   layer check / ET popcount overlap the write phase (calc_en -> chk_d1 -> chk_d2).
// Layer schedule (model/layer_sched.py): first write issue = last read issue + 6 (r1b of the last read triggers
// S_WR), next layer's first read issue = last write issue + layer_gap (ROM, per code and layer, >= 2), no drain.
// layer_gap is the smallest gap for which no column of the next layer is read while its write is in flight
// (write of column X issued at S lands at the end of S + 8; asserted in simulation). The last layer of an
// iteration drains: next iteration's first read = last write issue + 11. Cycles per iteration are printed by
// layer_sched.py (2026-10-24, latency-2 APP / C2V RAMs: r12 248, r23 211, r34 199, r56 179;
// 2026-10-11: 213 / 201 / 191 / 173; 2026-10-10 serial schedule: 290 / 250 / 226 / 194).
//
// Fixed point: APP 7 bit, C2V 6 bit, V2C 8 bit; NMS x0.75 (cn_nms = 1) or offset 3 (it < 10) / 2 (it < 30) / 1.
module ldpc_ir_decoder #(
    parameter ZC    = 128,
    parameter SH_W  = 7,       // ceil(log2(ZC))
    parameter APP_W = 7,
    parameter C2V_W = 6,
    parameter V2C_W = 8,
    parameter NGRP  = 16,      // shifter control replicated per group of ZC/NGRP lanes (fanout)
    parameter CTX_W = 2        // 2^CTX_W block contexts: channel and syndrome RAMs hold one bank per context
)(
    input                    clk,
    input                    rst,

    input                    start,        // pulse: decode the block in the channel / syndrome RAMs of bank ctx
    input                    fresh,        // with start: clear post-processing sign flips first
    input  [CTX_W-1:0]       ctx,          // context (RAM bank) of the attempt, sampled with start
    input  [1:0]             code,
    input  [7:0]             iter_max,
    input  [4:0]             lq,           // |channel LLR| of a key bit
    input  [1:0]             pp_rounds,
    input  [1:0]             pp_min_usc,
    input  [11:0]            pp_max_usc,
    input  [3:0]             et_patience,  // early termination: stop after this many iterations without
                                           // improvement of the read-time unsatisfied-check count (0 = off)
    input                    cn_nms,       // check-node magnitude: 1 normalized min-sum (x0.75), 0 offset min-sum

    // channel RAM host port, any bank, also while the decoder runs another context: the host owns both RAM
    // ports whenever ch_grant = 1 (decoder outside S_LOAD / S_CNT / S_CFLIP); a host write is performed in a
    // cycle with ch_grant = 1, a host read address presented in such a cycle returns its data one cycle later.
    // Word = {type[1] x ZC, type[0] x ZC, bit x ZC}
    output                   ch_grant,
    input                    h_ch_we,
    input  [CTX_W-1:0]       h_ch_wctx,
    input  [4:0]             h_ch_waddr,
    input  [3*ZC-1:0]        h_ch_wdata,
    input  [CTX_W-1:0]       h_ch_rctx,
    input  [4:0]             h_ch_raddr,
    output [3*ZC-1:0]        h_ch_rdata,

    // syndrome RAM host write port, any bank; performed in a cycle with syn_grant = 1 (no decoder USC write)
    output                   syn_grant,
    input                    h_syn_we,
    input  [CTX_W-1:0]       h_syn_ctx,
    input  [3:0]             h_syn_waddr,
    input  [ZC-1:0]          h_syn_wdata,

    // hard decision read port (only while !busy: the APP RAM is the decoder's working memory), 1-cycle latency
    input  [4:0]             hd_raddr,
    output [ZC-1:0]          hd_rdata,

    output                   busy,
    output reg               done,          // 1-cycle pulse at the end of the attempt
    output reg               converged,
    output reg [11:0]        iters_total,   // iterations summed over all decodes of the attempt
    output reg [1:0]         pp_used,       // post-processing rounds used
    output reg [11:0]        n_usc          // unsatisfied checks of the last decode (0 when converged)
);

    localparam S_IDLE = 4'd0,  S_LOAD = 4'd1, S_RD = 4'd2,                  S_WR = 4'd4,  S_CHK = 4'd5,
               S_LEND = 4'd6,  S_USC = 4'd7,  S_UEND = 4'd8, S_UP1 = 4'd9,  S_UP2 = 4'd10, S_UFIN = 4'd11,
               S_CNT = 4'd12,  S_CFLIP = 4'd13;
    localparam M_RD = 2'd0, M_WR = 2'd1, M_USC = 2'd2, M_CNT = 2'd3;
    localparam [6:0] MAG_MAX = 7'h7F;
    localparam NPOP = ZC / 16;

    reg  [3:0]  state;
    reg  [4:0]  load_cnt;
    reg  [3:0]  layer;
    reg  [6:0]  it;
    reg  [4:0]  issue_e;
    reg         issuing;
    reg         all_ok, any_flip, chk_wait;   // all_ok: every layer check of the iteration passed so far
    reg  [1:0]  code_q;
    reg  [7:0]  iter_max_q;
    reg  [4:0]  lq_q;
    reg         fresh_q;
    reg  [CTX_W-1:0] ctx_q;     // context of the running attempt
    reg  [1:0]  pp_left, pp_min_q;
    reg  [11:0] pp_max_q;
    reg  [4:0]  ccol;
    reg  [11:0] usc_acc;
    reg  [3:0]  et_q;
    reg  [3:0]  wr_tail;        // cycles since the last write issue of the layer (S_WR)
    reg         nms_q;          // cn_nms latched at start
    reg  [11:0] unsat_acc;      // read-time unsatisfied checks of the current iteration (sum over layers)
    reg  [11:0] unsat_best;     // best (lowest) per-iteration count of this decode
    reg  [7:0]  et_stall;       // iterations since unsat_best last improved

    // `it`-derived controls are registered: `it` only changes at S_LOAD / S_LEND, many cycles before the
    // read (first_r) and calc_en (offset_r) stages that use them.
    reg        first_r;         // first iteration: C2V RAM content is ignored (treated as 0)
    reg  [2:0] offset_r;        // offset min-sum: 3 (it < 10), 2 (it < 30), 1
    always @(posedge clk) begin
        first_r  <= (it == 7'd0);
        offset_r <= (it < 7'd10) ? 3'd3 : (it < 7'd30) ? 3'd2 : 3'd1;
    end

    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------------
    // Code ROM
    // ------------------------------------------------------------------
    wire [3:0]      num_layers;
    wire [3:0]      layer_gap;      // last write issue -> next layer's first read issue (cycles)
    wire [4:0]      layer_deg, e_col;
    wire [SH_W-1:0] e_shift, c_shift;
    wire [6:0]      e_g;
    wire [2:0]      col_deg;
    wire [3:0]      c_layer;

    ldpc_code_rom u_rom (
        .code(code_q), .layer(layer), .e(issue_e),
        .num_layers(num_layers), .layer_gap(layer_gap), .layer_deg(layer_deg), .e_col(e_col), .e_shift(e_shift), .e_g(e_g),
        .col(ccol), .ce(issue_e[2:0]), .col_deg(col_deg), .c_layer(c_layer), .c_shift(c_shift)
    );

    // Last edge index of the current layer / column, registered off the ROM path. The value lags one cycle
    // after layer / ccol change; that cycle compares against issue_e = 0, and every row and column degree is
    // >= 2 (checked by gen_rom.py), so the lag never matters.
    reg  [4:0] row_last, col_last;
    always @(posedge clk) begin
        row_last <= layer_deg - 5'd1;
        col_last <= {2'd0, col_deg} - 5'd1;
    end
    wire [4:0] last_e = (state == S_CNT) ? col_last : row_last;

    // issue stage registers: RAM read addresses come straight from flip-flops
    reg            a_valid;
    reg  [1:0]     a_mode;
    reg  [4:0]     a_e;
    reg  [4:0]     a_col;
    reg  [SH_W-1:0] a_shift, a_inv;
    reg  [6:0]     a_g;
    reg  [3:0]     a_ulayer;

    // ------------------------------------------------------------------
    // Memories
    // ------------------------------------------------------------------
    reg              d_ch_we;
    reg  [4:0]       d_ch_waddr;
    reg  [3*ZC-1:0]  d_ch_wdata;
    wire [4:0]       d_ch_raddr = (state == S_LOAD) ? load_cnt : ccol;
    wire [3*ZC-1:0]  ch_rdata;
    // The decoder uses the channel RAM only while loading the APP (S_LOAD, incl. its last write-back) and during
    // post-processing (S_CNT / S_CFLIP, incl. the flip write that lands in the following S_CNT / S_LOAD cycle).
    // Everywhere else the host (block controller) owns both ports: it loads other contexts and applies reveals
    // of waiting contexts while this one decodes.
    wire ch_own = (state == S_LOAD) || (state == S_CNT) || (state == S_CFLIP);
    assign ch_grant = !ch_own;
    ldpc_sdp_ram #(.DATA_W(3*ZC), .DEPTH(32 << CTX_W), .ADDR_W(5 + CTX_W)) u_ch_ram (
        .clk(clk), .we(ch_own ? d_ch_we : h_ch_we),
        .waddr(ch_own ? {ctx_q, d_ch_waddr} : {h_ch_wctx, h_ch_waddr}),
        .wdata(ch_own ? d_ch_wdata : h_ch_wdata),
        .raddr(ch_own ? {ctx_q, d_ch_raddr} : {h_ch_rctx, h_ch_raddr}), .rdata(ch_rdata)
    );
    assign h_ch_rdata = ch_rdata;

    reg                  app_we;
    reg  [4:0]           app_waddr;
    reg  [ZC*APP_W-1:0]  app_wdata;
    wire [ZC*APP_W-1:0]  app_rdata;
    // APP and C2V: BSRAM output register (read latency 2, 2026-10-24): the 896 / 768-bit read buses had ~8 ns of
    // routing from the RAM to the shifter / write datapath in the 65 MHz PnR.
    ldpc_sdp_ram #(.DATA_W(ZC*APP_W), .DEPTH(24), .ADDR_W(5), .OUT_REG(1)) u_app_ram (
        .clk(clk), .we(app_we), .waddr(app_waddr), .wdata(app_wdata),
        .raddr(busy ? a_col : hd_raddr), .rdata(app_rdata)
    );

    reg                  c2v_we;
    reg  [6:0]           c2v_waddr;
    reg  [ZC*C2V_W-1:0]  c2v_wdata;
    wire [ZC*C2V_W-1:0]  c2v_rdata;
    ldpc_sdp_ram #(.DATA_W(ZC*C2V_W), .DEPTH(128), .ADDR_W(7), .OUT_REG(1)) u_c2v_ram (
        .clk(clk), .we(c2v_we), .waddr(c2v_waddr), .wdata(c2v_wdata), .raddr(a_g), .rdata(c2v_rdata)
    );

    // signs of the V2C messages of the current layer (the write phase recomputes the APP as
    // app_old + inv_shift(c2v_new - c2v_old), so only the V2C sign has to be kept)
    reg                  s_we;
    reg  [4:0]           s_waddr;
    reg  [ZC-1:0]        s_wdata;
    wire [ZC-1:0]        s_rdata;
    ldpc_sdp_ram #(.DATA_W(ZC), .DEPTH(32), .ADDR_W(5)) u_sgn_ram (
        .clk(clk), .we(s_we), .waddr(s_waddr), .wdata(s_wdata), .raddr(a_e), .rdata(s_rdata)
    );

    // syndrome (addr 0..15) and unsatisfied-check rows (addr 16..31) share one RAM, one 32-row bank per context.
    // Write port: the decoder's USC write (one cycle per layer after a failed decode) has priority.
    reg              d_syn_we;
    reg  [ZC-1:0]    d_syn_wdata;
    wire [ZC-1:0]    syn_rdata;
    assign syn_grant = !d_syn_we;
    ldpc_sdp_ram #(.DATA_W(ZC), .DEPTH(32 << CTX_W), .ADDR_W(5 + CTX_W)) u_syn_ram (
        .clk(clk), .we(d_syn_we | h_syn_we),
        .waddr(d_syn_we ? {ctx_q, 1'b1, layer} : {h_syn_ctx, 1'b0, h_syn_waddr}),
        .wdata(d_syn_we ? d_syn_wdata : h_syn_wdata),
        .raddr((state == S_CNT) ? {ctx_q, 1'b1, a_ulayer} : {ctx_q, 1'b0, layer}), .rdata(syn_rdata)
    );

    genvar j;
    generate
        for (j = 0; j < ZC; j = j + 1) begin : g_hd
            assign hd_rdata[j] = app_rdata[j*APP_W + APP_W - 1];
        end
    endgenerate

    // ------------------------------------------------------------------
    // Pipeline registers
    // ------------------------------------------------------------------
    reg        r0_valid, r0_usc;  reg [4:0] r0_e;  reg [SH_W-1:0] r0_shift;   // APP / C2V RAM latency 2
    reg        r1_valid, r1_usc;  reg [4:0] r1_e;
    reg        r1x_valid, r1x_usc; reg [4:0] r1x_e;  reg [ZC*C2V_W-1:0] r1x_c2v;   // shifter latency
    reg        r1b_valid, r1b_usc; reg [4:0] r1b_e;
    reg  [ZC*V2C_W-1:0] r1b_sh;
    reg  [ZC*C2V_W-1:0] r1b_c2v;
    reg        r2_valid;  reg [4:0] r2_e;  reg [ZC*V2C_W-1:0] r2_v2c;
    reg  [NGRP*5-1:0]   r2_e_rep /* synthesis syn_preserve = 1 */;   // r2_e per lane group (fanout 128)
    // w0: c2v_new from min1/min2/rsgn and the V2C sign (SGN RAM latency 1); w1: delta = c2v_new - c2v_old
    // (C2V RAM latency 2) and old APP (APP RAM latency 2)
    reg        w0_valid;  reg [4:0] w0_e;  reg [SH_W-1:0] w0_shift;  reg [4:0] w0_col;  reg [6:0] w0_g;
    reg  [NGRP*5-1:0]   w0_e_rep /* synthesis syn_preserve = 1 */;   // w0_e per lane group (fanout 128)
    reg        w1_valid;  reg [4:0] w1_e;  reg [SH_W-1:0] w1_shift;  reg [4:0] w1_col;  reg [6:0] w1_g;
    reg  [ZC*C2V_W-1:0] w1_r;           // c2v_new
    reg        w2_valid;  reg [4:0] w2_e;  reg [4:0] w2_col;  reg [6:0] w2_g;
    reg  [ZC*V2C_W-1:0] w2_delta;       // c2v_new - c2v_old (check domain)
    reg  [ZC*C2V_W-1:0] w2_r;
    reg  [ZC*APP_W-1:0] w2_app;         // old APP (variable-node domain)
    reg        w2b_valid; reg [4:0] w2b_e;  reg [4:0] w2b_col;  reg [ZC*APP_W-1:0] w2b_app;   // shifter latency
    // w2c: register after the shifter so that "add + saturate" gets a cycle of its own (timing)
    reg        w2c_valid; reg [4:0] w2c_e;  reg [4:0] w2c_col;  reg [ZC*APP_W-1:0] w2c_app;
    reg  [ZC*V2C_W-1:0] w2c_dsh;        // inverse-shifted delta
    // w2d: app_old + delta registered; saturation in its own cycle before the APP write register (timing)
    reg        w2d_valid; reg [4:0] w2d_e;  reg [4:0] w2d_col;  reg [ZC*APP_W-1:0] w2d_app;
    reg  [ZC*V2C_W-1:0] w2d_sum;
    // layer check / early termination: read-time parity of the layer, compared during the write phase
    reg        calc_en;                 // one cycle after r2 of the last read edge, registered for the fanout
    reg        chk_d1, chk_d2;          // calc_en delayed by 1 / 2 cycles
    reg  [ZC-1:0]       chk_vec;        // unsatisfied checks of the layer at read time
    reg  [5*NPOP-1:0]   chk_pop;        // their 16-lane popcounts
    reg        u1_valid;  reg [4:0] u1_e;
    reg        u2_valid;  reg [4:0] u2_e;
    reg  [NPOP-1:0]     chk_grp;
    // sign-change detection, pipelined after the APP write register (w3) in groups of 16 lanes
    reg        w3_valid;
    reg  [ZC-1:0]       w3_oldsgn;
    reg  [NPOP-1:0]     flip_grp;

    // Shared cyclic shifter (latency 1). Control registered one cycle ahead, replicated NGRP times.
    //   read / USC pass : forward shift of the APP read from RAM
    //   write phase     : inverse shift of c2v_new - c2v_old
    //   count pass      : inverse shift of an unsatisfied-check row (bit 0 of each lane)
    wire [SH_W-1:0]      w1_inv = (w1_shift == {SH_W{1'b0}}) ? {SH_W{1'b0}} : (ZC - w1_shift);
    reg  [NGRP*SH_W-1:0] sh_amt_rep /* synthesis syn_preserve = 1 */;
    reg  [NGRP*2-1:0]    sel_rep    /* synthesis syn_preserve = 1 */;
    wire [ZC*V2C_W-1:0]  sh_in;
    wire [ZC*V2C_W-1:0]  sh_out;
    // pipelined after stage SH_W/2: sh_out is valid one cycle after sh_in
    qc_cyclic_shifter #(.ZC(ZC), .WORD_W(V2C_W), .SHIFT_W(SH_W), .NGRP(NGRP), .PIPE_AT(SH_W/2)) u_shifter (
        .clk(clk), .data_in(sh_in), .shift_amt(sh_amt_rep), .data_out(sh_out)
    );

    integer gi;
    always @(posedge clk) begin
        for (gi = 0; gi < NGRP; gi = gi + 1) begin
            // selected by the pipeline stage, not the state: the next layer's reads start while the last
            // writes are still in w1 / w2 (a read in stage a and a write in w1 never coincide, see S_WR)
            sh_amt_rep[gi*SH_W +: SH_W] <= w1_valid ? w1_inv : (state == S_CNT) ? a_inv : r0_shift;
            sel_rep[gi*2 +: 2]          <= w1_valid ? 2'd1 : (state == S_CNT) ? 2'd2 : 2'd0;
        end
    end

    // ------------------------------------------------------------------
    // Per-lane datapath
    // ------------------------------------------------------------------
    wire [ZC*V2C_W-1:0] v2c_next;
    wire [ZC*V2C_W-1:0] delta_next;
    wire [ZC*C2V_W-1:0] r_next;
    wire [ZC*APP_W-1:0] app_fin;
    wire [ZC*V2C_W-1:0] sum_next;
    wire [ZC-1:0]       uacc_vec;
    wire [ZC-1:0]       flip_mask;
    wire [3*ZC-1:0]     ch_load_wb;      // channel row with key-flip marks cleared (fresh)
    wire [ZC*APP_W-1:0] ch_app;          // initial APP of a channel row

    generate
        for (j = 0; j < ZC; j = j + 1) begin : g_lane
            reg [6:0] min1, min2;
            reg [4:0] min_i;
            reg       sx;
            reg [5:0] m1s, m2s;
            reg       rsgn;
            reg       uacc;
            reg [1:0] cnt;
            wire [6:0] d1 = min1 - {4'd0, offset_r};
            wire [6:0] d2 = min2 - {4'd0, offset_r};
            wire [6:0] n1 = min1 - {2'd0, min1[6:2]};        // normalized min-sum: floor(min * 0.75)
            wire [6:0] n2 = min2 - {2'd0, min2[6:2]};

            // ---- read phase stage 1b: v2c = shift(app) - c2v_old (frozen nodes -> +-127)
            wire signed [V2C_W-1:0] app_s = r1b_sh[j*V2C_W +: V2C_W];
            wire signed [C2V_W-1:0] c2v_o = r1b_c2v[j*C2V_W +: C2V_W];
            wire signed [V2C_W-1:0] c2v_x = first_r ? {V2C_W{1'b0}} : {{(V2C_W-C2V_W){c2v_o[C2V_W-1]}}, c2v_o};
            assign v2c_next[j*V2C_W +: V2C_W] = (app_s == 8'sh3F) ? 8'sh7F :
                                                (app_s == 8'shC1) ? 8'sh81 : app_s - c2v_x;

            // ---- read phase stage 2: serial CNU
            wire signed [V2C_W-1:0] v2c_r = r2_v2c[j*V2C_W +: V2C_W];
            wire [4:0]              e_r2  = r2_e_rep[(j*NGRP/ZC)*5 +: 5];
            wire [4:0]              e_w0  = w0_e_rep[(j*NGRP/ZC)*5 +: 5];
            wire                    v_sgn = v2c_r[V2C_W-1];
            wire [V2C_W-1:0]        v_abs = v_sgn ? (~v2c_r + 1'b1) : v2c_r;
            wire [6:0]              mag   = v_abs[6:0];           // |v2c| <= 127

            always @(posedge clk) begin
                if (r2_valid) begin
                    if (e_r2 == 5'd0) begin
                        min1 <= mag;  min2 <= MAG_MAX;  min_i <= 5'd0;  sx <= v_sgn;
                    end else begin
                        sx <= sx ^ v_sgn;
                        if (mag < min1) begin
                            min2 <= min1;  min1 <= mag;  min_i <= e_r2;
                        end else if (mag < min2) begin
                            min2 <= mag;
                        end
                    end
                end
                if (calc_en) begin
                    // |c2v| clamped to 32 (6-bit C2V range; +32 becomes +31 at the sign stage)
                    //   normalized min-sum (cn_nms = 1): min - (min >> 2)      (model CN_MODE "nms75")
                    //   offset min-sum     (cn_nms = 0): max(min - offset, 0)  (model CN_MODE "oms")
                    if (nms_q) begin
                        m1s <= (n1 >= 7'd32) ? 6'd32 : n1[5:0];
                        m2s <= (n2 >= 7'd32) ? 6'd32 : n2[5:0];
                    end else begin
                        m1s <= (min1 <= {4'd0, offset_r}) ? 6'd0 : (d1 >= 7'd32) ? 6'd32 : d1[5:0];
                        m2s <= (min2 <= {4'd0, offset_r}) ? 6'd0 : (d2 >= 7'd32) ? 6'd32 : d2[5:0];
                    end
                    rsgn <= sx ^ syn_rdata[j];
                end
                // read phase / USC pass: XOR of the hard decisions of the check's variable nodes. In the
                // read phase this is the layer parity check (equal to the post-update parity whenever no
                // APP sign changes, which strict convergence requires anyway)
                if (r1b_valid)
                    uacc <= (r1b_e == 5'd0) ? app_s[V2C_W-1] : (uacc ^ app_s[V2C_W-1]);
                // count pass: unsatisfied checks per variable node (saturating at 3)
                if (u2_valid)
                    cnt <= (u2_e == 5'd0) ? {1'b0, sh_out[j*V2C_W]} :
                           (cnt == 2'd3)  ? 2'd3 : cnt + {1'b0, sh_out[j*V2C_W]};
            end
            assign uacc_vec[j] = uacc;

            // ---- write phase stage w0: c2v_new (check domain)
            wire [5:0]              mg    = (min_i == e_w0) ? m2s : m1s;
            wire                    neg   = rsgn ^ s_rdata[j];
            wire [5:0]              mg_p  = mg[5] ? 6'd31 : mg;            // +32 saturates to +31
            wire signed [C2V_W-1:0] r_val = neg ? (~mg + 1'b1) : mg_p;     // -32 is representable
            assign r_next[j*C2V_W +: C2V_W] = r_val;
            // ---- write phase stage w1: delta = c2v_new - c2v_old
            wire signed [C2V_W-1:0] r_w1  = w1_r[j*C2V_W +: C2V_W];
            wire signed [C2V_W-1:0] c2v_w = c2v_rdata[j*C2V_W +: C2V_W];
            wire signed [V2C_W-1:0] c2v_wx = first_r ? {V2C_W{1'b0}} : {{(V2C_W-C2V_W){c2v_w[C2V_W-1]}}, c2v_w};
            assign delta_next[j*V2C_W +: V2C_W] = {{(V2C_W-C2V_W){r_w1[C2V_W-1]}}, r_w1} - c2v_wx;

            // ---- write phase stage w2c (after the inverse shift and its output register): sum = app_old + delta
            //      (= v2c + c2v_new); stage w2d: saturate to +-62, frozen nodes (+-63) keep their value
            wire signed [V2C_W-1:0] dsh   = w2c_dsh[j*V2C_W +: V2C_W];
            wire [APP_W-1:0]        app_c = w2c_app[j*APP_W +: APP_W];
            assign sum_next[j*V2C_W +: V2C_W] = {{(V2C_W-APP_W){app_c[APP_W-1]}}, app_c} + dsh;   // |sum| <= 125
            wire [APP_W-1:0]        app_o = w2d_app[j*APP_W +: APP_W];
            wire signed [V2C_W-1:0] sum   = w2d_sum[j*V2C_W +: V2C_W];
            assign app_fin[j*APP_W +: APP_W] = (app_o == 7'h3F || app_o == 7'h41) ? app_o :
                                               (sum > 8'sd62)  ? 7'h3E :
                                               (sum < -8'sd62) ? 7'h42 : sum[APP_W-1:0];

            // shifter input
            wire [APP_W-1:0] app_l = app_rdata[j*APP_W +: APP_W];
            wire [1:0]       sel   = sel_rep[(j*NGRP/ZC)*2 +: 2];
            assign sh_in[j*V2C_W +: V2C_W] = (sel == 2'd1) ? w2_delta[j*V2C_W +: V2C_W] :
                                             (sel == 2'd2) ? {{(V2C_W-1){1'b0}}, syn_rdata[j]} :
                                                             {{(V2C_W-APP_W){app_l[APP_W-1]}}, app_l};

            // ---- channel row: type / bit planes
            wire t1 = ch_rdata[2*ZC + j];
            wire t0 = ch_rdata[ZC + j];
            wire b  = ch_rdata[j];
            wire c1 = fresh_q ? (t1 & ~t0) : t1;        // fresh: 11 (key, flipped) -> 00
            wire c0 = fresh_q ? (t0 & ~t1) : t0;
            assign ch_load_wb[2*ZC + j] = c1;
            assign ch_load_wb[ZC + j]   = c0;
            assign ch_load_wb[j]        = b;
            wire [APP_W-1:0] lq_p = {2'b00, lq_q};
            wire [APP_W-1:0] lq_n = ~lq_p + 1'b1;
            assign ch_app[j*APP_W +: APP_W] = ({c1, c0} == 2'b00) ? (b ? lq_n : lq_p) :
                                              ({c1, c0} == 2'b11) ? (b ? lq_p : lq_n) :
                                              ({c1, c0} == 2'b10) ? (b ? 7'h41 : 7'h3F) : {APP_W{1'b0}};
            assign flip_mask[j] = (cnt >= pp_min_q) && (t1 == t0);
        end
    endgenerate

    // 16-bit popcounts of the unsatisfied-check row (2-cycle pipelined sum)
    reg  [ZC-1:0]   usc_r;
    reg  [5*NPOP-1:0] pop_grp;
    integer pg, pb;
    reg  [4:0]  pop_tmp;
    reg  [11:0] pop_sum;
    always @(*) begin
        pop_sum = 12'd0;
        for (pg = 0; pg < NPOP; pg = pg + 1) pop_sum = pop_sum + pop_grp[pg*5 +: 5];
    end

    // ------------------------------------------------------------------
    // Control
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            done <= 1'b0; converged <= 1'b0; iters_total <= 12'd0; pp_used <= 2'd0; n_usc <= 12'd0;
            load_cnt <= 5'd0; layer <= 4'd0; it <= 7'd0; issue_e <= 5'd0; issuing <= 1'b0;
            all_ok <= 1'b1; any_flip <= 1'b0; chk_wait <= 1'b0; w3_valid <= 1'b0; flip_grp <= {NPOP{1'b0}};
            code_q <= 2'd0; iter_max_q <= 8'd1; lq_q <= 5'd8; fresh_q <= 1'b0; ctx_q <= {CTX_W{1'b0}};
            pp_left <= 2'd0; pp_min_q <= 2'd2; pp_max_q <= 12'd0; ccol <= 5'd0; usc_acc <= 12'd0;
            app_we <= 1'b0; c2v_we <= 1'b0; s_we <= 1'b0; d_ch_we <= 1'b0; d_syn_we <= 1'b0;
            a_valid <= 1'b0; r0_valid <= 1'b0; r1_valid <= 1'b0; r1b_valid <= 1'b0; r2_valid <= 1'b0;
            w0_valid <= 1'b0; w1_valid <= 1'b0; w2_valid <= 1'b0; u1_valid <= 1'b0;
            r1x_valid <= 1'b0; w2b_valid <= 1'b0; u2_valid <= 1'b0; w2c_valid <= 1'b0; w2d_valid <= 1'b0;
            wr_tail <= 4'd0;
            calc_en <= 1'b0; chk_d1 <= 1'b0; chk_d2 <= 1'b0;
            et_q <= 4'd0; unsat_acc <= 12'd0; unsat_best <= 12'hFFF; et_stall <= 8'd0;
        end else begin
            done     <= 1'b0;
            app_we   <= 1'b0;
            c2v_we   <= 1'b0;
            s_we     <= 1'b0;
            d_ch_we  <= 1'b0;
            d_syn_we <= 1'b0;

            // issue stage
            a_valid  <= ((state == S_RD) || (state == S_WR) || (state == S_USC) || (state == S_CNT)) && issuing;
            a_mode   <= (state == S_WR) ? M_WR : (state == S_USC) ? M_USC : (state == S_CNT) ? M_CNT : M_RD;
            a_e      <= issue_e;
            a_col    <= e_col;
            a_shift  <= e_shift;
            a_g      <= e_g;
            a_ulayer <= c_layer;
            a_inv    <= (c_shift == {SH_W{1'b0}}) ? {SH_W{1'b0}} : (ZC - c_shift);

            // read pipeline (decoding and USC pass); APP / C2V RAM data valid in r1 (= a + 2)
            r0_valid  <= a_valid && (a_mode == M_RD || a_mode == M_USC);
            r0_usc    <= (a_mode == M_USC);
            r0_e      <= a_e;
            r0_shift  <= a_shift;
            r1_valid  <= r0_valid;
            r1_usc    <= r0_usc;
            r1_e      <= r0_e;
            r1x_valid <= r1_valid;
            r1x_usc   <= r1_usc;
            r1x_e     <= r1_e;
            r1x_c2v   <= c2v_rdata;
            r1b_valid <= r1x_valid;
            r1b_usc   <= r1x_usc;
            r1b_e     <= r1x_e;
            r1b_sh    <= sh_out;
            r1b_c2v   <= r1x_c2v;
            r2_valid  <= r1b_valid && !r1b_usc;
            r2_e      <= r1b_e;
            r2_e_rep  <= {NGRP{r1b_e}};
            r2_v2c    <= v2c_next;
            if (r2_valid) begin
                s_we    <= 1'b1;
                s_waddr <= r2_e;
                begin : v2c_sign
                    integer k;
                    for (k = 0; k < ZC; k = k + 1) s_wdata[k] <= r2_v2c[k*V2C_W + V2C_W - 1];
                end
            end

            // write pipeline: a -> w0 (c2v_new) -> w1 (delta, RAM data) -> w2 (C2V write, shifter) -> w2b -> w2c
            //                 (sum) -> w2d (saturate) -> APP write
            w0_valid  <= a_valid && (a_mode == M_WR);
            w0_e      <= a_e;
            w0_e_rep  <= {NGRP{a_e}};
            w0_shift  <= a_shift;
            w0_col    <= a_col;
            w0_g      <= a_g;
            w1_valid  <= w0_valid;
            w1_e      <= w0_e;
            w1_shift  <= w0_shift;
            w1_col    <= w0_col;
            w1_g      <= w0_g;
            w1_r      <= r_next;
            w2_valid  <= w1_valid;
            w2_e      <= w1_e;
            w2_col    <= w1_col;
            w2_g      <= w1_g;
            w2_delta  <= delta_next;
            w2_r      <= w1_r;
            w2_app    <= app_rdata;
            w2b_valid <= w2_valid;
            w2b_e     <= w2_e;
            w2b_col   <= w2_col;
            w2b_app   <= w2_app;
            w2c_valid <= w2b_valid;
            w2c_e     <= w2b_e;
            w2c_col   <= w2b_col;
            w2c_app   <= w2b_app;
            w2c_dsh   <= sh_out;
            w2d_valid <= w2c_valid;
            w2d_e     <= w2c_e;
            w2d_col   <= w2c_col;
            w2d_app   <= w2c_app;
            w2d_sum   <= sum_next;
            w3_valid  <= w2d_valid;
            begin : old_sign
                integer k;
                for (k = 0; k < ZC; k = k + 1) w3_oldsgn[k] <= w2d_app[k*APP_W + APP_W - 1];
            end
            begin : flip_detect
                integer g, k;
                for (g = 0; g < NPOP; g = g + 1) begin
                    flip_grp[g] <= 1'b0;
                    for (k = 0; k < 16; k = k + 1)
                        if (w3_valid && (app_wdata[(g*16+k)*APP_W + APP_W - 1] != w3_oldsgn[g*16+k]))
                            flip_grp[g] <= 1'b1;
                end
            end
            if (w2_valid) begin
                c2v_we    <= 1'b1;
                c2v_waddr <= w2_g;
                c2v_wdata <= w2_r;
            end
            if (w2d_valid) begin
                app_we    <= 1'b1;
                app_waddr <= w2d_col;
                app_wdata <= app_fin;
            end

            // layer check + early-termination count, overlapped with the write phase:
            //   calc_en     : chk_vec = read-time parity ^ syndrome (uacc is final once the read phase ended),
            //                 min1/min2 -> m1s/m2s, rsgn (per lane, above); one cycle after r2 of the last edge,
            //                 i.e. exactly when w0 of the first write of the layer needs them
            //   calc_en + 1 : per-16-lane OR (layer check) and popcount
            //   calc_en + 2 : all_ok &= layer check, unsat_acc += popcount
            calc_en <= r2_valid && (r2_e == last_e);
            chk_d1  <= calc_en;
            chk_d2  <= chk_d1;
            if (calc_en) chk_vec <= uacc_vec ^ syn_rdata;
            if (chk_d1) begin : chk_stage1
                integer g, k;
                reg [4:0] pc;
                for (g = 0; g < NPOP; g = g + 1) begin
                    chk_grp[g] <= |chk_vec[g*16 +: 16];
                    pc = 5'd0;
                    for (k = 0; k < 16; k = k + 1) pc = pc + {4'd0, chk_vec[g*16 + k]};
                    chk_pop[g*5 +: 5] <= pc;
                end
            end
            if (chk_d2) begin : chk_stage2
                integer g;
                reg [11:0] ps;
                all_ok <= all_ok & ~|chk_grp;      // every layer of the iteration must match its syndrome
                ps = 12'd0;
                for (g = 0; g < NPOP; g = g + 1) ps = ps + {7'd0, chk_pop[g*5 +: 5]};
                unsat_acc <= unsat_acc + ps;
            end

            // count pipeline
            u1_valid <= a_valid && (a_mode == M_CNT);
            u1_e     <= a_e;
            u2_valid <= u1_valid;
            u2_e     <= u1_e;

            case (state)
                S_IDLE: begin
                    if (start) begin
                        code_q      <= code;
                        iter_max_q  <= (iter_max == 8'd0) ? 8'd1 : iter_max;
                        lq_q        <= lq;
                        fresh_q     <= fresh;
                        ctx_q       <= ctx;
                        pp_left     <= pp_rounds;
                        pp_min_q    <= pp_min_usc;
                        pp_max_q    <= pp_max_usc;
                        et_q        <= et_patience;
                        nms_q       <= cn_nms;
                        iters_total <= 12'd0;
                        pp_used     <= 2'd0;
                        n_usc       <= 12'd0;
                        converged   <= 1'b0;
                        load_cnt    <= 5'd0;
                        state       <= S_LOAD;
                    end
                end
                S_LOAD: begin
                    // CH RAM latency 1: row load_cnt-1 is on ch_rdata while load_cnt is presented
                    if (load_cnt != 5'd0 && load_cnt <= 5'd24) begin
                        app_we    <= 1'b1;
                        app_waddr <= load_cnt - 5'd1;
                        app_wdata <= ch_app;
                        if (fresh_q) begin
                            d_ch_we    <= 1'b1;
                            d_ch_waddr <= load_cnt - 5'd1;
                            d_ch_wdata <= ch_load_wb;
                        end
                    end
                    if (load_cnt == 5'd25) begin
                        fresh_q  <= 1'b0;
                        layer    <= 4'd0;
                        it       <= 7'd0;
                        all_ok     <= 1'b1;
                        any_flip   <= 1'b0;
                        unsat_acc  <= 12'd0;
                        unsat_best <= 12'hFFF;
                        et_stall   <= 8'd0;
                        issue_e    <= 5'd0;
                        issuing    <= 1'b1;
                        state      <= S_RD;
                    end else begin
                        load_cnt <= load_cnt + 5'd1;
                    end
                end
                S_RD: begin
                    if (issuing) begin
                        if (issue_e == last_e) issuing <= 1'b0;
                        else issue_e <= issue_e + 5'd1;
                    end
                    // last edge in r1b: the first write is issued next cycle (last read issue + 5). Its w1 stage
                    // comes one cycle after calc_en (r2 of the last edge) registered m1s / m2s / rsgn.
                    if (r1b_valid && !r1b_usc && r1b_e == last_e) begin
                        issue_e <= 5'd0;
                        issuing <= 1'b1;
                        state   <= S_WR;
                    end
                end
                S_WR: begin
                    if (issuing) begin
                        if (issue_e == last_e) issuing <= 1'b0;
                        else issue_e <= issue_e + 5'd1;
                    end
                    if (issuing && issue_e == last_e) wr_tail <= 4'd1;
                    else if (!issuing)                wr_tail <= wr_tail + 4'd1;
                    if (layer != num_layers - 4'd1) begin
                        // Overlap: start reading the next layer layer_gap cycles after the last write issue, while
                        // the writes drain. layer_gap >= 2 (a read in stage r0 never meets a write in w1, so the
                        // shared shifter is free for it) and large enough that no column of the next layer is read
                        // while its write is in flight (model/layer_sched.py, generated into the ROM; checked by
                        // the simulation assertion below). No stall logic.
                        if (!issuing && wr_tail + 4'd1 >= layer_gap) begin
                            layer   <= layer + 4'd1;
                            issue_e <= 5'd0;
                            issuing <= 1'b1;
                            state   <= S_RD;
                        end
                    end else if (w2d_valid && w2d_e == last_e) begin
                        // last layer of the iteration: wait for its last APP write and sign-change flag
                        state <= S_CHK;
                    end
                end
                S_CHK: begin
                    chk_wait <= ~chk_wait;
                    if (chk_wait) state <= S_LEND;
                end
                S_LEND: begin
                    // end of an iteration (only the last layer comes here; the others overlap into S_RD)
                    issue_e <= 5'd0;
                    begin
                        if (all_ok && !any_flip) begin
                            converged   <= 1'b1;
                            iters_total <= iters_total + {5'd0, it} + 12'd1;
                            n_usc       <= 12'd0;
                            done        <= 1'b1;
                            state       <= S_IDLE;
                        end else if (({1'b0, it} + 8'd1 >= iter_max_q) ||
                                     (et_q != 4'd0 && unsat_acc >= unsat_best && et_stall + 8'd1 >= {4'd0, et_q})) begin
                            // failed (iteration budget used up, or early termination: no improvement of the
                            // read-time unsatisfied count for et_q iterations): count the unsatisfied checks
                            // of the final hard decision
                            iters_total <= iters_total + {5'd0, it} + 12'd1;
                            layer       <= 4'd0;
                            usc_acc     <= 12'd0;
                            issuing     <= 1'b1;
                            state       <= S_USC;
                        end else begin
                            if (unsat_acc < unsat_best) begin
                                unsat_best <= unsat_acc;
                                et_stall   <= 8'd0;
                            end else begin
                                et_stall   <= et_stall + 8'd1;
                            end
                            unsat_acc <= 12'd0;
                            it        <= it + 7'd1;
                            layer     <= 4'd0;
                            all_ok    <= 1'b1;
                            issuing   <= 1'b1;
                            state     <= S_RD;
                        end
                    end
                end

                // ---- unsatisfied checks: usc[layer] = XOR of hard decisions ^ syndrome
                S_USC: begin
                    if (issuing) begin
                        if (issue_e == last_e) issuing <= 1'b0;
                        else issue_e <= issue_e + 5'd1;
                    end
                    if (r1b_valid && r1b_usc && r1b_e == last_e) state <= S_UEND;
                end
                S_UEND: begin
                    usc_r       <= uacc_vec ^ syn_rdata;
                    d_syn_we    <= 1'b1;               // stored at address 16 + layer
                    d_syn_wdata <= uacc_vec ^ syn_rdata;
                    state       <= S_UP1;
                end
                S_UP1: begin
                    for (pg = 0; pg < NPOP; pg = pg + 1) begin
                        pop_tmp = 5'd0;
                        for (pb = 0; pb < 16; pb = pb + 1) pop_tmp = pop_tmp + {4'd0, usc_r[pg*16 + pb]};
                        pop_grp[pg*5 +: 5] <= pop_tmp;
                    end
                    state <= S_UP2;
                end
                S_UP2: begin
                    usc_acc <= usc_acc + pop_sum;
                    issue_e <= 5'd0;
                    if (layer == num_layers - 4'd1) begin
                        state <= S_UFIN;
                    end else begin
                        layer   <= layer + 4'd1;
                        issuing <= 1'b1;
                        state   <= S_USC;
                    end
                end
                S_UFIN: begin
                    n_usc <= usc_acc;
                    if (usc_acc == 12'd0) begin
                        // hard decision satisfies the syndrome (only APP signs kept moving): accept
                        converged <= 1'b1;
                        done      <= 1'b1;
                        state     <= S_IDLE;
                    end else if (pp_left != 2'd0 && usc_acc <= pp_max_q) begin
                        pp_left <= pp_left - 2'd1;
                        pp_used <= pp_used + 2'd1;
                        ccol    <= 5'd0;
                        issue_e <= 5'd0;
                        issuing <= 1'b1;
                        state   <= S_CNT;
                    end else begin
                        converged <= 1'b0;
                        done      <= 1'b1;
                        state     <= S_IDLE;
                    end
                end

                // ---- post-processing: per column, count USCs per node, invert the channel sign
                S_CNT: begin
                    if (issuing) begin
                        if (issue_e == last_e) issuing <= 1'b0;
                        else issue_e <= issue_e + 5'd1;
                    end
                    if (u2_valid && u2_e == last_e) state <= S_CFLIP;
                end
                S_CFLIP: begin
                    d_ch_we    <= 1'b1;
                    d_ch_waddr <= ccol;
                    d_ch_wdata <= {ch_rdata[3*ZC-1:2*ZC] ^ flip_mask, ch_rdata[2*ZC-1:ZC] ^ flip_mask, ch_rdata[ZC-1:0]};
                    issue_e    <= 5'd0;
                    if (ccol == 5'd23) begin
                        load_cnt <= 5'd0;
                        state    <= S_LOAD;
                    end else begin
                        ccol    <= ccol + 5'd1;
                        issuing <= 1'b1;
                        state   <= S_CNT;
                    end
                end
                default: state <= S_IDLE;
            endcase

            // strict convergence: any APP sign change during the iteration (cleared when an iteration starts)
            if (state == S_LEND)  any_flip <= 1'b0;
            else if (|flip_grp)   any_flip <= 1'b1;
        end
    end

    // synthesis translate_off
    // Overlapped schedule check: a decode read must not see a column whose APP write is still in flight
    // (stages w0 .. w2d, or the APP write of this very cycle; the RAM returns old data then).
    always @(posedge clk) begin
        if (!rst && a_valid && a_mode == M_RD &&
            ((w0_valid && w0_col == a_col) || (w1_valid && w1_col == a_col) || (w2_valid && w2_col == a_col) ||
             (w2b_valid && w2b_col == a_col) || (w2c_valid && w2c_col == a_col) || (w2d_valid && w2d_col == a_col) ||
             (app_we && app_waddr == a_col))) begin
            $display("ERROR %0t ldpc_ir_decoder: read of column %0d while its write is in flight (layer %0d)",
                     $time, a_col, layer);
            $stop;
        end
    end
    // synthesis translate_on

endmodule
