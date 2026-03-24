from python_rp.redpitaya_dev import redpitaya_dev
from python_rp.compute_coeff import *
import time

# Connect to Red Pitaya

#dev = redpitaya_dev("171.64.56.120", "config/iir2nd_coupled_axi_2ch.json")
dev = redpitaya_dev("171.64.56.120", "config/iir2nd_coupled_2ch_stream.json")
dev.base.bitfile = r'C:\Users\magrini\Documents\programming\redpitaya\projects\iir2nd_coupled_2ch_stream\iir2nd_coupled_2ch_stream.runs\impl_1\system_wrapper.bit'

#dev.base.load_bitfile()

# Configure IIR filter coefficients
f0 = 1000  # 1 kHz notch frequency
Q = 10      # Quality factor

# Calculate coefficients for coupled IIR
coeffs = coupled_oscillator(f0, Q, gainI=-1, gainQ=0, Ts=8.192e-6)


dev.set_all_registers('filt0', coeffs, reset=True)

# Set all registers for IIR module
dev.set_all_registers('filt0', coeffs, reset=True)

print("IIR2nd Coupled Filter Configured:")
print(f"  Notch frequency: {f0/1e3:.1f} kHz")
print(f"  Q factor: {Q}")


# Read back configuration
print("\nRegister values:")
print(dev.get_all_registers('filt0'))
print("\nFilter ready!")
