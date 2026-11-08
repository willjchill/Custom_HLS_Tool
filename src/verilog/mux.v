// mux with INPUTS sources, source 0 is the lowest WIDTH bits of "in"
module mux #(parameter WIDTH = 32, parameter INPUTS = 2) (
    input  wire [WIDTH*INPUTS-1:0]   in,
    input  wire [$clog2(INPUTS)-1:0] sel,
    output wire [WIDTH-1:0]          out
);
    assign out = in[sel*WIDTH +: WIDTH];
endmodule
