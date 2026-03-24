from redpitaya_dev import redpitaya_dev
import time
import numpy as np
import matplotlib.pyplot as plt

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/stream_bram_4ch.json")
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\test\\test.runs\\impl_1\\system_wrapper.bit'
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_bram_4ch\\stream_bram_4ch.runs\\impl_1\\system_wrapper.bit'

dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_cdma_4ch\\stream_cdma_4ch.runs\\impl_1\\system_wrapper.bit'

dev.base.load_bitfile()

# Configure capture parameters
frame_len = 1024
log_div = 0  # No decimation

dev.set_register('stream4ch', 'frame_len', frame_len)
dev.set_register('stream4ch', 'log_div', log_div)
dev.set_register('stream4ch', 'ack', 0)

print(f"Configuration:")
print(f"  Frame length: {frame_len} samples")
print(f"  Decimation: {2**log_div}")

# Arm capture
dev.set_register('stream4ch', 'arm', 1)
print(f"\nArmed capture...")

# Wait for ready
print("Waiting for capture to complete...")
for i in range(100):
    status = int(dev.get_register('stream4ch', 'status'))
    ready = status & 0x01
    wr_idx = (status >> 11) & 0x7FF
    
    if ready:
        print(f"  Capture complete! Write Index: {wr_idx}")
        break
    time.sleep(0.01)
else:
    print("  ERROR: Capture timeout!")
    exit(1)

# Read BRAM data directly via monitor loop
print("\nReading BRAM via monitor loop...")

# Get addresses from config
bram_base = int(dev.modules['stream4ch']['bram']['base'], 16)
num_samples = frame_len
num_words = num_samples * 2  # Each 64-bit sample = 2 x 32-bit words

print(f"  BRAM address: 0x{bram_base:08X}")
print(f"  Reading {num_words} words ({num_samples} samples)...")

# Read BRAM using shell loop (faster than Python loop)
start_time = time.time()

cmd = f"""sh -lc '
BRAM=0x{bram_base:X}
NWORDS={num_words}

for i in $(seq 0 $((NWORDS-1))); do
    ADDR=$((BRAM + i * 4))
    /opt/redpitaya/bin/monitor $ADDR
done
'"""

result = dev.base._sh(cmd)
elapsed = time.time() - start_time

# Parse the monitor output (one hex value per line)
values = []
for line in result.strip().split('\n'):
    if line.startswith('0x'):
        values.append(int(line, 16))

# Convert to bytes (little-endian)
raw_data = []
for word in values:
    raw_data.extend([
        word & 0xFF,
        (word >> 8) & 0xFF,
        (word >> 16) & 0xFF,
        (word >> 24) & 0xFF
    ])
raw_data = bytes(raw_data)

print(f"  Read complete in {elapsed*1000:.1f} ms ({len(raw_data)} bytes)")

# Show first few bytes
print(f"\nFirst 32 bytes:")
for i in range(0, min(32, len(raw_data)), 8):
    chunk = raw_data[i:i+8]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    print(f"  [{i:3d}] {hex_str}")

# Convert bytes to 64-bit samples (little-endian)
data = np.frombuffer(raw_data, dtype='<u8')

# Unpack 64-bit samples: {in3[63:48], in2[47:32], in1[31:16], in0[15:0]}
in0 = ((data & 0xFFFF).astype(np.int16))
in1 = (((data >> 16) & 0xFFFF).astype(np.int16))
in2 = (((data >> 32) & 0xFFFF).astype(np.int16))
in3 = (((data >> 48) & 0xFFFF).astype(np.int16))

print(f"\nFirst sample:")
print(f"  in0[0] = {in0[0]:6d}")
print(f"  in1[0] = {in1[0]:6d}")
print(f"  in2[0] = {in2[0]:6d}")
print(f"  in3[0] = {in3[0]:6d}")

# Acknowledge frame
dev.set_register('stream4ch', 'ack', 1)
time.sleep(0.001)
dev.set_register('stream4ch', 'ack', 0)

# Display results
print(f"\nData Summary:")
print(f"  in0 range: [{in0.min():6d}, {in0.max():6d}]")
print(f"  in1 range: [{in1.min():6d}, {in1.max():6d}]")
print(f"  in2 range: [{in2.min():6d}, {in2.max():6d}]")
print(f"  in3 range: [{in3.min():6d}, {in3.max():6d}]")

# Plot channels
fig, axes = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
channels = [in0, in1, in2, in3]
labels = ['Channel 0', 'Channel 1', 'Channel 2', 'Channel 3']
colors = ['blue', 'green', 'red', 'orange']

for ax, ch, label, color in zip(axes, channels, labels, colors):
    ax.plot(ch, color=color, linewidth=0.5)
    ax.set_ylabel(f'{label} [ADC]')
    ax.grid(True, alpha=0.3)
    ax.set_ylim([-8192, 8192])  # 14-bit ADC range

axes[-1].set_xlabel('Sample')
axes[0].set_title(f'4-Channel BRAM Capture ({frame_len} samples, {elapsed*1000:.1f} ms read time)')
plt.tight_layout()
plt.show()
