from redpitaya_control.redpitaya_dev import redpitaya_dev
import time
import numpy as np
import matplotlib.pyplot as plt

# Connect
dev = redpitaya_dev("171.64.56.117", "config/stream_cdma_8ch.json")
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_cdma_4ch\\stream_cdma_4ch.runs\\impl_1\\system_wrapper.bit'
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\z_control_v4_stream\\z_control_v4_stream.runs\\impl_1\\system_wrapper.bit'

dev.base.load_bitfile()

# Setup
frame_len = 1024
byte_count = frame_len * 8
bram_addr = 0x42000000
cdma_addr = 0x7E200000
ddr_addr = 0x10000000

dev.set_register('stream8ch', 'frame_len', frame_len)
log_div = 1  # 0 = 125 MHz, 1 = 62.5 MHz, etc. (divider = 2^log_div)
dev.set_register('stream8ch', 'log_div', log_div)
dev.set_register('stream8ch', 'ack', 0)

# Calculate expected acquisition time
acquisition_time = frame_len * (2**log_div) / 125e6  # seconds
print(f"Acquisition time: {acquisition_time*1000:.3f} ms (log_div={log_div})")

# Only poll status if acquisition takes longer than a threshold
NEED_STATUS_POLL = (acquisition_time > 0.001)  # Poll if >1ms acquisition time

# Configure CDMA once (addresses don't change between frames)
print("Configuring CDMA...")
dev.base._sh(f'''
/opt/redpitaya/bin/monitor {cdma_addr:#x} 4         # Soft reset
/opt/redpitaya/bin/monitor {cdma_addr:#x} 0         # Clear reset
/opt/redpitaya/bin/monitor {cdma_addr + 0x18:#x} {bram_addr:#x}  # Source = BRAM
/opt/redpitaya/bin/monitor {cdma_addr + 0x20:#x} {ddr_addr:#x}   # Dest = DDR
''')

print(f"Starting continuous acquisition loop ({frame_len} samples per frame)...")
print("Press Ctrl+C to stop.\n")

# Control parameter
SLEEP_TIME = 0.0  # seconds between frames (testing sweet spot)

# Setup interactive plot with blitting for speed
plt.ion()
fig, axes = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
fig.canvas.manager.set_window_title('Live ADC Data - Fast Mode')
lines = []
backgrounds = []

x = np.arange(frame_len)
for ax, label, color in zip(axes, ['Ch0', 'Ch1', 'Ch2', 'Ch3'], 
                             ['blue', 'green', 'red', 'orange']):
    line, = ax.plot(x, np.zeros(frame_len), color=color, linewidth=0.5, animated=True)
    lines.append(line)
    ax.set_ylabel(f'{label} [ADC]')
    ax.set_ylim([-8192, 8192])
    ax.set_xlim([0, frame_len])
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel('Sample')
title_text = fig.suptitle('', fontsize=12)
plt.tight_layout()
plt.show(block=False)

# Draw initial plot and cache background (for blitting)
fig.canvas.draw()
fig.canvas.flush_events()
background = fig.canvas.copy_from_bbox(fig.bbox)

# Statistics
frame_count = 0
start_time = time.time()
frame_times = []

try:
    while True:
        frame_start = time.time()
        
        # Arm capture, CDMA transfer, and output binary data directly
        if NEED_STATUS_POLL:
            # Slow acquisition - need to wait for ready
            result = dev.base._sh(f'''
# Arm capture
/opt/redpitaya/bin/monitor 0x40000008 1

# Wait for ready
while true; do
    ST=$(/opt/redpitaya/bin/monitor 0x4000001C)
    [ $((ST & 0x1)) -ne 0 ] && break
    sleep 0.001
done

# Start CDMA transfer (just write BTT register)
/opt/redpitaya/bin/monitor {cdma_addr + 0x28:#x} {byte_count}

# Read DDR and output as base64
dd if=/dev/mem bs={byte_count} count=1 iflag=skip_bytes skip={ddr_addr} 2>/dev/null | base64

# Acknowledge frame
/opt/redpitaya/bin/monitor 0x4000000C 1
/opt/redpitaya/bin/monitor 0x4000000C 0
''')
        else:
            # Fast acquisition - data ready by the time we get here
            result = dev.base._sh(f'''
# Arm capture
/opt/redpitaya/bin/monitor 0x40000008 1

# Start CDMA transfer (just write BTT register - triggers transfer)
/opt/redpitaya/bin/monitor {cdma_addr + 0x28:#x} {byte_count}

# Read DDR and output as base64
dd if=/dev/mem bs={byte_count} count=1 iflag=skip_bytes skip={ddr_addr} 2>/dev/null | base64

# Acknowledge frame
/opt/redpitaya/bin/monitor 0x4000000C 1
/opt/redpitaya/bin/monitor 0x4000000C 0
''')
        
        # Decode base64 output to get binary data
        import base64
        raw_data = base64.b64decode(result.strip())
        
        data = np.frombuffer(raw_data, dtype='<u8')
        
        # Parse data
        in0 = ((data & 0xFFFF).astype(np.int16))
        in1 = (((data >> 16) & 0xFFFF).astype(np.int16))
        in2 = (((data >> 32) & 0xFFFF).astype(np.int16))
        in3 = (((data >> 48) & 0xFFFF).astype(np.int16))
        
        frame_time = time.time() - frame_start
        frame_count += 1
        frame_times.append(frame_time)
        
        # Keep last 100 frames for average
        if len(frame_times) > 100:
            frame_times.pop(0)
        
        # Statistics
        avg_time = np.mean(frame_times)
        avg_rate = 1.0 / avg_time
        inst_rate = 1.0 / frame_time
        elapsed = time.time() - start_time
        overall_rate = frame_count / elapsed
        
        # Update plot using blitting (MUCH faster - only redraw lines, not whole figure)
        fig.canvas.restore_region(background)
        
        for line, ch in zip(lines, [in0, in1, in2, in3]):
            line.set_ydata(ch)
            ax = line.axes
            ax.draw_artist(line)
        
        # Update title (not blitted, but fast enough)
        title_text.set_text(f'Frame {frame_count} | This: {frame_time*1000:.1f} ms ({inst_rate:.1f} Hz) | '
                           f'Avg: {avg_time*1000:.1f} ms ({avg_rate:.1f} Hz) | Overall: {overall_rate:.2f} Hz')
        
        # Blit just the changed parts
        fig.canvas.blit(fig.bbox)
        fig.canvas.flush_events()
        
        # Print status every 10 frames
        if frame_count % 10 == 0:
            print(f"Frame {frame_count:4d} | This: {frame_time*1000:5.1f} ms ({inst_rate:4.1f} Hz) | "
                  f"Avg: {avg_time*1000:5.1f} ms ({avg_rate:4.1f} Hz) | "
                  f"Overall: {overall_rate:4.2f} Hz | "
                  f"Data: [{in0.min():6d}, {in0.max():6d}]")
        
        # Controlled sleep for testing
        if SLEEP_TIME > 0:
            time.sleep(SLEEP_TIME)

except KeyboardInterrupt:
    print("\n\nStopped by user.")
finally:
    plt.ioff()

# Final statistics
print(f"\nFinal Statistics:")
print(f"  Total frames: {frame_count}")
print(f"  Total time: {time.time() - start_time:.1f} s")
print(f"  Average rate: {frame_count / (time.time() - start_time):.2f} Hz")
if frame_times:
    print(f"  Average frame time: {np.mean(frame_times)*1000:.1f} ms")

# Keep final plot open
plt.show()
