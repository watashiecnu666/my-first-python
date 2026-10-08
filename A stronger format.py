
# -*- coding: utf-8 -*-
"""
美国经济走势分析 —— 健壮版
运行: python us_economy.py
诊断: python us_economy.py --diagnose
"""

from __future__ import annotations
import sys, io, time, argparse, traceback
from pathlib import Path

# ---------------- 依赖检查（比原版更早报错） ----------------
missing = []
for mod in ("pandas", "numpy", "requests", "matplotlib"):
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)

if missing:
    print("[错误] 缺少依赖: " + ", ".join(missing))
    print("请运行:  pip install " + " ".join(missing))
    sys.exit(1)

import pandas as pd
import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")             # 无 GUI 环境下也能跑
import matplotlib.pyplot as plt

# ---------------- 配置 ----------------
START_DATE = "1990-01-01"
CACHE_DIR  = Path(".fred_cache")
OUTPUT_PNG = "us_economy_dashboard.png"
FRED_CSV   = "https://fred.stlouisfed.org/graph/fredgraph.csv"

INDICATORS = {
    "GDPC1":    "实际GDP",
    "UNRATE":   "失业率",
    "PAYEMS":   "非农就业",
    "ICSA":     "初请失业金",
    "CPIAUCSL": "CPI",
    "PCEPI":    "PCE价格",
    "FEDFUNDS": "联邦基金利率",
    "DGS10":    "10年国债",
    "DGS2":     "2年国债",
    "T10Y2Y":   "10Y-2Y利差",
    "UMCSENT":  "消费者信心",
    "USREC":    "NBER衰退指标",
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept": "text/csv,*/*",
}


# ---------------- 诊断 ----------------
def diagnose():
    print("=" * 60)
    print("环境诊断")
    print("=" * 60)
    print(f"Python : {sys.version.split()[0]}")
    print(f"pandas : {pd.__version__}")
    print(f"numpy  : {np.__version__}")
    print(f"requests: {requests.__version__}")
    print(f"matplotlib: {matplotlib.__version__}")
    print()
    print("测试 FRED 连通性 ...")
    try:
        r = requests.get(FRED_CSV, params={"id": "GDPC1", "cosd": "2020-01-01"},
                         headers=HEADERS, timeout=20)
        print(f"  HTTP 状态码 : {r.status_code}")
        print(f"  响应前 120 字 : {r.text[:120]!r}")
        if r.status_code == 200 and "GDPC1" in r.text:
            print("  [OK] FRED 可访问")
        else:
            print("  [!!] 返回内容异常，可能被拦截或格式变化")
    except Exception as e:
        print(f"  [XX] 连接失败: {type(e).__name__}: {e}")
        print("  → 如果你在中国大陆，FRED 可能被墙，请使用代理或换网络。")


# ---------------- 数据获取 ----------------
def _parse_csv(text: str) -> pd.Series:
    """宽容解析 FRED 返回的 CSV。"""
    if not text or not text.strip():
        raise ValueError("响应为空")

    # 有时 FRED 会返回 HTML 错误页
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        raise ValueError("返回的是 HTML 页面（可能被拦截）")

    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise ValueError(f"列数不足: {list(df.columns)}")

    # 找日期列：优先名字里带 date 的
    date_col = None
    for c in df.columns:
        if "date" in str(c).lower():
            date_col = c
            break
    if date_col is None:
        date_col = df.columns[0]

    # 值列：排除日期列
    val_col = next(c for c in df.columns if c != date_col)

    idx = pd.to_datetime(df[date_col], errors="coerce")
    val = pd.to_numeric(df[val_col], errors="coerce")
    s = pd.Series(val.to_numpy(), index=idx, dtype="float64")
    return s[~s.index.isna()].dropna().sort_index()


def fetch(sid: str, start: str, refresh: bool, retries: int = 3) -> pd.Series:
    cache = CACHE_DIR / f"{sid}_{start}.csv"
    if cache.exists() and not refresh:
        try:
            s = _parse_csv(cache.read_text(encoding="utf-8-sig"))
            s.name = sid
            return s
        except Exception:
            pass  # 缓存坏了就重下

    err = None
    for i in range(retries):
        try:
            r = requests.get(FRED_CSV, params={"id": sid, "cosd": start},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            s = _parse_csv(r.text)
            s.name = sid
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(r.text, encoding="utf-8")
            return s
        except Exception as e:
            err = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"{sid}: {err}")


def load_all(start: str, refresh: bool) -> dict[str, pd.Series]:
    data: dict[str, pd.Series] = {}
    print(f"从 FRED 获取 {len(INDICATORS)} 个指标 ...\n")
    for sid, desc in INDICATORS.items():
        try:
            s = fetch(sid, start, refresh)
            data[sid] = s
            print(f"  [OK] {sid:<9} {desc:<12} {len(s):>5} 条  最新 {s.index[-1]:%Y-%m-%d}")
        except Exception as e:
            print(f"  [!!] {sid:<9} {desc:<12} 失败: {e}")
    print()
    return data


# ---------------- 分析 ----------------
def yoy(s: pd.Series, n: int) -> pd.Series:
    return (s / s.shift(n) - 1.0) * 100.0

def sahm_rule(unrate: pd.Series, window: int = 12) -> pd.Series:
    u3 = unrate.rolling(3, min_periods=2).mean()
    return u3 - u3.rolling(window, min_periods=window).min()


def report(data: dict[str, pd.Series]) -> str:
    L, notes, signals = [], [], []
    sep = "=" * 68
    L.append(sep)
    L.append("                 美 国 经 济 走 势 体 检 报 告")
    L.append(f"                 生成时间: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    L.append(sep)

    # 增长
    L.append("\n[一] 经济增长")
    g = data.get("GDPC1")
    if g is not None and len(g) > 6:
        gy = yoy(g, 4).dropna()
        L.append(f"  · 实际GDP 最新: {g.iloc[-1]:,.1f} 十亿(2017链式, {g.index[-1]:%Y-%m})")
        if len(gy) >= 2:
            cur, prev = float(gy.iloc[-1]), float(gy.iloc[-2])
            L.append(f"  · 同比增速: {cur:+.2f}%  (上季 {prev:+.2f}%, 变化 {cur-prev:+.2f}pp)")
            signals.append(("GDP同比 < 1%", cur < 1.0, f"{cur:+.2f}%"))
            if cur < 0:
                notes.append("GDP同比转负，经济处于收缩。")
            elif cur < 1.0:
                notes.append("GDP增速低于1%，动能不足。")
    else:
        L.append("  · GDP 数据不足")

    # 就业
    L.append("\n[二] 就业市场")
    u = data.get("UNRATE")
    if u is not None and len(u) > 13:
        cur = float(u.iloc[-1])
        chg = cur - float(u.iloc[-13])
        L.append(f"  · 失业率: {cur:.1f}%  (一年前 {u.iloc[-13]:.1f}%, 变化 {chg:+.1f}pp)")
        signals.append(("失业率一年升 ≥0.5pp", chg >= 0.5, f"{chg:+.1f}pp"))
        if chg >= 0.5:
            notes.append(f"失业率一年内上升 {chg:+.1f}pp，就业市场明显降温。")

        sr = sahm_rule(u).dropna()
        if len(sr):
            v = float(sr.iloc[-1])
            L.append(f"  · Sahm规则: {v:+.2f}  (衰退触发线 +0.50)")
            signals.append(("Sahm规则触发", v >= 0.5, f"{v:+.2f}"))
            if v >= 0.5:
                notes.append("Sahm规则已触发，历史上通常伴随衰退。")

    p = data.get("PAYEMS")
    if p is not None and len(p) > 3:
        d = p.diff().dropna()
        avg3 = float(d.rolling(3).mean().iloc[-1])
        L.append(f"  · 非农: 最新 {d.iloc[-1]:+,.0f}k, 3月均值 {avg3:+,.0f}k")
        signals.append(("非农3月均值为负", avg3 < 0, f"{avg3:+,.0f}k"))

    ic = data.get("ICSA")
    if ic is not None and len(ic) > 60:
        ma = ic.rolling(4).mean()
        base = float(ma.iloc[-53])
        if base > 0:
            y = (float(ma.iloc[-1]) / base - 1) * 100
            L.append(f"  · 初请(4周均值): {float(ma.iloc[-1]):,.0f}, 同比 {y:+.1f}%")
            signals.append(("初请同比 > 15%", y > 15, f"{y:+.1f}%"))

    # 通胀
    L.append("\n[三] 通货膨胀")
    cpi_yoy = None
    c = data.get("CPIAUCSL")
    if c is not None and len(c) > 13:
        cy = yoy(c, 12).dropna()
        cpi_yoy = float(cy.iloc[-1])
        L.append(f"  · CPI同比 ({cy.index[-1]:%Y-%m}): {cpi_yoy:+.2f}%")
    pc = data.get("PCEPI")
    if pc is not None and len(pc) > 13:
        py = yoy(pc, 12).dropna()
        L.append(f"  · PCE同比 ({py.index[-1]:%Y-%m}): {float(py.iloc[-1]):+.2f}%  (目标2%)")
    if cpi_yoy is not None:
        signals.append(("CPI同比 > 4%", cpi_yoy > 4.0, f"{cpi_yoy:+.2f}%"))
        if cpi_yoy > 4:
            notes.append(f"通胀偏高 (CPI同比 {cpi_yoy:.1f}%)，宽松空间受限。")
        elif cpi_yoy < 1:
            notes.append(f"通胀过低 (CPI同比 {cpi_yoy:.1f}%)，有通缩风险。")

    # 利率
    L.append("\n[四] 货币政策与利率")
    ff = data.get("FEDFUNDS")
    if ff is not None and len(ff):
        L.append(f"  · 联邦基金利率 ({ff.index[-1]:%Y-%m}): {ff.iloc[-1]:.2f}%")
    for sid, lbl in (("DGS10","10年国债"), ("DGS2","2年国债")):
        s = data.get(sid)
        if s is not None and len(s):
            L.append(f"  · {lbl}收益率 ({s.index[-1]:%Y-%m-%d}): {s.iloc[-1]:.2f}%")
    sp = data.get("T10Y2Y")
    if sp is not None and len(sp):
        cur_sp = float(sp.iloc[-1])
        recent = sp[sp.index >= sp.index[-1] - pd.DateOffset(months=12)]
        inv = int((recent < 0).sum())
        L.append(f"  · 10Y-2Y利差: {cur_sp:+.2f}pp  (过去12个月倒挂 {inv} 天)")
        signals.append(("过去12月有倒挂", inv > 0, f"{inv}天"))
        if inv > 0:
            notes.append("收益率曲线曾倒挂，历史领先衰退 6~18 个月。")

    # 消费
    L.append("\n[五] 消费与信心")
    um = data.get("UMCSENT")
    if um is not None and len(um) > 13:
        cur = float(um.iloc[-1])
        chg = cur - float(um.iloc[-13])
        L.append(f"  · 密歇根消费者信心 ({um.index[-1]:%Y-%m}): {cur:.1f}, 一年变化 {chg:+.1f}")
        signals.append(("信心一年降 > 10", chg < -10, f"{chg:+.1f}"))

    # 综合
    L.append("\n[六] 综合衰退风险")
    total = len(signals); hit = sum(1 for _, t, _ in signals if t)
    for name, trig, d in signals:
        L.append(f"  {'[触发]' if trig else '[正常]'} {name:<22} 当前 {d}")
    if total:
        r = hit / total
        lvl = "低" if r < .2 else "中低" if r < .45 else "中高" if r < .7 else "高"
        L.append(f"\n  >>> 衰退风险评分: {hit}/{total} 触发  →  风险等级: {lvl}")

    if notes:
        L.append("\n[七] 关键提示")
        for n in notes:
            L.append(f"  · {n}")

    L.append("\n" + "-" * 68)
    L.append("  说明: 基于公开历史数据自动生成，仅供学习研究，不构成投资建议。")
    L.append("-" * 68)
    return "\n".join(L)


# ---------------- 绘图 ----------------
def setup_font():
    from matplotlib import font_manager
    wanted = ["Microsoft YaHei", "SimHei", "PingFang SC", "Hiragino Sans GB",
              "Heiti SC", "Noto Sans CJK SC", "Source Han Sans SC",
              "WenQuanYi Micro Hei", "Arial Unicode MS"]
    have = {f.name for f in font_manager.fontManager.ttflist}
    for n in wanted:
        if n in have:
            plt.rcParams["font.sans-serif"] = [n, "DejaVu Sans"]
            return True
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    return False


def shade_recessions(ax, usrec):
    if usrec is None or usrec.empty:
        return
    flag = (usrec.dropna() > 0).astype(int)
    for _, seg in flag.groupby((flag != flag.shift()).cumsum()):
        if seg.iloc[0] == 1:
            ax.axvspan(seg.index[0], seg.index[-1], color="#999", alpha=.18, lw=0, zorder=0)


def plot_dashboard(data, out=OUTPUT_PNG):
    ok = setup_font()
    if not ok:
        print("[提示] 未找到中文字体，图中中文可能显示为方块。")

    usrec = data.get("USREC")
    fig, axes = plt.subplots(3, 3, figsize=(18, 12))
    fig.suptitle("美国经济走势仪表板", fontsize=18, fontweight="bold")
    axes = axes.ravel()

    def s(ax, title, ylab=""):
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.grid(alpha=.3, ls="--", lw=.6)
        if ylab: ax.set_ylabel(ylab, fontsize=9)
        ax.tick_params(labelsize=8)

    # ① GDP
    ax = axes[0]
    if "GDPC1" in data:
        g = yoy(data["GDPC1"], 4).dropna()
        ax.plot(g.index, g.values, color="#1f77b4", lw=1.8)
        ax.axhline(0, color="k", lw=.9)
        ax.fill_between(g.index, g.values, 0, where=(g.values < 0),
                        color="#d62728", alpha=.3)
        shade_recessions(ax, usrec)
    s(ax, "① 实际GDP同比", "%")

    # ② 失业率
    ax = axes[1]
    if "UNRATE" in data:
        u = data["UNRATE"]
        ax.plot(u.index, u.values, color="#d62728", lw=1.8)
        shade_recessions(ax, usrec)
    s(ax, "② 失业率", "%")

    # ③ Sahm
    ax = axes[2]
    if "UNRATE" in data:
        sr = sahm_rule(data["UNRATE"]).dropna()
        if len(sr):
            ax.plot(sr.index, sr.values, color="#9467bd", lw=1.8)
            ax.axhline(.5, color="#d62728", ls="--", lw=1.3)
    s(ax, "③ Sahm规则", "pp")

    # ④ 通胀
    ax = axes[3]
    if "CPIAUCSL" in data:
        ax.plot(yoy(data["CPIAUCSL"], 12).dropna().index,
                yoy(data["CPIAUCSL"], 12).dropna().values,
                color="#ff7f0e", lw=1.8, label="CPI同比")
    if "PCEPI" in data:
        ax.plot(yoy(data["PCEPI"], 12).dropna().index,
                yoy(data["PCEPI"], 12).dropna().values,
                color="#2ca02c", lw=1.8, label="PCE同比")
    ax.axhline(2, color="k", ls=":", lw=1)
    ax.legend(fontsize=8)
    s(ax, "④ 通胀同比", "%")

    # ⑤ 利率
    ax = axes[4]
    for sid, c, lbl in (("FEDFUNDS", "#1f77b4", "联邦基金"),
                        ("DGS10", "#d62728", "10年"),
                        ("DGS2", "#2ca02c", "2年")):
        if sid in data:
            ax.plot(data[sid].index, data[sid].values, color=c, lw=1.5, label=lbl)
    ax.legend(fontsize=8)
    s(ax, "⑤ 利率与国债收益率", "%")

    # ⑥ 利差
    ax = axes[5]
    if "T10Y2Y" in data:
        sp = data["T10Y2Y"]
        ax.plot(sp.index, sp.values, color="#8c564b", lw=1.4)
        ax.axhline(0, color="#d62728", ls="--", lw=1.2)
        ax.fill_between(sp.index, sp.values, 0, where=(sp.values < 0),
                        color="#d62728", alpha=.3)
    s(ax, "⑥ 10Y-2Y利差", "%")

    # ⑦ 非农
    ax = axes[6]
    if "PAYEMS" in data:
        d = data["PAYEMS"].diff().dropna()
        ax.bar(d.index, d.values, width=25, color="#aec7e8", label="月变化")
        ax.plot(d.index, d.rolling(3).mean().values, color="#1f77b4", lw=1.8, label="3月均值")
        ax.axhline(0, color="k", lw=.8)
        ax.legend(fontsize=8)
    s(ax, "⑦ 非农就业月变化", "千人")

    # ⑧ 初请
    ax = axes[7]
    if "ICSA" in data:
        ic = data["ICSA"]
        ax.plot(ic.index, ic.rolling(4).mean().values / 1000, color="#17becf", lw=1.4)
        shade_recessions(ax, usrec)
    s(ax, "⑧ 初请失业金(4周均值)", "千人")

    # ⑨ 信心
    ax = axes[8]
    if "UMCSENT" in data:
        u = data["UMCSENT"]
        ax.plot(u.index, u.values, color="#e377c2", lw=1.8)
        shade_recessions(ax, usrec)
    s(ax, "⑨ 密歇根消费者信心", "指数")

    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"图表已保存: {Path(out).resolve()}")


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START_DATE)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    if args.diagnose:
        diagnose()
        return

    t0 = time.time()
    try:
        data = load_all(args.start, args.refresh)
    except Exception:
        print("[致命错误] 数据加载失败：")
        traceback.print_exc()
        return

    if not data:
        print("未获取到任何数据。请运行：  python us_economy.py --diagnose")
        return

    print(report(data))

    if not args.no_plot:
        try:
            plot_dashboard(data)
        except Exception as e:
            print(f"[警告] 绘图失败: {e}")
            traceback.print_exc()

    print(f"\n总耗时 {time.time()-t0:.1f} 秒")


if __name__ == "__main__":
    main()
