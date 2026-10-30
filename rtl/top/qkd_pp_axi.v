`timescale 1ns / 1ps

// QKD post-processing IP: information reconciliation (qkd_ir_core) + privacy amplification (pa_hankel_hash),
// one AXI4-Lite slave for the CPU (AE350) and five AXI-Stream ports for the DMA.
//
// ---------------------------------------------------------------------------------------------------------
// Register map (byte offsets, 32-bit registers, word aligned; wstrb is ignored - always write whole words)
// ---------------------------------------------------------------------------------------------------------
//  IR (information reconciliation)
//   0x00 ID       R   {8'h49 'I', 8'h52 'R', 16'd ZC}                                       ZC = 128 -> 0x49520080
//   0x04 CTRL     W   [0] RETRY  : queue the next attempt (after reveals) / the first attempt in HOLD mode
//                     [1] DISCARD: drop the block
//                     [8 +: CTX_W] context the command applies to (ignored unless that context waits)
//   0x08 CFG      RW  [1:0]   code        0 r12 (R0 1/2), 1 r23 (2/3), 2 r34 (3/4), 3 r56 (5/6)      reset 2
//                     [6:2]   lq          |channel LLR| of a key bit (best 7..9)                        reset 8
//                     [15:8]  iter_max    decoder iterations per decode                                reset 50
//                     [17:16] pp_rounds   trapping-set post-processing rounds per attempt (0 = off)    reset 1
//                     [19:18] pp_min_usc  flip key bits touching >= this many unsatisfied checks       reset 2
//                     [31:20] pp_max_usc  run post-processing only if n_usc <= this (trapping set)     reset 16
//   0x0C STATUS   R   [0] SUCCESS of any context (sticky, write 1 to clear)  [1] FAIL of any context (sticky, W1C)
//                     [2] decoder busy  [3] some context waits for REVEAL / RETRY / DISCARD
//                     [5:4] pp_used of the last attempt  [27:16] n_usc of the last decode (0 when converged)
//                     [8] PA_DONE (sticky, W1C)  [9] PA busy
//   0x10 ITERS    R   [11:0] iterations of the last attempt (all decodes)  [23:16] attempts of its block
//   0x14 CYCLES   R   decoder cycles of the block of the last attempt
//   0x18 REVEAL   W   [15:0] variable-node position  [16] value (Alice's bit)  [20 +: CTX_W] context.
//                     The position becomes shortened. The write stalls while the core applies the previous
//                     reveal; dropped if that context does not wait.
//   0x1C IRQ_EN   RW  [0] SUCCESS  [1] FAIL  [2] PA_DONE.   irq = |({PA_DONE, FAIL, SUCCESS} & IRQ_EN)
//   0x20 CFG2     RW  [3:0] et_patience  early termination after this many iterations without improvement of
//                                        the read-time unsatisfied-check count (0 = off)            reset 12
//                     [4]   HOLD         a loaded block waits (STATUS[3]) for pre-reveals + RETRY   reset 0
//                     [5]   NMS          check node: 1 normalized min-sum x0.75, 0 offset min-sum   reset 1
//   0x24 ERRCNT   R   [11:0] channel errors corrected in the last successful block (QBER = ERRCNT / (n - d))
//  Block contexts (2026-10-23): 2^CTX_W blocks in flight share the decoder, so the decoder works on one block
//  while the others wait for Alice. A single-block driver uses context 0 everywhere and sees the old behaviour.
//   0x28 LOAD_CTX RW  [CTX_W-1:0] context that receives the next block on s_axis_ch / s_axis_syn (must be free;
//                     sampled at the block's first beat)                                         reset 0
//   0x2C CTX_SUM  R   [7:0] free contexts  [15:8] waiting contexts (HOLD / failed)  [23:16] SUCCESS per context
//                     [31:24] FAIL per context (both sticky; write 1 to [31:16] bits to clear)
//   0x30 CTX_CFG  R   [3:0] CTX_W
//   0x80 + 8c CTX_A R [11:0] iterations of the last attempt  [23:12] n_usc  [31:24] attempts       (context c)
//   0x84 + 8c CTX_B R [11:0] ERRCNT of its last success  [25:24] pp_used  [30:28] state
//                     (0 free, 1 hold, 2 queued, 3 decoding, 4 waiting after FAIL, 5 key output)
//   0xC0 + 4c CTX_CYC R decoder cycles of the block in context c
//  PA (privacy amplification)
//   0x40 PA_CTRL  W   [0] START a pass over PA_NWORDS input words (seed and input via s_axis_pa_*)
//   0x44 PA_NWORDS RW [19:0] input length in 32-bit words (reconciled key bits, zero-padded)
//
// ---------------------------------------------------------------------------------------------------------
// Streams
//   s_axis_ch   32 bit  channel symbols, 16 x 2 bit per beat: 0/1 key bit, 2 punctured      (24 * ZC / 16 beats)
//   s_axis_syn  32 bit  Alice's syndrome, LSB first, layer by layer                          (mb * ZC / 32 beats)
//   m_axis_key  64 bit  decoded n bits (incl. D positions) after SUCCESS, tuser = context    (24 * ZC / 64 words)
//   s_axis_pa_x / s_axis_pa_seed  32 bit  PA input / TRNG seed (PA_NWORDS + 33 seed words)
//   m_axis_pa_y 64 bit  1024 hash bits per pass (16 words)
// ---------------------------------------------------------------------------------------------------------
module qkd_pp_axi #(
    parameter ZC    = 128,
    parameter SH_W  = 7,
    parameter CTX_W = 2
)(
    input             s_axi_aclk,
    input             s_axi_aresetn,

    input      [7:0]  s_axi_awaddr,
    input             s_axi_awvalid,
    output            s_axi_awready,
    input      [31:0] s_axi_wdata,
    input      [3:0]  s_axi_wstrb,
    input             s_axi_wvalid,
    output            s_axi_wready,
    output     [1:0]  s_axi_bresp,
    output reg        s_axi_bvalid,
    input             s_axi_bready,
    input      [7:0]  s_axi_araddr,
    input             s_axi_arvalid,
    output            s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output     [1:0]  s_axi_rresp,
    output reg        s_axi_rvalid,
    input             s_axi_rready,

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
    output [CTX_W-1:0] m_axis_key_tuser,

    input      [31:0] s_axis_pa_x_tdata,
    input             s_axis_pa_x_tvalid,
    output            s_axis_pa_x_tready,
    input      [31:0] s_axis_pa_seed_tdata,
    input             s_axis_pa_seed_tvalid,
    output            s_axis_pa_seed_tready,
    output     [63:0] m_axis_pa_y_tdata,
    output            m_axis_pa_y_tvalid,
    input             m_axis_pa_y_tready,
    output            m_axis_pa_y_tlast,

    output            irq
);

    localparam [15:0] ZC16 = ZC;
    localparam NCTX = 1 << CTX_W;

    wire clk = s_axi_aclk;
    wire rst = ~s_axi_aresetn;

    reg  [31:0] cfg;                 // 0x08
    reg  [31:0] cfg2;                // 0x20
    reg  [2:0]  irq_en;              // 0x1C
    reg         sticky_ok, sticky_fail, sticky_pa;
    reg         cmd_retry, cmd_discard, pa_start;
    reg  [CTX_W-1:0] cmd_ctx, load_ctx, rv_ctx;
    reg  [NCTX-1:0]  ok_c, fail_c;   // per-context sticky SUCCESS / FAIL
    reg         rv_valid;
    reg  [15:0] rv_pos;
    reg         rv_val;
    reg  [19:0] pa_nwords;           // 0x44

    wire        st_success, st_fail, st_busy, st_wait;
    wire [CTX_W-1:0] ev_s_ctx, ev_f_ctx;
    wire [3*NCTX-1:0]  c_state;
    wire [12*NCTX-1:0] c_n_usc, c_iters, c_err;
    wire [2*NCTX-1:0]  c_pp;
    wire [8*NCTX-1:0]  c_att;
    wire [32*NCTX-1:0] c_cycles;
    wire [11:0] st_iters, st_n_usc;
    wire [1:0]  st_pp_used;
    wire [7:0]  st_attempts;
    wire [31:0] st_cycles;
    wire [11:0] st_err_cnt;
    wire        reveal_ready;
    wire        pa_busy, pa_done;

    // ------------------------------------------------------------------
    // Information reconciliation
    // ------------------------------------------------------------------
    qkd_ir_core #(.ZC(ZC), .SH_W(SH_W), .CTX_W(CTX_W)) u_core (
        .clk(clk), .rst(rst),
        .s_axis_ch_tdata(s_axis_ch_tdata), .s_axis_ch_tvalid(s_axis_ch_tvalid), .s_axis_ch_tready(s_axis_ch_tready),
        .s_axis_syn_tdata(s_axis_syn_tdata), .s_axis_syn_tvalid(s_axis_syn_tvalid), .s_axis_syn_tready(s_axis_syn_tready),
        .m_axis_key_tdata(m_axis_key_tdata), .m_axis_key_tvalid(m_axis_key_tvalid),
        .m_axis_key_tready(m_axis_key_tready), .m_axis_key_tlast(m_axis_key_tlast), .m_axis_key_tuser(m_axis_key_tuser),
        .cfg_code(cfg[1:0]), .cfg_lq(cfg[6:2]), .cfg_iter_max(cfg[15:8]), .cfg_pp_rounds(cfg[17:16]),
        .cfg_pp_min_usc(cfg[19:18]), .cfg_pp_max_usc(cfg[31:20]),
        .cfg_et_patience(cfg2[3:0]), .cfg_hold(cfg2[4]), .cfg_cn_nms(cfg2[5]), .load_ctx(load_ctx),
        .cmd_retry(cmd_retry), .cmd_discard(cmd_discard), .cmd_ctx(cmd_ctx),
        .reveal_valid(rv_valid), .reveal_pos(rv_pos), .reveal_val(rv_val), .reveal_ctx(rv_ctx),
        .reveal_ready(reveal_ready),
        .ev_success(st_success), .ev_s_ctx(ev_s_ctx), .ev_fail(st_fail), .ev_f_ctx(ev_f_ctx),
        .st_busy(st_busy), .st_wait_any(st_wait),
        .st_iters(st_iters), .st_pp_used(st_pp_used), .st_n_usc(st_n_usc),
        .st_attempts(st_attempts), .st_cycles(st_cycles), .st_err_cnt(st_err_cnt),
        .c_state(c_state), .c_n_usc(c_n_usc), .c_iters(c_iters), .c_pp(c_pp), .c_att(c_att), .c_err(c_err),
        .c_cycles(c_cycles)
    );

    // ------------------------------------------------------------------
    // Privacy amplification
    // ------------------------------------------------------------------
    pa_hankel_hash #(.L_OUT(1024), .NW_W(20)) u_pa (
        .clk(clk), .rst(rst),
        .start(pa_start), .n_words(pa_nwords), .busy(pa_busy), .done(pa_done),
        .s_axis_x_tdata(s_axis_pa_x_tdata), .s_axis_x_tvalid(s_axis_pa_x_tvalid), .s_axis_x_tready(s_axis_pa_x_tready),
        .s_axis_seed_tdata(s_axis_pa_seed_tdata), .s_axis_seed_tvalid(s_axis_pa_seed_tvalid),
        .s_axis_seed_tready(s_axis_pa_seed_tready),
        .m_axis_y_tdata(m_axis_pa_y_tdata), .m_axis_y_tvalid(m_axis_pa_y_tvalid),
        .m_axis_y_tready(m_axis_pa_y_tready), .m_axis_y_tlast(m_axis_pa_y_tlast)
    );

    assign irq = |({sticky_pa, sticky_fail, sticky_ok} & irq_en);

    // ------------------------------------------------------------------
    // Write channel: address and data latched independently, one response per write
    // ------------------------------------------------------------------
    reg         aw_full, w_full;
    reg  [7:0]  aw_addr;
    reg  [31:0] w_data;
    assign s_axi_awready = !aw_full && !s_axi_bvalid;
    assign s_axi_wready  = !w_full && !s_axi_bvalid;
    assign s_axi_bresp   = 2'b00;

    wire        wr_go     = aw_full && w_full && !s_axi_bvalid;
    wire        wr_reveal = (aw_addr[7:2] == 6'h06);
    // a REVEAL write waits while the core is still applying the previous one
    wire        wr_stall  = wr_reveal && (!reveal_ready || rv_valid);

    always @(posedge clk) begin
        if (rst) begin
            aw_full <= 1'b0; w_full <= 1'b0; s_axi_bvalid <= 1'b0;
            //       pp_max  pp_min pp_rnd iter_max  -    lq    code
            cfg  <= {12'd16, 2'd2,  2'd1,  8'd50,   1'b0, 5'd8, 2'd2};
            cfg2 <= 32'd44;                           // et_patience 12, HOLD off, NMS on
            irq_en <= 3'b000; sticky_ok <= 1'b0; sticky_fail <= 1'b0; sticky_pa <= 1'b0;
            cmd_retry <= 1'b0; cmd_discard <= 1'b0; rv_valid <= 1'b0; pa_start <= 1'b0; pa_nwords <= 20'd0;
            cmd_ctx <= {CTX_W{1'b0}}; load_ctx <= {CTX_W{1'b0}}; rv_ctx <= {CTX_W{1'b0}};
            ok_c <= {NCTX{1'b0}}; fail_c <= {NCTX{1'b0}};
        end else begin
            cmd_retry   <= 1'b0;
            cmd_discard <= 1'b0;
            rv_valid    <= 1'b0;
            pa_start    <= 1'b0;
            if (st_success) begin sticky_ok   <= 1'b1; ok_c[ev_s_ctx]   <= 1'b1; end
            if (st_fail)    begin sticky_fail <= 1'b1; fail_c[ev_f_ctx] <= 1'b1; end
            if (pa_done)    sticky_pa   <= 1'b1;

            if (s_axi_awvalid && s_axi_awready) begin aw_full <= 1'b1; aw_addr <= s_axi_awaddr; end
            if (s_axi_wvalid && s_axi_wready)   begin w_full  <= 1'b1; w_data  <= s_axi_wdata;  end

            if (wr_go && !wr_stall) begin
                aw_full      <= 1'b0;
                w_full       <= 1'b0;
                s_axi_bvalid <= 1'b1;
                case (aw_addr[7:2])
                    6'h01: begin cmd_retry <= w_data[0]; cmd_discard <= w_data[1]; cmd_ctx <= w_data[8 +: CTX_W]; end
                    6'h02: cfg <= w_data;
                    6'h03: begin
                        if (w_data[0]) sticky_ok   <= 1'b0;
                        if (w_data[1]) sticky_fail <= 1'b0;
                        if (w_data[8]) sticky_pa   <= 1'b0;
                    end
                    6'h06: begin
                        rv_valid <= 1'b1; rv_pos <= w_data[15:0]; rv_val <= w_data[16]; rv_ctx <= w_data[20 +: CTX_W];
                    end
                    6'h07: irq_en <= w_data[2:0];
                    6'h08: cfg2 <= w_data;
                    6'h0A: load_ctx <= w_data[CTX_W-1:0];
                    6'h0B: begin : clr_ctx
                        integer ci;
                        for (ci = 0; ci < NCTX; ci = ci + 1) begin
                            if (w_data[16 + ci]) ok_c[ci]   <= 1'b0;
                            if (w_data[24 + ci]) fail_c[ci] <= 1'b0;
                        end
                    end
                    6'h10: pa_start <= w_data[0] && !pa_busy;
                    6'h11: pa_nwords <= w_data[19:0];
                    default: ;
                endcase
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
        end
    end

    // ------------------------------------------------------------------
    // Read channel
    // ------------------------------------------------------------------
    reg [31:0] ctx_sum;
    integer si;
    always @(*) begin
        ctx_sum = 32'd0;
        for (si = 0; si < NCTX; si = si + 1) begin
            ctx_sum[si]      = (c_state[si*3 +: 3] == 3'd0);
            ctx_sum[8 + si]  = (c_state[si*3 +: 3] == 3'd1) || (c_state[si*3 +: 3] == 3'd4);
            ctx_sum[16 + si] = ok_c[si];
            ctx_sum[24 + si] = fail_c[si];
        end
    end
    assign s_axi_arready = !s_axi_rvalid;
    assign s_axi_rresp   = 2'b00;

    always @(posedge clk) begin
        if (rst) begin
            s_axi_rvalid <= 1'b0;
            s_axi_rdata  <= 32'd0;
        end else begin
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                case (s_axi_araddr[7:2])
                    6'h00: s_axi_rdata <= {8'h49, 8'h52, ZC16};
                    6'h02: s_axi_rdata <= cfg;
                    6'h03: s_axi_rdata <= {4'd0, st_n_usc, 6'd0, pa_busy, sticky_pa, 2'd0, st_pp_used,
                                           st_wait, st_busy, sticky_fail, sticky_ok};
                    6'h04: s_axi_rdata <= {8'd0, st_attempts, 4'd0, st_iters};
                    6'h05: s_axi_rdata <= st_cycles;
                    6'h07: s_axi_rdata <= {29'd0, irq_en};
                    6'h08: s_axi_rdata <= cfg2;
                    6'h09: s_axi_rdata <= {20'd0, st_err_cnt};
                    6'h0A: s_axi_rdata <= {{(32-CTX_W){1'b0}}, load_ctx};
                    6'h0B: s_axi_rdata <= ctx_sum;
                    6'h0C: s_axi_rdata <= {28'd0, CTX_W[3:0]};
                    6'h11: s_axi_rdata <= {12'd0, pa_nwords};
                    default: begin
                        s_axi_rdata <= 32'd0;
                        if (s_axi_araddr[7:6] == 2'b10 && s_axi_araddr[5:3] < NCTX) begin      // 0x80 + 8c (+4)
                            if (!s_axi_araddr[2])
                                s_axi_rdata <= {c_att[s_axi_araddr[5:3]*8 +: 8], c_n_usc[s_axi_araddr[5:3]*12 +: 12],
                                                c_iters[s_axi_araddr[5:3]*12 +: 12]};
                            else
                                s_axi_rdata <= {1'b0, c_state[s_axi_araddr[5:3]*3 +: 3], 2'b0,
                                                c_pp[s_axi_araddr[5:3]*2 +: 2], 12'd0, c_err[s_axi_araddr[5:3]*12 +: 12]};
                        end
                        if (s_axi_araddr[7:5] == 3'b110 && s_axi_araddr[4:2] < NCTX)          // 0xC0 + 4c
                            s_axi_rdata <= c_cycles[s_axi_araddr[4:2]*32 +: 32];
                    end
                endcase
            end else if (s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
