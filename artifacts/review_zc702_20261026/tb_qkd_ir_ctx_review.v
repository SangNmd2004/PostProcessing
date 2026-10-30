`timescale 1ns / 1ps

// Self-checking testbench for the block contexts of qkd_pp_axi (2026-10-23): up to USE_CTX blocks in flight share
// the decoder. Alice's answers (reveals after a failed attempt) come back RTT_CYC cycles after the FAIL event, so
// the decoder runs other blocks meanwhile. New blocks are streamed into free contexts while others decode.
// Every attempt of every block is checked against the golden model (converged / n_usc / iterations / attempts /
// pp_used), keys are collected per context (m_axis_key_tuser) and compared bit by bit, ERRCNT per context.
// The vectors must share one decoder configuration (CFG except the code, CFG2 except HOLD): data/sessions_tb.
// Alice's syndrome of a new block also arrives one round trip after the context became free (as every attempt
// in model/exp_ctx.py costs RTT + decode).
// Run with USE_CTX = 1 and 4 to measure the speed-up on the RTL:
//   vlog +define+DATA_DIR=\"data/sessions_tb/\" +define+USE_CTX=4 +define+RTT_CYC=5000 ...
`ifndef DATA_DIR
`define DATA_DIR "C:/Users/Admin/Downloads/PostProcessing/PostProcessing/data/sessions_tb/"
`endif
`ifndef USE_CTX
`define USE_CTX 4
`endif
`ifndef RTT_CYC
`define RTT_CYC 10000
`endif

