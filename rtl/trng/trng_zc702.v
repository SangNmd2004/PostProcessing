`timescale 1ns / 1ps

// =============================================================================
// Module: trng_zc702
// Reference: Work Item P03, NIST SP 800-90B (Entropy Sources for Random Bit Generation)
// Target: Xilinx ZC702 (Zynq-7000 xc7z020clg484-1), FCLK0 = 50 MHz
//
// Features:
// 1. Physical Entropy Harvesting:
//    - 8 Independent Ring Oscillators (RO) of coprime inverter stages (3, 5, 7, 11).
//    - Xilinx DONT_TOUCH and KEEP attributes prevent synthesis optimization.
//    - Multi-stage XOR parity collector with thermal noise / phase jitter sampling.
// 2. Hardware Conditioning:
//    - Selectable Von Neumann debiasing (transition extraction).
// 3. NIST SP 800-90B Online Continuous Health Testing:
//    - Repetition Count Test (RCT, Section 4.4.1): Cutoff C = 40 (alpha = 2^-20).
//    - Adaptive Proportion Test (APT, Section 4.4.2): Window W = 512, Cutoff C = 325.
//    - Immediate alarm and fail-closed isolation if health test fails.
// 4. Dual Output Interface:
//    - AXI4-Lite slave for CPU status, configuration, diagnostics, and FIFO read.
//    - AXI4-Stream master for direct streaming into PA Hankel hash seed port.
// =============================================================================

module trng_zc702 #(
    parameter NUM_RO        = 8,
    parameter FIFO_DEPTH_W  = 4   // 16 words FIFO
)(
    input  wire        clk,          // System clock (50 MHz)
    input  wire        rst_n,        // Active-low synchronous reset

    // AXI4-Lite Slave Interface
    input  wire [5:0]  s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,

    input  wire [5:0]  s_axi_araddr,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    // AXI4-Stream Master Interface (Direct seed feed to Privacy Amplification)
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready
);

    // -------------------------------------------------------------------------
    // 1. Ring Oscillator Entropy Harvesting Cells
    // -------------------------------------------------------------------------
    wire [NUM_RO-1:0] ro_out;
    wire              ro_enable;

    genvar g;
    generate
        for (g = 0; g < NUM_RO; g = g + 1) begin : gen_ro
            // Prime stage counts: 3, 5, 7, 11, 3, 5, 7, 11
            localparam STAGES = (g % 4 == 0) ? 3 :
                                (g % 4 == 1) ? 5 :
                                (g % 4 == 2) ? 7 : 11;

            (* DONT_TOUCH = "TRUE", KEEP = "TRUE" *) wire [STAGES:0] node;

            // Inverter chain with NAND gate for enable/gating
            assign node[0] = ~(node[STAGES] & ro_enable);

            genvar s;
            for (s = 0; s < STAGES; s = s + 1) begin : gen_inv
                (* DONT_TOUCH = "TRUE", KEEP = "TRUE" *)
                assign node[s+1] = ~node[s];
            end

            assign ro_out[g] = node[STAGES];
        end
    endgenerate

    // -------------------------------------------------------------------------
    // 2. Sampling and Parity Tree Collection
    // -------------------------------------------------------------------------
    reg [NUM_RO-1:0] ro_sample_meta;
    reg [NUM_RO-1:0] ro_sample_sync;
    wire             harvested_bit;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ro_sample_meta <= {NUM_RO{1'b0}};
            ro_sample_sync <= {NUM_RO{1'b0}};
        end else begin
            ro_sample_meta <= ro_out;
            ro_sample_sync <= ro_sample_meta;
        end
    end

    // XOR parity collector
    assign harvested_bit = ^ro_sample_sync;

    // -------------------------------------------------------------------------
    // 3. Von Neumann Debiasing Corrector
    // -------------------------------------------------------------------------
    reg        vn_state;      // 0: sample first bit, 1: sample second bit
    reg        vn_first_bit;
    reg        conditioned_bit;
    reg        conditioned_valid;
    wire       von_neumann_en;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            vn_state          <= 1'b0;
            vn_first_bit      <= 1'b0;
            conditioned_bit   <= 1'b0;
            conditioned_valid <= 1'b0;
        end else if (ro_enable) begin
            if (von_neumann_en) begin
                if (!vn_state) begin
                    vn_first_bit      <= harvested_bit;
                    vn_state          <= 1'b1;
                    conditioned_valid <= 1'b0;
                end else begin
                    vn_state <= 1'b0;
                    if (vn_first_bit != harvested_bit) begin
                        conditioned_bit   <= vn_first_bit; // 2'b01 -> 0, 2'b10 -> 1
                        conditioned_valid <= 1'b1;
                    end else begin
                        conditioned_valid <= 1'b0;         // 2'b00, 2'b11 discarded
                    end
                end
            end else begin
                conditioned_bit   <= harvested_bit;
                conditioned_valid <= 1'b1;
            end
        end else begin
            conditioned_valid <= 1'b0;
            vn_state          <= 1'b0;
        end
    end

    // -------------------------------------------------------------------------
    // 4. NIST SP 800-90B Online Continuous Health Testing
    // -------------------------------------------------------------------------
    wire        health_test_en;
    reg  [15:0] rct_cutoff;    // Default 40
    reg  [15:0] apt_cutoff;    // Default 325

    reg  [15:0] rct_count;
    reg         rct_last_sample;
    reg         rct_alarm;

    reg  [9:0]  apt_window_idx; // Window 0..511 (W = 512)
    reg         apt_target_sample;
    reg  [15:0] apt_count;
    reg         apt_alarm;
    reg  [15:0] total_alarms;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rct_count         <= 16'd0;
            rct_last_sample   <= 1'b0;
            rct_alarm         <= 1'b0;
            apt_window_idx    <= 10'd0;
            apt_target_sample <= 1'b0;
            apt_count         <= 16'd0;
            apt_alarm         <= 1'b0;
            total_alarms      <= 16'd0;
        end else if (health_test_en && conditioned_valid) begin
            // 4a. Repetition Count Test (RCT)
            if (conditioned_bit == rct_last_sample) begin
                if (rct_count + 1 >= rct_cutoff) begin
                    rct_alarm    <= 1'b1;
                    total_alarms <= total_alarms + 1;
                end else begin
                    rct_count <= rct_count + 1;
                end
            end else begin
                rct_last_sample <= conditioned_bit;
                rct_count       <= 16'd1;
            end

            // 4b. Adaptive Proportion Test (APT)
            if (apt_window_idx == 10'd0) begin
                apt_target_sample <= conditioned_bit;
                apt_count         <= 16'd1;
                apt_window_idx    <= 10'd1;
            end else begin
                if (conditioned_bit == apt_target_sample) begin
                    if (apt_count + 1 >= apt_cutoff) begin
                        apt_alarm    <= 1'b1;
                        total_alarms <= total_alarms + 1;
                    end
                    apt_count <= apt_count + 1;
                end
                if (apt_window_idx == 10'd511) begin
                    apt_window_idx <= 10'd0;
                end else begin
                    apt_window_idx <= apt_window_idx + 1;
                end
            end
        end
    end

    // Fail-closed gate: Entropy bit is only accepted if NO health alarm is raised
    wire valid_entropy_bit;
    assign valid_entropy_bit = conditioned_valid && (!rct_alarm) && (!apt_alarm);

    // -------------------------------------------------------------------------
    // 5. 32-bit Word Assembly and FIFO
    // -------------------------------------------------------------------------
    reg [4:0]  bit_count;
    reg [31:0] shift_word;
    reg [31:0] fifo_mem [0:(1<<FIFO_DEPTH_W)-1];
    reg [FIFO_DEPTH_W-1:0] fifo_wr_ptr;
    reg [FIFO_DEPTH_W-1:0] fifo_rd_ptr;
    reg [FIFO_DEPTH_W:0]   fifo_occupancy;

    wire fifo_full;
    wire fifo_empty;
    assign fifo_full  = (fifo_occupancy == (1 << FIFO_DEPTH_W));
    assign fifo_empty = (fifo_occupancy == 0);

    wire fifo_push;
    wire fifo_pop;
    assign fifo_push = (bit_count == 5'd31) && valid_entropy_bit && (!fifo_full);
    assign fifo_pop  = (m_axis_tvalid && m_axis_tready);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_count      <= 5'd0;
            shift_word     <= 32'd0;
            fifo_wr_ptr    <= {FIFO_DEPTH_W{1'b0}};
            fifo_rd_ptr    <= {FIFO_DEPTH_W{1'b0}};
            fifo_occupancy <= {(FIFO_DEPTH_W+1){1'b0}};
        end else begin
            // Shift register assembly
            if (valid_entropy_bit && (!fifo_full)) begin
                shift_word <= {shift_word[30:0], conditioned_bit};
                bit_count  <= bit_count + 1;
            end

            // FIFO Push
            if (fifo_push) begin
                fifo_mem[fifo_wr_ptr] <= {shift_word[30:0], conditioned_bit};
                fifo_wr_ptr           <= fifo_wr_ptr + 1;
            end

            // FIFO Pop
            if (fifo_pop) begin
                fifo_rd_ptr <= fifo_rd_ptr + 1;
            end

            // Occupancy update
            case ({fifo_push, fifo_pop})
                2'b10: fifo_occupancy <= fifo_occupancy + 1;
                2'b01: fifo_occupancy <= fifo_occupancy - 1;
                default: fifo_occupancy <= fifo_occupancy;
            endcase
        end
    end

    // AXI-Stream Output
    assign m_axis_tdata  = fifo_mem[fifo_rd_ptr];
    assign m_axis_tvalid = (!fifo_empty);

    // -------------------------------------------------------------------------
    // 6. AXI4-Lite Register Map & CSR
    // -------------------------------------------------------------------------
    // 0x00 CTRL:        [0] ENABLE, [1] SOFT_RESET, [2] VN_EN, [3] HEALTH_EN
    // 0x04 STATUS:      [0] READY, [1] RCT_ALARM, [2] APT_ALARM, [3] PASS, [15:8] OCCUPANCY
    // 0x08 DATA:        Read 32-bit entropy word (software pop)
    // 0x0C HEALTH_CFG:  [15:0] RCT_CUTOFF, [31:16] APT_CUTOFF
    // 0x10 DIAG:        [15:0] TOTAL_ALARMS, [31:16] RO_COUNT
    reg        reg_enable;
    reg        reg_vn_en;
    reg        reg_health_en;

    assign ro_enable      = reg_enable;
    assign von_neumann_en = reg_vn_en;
    assign health_test_en = reg_health_en;

    // AXI Write Channel
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_awready <= 1'b0;
            s_axi_wready  <= 1'b0;
            s_axi_bvalid  <= 1'b0;
            s_axi_bresp   <= 2'b00;
            reg_enable    <= 1'b1;  // Enabled by default
            reg_vn_en     <= 1'b1;  // Von Neumann enabled by default
            reg_health_en <= 1'b1;  // Health test enabled by default
            rct_cutoff    <= 16'd40;
            apt_cutoff    <= 16'd325;
        end else begin
            // Address ready
            if (s_axi_awvalid && !s_axi_awready) s_axi_awready <= 1'b1;
            else s_axi_awready <= 1'b0;

            // Write data ready
            if (s_axi_wvalid && !s_axi_wready) s_axi_wready <= 1'b1;
            else s_axi_wready <= 1'b0;

            // Handle register writes
            if (s_axi_awvalid && s_axi_wvalid && s_axi_awready && s_axi_wready) begin
                s_axi_bvalid <= 1'b1;
                case (s_axi_awaddr[5:2])
                    4'h0: begin // 0x00 CTRL
                        reg_enable    <= s_axi_wdata[0];
                        if (s_axi_wdata[1]) begin // Soft reset
                            rct_alarm <= 1'b0;
                            apt_alarm <= 1'b0;
                        end
                        reg_vn_en     <= s_axi_wdata[2];
                        reg_health_en <= s_axi_wdata[3];
                    end
                    4'h3: begin // 0x0C HEALTH_CFG
                        rct_cutoff <= s_axi_wdata[15:0];
                        apt_cutoff <= s_axi_wdata[31:16];
                    end
                    default: ;
                endcase
            end else if (s_axi_bready && s_axi_bvalid) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end

    // AXI Read Channel
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_arready <= 1'b0;
            s_axi_rvalid  <= 1'b0;
            s_axi_rresp   <= 2'b00;
            s_axi_rdata   <= 32'd0;
        end else begin
            if (s_axi_arvalid && !s_axi_arready) s_axi_arready <= 1'b1;
            else s_axi_arready <= 1'b0;

            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                case (s_axi_araddr[5:2])
                    4'h0: s_axi_rdata <= {28'd0, reg_health_en, reg_vn_en, 1'b0, reg_enable};
                    4'h1: s_axi_rdata <= {16'd0, 3'd0, fifo_occupancy, (!rct_alarm && !apt_alarm), apt_alarm, rct_alarm, !fifo_empty};
                    4'h2: s_axi_rdata <= fifo_mem[fifo_rd_ptr]; // 0x08 DATA (peek)
                    4'h3: s_axi_rdata <= {apt_cutoff, rct_cutoff};
                    4'h4: s_axi_rdata <= {16'd8, total_alarms};
                    default: s_axi_rdata <= 32'h54524E47; // "TRNG"
                endcase
            end else if (s_axi_rready && s_axi_rvalid) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
