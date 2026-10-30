# Internal accelerator clock target: 70 MHz. This is not a board pin constraint file.
create_clock -name qkd_clk -period 14.285714 [get_ports s_axi_aclk]
