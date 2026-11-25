/* Opt-in PS wall-time/PMU profiler. UART replies are read after snapshots freeze.
 * Parent/child phases overlap; these values must not be added indiscriminately. */
#define HP_PHASES 29u
#define HP_HISTORY 64u
enum {
    HP_UART_RX_ACK,HP_CRC,HP_COMMAND_PRINTF,HP_TX_DRAIN,
    HP_IR_SETUP,HP_IR_COPY_START,HP_IR_INPUT_DRAIN,HP_IR_PRE_REVEAL,
    HP_IR_DECODE_POLL,HP_IR_KEY_RX,HP_REVEAL_WRITE,HP_FAIL_TO_REVEAL,
    HP_STRIP_D,HP_VERIFY_CALL,HP_PA_CALL,
    HP_VERIFY_SETUP,HP_VERIFY_START,HP_VERIFY_DRAIN,
    HP_PA_SETUP,HP_PA_START,HP_PA_DRAIN,
    HP_STREAM_APPEND,HP_STREAM_DECIDE,HP_EMIT_PREP,HP_EMIT_FINALIZE,
    HP_SEED_COPY,HP_STREAM_WIPE,HP_RESERVED27,HP_RESERVED28
};
typedef struct {XTime tick;uint32_t cycle;} hp_mark_t;
typedef struct {uint64_t ticks,cycles;uint32_t count,valid;} hp_phase_t;
typedef struct {uint32_t seq,op;uint64_t total_ticks;hp_phase_t phase[HP_PHASES];} hp_snapshot_t;
static hp_snapshot_t hp_work,hp_history[HP_HISTORY];
static uint32_t hp_enabled,hp_seen,hp_cal_ticks,hp_cal_cycles,hp_read_ticks;
static uint32_t hp_waiting;
static hp_mark_t hp_frame_start,hp_wait_start;
static uint32_t hp_cycle(void)
{
    uint32_t value;__asm__ volatile("mrc p15, 0, %0, c9, c13, 0":"=r"(value));return value;
}
static hp_mark_t hp_mark(void)
{
    hp_mark_t value={0,0};
    if (hp_enabled) {
        __asm__ volatile("dsb sy\n\tisb sy":::"memory");
        XTime_GetTime(&value.tick);value.cycle=hp_cycle();
    }
    return value;
}
static void hp_add(uint32_t phase,hp_mark_t start)
{
    if (!hp_enabled||phase>=HP_PHASES) return;
    hp_mark_t end=hp_mark();uint64_t elapsed=end.tick-start.tick;
    hp_phase_t *p=&hp_work.phase[phase];p->ticks+=elapsed;p->count++;
    /* BSP: global timer = CPU/2. Mark long spans invalid for 32-bit CCNT. */
    if (elapsed<=0x7fffffffull) {p->cycles+=(uint32_t)(end.cycle-start.cycle);p->valid++;}
}
static void hp_begin_frame(void)
{
    if (hp_enabled) {memset(&hp_work,0,sizeof(hp_work));hp_frame_start=hp_mark();}
}
static void hp_finish(uint32_t seq,uint32_t op)
{
    if (!hp_enabled) return;
    hp_mark_t end=hp_mark();hp_work.seq=seq;hp_work.op=op;
    hp_work.total_ticks=end.tick-hp_frame_start.tick;
    hp_history[hp_seen%HP_HISTORY]=hp_work;hp_seen++;
}
static void hp_wait_begin(void) {if (hp_enabled) {hp_wait_start=hp_mark();hp_waiting=1;}}
static void hp_wait_end(void) {if (hp_waiting) {hp_add(HP_FAIL_TO_REVEAL,hp_wait_start);hp_waiting=0;}}
static int hp_control(uint32_t seq,uint32_t enable)
{
    if (enable>1u) return -1;
    if (enable) {
        uint32_t pmcr,cnten=0x80000000u;
        __asm__ volatile("mrc p15, 0, %0, c9, c12, 0":"=r"(pmcr));
        pmcr=(pmcr|1u)&~8u; /* enable; CCNT divider off; preserve counter values */
        __asm__ volatile("mcr p15, 0, %0, c9, c12, 0"::"r"(pmcr):"memory");
        __asm__ volatile("mcr p15, 0, %0, c9, c12, 1\n\tisb sy"::"r"(cnten):"memory");
        hp_enabled=1;hp_seen=0;hp_waiting=0;
        memset(hp_history,0,sizeof(hp_history));
        hp_mark_t start=hp_mark(),end=hp_mark();hp_read_ticks=(uint32_t)(end.tick-start.tick);
        start=hp_mark();
        do {end=hp_mark();} while (end.tick-start.tick<(XTime)COUNTS_PER_SECOND/10000u);
        hp_cal_ticks=(uint32_t)(end.tick-start.tick);hp_cal_cycles=end.cycle-start.cycle;
    } else {hp_enabled=0;hp_waiting=0;}
    xil_printf("QKD_PROFILE_CONFIG seq=%u enabled=%u timer_hz=%u cpu_hz=%u cal_ticks=%u cal_cycles=%u read_ticks=%u\r\n",
               seq,hp_enabled,(uint32_t)COUNTS_PER_SECOND,(uint32_t)XPAR_CPU_CORTEXA9_0_CPU_CLK_FREQ_HZ,
               hp_cal_ticks,hp_cal_cycles,hp_read_ticks);return 0;
}
static int hp_read(uint32_t seq,uint32_t index)
{
    uint32_t count=hp_seen<HP_HISTORY?hp_seen:HP_HISTORY;
    if (index==0xffffffffu) {
        xil_printf("QKD_PROFILE_META seq=%u count=%u dropped=%u enabled=%u timer_hz=%u cpu_hz=%u\r\n",
                   seq,count,hp_seen-count,hp_enabled,(uint32_t)COUNTS_PER_SECOND,(uint32_t)XPAR_CPU_CORTEXA9_0_CPU_CLK_FREQ_HZ);return 0;
    }
    if (index>=count) return -1;
    uint32_t oldest=hp_seen>HP_HISTORY?hp_seen%HP_HISTORY:0u;
    hp_snapshot_t *s=&hp_history[(oldest+index)%HP_HISTORY];uint32_t phases=0;
    for (uint32_t i=0;i<HP_PHASES;i++) if (s->phase[i].count) phases++;
    xil_printf("QKD_PROFILE_SNAPSHOT seq=%u index=%u command_seq=%u op=%u phases=%u total_ticks=%08x%08x\r\n",
               seq,index,s->seq,s->op,phases,(uint32_t)(s->total_ticks>>32),(uint32_t)s->total_ticks);
    for (uint32_t i=0;i<HP_PHASES;i++) {
        hp_phase_t *p=&s->phase[i];if (!p->count) continue;
        xil_printf("QKD_PROFILE_PHASE seq=%u id=%u count=%u valid=%u ticks=%08x%08x cycles=%08x%08x\r\n",
                   seq,i,p->count,p->valid,(uint32_t)(p->ticks>>32),(uint32_t)p->ticks,
                   (uint32_t)(p->cycles>>32),(uint32_t)p->cycles);
    }
    xil_printf("QKD_PROFILE_END seq=%u\r\n",seq);return 0;
}
