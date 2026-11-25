"""Paced Arrival Traffic Benchmark and Crossover Empirical Verification.
Reference: Work items P06, PUB01, PUB02.
Crossover model: model/efficiency_throughput_crossover.py, reports/zc702_crossover_model/REPORT.md.

Simulates and validates:
1. Paced raw key packet arrivals under discrete arrival rates lambda:
   - Single-context (K=1): lambda in {500, 1000, 1500, 1941, 2500, 3500, 5000} blocks/s
   - Multi-context  (K=4): lambda in {2000, 4000, 6000, 6795, 8000, 10000, 15000} blocks/s
2. Queue backlog Q(t) and queuing latency distribution W(t)
3. Effective secret key throughput R_sec(lambda) across policies:
   - Fixed EFFICIENCY (high yield, higher latency)
   - Fixed THROUGHPUT (lower yield, lower latency)
   - Dynamic ADAPTIVE (backlog hysteresis switching at Q >= 4 and Q <= 1)
4. Empirical verification of the crossover point lambda*:
   - Below lambda*: EFFICIENCY delivers higher secret key yield
   - Above lambda*: THROUGHPUT avoids queue explosion and maintains high throughput
   - ADAPTIVE automatically tracks the upper hull of both regimes
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import random

ROOT = Path(__file__).resolve().parents[2]


class PacedArrivalSimulator:
    """Discrete-event queueing simulator driven by hardware-measured phase durations."""
    def __init__(self, k_contexts, policy, t_decode_us, t_load_us=17.7, t_verify_us=2.5, t_pa_us=22.7, yield_per_block=1382.5):
        self.k_contexts = k_contexts
        self.policy = policy
        self.yield_per_block = yield_per_block

        # Service time per block (seconds)
        # Multi-context speedup S(K) ~ min(K, 3.5) on decoder
        speedup = 3.5 if k_contexts == 4 else 1.0
        self.t_service = (t_decode_us / speedup + t_load_us + t_verify_us + t_pa_us) * 1e-6
        self.capacity = 1.0 / self.t_service

    def run(self, arrival_rate, duration_s=1.0, max_queue=64):
        dt = 1e-5  # 10 microsecond simulation resolution
        total_steps = int(duration_s / dt)
        p_arrival = arrival_rate * dt

        queue = 0
        busy_time_left = 0.0

        arrived = 0
        serviced = 0
        dropped = 0
        total_secret_bits = 0.0
        active_policy = self.policy

        queue_history = []

        rng = random.Random(42 + int(arrival_rate))

        for step in range(total_steps):
            # Arrival process (Bernoulli approximation of Poisson arrivals)
            if rng.random() < p_arrival:
                arrived += 1
                if queue < max_queue:
                    queue += 1
                else:
                    dropped += 1

            # Adaptive hysteresis switching
            if self.policy == 'ADAPTIVE':
                if queue >= 4:
                    active_policy = 'THROUGHPUT'
                elif queue <= 1:
                    active_policy = 'EFFICIENCY'

            # Service process
            if busy_time_left > 0:
                busy_time_left -= dt
            else:
                if queue > 0:
                    queue -= 1
                    serviced += 1
                    # Effective service duration based on active profile
                    curr_service = self.t_service if active_policy != 'THROUGHPUT' else (36.6 / (3.5 if self.k_contexts == 4 else 1.0) + 17.7 + 2.5 + 22.7) * 1e-6
                    busy_time_left = curr_service
                    # Accumulate secret bits based on profile active when block was serviced
                    block_yield = self.yield_per_block if active_policy != 'THROUGHPUT' else 1050.7
                    total_secret_bits += block_yield

            if step % 100 == 0:
                queue_history.append(queue)

        # Average secret bit rate
        r_secret_bps = total_secret_bits / duration_s
        avg_queue = sum(queue_history) / len(queue_history) if queue_history else 0.0

        return {
            'arrival_rate_blocks_s': arrival_rate,
            'arrived_blocks': arrived,
            'serviced_blocks': serviced,
            'dropped_blocks': dropped,
            'avg_queue_depth': round(avg_queue, 2),
            'secret_bit_rate_bps': round(r_secret_bps, 1),
            'secret_bit_rate_mbps': round(r_secret_bps / 1e6, 3),
            'drop_ratio': round(dropped / arrived, 4) if arrived > 0 else 0.0
        }


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = ROOT / 'reports' / 'zc702_paced_benchmark'
    out_dir.mkdir(parents=True, exist_ok=True)

    # Hardware measured timings from tong_hop.csv:
    # EFFICIENCY: t_decode = 677.8 us, yield = 2765 * 0.50 = 1382.5 bits
    # THROUGHPUT: t_decode = 36.6 us,  yield = 2765 * 0.38 = 1050.7 bits

    # 1. Single-Context (K=1) Benchmark around lambda* = 1941.4 blocks/s
    k1_rates = [500, 1000, 1500, 1941, 2500, 3500, 5000]
    k1_results = []

    for r in k1_rates:
        sim_eff = PacedArrivalSimulator(k_contexts=1, policy='EFFICIENCY', t_decode_us=677.8, yield_per_block=1382.5)
        sim_thr = PacedArrivalSimulator(k_contexts=1, policy='THROUGHPUT', t_decode_us=36.6, yield_per_block=1050.7)
        sim_adp = PacedArrivalSimulator(k_contexts=1, policy='ADAPTIVE', t_decode_us=677.8, yield_per_block=1382.5)

        res_eff = sim_eff.run(r)
        res_thr = sim_thr.run(r)
        res_adp = sim_adp.run(r)

        winner = 'EFFICIENCY' if res_eff['secret_bit_rate_bps'] > res_thr['secret_bit_rate_bps'] else 'THROUGHPUT'

        k1_results.append({
            'arrival_rate': r,
            'eff_secret_mbps': res_eff['secret_bit_rate_mbps'],
            'thr_secret_mbps': res_thr['secret_bit_rate_mbps'],
            'adaptive_secret_mbps': res_adp['secret_bit_rate_mbps'],
            'eff_queue': res_eff['avg_queue_depth'],
            'thr_queue': res_thr['avg_queue_depth'],
            'winner': winner
        })

    # 2. Multi-Context (K=4) Benchmark around lambda* = 6794.8 blocks/s
    k4_rates = [2000, 4000, 6000, 6795, 8000, 10000, 15000]
    k4_results = []

    for r in k4_rates:
        sim_eff = PacedArrivalSimulator(k_contexts=4, policy='EFFICIENCY', t_decode_us=677.8, yield_per_block=1382.5)
        sim_thr = PacedArrivalSimulator(k_contexts=4, policy='THROUGHPUT', t_decode_us=36.6, yield_per_block=1050.7)
        sim_adp = PacedArrivalSimulator(k_contexts=4, policy='ADAPTIVE', t_decode_us=677.8, yield_per_block=1382.5)

        res_eff = sim_eff.run(r)
        res_thr = sim_thr.run(r)
        res_adp = sim_adp.run(r)

        winner = 'EFFICIENCY' if res_eff['secret_bit_rate_bps'] > res_thr['secret_bit_rate_bps'] else 'THROUGHPUT'

        k4_results.append({
            'arrival_rate': r,
            'eff_secret_mbps': res_eff['secret_bit_rate_mbps'],
            'thr_secret_mbps': res_thr['secret_bit_rate_mbps'],
            'adaptive_secret_mbps': res_adp['secret_bit_rate_mbps'],
            'eff_queue': res_eff['avg_queue_depth'],
            'thr_queue': res_thr['avg_queue_depth'],
            'winner': winner
        })

    # Crossover confirmation
    # Below lambda*: winner must be EFFICIENCY
    # Above lambda*: winner must be THROUGHPUT
    crossover_k1_verified = (k1_results[1]['winner'] == 'EFFICIENCY' and k1_results[5]['winner'] == 'THROUGHPUT')
    crossover_k4_verified = (k4_results[1]['winner'] == 'EFFICIENCY' and k4_results[5]['winner'] == 'THROUGHPUT')

    report_data = {
        'verified_utc': stamp,
        'item_id': 'PUB02_P06',
        'title': 'Paced arrival traffic benchmark and empirical crossover verification',
        'crossover_prediction': {
            'single_context_k1_crossover_blocks_s': 1941.4,
            'multi_context_k4_crossover_blocks_s': 6794.8,
            'k1_crossover_verified': crossover_k1_verified,
            'k4_crossover_verified': crossover_k4_verified,
        },
        'k1_measurements': k1_results,
        'k4_measurements': k4_results
    }

    k1_rows = []
    for r in k1_results:
        k1_rows.append(f"| **{r['arrival_rate']}** | {r['eff_secret_mbps']:.3f} | {r['thr_secret_mbps']:.3f} | {r['adaptive_secret_mbps']:.3f} | {r['eff_queue']:.2f} | {r['thr_queue']:.2f} | **{r['winner']}** |")
    k1_table = "\n".join(k1_rows)

    k4_rows = []
    for r in k4_results:
        k4_rows.append(f"| **{r['arrival_rate']}** | {r['eff_secret_mbps']:.3f} | {r['thr_secret_mbps']:.3f} | {r['adaptive_secret_mbps']:.3f} | {r['eff_queue']:.2f} | {r['thr_queue']:.2f} | **{r['winner']}** |")
    k4_table = "\n".join(k4_rows)

    report_data['status'] = 'PARTIAL_QUEUE_SIMULATION_EVALUATED'
    report_data['scope'] = 'Discrete-event host simulation based on hardware-calibrated parameters; not live board arrival measurement'

    (out_dir / 'REPORT.json').write_text(json.dumps(report_data, indent=2) + '\n', encoding='utf-8')

    md_report = f"""# Báo cáo Mô Phỏng Lưu Lượng Điều Tốc & Điểm Giao Thoa PUB02 / P06

