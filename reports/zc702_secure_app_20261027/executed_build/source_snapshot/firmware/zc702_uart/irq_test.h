/* One-shot level IRQ gate: ISR masks source, preserving status for polling. */
#include "xparameters.h"
#include "xscugic.h"
#include "xil_exception.h"
static XScuGic functional_gic;
static volatile uint32_t functional_irq_count,functional_irq_status;
static int functional_irq_initialized;
static void functional_irq_handler(void *unused)
{
    (void)unused;
    functional_irq_status=rd(QKD,0x0cu);
    wr(QKD,0x1cu,0u);
    functional_irq_count++;
}
static int functional_irq_arm(void)
{
    wr(QKD,0x1cu,0u);wr(QKD,0x0cu,3u);
    if (!functional_irq_initialized) {
        XScuGic_Config *config=XScuGic_LookupConfig(XPAR_SCUGIC_0_DEVICE_ID);
        if (!config || XScuGic_CfgInitialize(&functional_gic,config,config->CpuBaseAddress)!=XST_SUCCESS) return -1;
        Xil_ExceptionInit();
        Xil_ExceptionRegisterHandler(XIL_EXCEPTION_ID_INT,(Xil_ExceptionHandler)XScuGic_InterruptHandler,&functional_gic);
        if (XScuGic_Connect(&functional_gic,XPAR_FABRIC_QKD_IRQ_INTR,functional_irq_handler,0)!=XST_SUCCESS) return -1;
        XScuGic_SetPriorityTriggerType(&functional_gic,XPAR_FABRIC_QKD_IRQ_INTR,0xa0u,1u);
        XScuGic_Enable(&functional_gic,XPAR_FABRIC_QKD_IRQ_INTR);
        Xil_ExceptionEnable();functional_irq_initialized=1;
    }
    functional_irq_count=0;functional_irq_status=0;wr(QKD,0x1cu,3u);
    return 0;
}
