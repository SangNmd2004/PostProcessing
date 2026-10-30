"""Profiler wire helpers; reads snapshots after the measured operations finish."""
PHASES=['uart_rx_ack_enqueue','crc32','command_including_reply_printf','reply_fifo_drain',
 'ir_setup_reset','ir_copy_cache_and_dma_start','ir_input_dma_and_hold_drain','ir_pre_reveal_write',
 'ir_run_to_status_poll','ir_key_rx_and_cache','reveal_mmio_write','fail_detect_to_reveal_command',
 'strip_D_positions','verification_PL_call','PA_PL_call','verification_reset_and_rx_setup',
 'verification_mm2s_cache_and_start','verification_dma_and_output_drain','PA_reset_and_rx_setup',
 'PA_mm2s_cache_and_start','PA_dma_and_output_drain','stream_append_and_counts','finite_key_decision',
 'emit_prefix_prepare','emit_tail_and_wipe','seed_copy','stream_reset_and_wipe','reserved27','reserved28']
def enable(session):
    _,reply=session.command([74,1],r'QKD_PROFILE_CONFIG seq={seq} enabled=1 timer_hz=(\d+) cpu_hz=(\d+) cal_ticks=(\d+) cal_cycles=(\d+) read_ticks=(\d+)')
    fields=['timer_hz','cpu_hz','cal_ticks','cal_cycles','read_ticks'];config=dict(zip(fields,map(int,reply.groups())))
    assert abs(config['cal_cycles']/config['cal_ticks']-config['cpu_hz']/config['timer_hz'])<.02
    return config
def collect(session):
    _,meta=session.command([75,0xffffffff],r'QKD_PROFILE_META seq={seq} count=(\d+) dropped=(\d+) enabled=1 timer_hz=(\d+) cpu_hz=(\d+)')
    count,dropped,_,_=map(int,meta.groups());assert not dropped
    snapshots=[]
    for index in range(count):
        seq,head=session.command([75,index],r'QKD_PROFILE_SNAPSHOT seq={seq} index=(\d+) command_seq=(\d+) op=(\d+) phases=(\d+) total_ticks=([0-9a-fA-F]{16})')
        i,command_seq,op,nphase=map(int,head.groups()[:4]);assert i==index
        snapshot={'command_seq':command_seq,'op':op,'total_ticks':int(head.group(5),16),'query_seq':seq,'phases':[]}
        for _ in range(nphase):
            p=session.expect(fr'QKD_PROFILE_PHASE seq={seq} id=(\d+) count=(\d+) valid=(\d+) ticks=([0-9a-fA-F]{{16}}) cycles=([0-9a-fA-F]{{16}})')
            phase_id,n,valid=map(int,p.groups()[:3]);ticks=int(p.group(4),16);cycles=int(p.group(5),16)
            snapshot['phases'].append(dict(id=phase_id,count=n,valid=valid,ticks=ticks,cycles=cycles))
        session.expect(fr'QKD_PROFILE_END seq={seq}');snapshots.append(snapshot)
    return snapshots
def disable(session):
    session.command([74,0],r'QKD_PROFILE_CONFIG seq={seq} enabled=0 timer_hz=\d+ cpu_hz=\d+ cal_ticks=\d+ cal_cycles=\d+ read_ticks=\d+')
