from redpitaya_dev import redpitaya_dev
import time

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/stream_axibram_4ch.json")
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_axibram_4ch\\stream_axibram_4ch.runs\\impl_1\\system_wrapper.bit'
dev.base.load_bitfile()

# Get addresses from config
bram_base = int(dev.modules['stream4ch']['bram']['base'], 16)
cdma_base = int(dev.modules['stream4ch']['cdma']['base'], 16)
ddr_target = int(dev.modules['stream4ch']['cdma']['ddr_target'], 16)
bram_size = dev.modules['stream4ch']['bram']['size']

print(f"Address Map:")
print(f"  BRAM:   0x{bram_base:08X}")
print(f"  CDMA:   0x{cdma_base:08X}")
print(f"  DDR:    0x{ddr_target:08X}")
print(f"  Size:   {bram_size} bytes")
print()


# Test 1: Read BRAM directly with monitor
print("="*60)
print("Test 1: BRAM Read via monitor (GP0 bus)")
print("="*60)

cmd = f"""sh -lc '
BRAM=0x{bram_base:X}

echo "Reading first 16 words (64 bytes = 8 samples) from BRAM:"
for i in $(seq 0 15); do
    ADDR=$((BRAM + i * 4))
    VAL=$(/opt/redpitaya/bin/monitor $ADDR 2>&1)
    printf "  [0x%08X] = %s\n" $ADDR "$VAL"
done
'"""

start_time = time.time()
result = dev.base._sh(cmd)
elapsed = time.time() - start_time
print(result)
print(f"Time: {elapsed*1000:.1f} ms\n")

# Test 2: Read DDR directly
print("="*60)
print("Test 2: DDR Read via /dev/mem")
print("="*60)

cmd = f"""sh -lc '
DA=0x{ddr_target:X}
N=64

echo "Reading first 64 bytes from DDR at 0x$DA:"
dd if=/dev/mem of=/tmp/ddr_test.bin bs=$N count=1 iflag=skip_bytes skip=$DA status=none 2>&1
echo "First 64 bytes:"
hexdump -C /tmp/ddr_test.bin
'"""

start_time = time.time()
result = dev.base._sh(cmd)
elapsed = time.time() - start_time
print(result)
print(f"Time: {elapsed*1000:.1f} ms\n")

print("="*60)
print("RESULT:")
print("  - If BRAM shows data: BRAM accessible at new address!")
print("  - If DDR shows zeros: CDMA not transferring (source issue)")
print("  - If DDR shows data: CDMA working, check if matches BRAM")
print("="*60)
