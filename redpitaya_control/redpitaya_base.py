# rp_min.py  — minimal Red Pitaya helper

import os, time, paramiko
import base64
import numpy as np

class redpitaya_base:
    def __init__(self, host, bitfile, user='root', pwd='root'):
        self.host   = host
        self.bitfile = os.path.abspath(bitfile)
        self.user   = user
        self.pwd    = pwd
        self.ssh    = None

    # --- connection ---
    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.host, username=self.user, password=self.pwd)

    def disconnect(self):
        if self.ssh:
            self.ssh.close()
            self.ssh = None

    # --- bitfile programming ---
    def load_bitfile(self, remote='/root/fpga.bit'):
        sftp = self.ssh.open_sftp()
        sftp.put(self.bitfile, remote)
        sftp.close()
        self._sh(f"cat {remote} > /dev/xdevcfg")
        time.sleep(0.1)

    # --- low-level monitor helpers ---
    def read_word(self, addr):
        """Read 32-bit word at absolute address (int or hex-string)."""
        a = self._to_int(addr)
        out = self._sh(f"/opt/redpitaya/bin/monitor {hex(a)}")
        return int(out.strip(), 16)

    def read_words(self, addr, count):
        """Read multiple 32-bit words starting at address. Returns list of ints."""
        a = self._to_int(addr)
        cmd = f"sh -lc 'for i in $(seq 0 {count-1}); do /opt/redpitaya/bin/monitor $((0x{a:x} + i*4)); done'"
        out = self._sh(cmd)
        # Parse output: one hex value per line
        lines = out.strip().split('\n')
        return [int(line.strip(), 16) for line in lines if line.strip()]

    def write_word(self, addr, value):
        """Write 32-bit word at absolute address (int or hex-string)."""
        a = self._to_int(addr)
        v = self._to_int(value)
        self._sh(f"/opt/redpitaya/bin/monitor {hex(a)} {hex(v)}")

    def read_bram_fast(self, bram_addr, cdma_addr, ddr_addr, num_bytes, local_file='/tmp/frame.bin'):
        """
        Fast BRAM read using CDMA: BRAM -> DDR -> local file.
        
        Args:
            bram_addr: Source BRAM address (e.g., 0xC0000000)
            cdma_addr: CDMA controller address (e.g., 0x7E200000)
            ddr_addr: Target DDR address (e.g., 0x10000000)
            num_bytes: Number of bytes to transfer
            local_file: Local file path to save data (default: /tmp/frame.bin)
        
        Returns:
            bytes: Raw data read from DDR
        """
        cmd = f"""sh -lc '
CDMA=0x{cdma_addr:X}
SA=0x{bram_addr:X}
DA=0x{ddr_addr:X}
N={num_bytes}

# Soft reset CDMA to clear any error flags
/opt/redpitaya/bin/monitor $((CDMA+0x00)) 4 >/dev/null
usleep 1000
/opt/redpitaya/bin/monitor $((CDMA+0x00)) 0 >/dev/null

# Configure source and destination
/opt/redpitaya/bin/monitor $((CDMA+0x18)) $SA >/dev/null
/opt/redpitaya/bin/monitor $((CDMA+0x20)) $DA >/dev/null

# Start transfer (write BTT)
/opt/redpitaya/bin/monitor $((CDMA+0x28)) $N >/dev/null

# Poll for completion (don't exit on error bit 12, data might still be valid)
for i in $(seq 1 2000); do
    ST=$(/opt/redpitaya/bin/monitor $((CDMA+0x04)))
    [ $((ST & 0x2)) -ne 0 ] && break
    usleep 500
done

# Read from DDR to file (even if error bit set, data might be valid)
dd if=/dev/mem of={local_file} bs=$N count=1 iflag=skip_bytes skip=$DA 2>/dev/null
'"""
        result = self._sh(cmd)
        
        # Download file via SFTP
        sftp = self.ssh.open_sftp()
        local_temp = local_file.replace('/tmp/', 'temp_')
        sftp.get(local_file, local_temp)
        sftp.close()
        
        # Read data
        with open(local_temp, 'rb') as f:
            data = f.read()
        
        # Cleanup
        os.remove(local_temp)
        
        return data

    def setup_cdma(self, stream_base, bram_addr, cdma_addr, ddr_addr, frame_len=1024, sampling_frequency=125e6):
        """
        Configure CDMA and stream module for fast acquisition.
        
        Args:
            stream_base: Base address of stream4ch module (e.g., 0x40000000)
            bram_addr: BRAM address (e.g., 0x41000000)
            cdma_addr: CDMA controller address (e.g., 0x7E200000)
            ddr_addr: DDR target address (e.g., 0x10000000)
            frame_len: Number of samples per frame (default: 1024)
            sampling_frequency: Desired sampling frequency in Hz (default: 125 MHz)
        
        Returns:
            dict: Configuration with actual_frequency, acquisition_time, log_div, byte_count
        """
        
        # Calculate log_div for desired sampling frequency
        # Actual frequency = 125 MHz / 2^log_div
        import math
        log_div = int(round(math.log2(125e6 / sampling_frequency)))
        log_div = max(0, min(31, log_div))  # Clamp to valid range
        
        actual_frequency = 125e6 / (2**log_div)
        acquisition_time = frame_len * (2**log_div) / 125e6
        byte_count = frame_len * 8  # 4 channels × 16-bit each = 64-bit per sample
        
        # Disarm first so config registers are writable (they lock while arm=1)
        self.write_word(stream_base + 0x08, 0)          # arm register (clear BEFORE config)
        self.write_word(stream_base + 0x0C, 1)          # pulse ack to flush any pending state
        self.write_word(stream_base + 0x0C, 0)
        # Now safe to write config registers
        self.write_word(stream_base + 0x00, frame_len)  # frame_len register
        self.write_word(stream_base + 0x04, log_div)    # log_div register

        # Verify register writes landed (catches wrong bitfile / address mismatch)
        rb_frame_len = self.read_word(stream_base + 0x00) & 0xFFF
        rb_log_div   = self.read_word(stream_base + 0x04) & 0xFF
        if rb_frame_len != frame_len or rb_log_div != log_div:
            raise RuntimeError(
                f"setup_cdma: register readback mismatch "
                f"(frame_len wrote {frame_len} got {rb_frame_len}, "
                f"log_div wrote {log_div} got {rb_log_div}). "
                f"Is the correct bitfile loaded?"
            )

        # Configure CDMA (soft reset, clear, set addresses)
        self._sh(f'''
/opt/redpitaya/bin/monitor {cdma_addr:#x} 4         # Soft reset
/opt/redpitaya/bin/monitor {cdma_addr:#x} 0         # Clear reset
/opt/redpitaya/bin/monitor {cdma_addr + 0x18:#x} {bram_addr:#x}  # Source = BRAM
/opt/redpitaya/bin/monitor {cdma_addr + 0x20:#x} {ddr_addr:#x}   # Dest = DDR
''')
        
        # Store configuration for read_cdma_frame
        self._cdma_config = {
            'stream_base': stream_base,
            'cdma_addr': cdma_addr,
            'ddr_addr': ddr_addr,
            'byte_count': byte_count,
            'acquisition_time': acquisition_time,
            'actual_frequency': actual_frequency,
            'log_div': log_div,
            'frame_len': frame_len
        }
        
        return {
            'actual_frequency': actual_frequency,
            'acquisition_time': acquisition_time,
            'log_div': log_div,
            'byte_count': byte_count
        }

    def read_cdma_frame(self):
        """
        Read one frame using CDMA (fast method).
        Requires setup_cdma() to be called first.
        
        Returns:
            numpy.ndarray: Raw 64-bit unsigned integers from BRAM
        """
        if not hasattr(self, '_cdma_config'):
            raise RuntimeError("Must call setup_cdma() before read_cdma_frame()")
        
        cfg = self._cdma_config
        stream_base = cfg['stream_base']
        cdma_addr = cfg['cdma_addr']
        ddr_addr = cfg['ddr_addr']
        byte_count = cfg['byte_count']
        acquisition_time = cfg['acquisition_time']
        
        # Shell does smart waiting based on acquisition time
        need_wait = 1 if acquisition_time > 0.001 else 0
        
        # Timeout in loop iterations: status poll ~1ms each, CDMA poll ~0.1ms each
        acq_timeout_iters = max(5000, int(acquisition_time / 0.001) * 10)
        cdma_timeout_iters = max(50000, int(byte_count / 100))

        result = self._sh(f'''
# Arm capture
/opt/redpitaya/bin/monitor {stream_base + 0x08:#x} 1

# Wait for ready only if needed (slow acquisition)
if [ {need_wait} -eq 1 ]; then
    N=0
    while true; do
        ST=$(/opt/redpitaya/bin/monitor {stream_base + 0x1C:#x})
        [ $((ST & 0x1)) -ne 0 ] && break
        N=$((N+1))
        [ $N -ge {acq_timeout_iters} ] && echo "ERROR: status poll timeout" >&2 && exit 1
        sleep 0.001
    done
fi

# Start CDMA transfer (write BTT)
/opt/redpitaya/bin/monitor {cdma_addr + 0x28:#x} {byte_count}

# Wait for CDMA to complete (poll status register bit 1 = idle)
N=0
while true; do
    CDMA_ST=$(/opt/redpitaya/bin/monitor {cdma_addr + 0x04:#x})
    [ $((CDMA_ST & 0x2)) -ne 0 ] && break
    [ $((CDMA_ST & 0x10)) -ne 0 ] && echo "ERROR: CDMA error bit set (status=$CDMA_ST)" >&2 && exit 1
    N=$((N+1))
    [ $N -ge {cdma_timeout_iters} ] && echo "ERROR: CDMA completion timeout" >&2 && exit 1
    sleep 0.0001
done

# Read DDR and output as base64
dd if=/dev/mem bs={byte_count} count=1 iflag=skip_bytes skip={ddr_addr} 2>/dev/null | base64

# Acknowledge frame
/opt/redpitaya/bin/monitor {stream_base + 0x0C:#x} 1
/opt/redpitaya/bin/monitor {stream_base + 0x0C:#x} 0
''')
        
        # Decode base64 to binary and return raw 64-bit data
        raw_data = base64.b64decode(result.strip())
        data = np.frombuffer(raw_data, dtype='<u8')
        
        return data

    # --- field-level convenience (base+offset+bit slice) ---
    def read_reg(self, base, offset, msb=31, lsb=0, signed=False):
        """
        Read a bitfield from base+offset.
        base/offset can be int or hex-string like '0x40000000'.
        """
        addr = self._to_int(base) + self._to_int(offset)
        word = self.read_word(addr)
        width = msb - lsb + 1
        field = (word >> lsb) & ((1 << width) - 1)
        if signed and (field & (1 << (width - 1))):
            field -= (1 << width)
        return field

    def write_reg(self, base, offset, msb=31, lsb=0, value=0):
        """
        Write a bitfield into base+offset (read-modify-write).
        """
        addr = self._to_int(base) + self._to_int(offset)
        word = self.read_word(addr)
        width = msb - lsb + 1
        # insert field
        mask = ((1 << width) - 1) << lsb
        neww = (word & ~mask) | (((int(value) & ((1 << width) - 1)) << lsb) & mask)
        self.write_word(addr, neww)

    # --- internals ---
    def _sh(self, cmd):
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        stdout.channel.close()
        # Only raise on explicit ERROR markers written by our shell scripts
        for line in err.splitlines():
            if line.strip().startswith("ERROR:"):
                raise RuntimeError(f"Remote: {line.strip()}")
        return out

    @staticmethod
    def _to_int(x):
        if isinstance(x, int): return x
        s = str(x).lower().strip()
        return int(s, 16) if s.startswith('0x') else int(s)
    

if __name__ == "__main__":

    rp = redpitaya_base("171.64.56.58", "../bitfiles/pid_simple_axi_2ch.bit")
    rp.connect()
    rp.load_bitfile()

    print(rp.read_reg(0x40000000, 4, 31, 0, True))
    rp.write_reg(0x40000000, 4, 31, 0, 123456)
