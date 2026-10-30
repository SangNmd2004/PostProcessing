`timescale 1ns / 1ps

// Information-reconciliation core: stream packers + blind reconciliation controller for 2^CTX_W block contexts
// sharing one decoder + key output + ERRCNT.
//
// Why contexts (2026-10-23, model/exp_ctx.py): every attempt of a block costs one classical round trip (Alice's
// syndrome or reveals, ~100 us) but only 20-50 us of decoding, so with one block in flight the decoder idles most
// of the time. With 4 contexts the decoder runs attempts of other blocks while a block waits for Alice:
// RTT 100 us -> x3..3.5 reconciled-key throughput, RTT 1 ms -> x4.
// Only the channel RAM (types / bits incl. reveals) and the syndrome RAM are per block: every attempt reloads
// the APP from the channel RAM and restarts the C2V messages, so APP / C2V / SGN are shared. Both per-block RAMs
// are banked by context inside the decoder (deeper, not wider: no extra BSRAM).
//
// Context states (c_state, 3 bit per context):
//   C_FREE  0  empty; the loader fills the context selected by load_ctx
//   C_HOLD  1  loaded with cfg_hold = 1: accepts reveals (r0 pre-reveals), RETRY queues attempt 1
//   C_QUEUE 2  waiting for the decoder (round robin over queued contexts)
//   C_DEC   3  attempt running
//   C_WAIT  4  attempt failed (ev_fail): accepts reveals, RETRY queues the next attempt, DISCARD frees
//   C_OUT   5  attempt converged: key streams out on m_axis_key (tuser = context), then ev_success, C_FREE
// Shared resources and their arbitration:
//   decoder      one attempt at a time; not started while a key streams out (the key comes from the APP RAM)
//   loader       one block at a time into a free context (load_ctx is sampled at the block's first beat)
//   reveal RMW   one reveal at a time into a waiting context (reveal_ready)
//   channel RAM  host ports usable when the decoder grants them (ch_grant: decoder outside S_LOAD/S_CNT/S_CFLIP);
//                writes: loader rows before reveal writes; reads: key output before reveal reads
//   syndrome RAM host writes when syn_grant (no decoder USC write in that cycle)
// Stream formats:
//   s_axis_ch : 24*ZC channel symbols, 16 per 32-bit beat, symbol k of the beat in bits [2k+1:2k]:
//               2'b0b = key bit b, 2'b1x = punctured (modulated position, value unknown to Bob).
//   s_axis_syn: Alice's syndrome, mb(code)*ZC bits, layer by layer, LSB first, ZC/32 beats per layer.
//   m_axis_key: 24*ZC decoded bits, ZC/64 words per row, tlast on the last word, tuser = context.
// Configuration: cfg_code / cfg_hold are taken per block when its loading completes, the decoder settings
// (lq, iter_max, pp_*, et_patience, cn_nms) when an attempt starts (shared by all contexts).
module qkd_ir_core #(
    parameter ZC    = 128,
    parameter SH_W  = 7,
    parameter CTX_W = 2
)(
    input             clk,
    input             rst,

    input      [31:0] s_axis_ch_tdata,
    input             s_axis_ch_tvalid,
    output            s_axis_ch_tready,

    input      [31:0] s_axis_syn_tdata,
    input             s_axis_syn_tvalid,
    output            s_axis_syn_tready,

    output     [63:0] m_axis_key_tdata,
    output            m_axis_key_tvalid,
    input             m_axis_key_tready,
    output            m_axis_key_tlast,
    output [CTX_W-1:0] m_axis_key_tuser,  // context of the key

    input      [1:0]  cfg_code,
    input      [4:0]  cfg_lq,
    input      [7:0]  cfg_iter_max,
    input      [1:0]  cfg_pp_rounds,
    input      [1:0]  cfg_pp_min_usc,
    input      [11:0] cfg_pp_max_usc,
    input      [3:0]  cfg_et_patience,
    input             cfg_cn_nms,         // 1: normalized min-sum (x0.75), 0: offset min-sum
    input             cfg_hold,           // 1: a loaded block waits for pre-reveals + RETRY before attempt 1
    input  [CTX_W-1:0] load_ctx,          // context that receives the next streamed block (must be free)

    input             cmd_retry,          // pulse, for context cmd_ctx
    input             cmd_discard,        // pulse, for context cmd_ctx
    input  [CTX_W-1:0] cmd_ctx,
    input             reveal_valid,
    input      [15:0] reveal_pos,         // variable-node index 0 .. 24*ZC-1
    input             reveal_val,
    input  [CTX_W-1:0] reveal_ctx,
    output            reveal_ready,       // reveal engine idle

    output reg        ev_success,         // pulse: block of context ev_s_ctx reconciled, key streamed
    output reg [CTX_W-1:0] ev_s_ctx,
    output reg        ev_fail,            // pulse: attempt of context ev_f_ctx failed, waiting for reveals
    output reg [CTX_W-1:0] ev_f_ctx,
    output            st_busy,            // decoder running
    output            st_wait_any,        // some context waits for reveals / RETRY / DISCARD
    output reg [11:0] st_iters,           // last attempt (any context): iterations
    output reg [1:0]  st_pp_used,
    output reg [11:0] st_n_usc,
    output reg [7:0]  st_attempts,        //   attempts of its block so far
    output reg [31:0] st_cycles,          //   decoder cycles of its block so far
    output reg [11:0] st_err_cnt,         // channel errors corrected in the last successful block

    // per-context status, context c in bits [c*W +: W]
    output [3*(1<<CTX_W)-1:0]  c_state,
    output [12*(1<<CTX_W)-1:0] c_n_usc,
    output [12*(1<<CTX_W)-1:0] c_iters,
    output [2*(1<<CTX_W)-1:0]  c_pp,
    output [8*(1<<CTX_W)-1:0]  c_att,
    output [12*(1<<CTX_W)-1:0] c_err,
    output [32*(1<<CTX_W)-1:0] c_cycles
);

    localparam NCTX      = 1 << CTX_W;
    localparam ROW_BEATS = ZC / 16;       // channel beats per row
    localparam SYN_BEATS = ZC / 32;       // syndrome beats per layer
    localparam KEY_WORDS = ZC / 64;       // key words per row
    localparam [2:0] C_FREE = 3'd0, C_HOLD = 3'd1, C_QUEUE = 3'd2, C_DEC = 3'd3, C_WAIT = 3'd4, C_OUT = 3'd5;

    // ==========================================
    // Decoder
    // ==========================================
    reg              dec_start;
    reg  [CTX_W-1:0] dec_ctx;
    reg  [1:0]       dec_code;
    wire             ch_grant, syn_grant;
    wire             h_ch_we;
    wire [CTX_W-1:0] h_ch_wctx, h_ch_rctx;
    wire [4:0]       h_ch_waddr, h_ch_raddr;
    wire [3*ZC-1:0]  h_ch_wdata;
    wire [3*ZC-1:0]  h_ch_rdata;
    wire             h_syn_we;
    reg  [4:0]       hd_raddr;
    wire [ZC-1:0]    hd_rdata;
    wire             dec_busy, dec_done, dec_conv;
    wire [11:0]      dec_iters, dec_n_usc;
    wire [1:0]       dec_pp_used;

    reg  [CTX_W-1:0] syw_ctx;
    reg  [3:0]       syw_row;
    reg  [ZC-1:0]    syw_data;
    reg              syw_pend;

    ldpc_ir_decoder #(.ZC(ZC), .SH_W(SH_W), .CTX_W(CTX_W)) u_dec (
        .clk(clk), .rst(rst),
        .start(dec_start), .fresh(1'b1), .ctx(dec_ctx), .code(dec_code), .iter_max(cfg_iter_max), .lq(cfg_lq),
        .pp_rounds(cfg_pp_rounds), .pp_min_usc(cfg_pp_min_usc), .pp_max_usc(cfg_pp_max_usc),
        .et_patience(cfg_et_patience), .cn_nms(cfg_cn_nms),
        .ch_grant(ch_grant), .h_ch_we(h_ch_we), .h_ch_wctx(h_ch_wctx), .h_ch_waddr(h_ch_waddr),
        .h_ch_wdata(h_ch_wdata), .h_ch_rctx(h_ch_rctx), .h_ch_raddr(h_ch_raddr), .h_ch_rdata(h_ch_rdata),
        .syn_grant(syn_grant), .h_syn_we(h_syn_we), .h_syn_ctx(syw_ctx), .h_syn_waddr(syw_row),
        .h_syn_wdata(syw_data),
        .hd_raddr(hd_raddr), .hd_rdata(hd_rdata),
        .busy(dec_busy), .done(dec_done), .converged(dec_conv),
        .iters_total(dec_iters), .pp_used(dec_pp_used), .n_usc(dec_n_usc)
    );
    assign st_busy = dec_busy;

    // ==========================================
    // Per-context state
    // ==========================================
    reg  [2:0]  cst   [0:NCTX-1];
    reg  [1:0]  ccode [0:NCTX-1];
    reg  [11:0] cnusc [0:NCTX-1];
    reg  [11:0] citer [0:NCTX-1];
    reg  [1:0]  cppu  [0:NCTX-1];
    reg  [7:0]  catt  [0:NCTX-1];
    reg  [11:0] cerr  [0:NCTX-1];
    reg  [31:0] ccyc  [0:NCTX-1];
    reg  [NCTX-1:0] retry_pend, discard_pend;

    wire [NCTX-1:0] c_waiting;
    genvar gc;
    generate
        for (gc = 0; gc < NCTX; gc = gc + 1) begin : g_ctx
            assign c_waiting[gc]       = (cst[gc] == C_HOLD) || (cst[gc] == C_WAIT);
            assign c_state[gc*3 +: 3]  = cst[gc];
            assign c_n_usc[gc*12 +: 12] = cnusc[gc];
            assign c_iters[gc*12 +: 12] = citer[gc];
            assign c_pp[gc*2 +: 2]     = cppu[gc];
            assign c_att[gc*8 +: 8]    = catt[gc];
            assign c_err[gc*12 +: 12]  = cerr[gc];
            assign c_cycles[gc*32 +: 32] = ccyc[gc];
        end
    endgenerate
    assign st_wait_any = |c_waiting;

    // ==========================================
    // Loader: channel / syndrome packers into context ld_ctx
    // ==========================================
    reg  [2*ZC-1:0]  ch_sr;
    reg  [7:0]       ch_beat;
    reg  [4:0]       ch_row;
    reg              ch_full;
    reg  [ZC-1:0]    syn_sr;
    reg  [7:0]       syn_beat;
    reg  [3:0]       syn_row;
    reg              syn_full;
    reg  [CTX_W-1:0] ld_ctx;
    reg  [1:0]       ld_code;
    reg              ldw_pend;            // loader channel-row write waiting for ch_grant
    reg  [4:0]       ldw_row;
    reg  [3*ZC-1:0]  ldw_data;

    wire             ld_partial  = (ch_beat != 8'd0) || (ch_row != 5'd0) || ch_full ||
                                   (syn_beat != 8'd0) || (syn_row != 4'd0) || syn_full;
    wire [CTX_W-1:0] ld_ctx_eff  = ld_partial ? ld_ctx : load_ctx;
    wire [1:0]       ld_code_eff = ld_partial ? ld_code : cfg_code;
    wire             ld_free     = (cst[ld_ctx_eff] == C_FREE);
    wire [3:0]       num_layers  = (ld_code_eff == 2'd0) ? 4'd12 : (ld_code_eff == 2'd1) ? 4'd8 :
                                   (ld_code_eff == 2'd2) ? 4'd6  : 4'd4;
    wire             ld_complete = ch_full && syn_full && !ldw_pend && !syw_pend;

    assign s_axis_ch_tready  = !ch_full && ld_free && !ldw_pend;
    assign s_axis_syn_tready = !syn_full && ld_free && !syw_pend;
    wire             ch_fire  = s_axis_ch_tvalid && s_axis_ch_tready;
    wire             syn_fire = s_axis_syn_tvalid && s_axis_syn_tready;
    wire [2*ZC-1:0]  ch_sr_next  = {s_axis_ch_tdata, ch_sr[2*ZC-1:32]};
    wire [ZC-1:0]    syn_sr_next = {s_axis_syn_tdata, syn_sr[ZC-1:32]};

    // symbol stream -> {type1, type0, bit} planes: key bit -> 00/b, punctured -> 01/0
    reg [3*ZC-1:0] ch_row_word;
    integer k;
    always @(*) begin
        for (k = 0; k < ZC; k = k + 1) begin
            ch_row_word[2*ZC + k] = 1'b0;
            ch_row_word[ZC + k]   = ch_sr_next[2*k + 1];
            ch_row_word[k]        = ch_sr_next[2*k] & ~ch_sr_next[2*k + 1];
        end
    end

    // ==========================================
    // Reveal engine (read-modify-write of one channel row of a waiting context)
    // ==========================================
    localparam R_IDLE = 2'd0, R_RD = 2'd1, R_CAP = 2'd2, R_WR = 2'd3;
    reg  [1:0]       rstate;
    reg  [CTX_W-1:0] rv_ctx;
    reg  [15:0]      rv_pos;
    reg              rv_val;
    reg  [3*ZC-1:0]  rv_word;
    reg              rmw_pend;            // reveal write waiting for ch_grant (loader writes go first)
    wire [4:0]       rv_row  = rv_pos[SH_W+4:SH_W];
    wire [SH_W-1:0]  rv_lane = rv_pos[SH_W-1:0];
    assign reveal_ready = (rstate == R_IDLE);

    // ==========================================
    // Key output state (declared here: it arbitrates the channel-RAM read port)
    // ==========================================
    localparam G_IDLE = 3'd0, G_REQ = 3'd1, G_CAP = 3'd2, G_SEND = 3'd3, G_REQ2 = 3'd4;
    reg  [2:0]       gstate;
    reg              out_start;
    reg  [CTX_W-1:0] out_ctx;
    wire             out_done;
    wire             key_reading = (gstate != G_IDLE) || out_start;
    reg  [11:0]      err_acc;             // ERRCNT accumulator of the key output (see the error counter below)

    // channel RAM host ports
    assign h_ch_we    = ldw_pend || rmw_pend;
    assign h_ch_wctx  = ldw_pend ? ld_ctx : rv_ctx;
    assign h_ch_waddr = ldw_pend ? ldw_row : rv_row;
    assign h_ch_wdata = ldw_pend ? ldw_data : rv_word;
    assign h_ch_rctx  = (gstate != G_IDLE) ? out_ctx : rv_ctx;
    assign h_ch_raddr = (gstate != G_IDLE) ? hd_raddr : rv_row;
    assign h_syn_we   = syw_pend;

    // ==========================================
    // Controller
    // ==========================================
    reg  [CTX_W-1:0] rr;                  // round-robin pointer of the scheduler
    reg              s_d1, s_d2, s_d3;    // success delayed until the ERRCNT pipeline has finished
    reg  [NCTX-1:0]  any_out;
    integer c, q, q2;
    reg              found;
    reg  [CTX_W-1:0] pick;

    always @(*) begin
        found = 1'b0;
        pick  = {CTX_W{1'b0}};
        for (q = 0; q < NCTX; q = q + 1)
            if (!found && cst[(rr + q) % NCTX] == C_QUEUE) begin
                found = 1'b1;
                pick  = (rr + q) % NCTX;
            end
    end
    always @(*) begin
        for (q2 = 0; q2 < NCTX; q2 = q2 + 1) any_out[q2] = (cst[q2] == C_OUT);
    end
    wire dispatch = found && !dec_busy && !dec_start && !dec_done && !key_reading && !(|any_out);

    // reveal reads use the channel read port only while no key streams out (key output has priority)
    wire rv_read_ok = ch_grant && (gstate == G_IDLE) && !out_start;

    always @(posedge clk) begin
        if (rst) begin
            for (c = 0; c < NCTX; c = c + 1) begin
                cst[c] <= C_FREE; ccode[c] <= 2'd0; cnusc[c] <= 12'd0; citer[c] <= 12'd0; cppu[c] <= 2'd0;
                catt[c] <= 8'd0; cerr[c] <= 12'd0; ccyc[c] <= 32'd0;
            end
            retry_pend <= {NCTX{1'b0}}; discard_pend <= {NCTX{1'b0}};
            dec_start <= 1'b0; dec_ctx <= {CTX_W{1'b0}}; dec_code <= 2'd0; rr <= {CTX_W{1'b0}};
            ev_success <= 1'b0; ev_fail <= 1'b0; ev_s_ctx <= {CTX_W{1'b0}}; ev_f_ctx <= {CTX_W{1'b0}};
            st_iters <= 12'd0; st_pp_used <= 2'd0; st_n_usc <= 12'd0; st_attempts <= 8'd0; st_cycles <= 32'd0;
            st_err_cnt <= 12'd0;
            out_start <= 1'b0; out_ctx <= {CTX_W{1'b0}}; s_d1 <= 1'b0; s_d2 <= 1'b0; s_d3 <= 1'b0;
            ch_beat <= 8'd0; ch_row <= 5'd0; ch_full <= 1'b0; syn_beat <= 8'd0; syn_row <= 4'd0; syn_full <= 1'b0;
            ld_ctx <= {CTX_W{1'b0}}; ld_code <= 2'd0; ldw_pend <= 1'b0; syw_pend <= 1'b0;
            rstate <= R_IDLE; rmw_pend <= 1'b0; rv_ctx <= {CTX_W{1'b0}};
        end else begin
            dec_start  <= 1'b0;
            ev_success <= 1'b0;
            ev_fail    <= 1'b0;
            out_start  <= 1'b0;

            // ---------------- decoder cycle counters
            for (c = 0; c < NCTX; c = c + 1)
                if (cst[c] == C_DEC) ccyc[c] <= ccyc[c] + 32'd1;

            // ---------------- loader
            if (!ld_partial) begin
                ld_ctx  <= load_ctx;
                ld_code <= cfg_code;
            end
            if (ch_fire) begin
                ch_sr <= ch_sr_next;
                if (ch_beat == ROW_BEATS - 1) begin
                    ch_beat  <= 8'd0;
                    ldw_pend <= 1'b1;
                    ldw_row  <= ch_row;
                    ldw_data <= ch_row_word;
                    if (ch_row == 5'd23) begin
                        ch_row  <= 5'd0;
                        ch_full <= 1'b1;
                    end else begin
                        ch_row <= ch_row + 5'd1;
                    end
                end else begin
                    ch_beat <= ch_beat + 8'd1;
                end
            end
            if (syn_fire) begin
                syn_sr <= syn_sr_next;
                if (syn_beat == SYN_BEATS - 1) begin
                    syn_beat <= 8'd0;
                    syw_pend <= 1'b1;
                    syw_ctx  <= ld_ctx_eff;
                    syw_row  <= syn_row;
                    syw_data <= syn_sr_next;
                    if (syn_row == num_layers - 4'd1) begin
                        syn_row  <= 4'd0;
                        syn_full <= 1'b1;
                    end else begin
                        syn_row <= syn_row + 4'd1;
                    end
                end else begin
                    syn_beat <= syn_beat + 8'd1;
                end
            end
            if (syw_pend && syn_grant) syw_pend <= 1'b0;
            if (ldw_pend && ch_grant)  ldw_pend <= 1'b0;
            else if (!ldw_pend && rmw_pend && ch_grant) rmw_pend <= 1'b0;
            if (ld_complete) begin
                ch_full  <= 1'b0;
                syn_full <= 1'b0;
                ccode[ld_ctx] <= ld_code;
                catt[ld_ctx]  <= 8'd0;
                ccyc[ld_ctx]  <= 32'd0;
                cst[ld_ctx]   <= cfg_hold ? C_HOLD : C_QUEUE;
            end

            // ---------------- reveal engine
            case (rstate)
                R_IDLE: if (reveal_valid && c_waiting[reveal_ctx]) begin   // reveals for other contexts: dropped
                    rv_ctx <= reveal_ctx;
                    rv_pos <= reveal_pos;
                    rv_val <= reveal_val;
                    rstate <= R_RD;
                end
                R_RD:  if (rv_read_ok) rstate <= R_CAP;                    // address {rv_ctx, rv_row} on the port
                R_CAP: begin                                               // h_ch_rdata = that row
                    rv_word <= h_ch_rdata;
                    rv_word[2*ZC + rv_lane] <= 1'b1;                       // type 10: shortened
                    rv_word[ZC + rv_lane]   <= 1'b0;
                    rv_word[rv_lane]        <= rv_val;
                    rmw_pend <= 1'b1;
                    rstate   <= R_WR;
                end
                R_WR:  if (!rmw_pend) rstate <= R_IDLE;
            endcase

            // ---------------- commands (only for waiting contexts; applied once no reveal of that context
            //                  is in the engine, so a RETRY never overtakes the reveals written before it)
            if (cmd_retry && c_waiting[cmd_ctx])   retry_pend[cmd_ctx]   <= 1'b1;
            if (cmd_discard && c_waiting[cmd_ctx]) discard_pend[cmd_ctx] <= 1'b1;
            for (c = 0; c < NCTX; c = c + 1) begin
                if (c_waiting[c] && !(rstate != R_IDLE && rv_ctx == c)) begin
                    if (discard_pend[c]) begin
                        discard_pend[c] <= 1'b0;
                        retry_pend[c]   <= 1'b0;
                        cst[c]          <= C_FREE;
                    end else if (retry_pend[c]) begin
                        retry_pend[c] <= 1'b0;
                        cst[c]        <= C_QUEUE;
                    end
                end
            end

            // ---------------- scheduler
            if (dispatch) begin
                dec_start     <= 1'b1;
                dec_ctx       <= pick;
                dec_code      <= ccode[pick];
                catt[pick]    <= catt[pick] + 8'd1;
                cst[pick]     <= C_DEC;
                rr            <= pick + 1'b1;
            end
            if (dec_done) begin
                cnusc[dec_ctx] <= dec_n_usc;
                citer[dec_ctx] <= dec_iters;
                cppu[dec_ctx]  <= dec_pp_used;
                st_iters    <= dec_iters;
                st_pp_used  <= dec_pp_used;
                st_n_usc    <= dec_n_usc;
                st_attempts <= catt[dec_ctx];
                st_cycles   <= ccyc[dec_ctx];
                if (dec_conv) begin
                    cst[dec_ctx] <= C_OUT;
                    out_ctx      <= dec_ctx;
                    out_start    <= 1'b1;
                end else begin
                    cst[dec_ctx] <= C_WAIT;
                    ev_fail      <= 1'b1;
                    ev_f_ctx     <= dec_ctx;
                end
            end

            // ---------------- end of key output: context free at once, success after the ERRCNT pipeline
            s_d1 <= out_done;
            s_d2 <= s_d1;
            s_d3 <= s_d2;
            if (out_done) cst[out_ctx] <= C_FREE;
            if (s_d3) begin
                cerr[out_ctx] <= err_acc;
                st_err_cnt    <= err_acc;
                ev_success    <= 1'b1;
                ev_s_ctx      <= out_ctx;
            end
        end
    end

    // ==========================================
    // Key output: 24 rows x ZC bits -> 64-bit words (decoder idle, APP RAM read through hd_raddr)
    // ==========================================
    reg  [ZC-1:0] gbuf;
    reg  [7:0]    gword;      // word inside the row
    wire          g_last = (hd_raddr == 5'd24) && (gword == KEY_WORDS - 1);
    assign m_axis_key_tdata  = gbuf[63:0];
    assign m_axis_key_tvalid = (gstate == G_SEND);
    assign m_axis_key_tlast  = (gstate == G_SEND) && g_last;
    assign m_axis_key_tuser  = out_ctx;
    assign out_done          = (gstate == G_SEND) && m_axis_key_tready && g_last;

    always @(posedge clk) begin
        if (rst) begin
            gstate <= G_IDLE; hd_raddr <= 5'd0; gword <= 8'd0;
        end else begin
            case (gstate)
                G_IDLE: if (out_start) begin hd_raddr <= 5'd0; gstate <= G_REQ; end
                G_REQ:  gstate <= G_REQ2;                          // APP RAM latency 2 (output register)
                G_REQ2: gstate <= G_CAP;                           // channel RAM (latency 1) holds the same row
                G_CAP: begin
                    // hd_rdata and h_ch_rdata both hold row hd_raddr of context out_ctx
                    gbuf     <= hd_rdata;
                    gword    <= 8'd0;
                    hd_raddr <= hd_raddr + 5'd1;                   // hd_raddr = row + 1 while sending
                    gstate   <= G_SEND;
                end
                G_SEND: begin
                    if (m_axis_key_tready) begin
                        gbuf <= gbuf >> 64;
                        if (gword == KEY_WORDS - 1) gstate <= (hd_raddr == 5'd24) ? G_IDLE : G_REQ;
                        else                        gword  <= gword + 8'd1;
                    end
                end
            endcase
        end
    end

    // ==========================================
    // Error counter for the controller: while the key streams out, count the key positions
    // (channel type 00 or 11) where the decoded bit differs from Bob's channel bit.
    //   G_CAP   : err_vec = (hd ^ bob) & key_mask of the row
    //   +1 cycle: 16-lane popcounts
    //   +2 cycles: err_acc += sum      (cleared when the next key output starts)
    // ==========================================
    reg  [ZC-1:0]        err_vec;
    reg                  err_v1, err_v2;
    reg  [5*(ZC/16)-1:0] err_grp;

    always @(posedge clk) begin
        if (rst) begin
            err_v1 <= 1'b0; err_v2 <= 1'b0; err_acc <= 12'd0;
        end else begin
            err_v1 <= (gstate == G_CAP);
            err_v2 <= err_v1;
            if (out_start) err_acc <= 12'd0;
            if (gstate == G_CAP) begin : err_row
                integer qq;
                for (qq = 0; qq < ZC; qq = qq + 1)
                    err_vec[qq] <= (hd_rdata[qq] ^ h_ch_rdata[qq]) & (h_ch_rdata[2*ZC + qq] == h_ch_rdata[ZC + qq]);
            end
            if (err_v1) begin : err_pop
                integer g, qq;
                reg [4:0] pc;
                for (g = 0; g < ZC/16; g = g + 1) begin
                    pc = 5'd0;
                    for (qq = 0; qq < 16; qq = qq + 1) pc = pc + {4'd0, err_vec[g*16 + qq]};
                    err_grp[g*5 +: 5] <= pc;
                end
            end
            if (err_v2) begin : err_sum
                integer g;
                reg [11:0] ps;
                ps = 12'd0;
                for (g = 0; g < ZC/16; g = g + 1) ps = ps + {7'd0, err_grp[g*5 +: 5]};
                err_acc <= err_acc + ps;
            end
        end
    end

endmodule
