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

# SETTINGS

# Everything you would normally touch is here. Nothing below needs editing.
RP_HOST  = os.environ.get("RP_HOST", "171.64.56.120")
OUT_DIR  = "run1"
DURATION = 60          # seconds of acquisition; None = run until Ctrl+C

N_AVG        = 4       # boxcar length in SAMPLES, power of two, <= 2048.
                       # 256 samples = 2.05 us at 125 MHz. The divide is a
                       # right shift, which is why it must be a power of two.
N_DELAY      = 8       # trigger edge -> energy latch, in CLOCK CYCLES of
                       # 8 ns each (no prescaler), so 625 = 5.0 us. The boxcar
                       # costs ~3 cycles of pipeline, so the stored average
                       # ends ~24 ns before this deadline.
DIR_THR      = 0.1     # symmetric IN2 threshold in volts: >= +0.1 V -> +1,
                       # <= -0.1 V -> -1, in between -> 0
DIR_THR_POS  = None    # set both of these to override DIR_THR with an
DIR_THR_NEG  = None    # asymmetric pair, e.g. +0.15 / -0.05
TRIG_SEL     = 0       # which DIO pin: 0-7 = exp_p[0..7], 8-15 = exp_n[0..7]
TRIG_INVERT  = 0       # 1 = trigger on the falling edge
TRIG_DEAD    = 0       # extra holdoff after each record (debounce), also in
                       # CLOCK CYCLES -- 125 cycles = 1 us. Total dead time is
                       # N_DELAY + TRIG_DEAD; triggers inside it are rejected
                       # and counted in `skipped`.
FLUSH_MS     = 100     # publish a partially filled buffer this often, so a
                       # low trigger rate still produces data (0 = never)
FRAME_LEN    = 4096    # records per buffer before the ping-pong swap, 1..4096.
                       # Lower = lower latency, more drain round-trips.
TIE_PERIOD_S = 1.0     # how often to write a clock tie-point

# CONNECT AND SETUP. The JSON file contains the FPGA bitfile name and the register map.

dev = redpitaya_dev(RP_HOST, "config/trig_logger.json")
dev.base.load_bitfile()

log = TrigLogger(dev)

log.configure(
    n_avg=N_AVG,
    n_delay=N_DELAY,
    dir_thr=DIR_THR,
    dir_thr_pos=DIR_THR_POS,
    dir_thr_neg=DIR_THR_NEG,
    trig_sel=TRIG_SEL,
    trig_invert=TRIG_INVERT,
    trig_dead=TRIG_DEAD,
    flush_ms=FLUSH_MS,
    frame_len=FRAME_LEN,
)

# Bring-up check before arming: is the trigger pin the one you think it is, has
# the boxcar primed, and does the direction read sensibly?
print("status before arming:")
for k, v in log.status().items():
    print(f"  {k:>11} = {v}")

# ACQUIRE. Ctrl+C stops cleanly; files are fsync'd as they go, so an
# interrupted run keeps everything already written.
print(f"\nlogging to {OUT_DIR}/ ...")
n = log.run(duration=DURATION, output_dir=OUT_DIR,
            tie_period_s=TIE_PERIOD_S)



# OFFLINE readout and analysis. The unpack() call returns three numpy arrays of the same length: timestamps, energies, and directions. 
# The timestamps are 46-bit clock cycles, which can be converted to seconds relative to the start of the run, 
# and then to absolute UNIX time using the tie-points.
#  The direction is a 2-bit value that can be -1, 0, or +1, and the energy is a signed 16-bit value.
#  The code prints out the number of records, the span of the run in seconds, the trigger rate, the crystal clock rate in ns/cycle and ppm, 
# and the number of records and mean energy for each direction. It also prints out the number of dropped and skipped triggers.      


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