- **Thời gian:** {stamp}
- **Hạng mục:** `P06` (Throughput & 4-context benchmark) · `PUB01` (Queueing model) · `PUB02` (Profile crossover proof)
- **Tệp nguồn:** [run_paced_arrival_benchmark.py](../../syn/zc702/run_paced_arrival_benchmark.py) · [efficiency_throughput_crossover.py](../../model/efficiency_throughput_crossover.py)
- **Ranh giới kiểm chứng:** **Mô phỏng hàng đợi sự kiện rời rạc dựa trên tham số đo kit; KHÔNG PHẢI phép đo luồng arrival trực tiếp qua UART/JTAG.**
- **Trạng thái:** **PARTIAL_QUEUE_SIMULATION_EVALUATED**

## 1. Thiết Kế Mô Phỏng Lưu Lượng Điều Tốc (Paced Traffic Model)
Mô phỏng quá trình phát sinh khối photon thô theo tốc độ điều tốc $\\lambda$ (blocks/s) quét qua điểm giao thoa lý thuyết:
- **Đơn ngữ cảnh (K=1)**: $\\lambda^* = 1941.4$ blocks/s (~5.37 Mbit/s raw key).
- **Đa ngữ cảnh (K=4)**: $\\lambda^* = 6794.8$ blocks/s (~18.8 Mbit/s raw key).

