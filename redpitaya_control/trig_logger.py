"""Host-side driver for the FPGA trig_logger core.

Three inputs, one record per digital trigger:

    IN1 (fast ADC ch A)  energy, boxcar-averaged over n_avg samples
    IN2 (fast ADC ch B)  piezo direction, thresholded to -1 / 0 / +1
    DIO pin              pulse trigger (rising edge by default)

Usage:
    dev = redpitaya_dev("171.64.56.120", "config/trig_logger.json")
    dev.base.load_bitfile()

    log = TrigLogger(dev)
    log.configure(n_avg=4, n_delay=16, dir_thr=0.1,
                  trig_sel=0, flush_ms=100)   # n_delay is CYCLES: 16 = 128 ns
    log.run(duration=60, output_dir="run1")   # None = run until Ctrl+C

Record layout (64-bit little-endian):
    bits [45:0]   timestamp   clock cycles since clear_ts (8 ns at 125 MHz)
    bits [47:46]  direction   signed 2-bit: 00 = 0, 01 = +1, 11 = -1
    bits [63:48]  energy      signed 16-bit boxcar average

Unlike event_logger's records the energy here is a plain signed int16 -- the
full averaged value, not the low bits of a positive peak height -- so there is
no 15-vs-16-bit ambiguity to get wrong.

The timestamp is clock cycles, not microseconds: 2^46 cycles is 6.5 days at
125 MHz. For a longer run, pass the records through unwrap_ts() before
converting to seconds; tiepoints.csv makes the rollover unambiguous.

    ts, energy, direction = unpack(load_run("run1/events_*.bin"))
    a, b, ppm = fit_clock("run1/tiepoints.csv")
    t_abs = counter_to_unix(unwrap_ts(ts), a, b)
"""

import os, time, signal, base64
import numpy as np

TS_BITS  = 46
E_BITS   = 16
DIR_LSB  = 46
TS_MASK  = (1 << TS_BITS) - 1
TS_SPAN  = 1 << TS_BITS          # counter wrap period, in cycles

CLK_HZ   = 125_000_000           # default; overridden from the config
TICK_NS  = 1e9 / CLK_HZ          # nominal ns per count (8.0 at 125 MHz)


def unpack(u64):
    """Decode a raw uint64 array -> (timestamp_cycles, energy, direction).

    energy    : int16, the boxcar average as the FPGA computed it
    direction : int8 in {-1, 0, +1}
    """
    u64 = np.asarray(u64, dtype='<u8')
    ts     = (u64 & TS_MASK).astype('u8')
    energy = ((u64 >> (TS_BITS + 2)) & 0xFFFF).astype(np.uint16).view(np.int16)

    code = ((u64 >> DIR_LSB) & 0x3).astype(np.uint8)
    direction = np.zeros(code.shape, dtype=np.int8)
    direction[code == 1] =  1
    direction[code == 3] = -1
    return ts, energy, direction


def unwrap_ts(ts):
    """Undo the 46-bit counter rollover in a time-ordered record stream.

    Records are written in counter order, so a decrease means the counter
    wrapped. Returns an int64 array of monotonically increasing cycle counts.
    Only meaningful for one continuous run (one clear_ts).
    """
    ts = np.asarray(ts, dtype=np.int64)
    if ts.size == 0:
        return ts
    wraps = np.zeros(ts.size, dtype=np.int64)
    wraps[1:] = np.cumsum(np.diff(ts) < 0)
    return ts + wraps * TS_SPAN


