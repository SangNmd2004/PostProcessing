set_param general.maxThreads 2
puts "ZC702_BOARD_PARTS=[get_board_parts -quiet *zc702*]"
puts "ZC702_PS_IP=[get_ipdefs -quiet xilinx.com:ip:processing_system7:*]"
puts "ZC702_DMA_IP=[get_ipdefs -quiet xilinx.com:ip:axi_dma:*]"
create_project -in_memory -part xc7z020clg484-1
create_bd_design inspect
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
puts "ZC702_PRESET_OPTIONS=[list_property_value CONFIG.preset $ps]"
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 dma]
foreach p [list_property $dma] {
    if {[string match CONFIG.* $p]} { puts "DMA_PARAM $p=[get_property $p $dma]" }
}
puts ZC702_INSPECT_DONE
