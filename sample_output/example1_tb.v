`timescale 1ns / 1ps

module tb_top;
    reg clk = 0, resetn = 1, btn = 0;
    reg [14:0] sw = 0;
    wire [15:0] led;
    wire [6:0] seg;
    wire [7:0] an;
    wire dp;
    integer errors = 0;

    top #(.DEBOUNCE_CYCLES(2)) dut (.CLK100MHZ(clk), .CPU_RESETN(resetn), .BTNC(btn), .SW(sw), .LED(led), .SEG(seg), .DP(dp), .AN(an));
    always #5 clk = ~clk;

    task press_step;
        begin
            btn = 1; repeat (8) @(posedge clk);
            btn = 0; repeat (8) @(posedge clk);
        end
    endtask

    task press_reset;
        begin
            resetn = 0; repeat (8) @(posedge clk);
            resetn = 1; repeat (8) @(posedge clk);
        end
    endtask

    task check_cycle(input [4:0] cycle);
        if (led[4:0] !== cycle) begin
            $display("FAIL: LED shows cycle %0d, expected %0d", led[4:0], cycle);
            errors = errors + 1;
        end
    endtask

    task check_fu(input [4:0] fu, input [31:0] expected);
        begin
            sw[4:0] = fu; #1;
            if (dut.display_valid !== 1'b1 || dut.display_value !== expected) begin
                $display("FAIL: FU %0d shows %0d, expected %0d", fu, dut.display_value, expected);
                errors = errors + 1;
            end
        end
    endtask

    task check_idle(input [4:0] fu);
        begin
            sw[4:0] = fu; #1;
            if (dut.display_valid !== 1'b0) begin
                $display("FAIL: FU %0d should be idle", fu);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        press_reset;
        sw[6:5] = 3;
        sw[8:7] = 3;
        check_cycle(1);
        check_fu(0, 6);
        check_idle(1);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(2);
        check_fu(0, 9);
        check_fu(1, 3);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(3);
        check_idle(0);
        check_idle(1);
        check_fu(2, 9);
        check_idle(3);
        press_step;
        press_reset;
        sw[6:5] = 1;
        sw[8:7] = 2;
        check_cycle(1);
        check_fu(0, 3);
        check_idle(1);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(2);
        check_fu(0, 4);
        check_fu(1, 1);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(3);
        check_idle(0);
        check_idle(1);
        check_fu(2, 2);
        check_idle(3);
        press_step;
        press_reset;
        sw[6:5] = 3;
        sw[8:7] = 1;
        check_cycle(1);
        check_fu(0, 4);
        check_idle(1);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(2);
        check_fu(0, 7);
        check_fu(1, 3);
        check_idle(2);
        check_idle(3);
        press_step;
        check_cycle(3);
        check_idle(0);
        check_idle(1);
        check_fu(2, 3);
        check_idle(3);
        press_step;
        if (errors == 0) $display("PASS");
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
