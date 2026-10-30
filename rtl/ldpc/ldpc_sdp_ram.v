`timescale 1ns / 1ps

// Simple dual-port RAM (1 write port, 1 read port), synchronous read, 1-cycle latency (OUT_REG = 0) or 2-cycle
// latency with an output register (OUT_REG = 1, BSRAM output register / pipeline read mode).
// Mapped to Gowin BSRAM (SDPB) via syn_ramstyle. Read-during-write to the same address returns old data.
module ldpc_sdp_ram #(
    parameter DATA_W  = 576,
    parameter DEPTH   = 24,
    parameter ADDR_W  = 5,
    parameter OUT_REG = 0
)(
    input                   clk,
    input                   we,
    input  [ADDR_W-1:0]     waddr,
    input  [DATA_W-1:0]     wdata,
    input  [ADDR_W-1:0]     raddr,
    output [DATA_W-1:0]     rdata
);

    (* syn_ramstyle = "block_ram" *) reg [DATA_W-1:0] mem [0:DEPTH-1];
    reg [DATA_W-1:0] rd_q, rd_q2;

    always @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        rd_q  <= mem[raddr];
        rd_q2 <= rd_q;
    end
    assign rdata = OUT_REG ? rd_q2 : rd_q;

endmodule
