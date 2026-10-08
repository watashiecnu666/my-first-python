#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
long_run.py —— 一个"能跑很久"的 Python 程序

用多进程蒙特卡洛方法估算 π:在单位正方形里随机撒点,
落在单位圆内的比例 × 4 就是 π 的估计值。跑得越久越精确。

用法示例:
    python long_run.py --seconds 10          # 跑 10 秒(测试用)
    python long_run.py --minutes 30          # 跑 30 分钟
    python long_run.py --hours 8 -w 8        # 跑 8 小时,8 个进程
    python long_run.py --forever             # 无限跑,直到 Ctrl+C
    python long_run.py --hours 24 --report 60

后台长跑(推荐):
    nohup python long_run.py --hours 24 > pi.log 2>&1 &
    # 或者
    tmux new -s pi 'python long_run.py --forever'
"""

import argparse
import math
import multiprocessing as mp
import os
import random
import time
from datetime import datetime

BATCH = 200_000  # 每批采样点数,用来摊薄加锁开销


# ----------------------------------------------------------------------
# 工作进程
# ----------------------------------------------------------------------
def worker(seed, stop_event, inside_counter, total_counter, lock):
    """不停地在单位正方形里撒点,分批把结果汇总到共享计数器。"""
    rng = random.Random(seed)
    rand = rng.random  # 绑定成局部变量,循环里快一点

    local_inside = 0
    local_total = 0

    while not stop_event.is_set():
        for _ in range(BATCH):
            x = rand()
            y = rand()
            if x * x + y * y <= 1.0:
                local_inside += 1
        local_total += BATCH

        with lock:
            inside_counter.value += local_inside
            total_counter.value += local_total
            local_inside = 0
            local_total = 0

    # 收尾:把最后不足一批的结果也交上去
    with lock:
        inside_counter.value += local_inside
        total_counter.value += local_total


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def format_duration(seconds):
    if seconds is None:
        return "∞"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def report(start, inside, total):
    elapsed = time.time() - start
    if total == 0:
        return
    p = inside / total
    pi_est = 4.0 * p
    stderr = 4.0 * math.sqrt(p * (1.0 - p) / total)
    speed = total / elapsed if elapsed > 0 else 0.0
    print(
        f"[{format_duration(elapsed)}] "
        f"采样 {total:>15,} | "
        f"π ≈ {pi_est:.10f} | "
        f"标准误 ±{stderr:.2e} | "
        f"实际误差 {abs(pi_est - math.pi):.2e} | "
        f"{speed / 1e6:.2f} M点/秒",
        flush=True,
    )


# ----------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="多进程蒙特卡洛估算 π —— 一个可以跑很久的程序"
    )
    parser.add_argument("--hours", type=float, default=0.0, help="运行小时数")
    parser.add_argument("--minutes", type=float, default=0.0, help="运行分钟数")
    parser.add_argument("--seconds", type=float, default=0.0, help="运行秒数")
    parser.add_argument("--forever", action="store_true", help="无限运行直到 Ctrl+C")
    parser.add_argument(
        "-w", "--workers", type=int, default=os.cpu_count() or 1, help="工作进程数"
    )
    parser.add_argument("--report", type=float, default=5.0, help="汇报间隔(秒)")
    parser.add_argument("--output", default="pi_result.txt", help="结果输出文件")
    args = parser.parse_args()

    if args.forever:
        duration = None
    else:
        duration = args.hours * 3600 + args.minutes * 60 + args.seconds
        if duration <= 0:
            duration = 3600.0
            print("未指定运行时长,默认运行 1 小时(可用 --hours/--minutes/--seconds/--forever)")

    workers = max(1, args.workers)

    # 跨进程共享状态
    stop_event = mp.Event()
    inside_counter = mp.Value("q", 0)   # 圆内点数
    total_counter = mp.Value("q", 0)    # 总点数
    lock = mp.Lock()

    procs = []
    for i in range(workers):
        seed = i * 1_000_003 + 12345
        p = mp.Process(
            target=worker,
            args=(seed, stop_event, inside_counter, total_counter, lock),
            daemon=True,
        )
        p.start()
        procs.append(p)

    start = time.time()
    deadline = None if duration is None else start + duration

    print("=" * 78)
    print(f"开始时间 : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"计划运行 : {format_duration(duration)}")
    print(f"工作进程 : {workers}")
    print(f"CPU 核心 : {os.cpu_count()}")
    print("按 Ctrl+C 可提前结束并输出当前结果")
    print("=" * 78, flush=True)

    interrupted = False
    try:
        while True:
            if deadline is not None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                sleep_for = min(args.report, remaining)
            else:
                sleep_for = args.report

            time.sleep(sleep_for)

            with lock:
                inside = inside_counter.value
                total = total_counter.value
            report(start, inside, total)

    except KeyboardInterrupt:
        interrupted = True
        print("\n收到 Ctrl+C,正在停止工作进程...", flush=True)

    stop_event.set()
    for p in procs:
        p.join(timeout=10)
        if p.is_alive():
            p.terminate()

    elapsed = time.time() - start
    with lock:
        inside = inside_counter.value
        total = total_counter.value

    if total == 0:
        print("没有采集到任何样本,无法估算。", flush=True)
        return

    p_hat = inside / total
    pi_est = 4.0 * p_hat
    stderr = 4.0 * math.sqrt(p_hat * (1.0 - p_hat) / total)

    lines = [
        "# 蒙特卡洛估算 π —— 结果",
        f"结束时间   : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"提前中断   : {'是' if interrupted else '否'}",
        f"运行时长   : {format_duration(elapsed)} ({elapsed:.1f} 秒)",
        f"工作进程   : {workers}",
        f"采样总点数 : {total}",
        f"圆内点数   : {inside}",
        f"π 估计值   : {pi_est:.15f}",
        f"π 真实值   : {math.pi:.15f}",
        f"绝对误差   : {abs(pi_est - math.pi):.3e}",
        f"标准误     : {stderr:.3e}",
        f"平均速度   : {total / elapsed / 1e6:.3f} M点/秒",
    ]
    text = "\n".join(lines) + "\n"

    print("\n" + text, flush=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"结果已写入 {args.output}", flush=True)


if __name__ == "__main__":
    main()
