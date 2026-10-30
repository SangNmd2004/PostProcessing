# Block contexts sharing one decoder (option C): reconciled-key throughput before the RTL change

Discrete-event model, 100 MHz, EFFICIENCY profile traces of the first 120 blocks of each simulated session; Mbit/s of reconciled key (2765 bits per block).

| Session | RTT | K = 1 | K = 2 | K = 3 | K = 4 | K = 6 | K = 8 | decoder-only limit |
|---|---|---|---|---|---|---|---|---|
| weak | 100 us | 18.2 | 35.7 | 50.9 | 64.1 | 78.2 | 79.8 | 82 |
| weak | 1000 us | 2.3 | 4.6 | 6.8 | 9.1 | 13.3 | 17.4 | 82 |
| moderate | 100 us | 11.3 | 21.8 | 30.2 | 34.2 | 35.5 | 35.5 | 36 |
| moderate | 1000 us | 1.6 | 3.1 | 4.7 | 6.1 | 9.0 | 11.6 | 36 |
| severe | 100 us | 16.7 | 32.0 | 45.0 | 53.0 | 55.2 | 55.2 | 56 |
| severe | 1000 us | 2.3 | 4.6 | 6.9 | 9.3 | 13.5 | 18.1 | 56 |

## Measured on the RTL (tb/tb_qkd_ir_ctx.v, 2026-10-23)

30 blocks of `data/sessions_tb` (all 5 levels, both profiles, HOLD blocks included), Alice's syndrome and every
reveal message one round trip of 10 000 cycles (100 us at 100 MHz) after the request, ModelSim:

| Contexts used | Cycles for 30 blocks | Reconciled key | Result |
|---|---|---|---|
| 1 (old behaviour) | 453 898 | 18.3 Mbit/s | PASS, bit-exact |
| 4 | 130 361 | **63.6 Mbit/s (x3.48)** | PASS, bit-exact |

The regression testbench (`tb/tb_qkd_ir.v`, context 0 only, data/tb) still passes: 9 IR blocks + 1 PA pass.
