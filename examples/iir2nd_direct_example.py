from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control.compute_coeff import *
import time

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/iir2nd_direct_axi_2ch.json")
dev.base.load_bitfile()

# Configure IIR filter coefficients
# Example: 10 kHz lowpass filter
f0 = 1e3   # 10 kHz cutoff frequency
Q = 10   # Butterworth response

# Calculate coefficients for direct form IIR
coeffs =iir_oscillator(f0, Q, gain=1, Ts=8.192e-6, response='I')

# Set all registers for IIR module
dev.set_all_registers('filt0', coeffs, reset=True)

print("IIR2nd Direct Form Filter Configured:")
print(f"  Lowpass cutoff: {f0/1e3:.1f} kHz")
print(f"  Q factor: {Q}")

# Read back configuration
print("\nRegister values:")
print(dev.get_all_registers('filt0'))
print("\nFilter ready!")
