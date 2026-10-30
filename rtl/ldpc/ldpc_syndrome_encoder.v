`timescale 1ns / 1ps

// =============================================================================
// Module: ldpc_syndrome_encoder
// Reference: Work Item R05 (FPGA-based Alice syndrome encoder reusing LDPC shifter and ROM)
// Target: Xilinx ZC702 (xc7z020clg484-1), FCLK0 = 50 MHz
//
// Features:
// 1. Unified Symmetrical Architecture:
//    - Reuses ldpc_code_rom auto-generated from model/codes.json for 100% bit-exact parity.
//    - Reuses qc_cyclic_shifter (ZC=128, WORD_W=1) from Bob decoder.
//    - Computes Alice Slepian-Wolf syndrome S = H * X mod 2 directly in FPGA PL.
// 2. High-Throughput Layered Circulant Accumulation:
//    - S_m = XOR_sum(X_n <<< H_{m,n}) for all non-null circulants H_{m,n} != -1.
//    - 128-bit parallel XOR parity accumulator.
// 3. AXI-Stream Compatibility:
//    - Slave port s_axis_key accepts Alice's 3072-bit raw key block (96 x 32-bit beats).
//    - Master port m_axis_syn emits packed syndrome matching Bob's s_axis_syn format.
// =============================================================================

module ldpc_syndrome_encoder #(
    parameter ZC      = 128,
    parameter SHIFT_W = 7,
    parameter NB_COLS = 24,
    parameter MB_MAX  = 12
)(
    input  wire                 clk,
    input  wire                 rst_n,

    // Control
    input  wire                 start,
    input  wire [1:0]           code_rate,   // 0: r12 (12 layers), 1: r23 (8 layers), 2: r34 (6 layers), 3: r56 (4 layers)
    output reg                  busy,
    output reg                  done,

    // Alice Raw Key Input (AXI-Stream slave)
    input  wire [31:0]          s_axis_key_tdata,
    input  wire                 s_axis_key_tvalid,
    output wire                 s_axis_key_tready,

    // Alice Syndrome Output (AXI-Stream master)
    output reg  [31:0]          m_axis_syn_tdata,
    output reg                  m_axis_syn_tvalid,
    input  wire                 m_axis_syn_tready
);

    // -------------------------------------------------------------------------
    // 1. Internal Storage & State Machine
    // -------------------------------------------------------------------------
    reg [ZC-1:0] key_mem [0:NB_COLS-1]; // Store 24 columns of ZC=128 bits
    reg [ZC-1:0] syn_acc;                // 128-bit accumulator for current layer

    localparam S_IDLE        = 3'd0;
    localparam S_LOAD_KEY    = 3'd1;
    localparam S_ENCODE_EDGE = 3'd2;
    localparam S_EMIT_SYN    = 3'd3;
    localparam S_DONE        = 3'd4;

    reg [2:0]  state;
    reg [3:0]  curr_layer;
    reg [4:0]  curr_edge;
    reg [6:0]  beat_count;
    reg [1:0]  syn_beat;

    assign s_axis_key_tready = (state == S_LOAD_KEY);

    // -------------------------------------------------------------------------
    // 2. LDPC Code ROM Instance (Reused directly from Bob's decoder)
    // -------------------------------------------------------------------------
    wire [3:0] rom_num_layers;
    wire [4:0] rom_layer_deg;
    wire [4:0] rom_e_col;
    wire [6:0] rom_e_shift;

    ldpc_code_rom u_rom (
        .code(code_rate),
        .layer(curr_layer),
        .e(curr_edge),
        .num_layers(rom_num_layers),
        .layer_gap(),
        .layer_deg(rom_layer_deg),
        .e_col(rom_e_col),
        .e_shift(rom_e_shift),
        .e_g(),
        .col(5'd0),
        .ce(3'd0),
        .col_deg(),
        .c_layer(),
        .c_shift()
    );

    // -------------------------------------------------------------------------
    // 3. Cyclic Shifter Instance (Reused from Bob's Decoder)
    // -------------------------------------------------------------------------
    wire [ZC-1:0]       shifter_in  = key_mem[rom_e_col];
    wire [SHIFT_W-1:0]  shifter_amt = rom_e_shift;
    wire [ZC-1:0]       shifter_out;

    qc_cyclic_shifter #(
        .ZC(ZC),
        .WORD_W(1),
        .SHIFT_W(SHIFT_W),
        .NGRP(1),
        .PIPE_AT(0)
    ) u_shifter (
        .clk(clk),
        .data_in(shifter_in),
        .shift_amt(shifter_amt),
        .data_out(shifter_out)
    );

    // -------------------------------------------------------------------------
    // 4. Encoder Sequence Logic
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state             <= S_IDLE;
            busy              <= 1'b0;
            done              <= 1'b0;
            curr_layer        <= 4'd0;
            curr_edge         <= 5'd0;
            beat_count        <= 7'd0;
            syn_beat          <= 2'd0;
            syn_acc           <= {ZC{1'b0}};
            m_axis_syn_tvalid <= 1'b0;
            m_axis_syn_tdata  <= 32'd0;
        end else begin
            case (state)
                S_IDLE: begin
                    busy              <= 1'b0;
                    done              <= 1'b0;
                    m_axis_syn_tvalid <= 1'b0;
                    if (start) begin
                        busy       <= 1'b1;
                        state      <= S_LOAD_KEY;
                        beat_count <= 7'd0;
                        curr_layer <= 4'd0;
                        curr_edge  <= 5'd0;
                    end
                end

                S_LOAD_KEY: begin
                    // 24 * ZC / 32 = 96 beats of 32-bit words
                    if (s_axis_key_tvalid) begin
                        // Assemble into key_mem
                        key_mem[beat_count >> 2][(beat_count[1:0] * 32) +: 32] <= s_axis_key_tdata;
                        if (beat_count + 1 == 7'd96) begin
                            state      <= S_ENCODE_EDGE;
                            curr_layer <= 4'd0;
                            curr_edge  <= 5'd0;
                            syn_acc    <= {ZC{1'b0}};
                        end else begin
                            beat_count <= beat_count + 1;
                        end
                    end
                end

                S_ENCODE_EDGE: begin
                    // Accumulate shifted parity for current circulant edge
                    syn_acc <= syn_acc ^ shifter_out;

                    if (curr_edge + 1 == rom_layer_deg) begin
                        curr_edge <= 5'd0;
                        state     <= S_EMIT_SYN;
                        syn_beat  <= 2'd0;
                    end else begin
                        curr_edge <= curr_edge + 1;
                    end
                end

                S_EMIT_SYN: begin
                    // Emit 128-bit syndrome as 4 words of 32 bits
                    m_axis_syn_tvalid <= 1'b1;
                    m_axis_syn_tdata  <= syn_acc[(syn_beat * 32) +: 32];

                    if (m_axis_syn_tready) begin
                        if (syn_beat == 2'd3) begin
                            syn_beat <= 2'd0;
                            if (curr_layer + 1 == rom_num_layers) begin
                                m_axis_syn_tvalid <= 1'b0;
                                state             <= S_DONE;
                                done              <= 1'b1;
                                busy              <= 1'b0;
                            end else begin
                                curr_layer        <= curr_layer + 1;
                                curr_edge         <= 5'd0;
                                syn_acc           <= {ZC{1'b0}};
                                state             <= S_ENCODE_EDGE;
                                m_axis_syn_tvalid <= 1'b0;
                            end
                        end else begin
                            syn_beat <= syn_beat + 1;
                        end
                    end
                end

                S_DONE: begin
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