class TrigLogger:
    def __init__(self, dev):
        """
        dev: a connected redpitaya_dev instance whose config has a
             'trig_logger' module and an 'acquisition' section.
        """
        self.dev = dev
        self.rp  = dev.base

        acq = dev.config['acquisition']
        self.bram_addr = self.rp._to_int(acq['logger_bram'])
        self.cdma_addr = self.rp._to_int(acq['cdma_addr'])
        self.ddr_addr  = self.rp._to_int(acq['ddr_addr'])
        self.frame_len = acq.get('frame_len', 4096)
        self.clk_hz    = acq.get('clk_hz', CLK_HZ)
        st = dev.modules['trig_logger']['settings']
        self.max_log_avg = st.get('MAX_LOG_AVG', 11)
        # one BRAM, two buffers -> 2**(ADDR_BITS-1) records each
        self.max_frame_len = 1 << (st.get('ADDR_BITS', 13) - 1)
        self.mon       = '/opt/redpitaya/bin/monitor'
        self._armed    = False

    # ---------------------------------------------------------------- helpers
    def cycles(self, seconds):
        """Seconds -> clock cycles (the module's only time unit)."""
        return int(round(seconds * self.clk_hz))

    def seconds(self, cycles):
        """Clock cycles -> seconds."""
        return np.asarray(cycles, dtype=float) / self.clk_hz

    # ------------------------------------------------------------- configure
    def configure(self, n_avg=256, n_delay=625, dir_thr=0.1,
                  dir_thr_pos=None, dir_thr_neg=None, trig_sel=0,
                  trig_invert=0, trig_dead=0, flush_ms=100,
                  frame_len=None):
        """Configure the logger. Uses dev.set_register for everything.

        n_avg        boxcar length in SAMPLES; must be a power of two, up to
                     2**MAX_LOG_AVG (2048 by default)
        n_delay      CLOCK CYCLES from the trigger edge to the energy latch,
                     8 ns each at 125 MHz. This is the register's own unit --
                     there is no prescaler anywhere in this module. Use
                     log.cycles(seconds) if you would rather think in time:
                     log.cycles(5e-6) == 625.
        trig_dead    CLOCK CYCLES of extra holdoff after each record, on top
                     of n_delay. Total dead time is n_delay + trig_dead.
        dir_thr      symmetric direction threshold in VOLTS: IN2 >= +dir_thr
                     is +1, <= -dir_thr is -1, in between is 0. Pass
                     dir_thr_pos / dir_thr_neg instead for an asymmetric pair.
        trig_sel     which digital pin, 0-15 = exp_p[0..7] then exp_n[0..7]
        trig_invert  1 = trigger on the falling edge
        flush_ms     MILLISECONDS before a partially filled buffer is
                     published, so a low trigger rate still produces data
                     (0 = never). Host-latency housekeeping, not signal
                     timing, which is why this one stays in human units.
        """
        if frame_len is not None:
            self.frame_len = frame_len
        # frame_len-1 is truncated to ADDR_BITS-1 bits in the FPGA, so 0 would
        # silently mean a full buffer while the host drained nothing, and
        # anything above max_frame_len would overlap the two buffers.
        if not 1 <= int(self.frame_len) <= self.max_frame_len:
            raise ValueError(f"frame_len must be 1..{self.max_frame_len}, "
                             f"got {self.frame_len}")

        if n_avg < 1 or (n_avg & (n_avg - 1)) != 0:
            raise ValueError(f"n_avg must be a power of two, got {n_avg}")
        log_n_avg = int(n_avg).bit_length() - 1
        if log_n_avg > self.max_log_avg:
            raise ValueError(f"n_avg must be <= {1 << self.max_log_avg} "
                             f"(MAX_LOG_AVG={self.max_log_avg}), got {n_avg}")

        if not 0 <= int(trig_sel) <= 15:
            raise ValueError(f"trig_sel must be 0..15, got {trig_sel}")

        if dir_thr_pos is None:
            dir_thr_pos = abs(dir_thr)
        if dir_thr_neg is None:
            dir_thr_neg = -abs(dir_thr)

        # Both are plain cycle counts in 32-bit registers. Check each one:
        # trig_dead was previously unchecked, and a value that wrapped would
        # have silently become a short holdoff rather than a long one.
        for name, val in (("n_delay", n_delay), ("trig_dead", trig_dead)):
            if int(val) != val or not 0 <= int(val) < (1 << 32):
                raise ValueError(f"{name} must be a whole number of clock "
                                 f"cycles in 0..2**32-1, got {val!r}")
        n_delay, trig_dead = int(n_delay), int(trig_dead)

        s = self.dev.set_register
        s('trig_logger', 'arm', 0, raw=True)
        s('trig_logger', 'frame_len',   self.frame_len, raw=True)
        # flush_ticks counts clock cycles: the timestamp has no prescaler.
        s('trig_logger', 'flush_ticks', self.cycles(flush_ms * 1e-3), raw=True)
        s('trig_logger', 'log_n_avg',   log_n_avg, raw=True)
        s('trig_logger', 'n_delay',     n_delay, raw=True)
        s('trig_logger', 'trig_dead',   trig_dead, raw=True)
        s('trig_logger', 'dir_thr_pos', dir_thr_pos)
        s('trig_logger', 'dir_thr_neg', dir_thr_neg)
        s('trig_logger', 'trig_sel',    int(trig_sel), raw=True)
        s('trig_logger', 'trig_invert', int(bool(trig_invert)), raw=True)

        self.n_avg     = n_avg
        self.n_delay   = n_delay
        self.trig_dead = trig_dead

    # ------------------------------------------------------------ run control
    def arm(self, clear=True):
        self.dev.set_register('trig_logger', 'reset', 1, raw=True)
        self.dev.set_register('trig_logger', 'reset', 0, raw=True)
        if clear:
            self.dev.set_register('trig_logger', 'clear_ts', 1, raw=True)
            self.dev.set_register('trig_logger', 'arm', 1, raw=True)
            self.dev.set_register('trig_logger', 'clear_ts', 0, raw=True)
        else:
            self.dev.set_register('trig_logger', 'arm', 1, raw=True)
        self._armed = True

    def disarm(self):
        self.dev.set_register('trig_logger', 'arm', 0, raw=True)
        self._armed = False

    def snap_counter(self):
        """Latch and read the 46-bit clock-cycle counter."""
        self.dev.set_register('trig_logger', 'snap', 1, raw=True)
        self.dev.set_register('trig_logger', 'snap', 0, raw=True)
        lo = self.dev.get_register('trig_logger', 'ts_snap_lo', raw=True)
        hi = self.dev.get_register('trig_logger', 'ts_snap_hi', raw=True)
        return (hi << 32) | lo

    def tie_point(self):
        """Return (host_unix_ns, fpga_counter_cycles).

        time_ns() (not clock_gettime_ns, which is Unix-only) so this runs on
        Windows too; both read the realtime clock in ns since the epoch. The
        host clock's own granularity is coarse on Windows -- ~15.6 ms before
        Python 3.13 -- but that is per-point jitter, not bias, and fit_clock()
        averages it out over a run.
        """
        t0 = time.time_ns()
        ctr = self.snap_counter()
        t1 = time.time_ns()
        return (t0 + t1) // 2, ctr

    def status(self):
        """Read the status bits as a dict (handy during bring-up)."""
        g = self.dev.get_register
        return {
            'ready':      g('trig_logger', 'ready',      raw=True),
            'ready_buf':  g('trig_logger', 'ready_buf',  raw=True),
            'busy':       g('trig_logger', 'busy',       raw=True),
            'avg_ready':  g('trig_logger', 'avg_ready',  raw=True),
            'trig_level': g('trig_logger', 'trig_level', raw=True),
            'events':     self.total_events(),
            'dropped':    self.dropped(),
            'skipped':    self.skipped(),
            'energy_now': g('trig_logger', 'energy_now'),
            'dir_now':    self.dir_now(),
        }

    def dropped(self):
        """Records lost because both BRAM buffers were full (host too slow)."""
        return self.dev.get_register('trig_logger', 'dropped', raw=True)

    def skipped(self):
        """Triggers ignored: arrived during n_delay / trig_dead, or before the
        boxcar window was primed. Not a host problem -- a rate problem."""
        return self.dev.get_register('trig_logger', 'skipped', raw=True)

    def total_events(self):
        lo = self.dev.get_register('trig_logger', 'events_lo', raw=True)
        hi = self.dev.get_register('trig_logger', 'events_hi', raw=True)
        return (hi << 32) | lo

    def dir_now(self):
        """Live direction code decoded to -1 / 0 / +1."""
        code = self.dev.get_register('trig_logger', 'dir_now', raw=True)
        return {0: 0, 1: 1, 3: -1}.get(code, 0)

    # ----------------------------------------------------------------- drain
    def _drain_once(self):
        """CDMA one ready buffer to host. Returns raw bytes or None.
        Does NOT ack -- caller must ack after a durable write."""
        base = self.rp._to_int(
            self.dev.modules['trig_logger']['registers']['status']['base'])
        b = base
        c, d = self.cdma_addr, self.ddr_addr
        R_STATUS = 0x30
        R_COUNT  = 0x34
        script = f"""sh -lc '
ST=$({self.mon} $(({b}+{R_STATUS})))
if [ $((ST & 0x1)) -eq 0 ]; then echo NOTREADY; exit 0; fi
BUF=$(( (ST>>1) & 1 ))
CNT=$({self.mon} $(({b}+{R_COUNT})))
N=$((CNT * 8))
SA=$(( {self.bram_addr} + BUF * {self.frame_len} * 8 ))
{self.mon} $(({c}+0x00)) 4 >/dev/null
{self.mon} $(({c}+0x00)) 0 >/dev/null
{self.mon} $(({c}+0x18)) $SA >/dev/null
{self.mon} $(({c}+0x20)) {d} >/dev/null
{self.mon} $(({c}+0x28)) $N >/dev/null
for i in $(seq 1 100000); do
    CST=$({self.mon} $(({c}+0x04)))
    [ $((CST & 0x2)) -ne 0 ] && break
    [ $((CST & 0x10)) -ne 0 ] && echo "ERROR: CDMA error $CST" >&2 && exit 1
done
dd if=/dev/mem bs=$N count=1 iflag=skip_bytes skip={d} 2>/dev/null | base64
'"""
        out = self.rp._sh(script).strip()
        if out == "" or out.startswith("NOTREADY"):
            return None
        return base64.b64decode(out)

    def _ack(self):
        self.dev.set_register('trig_logger', 'ack', 1, raw=True)
        self.dev.set_register('trig_logger', 'ack', 0, raw=True)

    def run(self, duration=None, output_dir="events", tie_period_s=1.0,
            idle_sleep_s=0.001, verbose=True):
        """Continuous acquisition. Ctrl+C stops gracefully.

        duration: seconds, or None for infinite.
        Output: output_dir/events_YYYYMMDD_HH.bin + tiepoints.csv
        """
        os.makedirs(output_dir, exist_ok=True)
        tp_path = os.path.join(output_dir, "tiepoints.csv")

        self.arm(clear=True)

        stop = [False]
        prev_handler = signal.getsignal(signal.SIGINT)
        def _handler(sig, frame):
            stop[0] = True
        signal.signal(signal.SIGINT, _handler)

        t_end    = (time.time() + duration) if duration else float('inf')
        next_tie = time.time()
        n_rec    = 0
        cur_key  = None
        ef       = None

        tf = open(tp_path, 'a')
        if tf.tell() == 0:
            tf.write("# host_unix_ns,fpga_counter_cycles\n"); tf.flush()
        try:
            while time.time() < t_end and not stop[0]:
                if time.time() >= next_tie:
                    host_ns, ctr = self.tie_point()
                    tf.write(f"{host_ns},{ctr}\n"); tf.flush(); os.fsync(tf.fileno())
                    next_tie += tie_period_s

                data = self._drain_once()
                if data:
                    key = time.strftime("%Y%m%d_%H", time.localtime())
                    if key != cur_key:
                        if ef: ef.close()
                        ef = open(os.path.join(output_dir, f"events_{key}.bin"), 'ab')
                        cur_key = key
                    ef.write(data); ef.flush(); os.fsync(ef.fileno())
                    self._ack()
                    n_rec += len(data) // 8
                else:
                    time.sleep(idle_sleep_s)
        finally:
            if ef: ef.close()
            tf.close()
            self.disarm()
            signal.signal(signal.SIGINT, prev_handler)

        if verbose:
            print(f"Logged {n_rec} records, "
                  f"dropped={self.dropped()}, skipped={self.skipped()}")
        return n_rec