module tb_qkd_ir_ctx;

    parameter ZC     = 128;
    parameter SH_W   = 7;
    parameter CTX_W  = 2;
    localparam NCTX      = 1 << CTX_W;
    localparam N         = 24 * ZC;
    localparam CH_BEATS  = N / 16;
    localparam KEY_WORDS = N / 64;
    localparam SYN_MAX   = 12 * ZC / 32;

    reg clk = 0;
    reg rstn = 0;
    always #5 clk = ~clk;

    reg  [7:0]  awaddr = 0;  reg awvalid = 0;  wire awready;
    reg  [31:0] wdata = 0;   reg wvalid = 0;   wire wready;
    wire [1:0]  bresp;       wire bvalid;      reg bready = 0;
    reg  [7:0]  araddr = 0;  reg arvalid = 0;  wire arready;
    wire [31:0] rdata;       wire [1:0] rresp; wire rvalid;  reg rready = 0;
    reg  [31:0] ch_tdata = 0;  reg ch_tvalid = 0;  wire ch_tready;
    reg  [31:0] syn_tdata = 0; reg syn_tvalid = 0; wire syn_tready;
    wire [63:0] key_tdata;     wire key_tvalid;    reg key_tready = 0;  wire key_tlast;
    wire [CTX_W-1:0] key_tuser;
    wire irq;
    wire pax_tready, pas_tready, pay_tvalid, pay_tlast;
    wire [63:0] pay_tdata;

    qkd_pp_zc702 dut (
        .s_axi_aclk(clk), .s_axi_aresetn(rstn),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_ch_tdata(ch_tdata), .s_axis_ch_tvalid(ch_tvalid), .s_axis_ch_tready(ch_tready),
        .s_axis_syn_tdata(syn_tdata), .s_axis_syn_tvalid(syn_tvalid), .s_axis_syn_tready(syn_tready),
        .m_axis_key_tdata(key_tdata), .m_axis_key_tvalid(key_tvalid), .m_axis_key_tready(key_tready),
        .m_axis_key_tlast(key_tlast), .m_axis_key_tuser(key_tuser),
        .s_axis_pa_x_tdata(32'd0), .s_axis_pa_x_tvalid(1'b0), .s_axis_pa_x_tready(pax_tready),
        .s_axis_pa_seed_tdata(32'd0), .s_axis_pa_seed_tvalid(1'b0), .s_axis_pa_seed_tready(pas_tready),
        .m_axis_pa_y_tdata(pay_tdata), .m_axis_pa_y_tvalid(pay_tvalid), .m_axis_pa_y_tready(1'b1),
        .m_axis_pa_y_tlast(pay_tlast),
        .irq(irq)
    );

    // ------------------------------------------------------------------ AXI-Lite tasks
    task axi_write(input [7:0] addr, input [31:0] data);
        begin
            @(posedge clk);
            awaddr <= addr; awvalid <= 1'b1; wdata <= data; wvalid <= 1'b1; bready <= 1'b1;
            @(posedge clk);
            while (awvalid || wvalid) begin
                if (awready) awvalid <= 1'b0;
                if (wready)  wvalid  <= 1'b0;
                @(posedge clk);
            end
            while (!bvalid) @(posedge clk);
            bready <= 1'b0;
        end
    endtask

    task axi_read(input [7:0] addr, output [31:0] data);
        begin
            @(posedge clk);
            araddr <= addr; arvalid <= 1'b1; rready <= 1'b1;
            @(posedge clk);
            while (!arready) @(posedge clk);
            arvalid <= 1'b0;
            while (!rvalid) @(posedge clk);
            data = rdata;
            @(posedge clk);
            rready <= 1'b0;
        end
    endtask

    // ------------------------------------------------------------------ per-context vectors (flattened)
    reg [31:0] ch_mem  [0:NCTX*CH_BEATS-1];
    reg [31:0] syn_mem [0:NCTX*SYN_MAX-1];
    reg [31:0] blk_mem [0:NCTX*32-1];
    reg [31:0] rev_mem [0:NCTX*N-1];
    reg [63:0] key_mem [0:NCTX*KEY_WORDS-1];
    reg [63:0] got     [0:NCTX*KEY_WORDS-1];
    reg [31:0] t_ch [0:CH_BEATS-1];
    reg [31:0] t_syn[0:SYN_MAX-1];
    reg [31:0] t_blk[0:31];
    reg [31:0] t_rev[0:N-1];
    reg [63:0] t_key[0:KEY_WORDS-1];
    reg [7:0]  nblk_mem [0:0];
    reg [8*256-1:0] fname;

    integer key_n [0:NCTX-1];        // key words received per context
    integer errors;

    // key collector, random backpressure, words routed by tuser
    always @(posedge clk) begin
        key_tready <= ($random % 4) != 0;
        if (key_tvalid && key_tready) begin
            got[key_tuser * KEY_WORDS + key_n[key_tuser]] <= key_tdata;
            if (key_tlast !== (key_n[key_tuser] == KEY_WORDS - 1)) begin
                $display("ERROR: tlast mismatch, context %0d word %0d", key_tuser, key_n[key_tuser]);
                errors = errors + 1;
            end
            key_n[key_tuser] <= key_n[key_tuser] + 1;
        end
    end

    // ------------------------------------------------------------------ context bookkeeping
    integer c_blk  [0:NCTX-1];       // block in the context, -1 = free
    integer c_att  [0:NCTX-1];       // attempt index being waited for
    integer c_rev  [0:NCTX-1];       // next reveal index
    integer c_due  [0:NCTX-1];       // cycle when Alice's reveals arrive (-1 none)
    integer c_t0   [0:NCTX-1];
    integer c_free [0:NCTX-1];       // cycle when Alice's syndrome for the next block arrives

    integer b_next, b_done, nblk, cyc, k, c, i, nrev, mb, sbeats, t_start;
    reg [31:0] sum, ra, rb, expw, cfgw, cfg2w;

    always @(posedge clk) cyc <= cyc + 1;

    task load_block(input integer cc, input integer bb);
        integer kk;
        begin
            $sformat(fname, "%sch_%0d.hex",  `DATA_DIR, bb); $readmemh(fname, t_ch);
            $sformat(fname, "%ssyn_%0d.hex", `DATA_DIR, bb); $readmemh(fname, t_syn);
            $sformat(fname, "%sblk_%0d.hex", `DATA_DIR, bb); $readmemh(fname, t_blk);
            $sformat(fname, "%srev_%0d.hex", `DATA_DIR, bb); $readmemh(fname, t_rev);
            $sformat(fname, "%skey_%0d.hex", `DATA_DIR, bb); $readmemh(fname, t_key);
            for (kk = 0; kk < CH_BEATS; kk = kk + 1)  ch_mem[cc*CH_BEATS + kk] = t_ch[kk];
            for (kk = 0; kk < SYN_MAX; kk = kk + 1)   syn_mem[cc*SYN_MAX + kk] = t_syn[kk];
            for (kk = 0; kk < 32; kk = kk + 1)        blk_mem[cc*32 + kk] = t_blk[kk];
            for (kk = 0; kk < N; kk = kk + 1)         rev_mem[cc*N + kk] = t_rev[kk];
            for (kk = 0; kk < KEY_WORDS; kk = kk + 1) key_mem[cc*KEY_WORDS + kk] = t_key[kk];
            cfgw  = t_blk[0];
            cfg2w = t_blk[1];
            mb = (cfgw[1:0] == 2'd0) ? 12 : (cfgw[1:0] == 2'd1) ? 8 : (cfgw[1:0] == 2'd2) ? 6 : 4;
            sbeats = mb * ZC / 32;
            c_blk[cc] = bb; c_att[cc] = 0; c_rev[cc] = 0; c_due[cc] = -1; c_t0[cc] = cyc;
            key_n[cc] = 0;
            axi_write(8'h08, cfgw);                       // code of this block (rest identical for all blocks)
            axi_write(8'h20, cfg2w);                      // HOLD of this block
            axi_write(8'h28, cc);                         // LOAD_CTX
            fork
                begin : s_ch
                    for (kk = 0; kk < CH_BEATS; kk = kk + 1) begin
                        ch_tdata <= t_ch[kk]; ch_tvalid <= 1'b1;
                        @(posedge clk);
                        while (!ch_tready) @(posedge clk);
                        ch_tvalid <= 1'b0;
                        if (($random % 8) == 0) @(posedge clk);
                    end
                end
                begin : s_syn
                    integer ks;
                    for (ks = 0; ks < sbeats; ks = ks + 1) begin
                        syn_tdata <= t_syn[ks]; syn_tvalid <= 1'b1;
                        @(posedge clk);
                        while (!syn_tready) @(posedge clk);
                        syn_tvalid <= 1'b0;
                        if (($random % 8) == 0) @(posedge clk);
                    end
                end
            join
            if (cfg2w[4]) begin                           // HOLD: r0 reveals travel with the syndrome
                sum = 0;
                while (!sum[8 + cc]) axi_read(8'h2C, sum);
                for (kk = 0; kk < t_blk[2]; kk = kk + 1) begin
                    axi_write(8'h18, rev_mem[cc*N + c_rev[cc]] | (cc << 20));
                    c_rev[cc] = c_rev[cc] + 1;
                end
                axi_write(8'h04, 32'h1 | (cc << 8));
            end
            $display("[%0d] block %0d -> context %0d (code %0d, %0d pre-reveals)", cyc, bb, cc, cfgw[1:0],
                     cfg2w[4] ? t_blk[2] : 0);
        end
    endtask

    initial begin
        errors = 0; cyc = 0;
        for (c = 0; c < NCTX; c = c + 1) begin c_blk[c] = -1; key_n[c] = 0; c_due[c] = -1; c_free[c] = `RTT_CYC; end
        $readmemh({`DATA_DIR, "nblk.hex"}, nblk_mem);
        nblk = nblk_mem[0];
        repeat (5) @(posedge clk);
        rstn <= 1'b1;
        repeat (3) @(posedge clk);
        axi_read(8'h30, sum);
        $display("CTX_W = %0d, contexts used by this run: %0d, RTT %0d cycles", sum[3:0], `USE_CTX, `RTT_CYC);
        b_next = 0; b_done = 0; t_start = cyc;

        while (b_done < nblk) begin
            // 1. fill free contexts
            for (c = 0; c < `USE_CTX; c = c + 1)
                if (c_blk[c] < 0 && b_next < nblk && cyc >= c_free[c]) begin
                    load_block(c, b_next);
                    b_next = b_next + 1;
                end
            // 2. events
            axi_read(8'h2C, sum);
            for (c = 0; c < `USE_CTX; c = c + 1) if (c_blk[c] >= 0 && (sum[16 + c] || sum[24 + c])) begin
                axi_read(8'h80 + 8*c, ra);
                axi_read(8'h84 + 8*c, rb);
                axi_write(8'h2C, (32'h1 << (16 + c)) | (32'h1 << (24 + c)));
                expw = blk_mem[c*32 + 4 + 2*c_att[c]];
                if (sum[16 + c] !== expw[31] || ra[23:12] !== expw[27:16] || ra[11:0] !== expw[11:0] ||
                    ra[31:24] !== c_att[c] + 1 || rb[25:24] !== expw[29:28]) begin
                    $display("[blk %0d ctx %0d att %0d] ERROR: sum %h ctxA %h ctxB %h, golden conv=%0d usc=%0d it=%0d pp=%0d",
                             c_blk[c], c, c_att[c], sum, ra, rb, expw[31], expw[27:16], expw[11:0], expw[29:28]);
                    errors = errors + 1;
                end
                if (sum[16 + c]) begin                    // success: key already streamed, check it
                    for (i = 0; i < KEY_WORDS; i = i + 1)
                        if (got[c*KEY_WORDS + i] !== key_mem[c*KEY_WORDS + i]) begin
                            errors = errors + 1;
                            if (errors < 10) $display("[blk %0d] ERROR key word %0d", c_blk[c], i);
                        end
                    if (key_n[c] != KEY_WORDS) begin
                        $display("[blk %0d] ERROR: %0d key words", c_blk[c], key_n[c]); errors = errors + 1;
                    end
                    if (rb[11:0] !== blk_mem[c*32 + 4 + 2*blk_mem[c*32 + 3]][11:0]) begin
                        $display("[blk %0d] ERROR: ERRCNT %0d", c_blk[c], rb[11:0]); errors = errors + 1;
                    end
                    $display("[%0d] block %0d (context %0d): %0d attempt(s) match golden, key bit-exact, ERRCNT %0d, %0d cycles in flight",
                             cyc, c_blk[c], c, c_att[c] + 1, rb[11:0], cyc - c_t0[c]);
                    c_blk[c] = -1;
                    c_free[c] = cyc + `RTT_CYC;
                    b_done = b_done + 1;
                end else if (c_att[c] == blk_mem[c*32 + 3] - 1) begin
                    axi_write(8'h04, 32'h2 | (c << 8));   // last attempt failed: discard (as golden)
                    $display("[%0d] block %0d (context %0d) discarded as golden", cyc, c_blk[c], c);
                    c_blk[c] = -1;
                    c_free[c] = cyc + `RTT_CYC;
                    b_done = b_done + 1;
                end else begin
                    c_due[c] = cyc + `RTT_CYC;            // Alice answers after one round trip
                end
            end
            // 3. Alice's answers that arrived
            for (c = 0; c < `USE_CTX; c = c + 1) if (c_blk[c] >= 0 && c_due[c] >= 0 && cyc >= c_due[c]) begin
                nrev = blk_mem[c*32 + 5 + 2*c_att[c]];
                for (i = 0; i < nrev; i = i + 1) begin
                    axi_write(8'h18, rev_mem[c*N + c_rev[c]] | (c << 20));
                    c_rev[c] = c_rev[c] + 1;
                end
                c_att[c] = c_att[c] + 1;
                c_due[c] = -1;
                axi_write(8'h04, 32'h1 | (c << 8));
            end
            repeat (20) @(posedge clk);
        end
        $display("TOTAL %0d blocks in %0d cycles with %0d context(s), RTT %0d cycles", nblk, cyc - t_start,
                 `USE_CTX, `RTT_CYC);
        if (errors == 0) $display("TB_RESULT: PASS (%0d blocks interleaved over %0d contexts, bit-exact vs golden model)",
                                  nblk, `USE_CTX);
        else             $display("TB_RESULT: FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #400_000_000;
        $display("TB_RESULT: FAIL (timeout)");
        $finish;
    end

endmodule