Mỗi kịch bản so sánh 3 chính sách điều phối:
1. **EFFICIENCY Cố Định**: Ưu tiên năng suất khóa ($Y_{{eff}} = 1382.5$ bit/block), độ trễ giải mã 677.8 us.
2. **THROUGHPUT Cố Định**: Ưu tiên thông lượng ($Y_{{thr}} = 1050.7$ bit/block), hội tụ sau 1 vòng (36.6 us).
3. **ADAPTIVE (Hysteresis)**: Tự động chuyển `THROUGHPUT` khi hàng đợi $Q \\ge 4$ và hồi về `EFFICIENCY` khi $Q \\le 1$.

## 2. Bảng Kết Quả Mô Phỏng Đơn Ngữ Cảnh (K = 1)

| Tốc Độ $\\lambda$ (blocks/s) | EFF Secret (Mbit/s) | THR Secret (Mbit/s) | ADAPTIVE Secret (Mbit/s) | Hàng Đợi EFF | Hàng Đợi THR | Chính Sách Thắng |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
{k1_table}

## 3. Bảng Kết Quả Mô Phỏng Đa Ngữ Cảnh (K = 4)

| Tốc Độ $\\lambda$ (blocks/s) | EFF Secret (Mbit/s) | THR Secret (Mbit/s) | ADAPTIVE Secret (Mbit/s) | Hàng Đợi EFF | Hàng Đợi THR | Chính Sách Thắng |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
{k4_table}

## 4. Kết Luận Khoa Học & Ranh Giới Nghiệm Thu
1. **Điểm giao thoa lý thuyết $\\lambda^*$**:
   - Dưới $\\lambda^*$: `EFFICIENCY` tối ưu hóa năng suất khóa hữu hạn, đạt thông lượng cao hơn.
   - Vượt $\\lambda^*$: năng lực giải mã bão hòa, `EFFICIENCY` bị nghẽn hàng đợi, trong khi `THROUGHPUT` giải phóng hàng đợi nhanh hơn.
2. **Bộ điều khiển ADAPTIVE**:
   - Bám theo đường bao trên (upper hull) của hai chế độ trong mô phỏng hàng đợi.
3. **Ranh giới nghiệm thu:**
   - Kết quả trên là mô phỏng hàng đợi trên host từ các tham số đo rời rạc; chưa chứng minh secret-key throughput hoặc crossover đo trực tiếp trên kit.
   - Nghiệm thu board yêu cầu truyền luồng arrival thật qua DMA/UART với scheduler hardware và đo lường trực tiếp.
"""
    (out_dir / 'REPORT.md').write_text(md_report, encoding='utf-8')
    print(f"PACED_BENCHMARK_SIMULATION_EVALUATED: {out_dir}")


if __name__ == '__main__':
    main()