# ---------------------------------------------------------------- offline tools
def fit_clock(tiepoint_path, tick_ns=TICK_NS):
    """Fit host_unix_ns = a + b*counter. Returns (a, b, ppm).

    b is ns per counter tick; nominally tick_ns (8.0 at 125 MHz), so ppm is the
    crystal's fractional error against the host's NTP-disciplined clock.
    """
    data = np.loadtxt(tiepoint_path, delimiter=',', comments='#')
    ctr, host_ns = data[:, 1], data[:, 0]
    b, a = np.polyfit(ctr, host_ns, 1)
    ppm = (b / tick_ns - 1.0) * 1e6
    return a, b, ppm


def counter_to_unix(counter_cycles, a, b):
    """Map an FPGA cycle count -> absolute UNIX time (seconds).

    Pass counts through unwrap_ts() first for runs longer than 6.5 days.
    """
    return (a + b * np.asarray(counter_cycles, dtype=float)) / 1e9


def load_run(events_glob):
    """Load hourly record files, concatenate, dedup restarts."""
    import glob
    u = [np.fromfile(f, dtype='<u8') for f in sorted(glob.glob(events_glob))]
    u = np.concatenate(u) if u else np.zeros(0, dtype='<u8')
    if u.size:
        keep = np.ones(u.size, dtype=bool)
        keep[1:] = u[1:] != u[:-1]
        u = u[keep]
    return u
