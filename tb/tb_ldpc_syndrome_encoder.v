`timescale 1ns / 1ps

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
