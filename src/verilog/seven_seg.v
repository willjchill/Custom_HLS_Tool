// shows value as 8 hex digits on the 7 segment display (outputs are active low)
// if valid is 0, all digits show a dash
module seven_seg (
    input  wire        clk,
    input  wire        valid,
    input  wire [31:0] value,
    output reg  [7:0]  an = 8'hFF,
    output reg  [6:0]  seg = 7'h7F
);
    reg [19:0] refresh = 0;
    wire [2:0] digit = refresh[19:17];       // goes through the 8 digits
    wire [3:0] nibble = value[digit*4 +: 4];

    always @(posedge clk) begin
        refresh <= refresh + 1;
        an <= ~(8'd1 << digit);
        if (!valid) seg <= 7'b0111111;
        else case (nibble)
            4'h0: seg <= 7'b1000000;
            4'h1: seg <= 7'b1111001;
            4'h2: seg <= 7'b0100100;
            4'h3: seg <= 7'b0110000;
            4'h4: seg <= 7'b0011001;
            4'h5: seg <= 7'b0010010;
            4'h6: seg <= 7'b0000010;
            4'h7: seg <= 7'b1111000;
            4'h8: seg <= 7'b0000000;
            4'h9: seg <= 7'b0010000;
            4'hA: seg <= 7'b0001000;
            4'hB: seg <= 7'b0000011;
            4'hC: seg <= 7'b1000110;
            4'hD: seg <= 7'b0100001;
            4'hE: seg <= 7'b0000110;
            4'hF: seg <= 7'b0001110;
        endcase
    end
endmodule
