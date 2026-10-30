`timescale 1ns / 1ps

// Self-checking testbench for qkd_pp_axi (AXI4-Lite CSR + AXI-Stream data): blind reconciliation blocks
// (basic and HOLD / pre-reveal mode, early termination, post-processing, ERRCNT), then one privacy-amplification
// pass checked against model/pa_model.py.
// Vectors: python model/gen_vectors.py   (writes data/tb/*.hex)
// For every attempt of every block it checks converged / pp_used / n_usc / iterations against the golden
// model, plays Alice's reveals through the REVEAL register, and compares the key stream bit by bit.
// Random valid / ready gaps exercise the AXI-Stream handshakes.
`ifndef DATA_DIR
`define DATA_DIR "C:/Users/Admin/Downloads/PostProcessing/PostProcessing/data/tb/"
`endif

module tb_qkd_ir;

    parameter ZC     = 128;
    parameter SH_W   = 7;
    localparam N      = 24 * ZC;
    localparam CH_BEATS = N / 16;
    localparam KEY_WORDS = N / 64;

    reg clk = 0;
    reg rstn = 0;
    always #5 clk = ~clk;

    // AXI-Lite
    reg  [7:0]  awaddr = 0;  reg awvalid = 0;  wire awready;
    reg  [31:0] wdata = 0;   reg wvalid = 0;   wire wready;
    wire [1:0]  bresp;       wire bvalid;      reg bready = 0;
    reg  [7:0]  araddr = 0;  reg arvalid = 0;  wire arready;
    wire [31:0] rdata;       wire [1:0] rresp; wire rvalid;  reg rready = 0;
    // streams
    reg  [31:0] ch_tdata = 0;  reg ch_tvalid = 0;  wire ch_tready;
    reg  [31:0] syn_tdata = 0; reg syn_tvalid = 0; wire syn_tready;
    wire [63:0] key_tdata;     wire key_tvalid;    reg key_tready = 0;  wire key_tlast;
    wire irq;
    reg  [31:0] pax_tdata = 0;  reg pax_tvalid = 0;  wire pax_tready;
    reg  [31:0] pas_tdata = 0;  reg pas_tvalid = 0;  wire pas_tready;
    wire [63:0] pay_tdata;      wire pay_tvalid;     reg pay_tready = 0;  wire pay_tlast;

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
        .m_axis_key_tlast(key_tlast),
        .s_axis_pa_x_tdata(pax_tdata), .s_axis_pa_x_tvalid(pax_tvalid), .s_axis_pa_x_tready(pax_tready),
        .s_axis_pa_seed_tdata(pas_tdata), .s_axis_pa_seed_tvalid(pas_tvalid), .s_axis_pa_seed_tready(pas_tready),
        .m_axis_pa_y_tdata(pay_tdata), .m_axis_pa_y_tvalid(pay_tvalid), .m_axis_pa_y_tready(pay_tready),
        .m_axis_pa_y_tlast(pay_tlast),
        .irq(irq)
    );

    // ------------------------------------------------------------------
    // PA vectors and stream drivers
    // ------------------------------------------------------------------
    integer    errors;
    // ------------------------------------------------------------------
    reg [31:0] pa_x_mem    [0:4095];
    reg [31:0] pa_seed_mem [0:4095];
    reg [63:0] pa_y_mem    [0:15];
    reg [63:0] pa_got      [0:15];
    reg [19:0] pa_n_mem    [0:0];
    integer    pa_ny;

    always @(posedge clk) begin
        pay_tready <= ($random % 3) != 0;
        if (pay_tvalid && pay_tready) begin
            pa_got[pa_ny] <= pay_tdata;
            if (pay_tlast !== (pa_ny == 15)) begin
                $display("ERROR: PA tlast mismatch at word %0d", pa_ny);
                errors = errors + 1;
            end
            pa_ny <= pa_ny + 1;
        end
    end

    task send_pa_x(input integer nw);
        integer k;
        begin
            for (k = 0; k < nw; k = k + 1) begin
                pax_tdata <= pa_x_mem[k]; pax_tvalid <= 1'b1;
                @(posedge clk);
                while (!pax_tready) @(posedge clk);
                pax_tvalid <= 1'b0;
                if (($random % 5) == 0) @(posedge clk);
            end
        end
    endtask

    task send_pa_seed(input integer nw);
        integer k;
        begin
            for (k = 0; k < nw; k = k + 1) begin
                pas_tdata <= pa_seed_mem[k]; pas_tvalid <= 1'b1;
                @(posedge clk);
                while (!pas_tready) @(posedge clk);
                pas_tvalid <= 1'b0;
                if (($random % 7) == 0) @(posedge clk);
            end
        end
    endtask

    // ------------------------------------------------------------------
    // AXI-Lite tasks
    // ------------------------------------------------------------------
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

    // ------------------------------------------------------------------
    // Vectors
    // ------------------------------------------------------------------
    reg [31:0] ch_mem  [0:CH_BEATS-1];
    reg [31:0] syn_mem [0:12*ZC/32-1];
    reg [31:0] blk_mem [0:31];
    reg [31:0] rev_mem [0:N-1];
    reg [63:0] key_mem [0:KEY_WORDS-1];
    reg [63:0] got     [0:KEY_WORDS-1];
    reg [7:0]  nblk_mem [0:0];
    reg [8*256-1:0] fname;

    integer nwords, b, a, i, w, nattempt, nrev, npre, rev_idx, syn_beats, mb, t0;
    reg [31:0] cfg, cfg2, expw, st, itw, cyc, errw;
    reg        exp_conv;

    // key collector with random backpressure
    always @(posedge clk) begin
        key_tready <= ($random % 4) != 0;
        if (key_tvalid && key_tready) begin
            got[nwords] <= key_tdata;
            if (key_tlast !== (nwords == KEY_WORDS - 1)) begin
                $display("ERROR: tlast mismatch at word %0d", nwords);
                errors = errors + 1;
            end
            nwords <= nwords + 1;
        end
    end

    task send_ch;
        integer k;
        begin
            for (k = 0; k < CH_BEATS; k = k + 1) begin
                ch_tdata <= ch_mem[k]; ch_tvalid <= 1'b1;
                @(posedge clk);
                while (!ch_tready) @(posedge clk);
                ch_tvalid <= 1'b0;
                if (($random % 8) == 0) @(posedge clk);
            end
        end
    endtask

    task send_syn;
        integer k;
        begin
            for (k = 0; k < syn_beats; k = k + 1) begin
                syn_tdata <= syn_mem[k]; syn_tvalid <= 1'b1;
                @(posedge clk);
                while (!syn_tready) @(posedge clk);
                syn_tvalid <= 1'b0;
                if (($random % 8) == 0) @(posedge clk);
            end
        end
    endtask

    initial begin
        errors = 0;
        $readmemh({`DATA_DIR, "nblk.hex"}, nblk_mem);
        repeat (5) @(posedge clk);
        rstn <= 1'b1;
        repeat (3) @(posedge clk);
        axi_read(8'h00, st);
        $display("ID = %h", st);
        axi_write(8'h1C, 32'h3);                        // IRQ on success and fail

        for (b = 0; b < nblk_mem[0]; b = b + 1) begin
            $sformat(fname, "%sch_%0d.hex",  `DATA_DIR, b); $readmemh(fname, ch_mem);
            $sformat(fname, "%ssyn_%0d.hex", `DATA_DIR, b); $readmemh(fname, syn_mem);
            $sformat(fname, "%sblk_%0d.hex", `DATA_DIR, b); $readmemh(fname, blk_mem);
            $sformat(fname, "%srev_%0d.hex", `DATA_DIR, b); $readmemh(fname, rev_mem);
            $sformat(fname, "%skey_%0d.hex", `DATA_DIR, b); $readmemh(fname, key_mem);
            cfg = blk_mem[0];
            cfg2 = blk_mem[1];
            npre = blk_mem[2];
            nattempt = blk_mem[3];
            mb = (cfg[1:0] == 2'd0) ? 12 : (cfg[1:0] == 2'd1) ? 8 : (cfg[1:0] == 2'd2) ? 6 : 4;
            syn_beats = mb * ZC / 32;
            axi_write(8'h08, cfg);
            axi_write(8'h20, cfg2);
            nwords = 0; rev_idx = 0;
            t0 = $time;

            fork
                send_ch;
                send_syn;
            join

            if (cfg2[4]) begin
                // HOLD (dynamic mode): wait for the loaded block, send the r0 pre-reveals, start attempt 1
                st = 0;
                while (!st[3]) axi_read(8'h0C, st);
                for (i = 0; i < npre; i = i + 1) begin
                    axi_write(8'h18, rev_mem[rev_idx]);
                    rev_idx = rev_idx + 1;
                end
                axi_write(8'h04, 32'h1);
                $display("[blk %0d] HOLD: %0d bits revealed with the syndrome, attempt 1 started", b, npre);
            end

            for (a = 0; a < nattempt; a = a + 1) begin
                expw = blk_mem[4 + 2*a];
                nrev = blk_mem[5 + 2*a];
                exp_conv = expw[31];
                wait (irq);
                axi_read(8'h0C, st);
                axi_read(8'h10, itw);
                axi_read(8'h14, cyc);
                if (st[0] !== exp_conv || st[1] !== !exp_conv || st[5:4] !== expw[29:28] ||
                    st[27:16] !== expw[27:16] || itw[11:0] !== expw[11:0] || itw[23:16] !== a + 1) begin
                    $display("[blk %0d att %0d] ERROR: status %h iters %h, golden conv=%0d pp=%0d usc=%0d it=%0d",
                             b, a, st, itw, expw[31], expw[29:28], expw[27:16], expw[11:0]);
                    errors = errors + 1;
                end else begin
                    $display("[blk %0d att %0d] conv=%0d pp_used=%0d n_usc=%0d iters=%0d cycles=%0d  (matches golden)",
                             b, a, exp_conv, st[5:4], st[27:16], itw[11:0], cyc);
                end
                axi_write(8'h0C, 32'h3);                // clear sticky flags
                if (!exp_conv) begin
                    if (a == nattempt - 1) begin
                        axi_write(8'h04, 32'h2);        // discard
                        $display("[blk %0d] discarded after %0d attempts (as golden)", b, nattempt);
                    end else begin
                        for (i = 0; i < nrev; i = i + 1) begin
                            axi_write(8'h18, rev_mem[rev_idx]);
                            rev_idx = rev_idx + 1;
                        end
                        axi_write(8'h04, 32'h1);        // retry
                    end
                end
            end

            if (exp_conv) begin
                for (w = 0; w < KEY_WORDS; w = w + 1) begin
                    if (got[w] !== key_mem[w]) begin
                        errors = errors + 1;
                        if (errors < 10) $display("[blk %0d] ERROR key word %0d: got %h exp %h", b, w, got[w], key_mem[w]);
                    end
                end
                axi_read(8'h24, errw);
                if (errw[11:0] !== blk_mem[4 + 2*nattempt][11:0]) begin
                    $display("[blk %0d] ERROR: ERRCNT %0d, golden %0d", b, errw[11:0], blk_mem[4 + 2*nattempt][11:0]);
                    errors = errors + 1;
                end else begin
                    $display("[blk %0d] ERRCNT = %0d corrected channel errors (matches golden)", b, errw[11:0]);
                end
                if (nwords != KEY_WORDS) begin
                    $display("[blk %0d] ERROR: %0d key words", b, nwords);
                    errors = errors + 1;
                end else begin
                    $display("[blk %0d] key %0d bits bit-exact with golden model, block time %0d cycles",
                             b, N, ($time - t0) / 10);
                end
            end else if (nwords != 0) begin
                $display("[blk %0d] ERROR: key words output for a discarded block", b);
                errors = errors + 1;
            end
            repeat (5) @(posedge clk);
        end

        // ---------------- privacy amplification pass
        $readmemh({`DATA_DIR, "pa_x.hex"}, pa_x_mem);
        $readmemh({`DATA_DIR, "pa_seed.hex"}, pa_seed_mem);
        $readmemh({`DATA_DIR, "pa_y.hex"}, pa_y_mem);
        $readmemh({`DATA_DIR, "pa_n.hex"}, pa_n_mem);
        pa_ny = 0;
        axi_write(8'h44, {12'd0, pa_n_mem[0]});
        axi_write(8'h1C, 32'h4);                        // IRQ on PA_DONE
        t0 = $time;
        axi_write(8'h40, 32'h1);
        fork
            send_pa_x(pa_n_mem[0]);
            send_pa_seed(pa_n_mem[0] + 33);
        join
        wait (irq);
        for (w = 0; w < 16; w = w + 1)
            if (pa_got[w] !== pa_y_mem[w]) begin
                errors = errors + 1;
                $display("[PA] ERROR word %0d: got %h exp %h", w, pa_got[w], pa_y_mem[w]);
            end
        $display("[PA] %0d input bits -> 1024 hash bits, %0d cycles, %s", 32 * pa_n_mem[0], ($time - t0) / 10,
                 (pa_ny == 16) ? "word count OK" : "WRONG word count");
        if (pa_ny != 16) errors = errors + 1;

        if (errors == 0) $display("TB_RESULT: PASS (%0d IR blocks + 1 PA pass bit-exact vs golden model)", nblk_mem[0]);
        else             $display("TB_RESULT: FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #200_000_000;
        $display("TB_RESULT: FAIL (timeout)");
        $finish;
    end

endmodule
