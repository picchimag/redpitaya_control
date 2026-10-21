"""Digitally triggered 3-input logger.

    IN1       energy, boxcar-averaged over n_avg samples
    IN2       piezo direction, thresholded to -1 / 0 / +1
    DIO pin   pulse trigger (exp_p[0] by default)

One 64-bit record per trigger: 46-bit clock-cycle timestamp + 2-bit direction
+ signed 16-bit energy. See redpitaya_fpga/docs/trig_logger.md.
"""
from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control.trig_logger import (
    TrigLogger, unpack, load_run, unwrap_ts, fit_clock, counter_to_unix)
import os
import numpy as np

RP_HOST = os.environ.get("RP_HOST", "171.64.56.120")
OUT_DIR = "run1"
DURATION = 60                      # seconds; None = run until Ctrl+C

# Connect
dev = redpitaya_dev(RP_HOST, "config/trig_logger.json")
dev.base.load_bitfile()

log = TrigLogger(dev)

# Configure. n_avg must be a power of two (<= 2048); the boxcar divide is a
# right shift, which is why. n_delay_us is measured from the trigger edge.
log.configure(
    n_avg=256,          # 256 samples = 2.05 us at 125 MHz
    n_delay_us=5.0,     # latch the averaged energy 5 us after the trigger
    dir_thr=0.1,        # IN2 >= +0.1 V -> +1, <= -0.1 V -> -1, between -> 0
    trig_sel=0,         # 0-7 = exp_p[0..7], 8-15 = exp_n[0..7]
    trig_invert=0,      # 1 = trigger on the falling edge
    trig_dead_us=0.0,   # extra holdoff per record (debounce); dead time is
                        # n_delay_us + trig_dead_us
    flush_ms=100,       # publish a partial buffer this often, so a low
                        # trigger rate still produces data
)

# Bring-up check before arming: is the trigger pin the one you think it is, has
# the boxcar primed, and does the direction read sensibly?
print("status before arming:")
for k, v in log.status().items():
    print(f"  {k:>11} = {v}")

# Acquire. Ctrl+C stops cleanly; files are fsync'd as they go, so an
# interrupted run keeps everything already written.
print(f"\nlogging to {OUT_DIR}/ ...")
n = log.run(duration=DURATION, output_dir=OUT_DIR)

# ---------------------------------------------------------------- offline
ts, energy, direction = unpack(load_run(f"{OUT_DIR}/events_*.bin"))
print(f"\n{len(ts)} records")

if len(ts):
    # Clock cycles -> seconds within the run, and -> absolute UNIX time via the
    # tie-points. unwrap_ts() matters only past the 6.5-day counter wrap.
    t_rel = log.seconds(unwrap_ts(ts) - ts[0])
    a, b, ppm = fit_clock(f"{OUT_DIR}/tiepoints.csv")
    t_abs = counter_to_unix(unwrap_ts(ts), a, b)
    print(f"span      : {t_rel[-1]:.3f} s")
    print(f"rate      : {len(ts) / max(t_rel[-1], 1e-9):.1f} triggers/s")
    print(f"crystal   : {b:.6f} ns/cycle ({ppm:+.2f} ppm vs the host clock)")

    for d, name in ((1, "+1"), (0, " 0"), (-1, "-1")):
        sel = direction == d
        if sel.any():
            print(f"dir {name}    : {sel.sum():>7} records, "
                  f"mean energy {energy[sel].mean():>8.1f}")
        else:
            print(f"dir {name}    : {0:>7} records")

    print(f"dropped   : {log.dropped()}  (host too slow: both buffers full)")
    print(f"skipped   : {log.skipped()}  (triggers inside the dead time)")
