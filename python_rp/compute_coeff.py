
import numpy as np
from scipy.signal import bilinear, butter

def pid_simple(setpoint=0, Kp=0, Ki=0, Kd=0, d_lpf=1e6, gain=1.0, Ts=8.192e-6):
    """Return raw PID coefficients (no scaling)."""
    Kp_d = float(Kp)
    Ki_d = float(Ki) * Ts
    Kd_d = float(Kd) / Ts
    alpha_d = np.exp(-2 * np.pi * d_lpf * Ts)
    return { "setpoint": setpoint, "Kp": Kp_d, "Ki": Ki_d, "Kd": Kd_d, "alpha_d": alpha_d, "gain": gain}


def lowpass(frequency, order=2, gain=1.0, Ts=8.192e-6):
    sf = 1 / Ts
    nyquist = sf / 2
    b, a = butter(order, frequency / nyquist, btype='low')
    return { "b0": b[0], "b1": b[1], "b2": b[2], "a1": a[1], "a2": a[2], "gain": gain }

def highpass_1st(frequency, Ts=8.192e-6):
    sf = 1 / Ts
    nyquist = sf / 2
    b, a = butter(1, frequency / nyquist, btype='high')
    return { "b0": b[0], "b1": b[1], "a1": a[1]}

def lowpass_1st(frequency, Ts=8.192e-6):
    sf = 1 / Ts
    nyquist = sf / 2
    b, a = butter(1, frequency / nyquist, btype='low')
    return { "b0": b[0], "b1": b[1], "a1": a[1]}

def highpass(frequency, order=2, gain=1.0, Ts=8.192e-6):
    sf = 1 / Ts
    nyquist = sf / 2
    b, a = butter(order, frequency / nyquist, btype='high')
    return { "b0": b[0], "b1": b[1], "b2": b[2], "a1": a[1], "a2": a[2], "gain": gain }

def bandpass(center_frequency, bandwidth, order=2, gain=1.0, Ts=8.192e-6):
    sf = 1 / Ts
    nyquist = sf / 2
    low_freq = center_frequency - bandwidth / 2
    high_freq = center_frequency + bandwidth / 2
    b, a = butter(order, [low_freq / nyquist, high_freq / nyquist], btype='band')
    return { "b0": b[0], "b1": b[1], "b2": b[2], "a1": a[1], "a2": a[2], "gain": gain }

def notch(frequency, Q, gain=1.0, Ts=8.192e-6):
    sf = 1 / Ts
    omega_0 = 2 * np.pi * frequency
    num = np.array([1, 0, omega_0**2])
    den = np.array([1, omega_0/Q, omega_0**2])
    b, a = bilinear(num, den, sf)
    return { "b0": b[0], "b1": b[1], "b2": b[2], "a1": a[1], "a2": a[2], "gain": gain }

def iir_oscillator(frequency, Q, gain=1.0, Ts=8.192e-6, response='Q'):
    sf = 1 / Ts
    omega_0 = 2 * np.pi * frequency 
    
    if response == 'Q':
        # Quadrature (90 degree phase shift) response: s transfer function
        num = np.array([omega_0**2]) / Q * np.sqrt(2)
    else:  # In-phase
        # In-phase response: constant transfer function
        num = np.array([0, omega_0, 0]) / Q * np.sqrt(2)
    
    den = np.array([1, np.sqrt(2) * omega_0 / Q, omega_0**2])
    b, a = bilinear(num, den, sf)

    return { "b0": b[0], "b1": b[1], "b2": b[2], "a1": a[1], "a2": a[2], "gain": gain }


def coupled_oscillator(frequency, Q, gainI=1.0, gainQ=1.0, Ts=8.192e-6):
    sf = 1 / Ts
    omega = 2 * np.pi * frequency / sf
    r = np.exp(-np.pi * frequency / (Q * sf))
    alpha = r * np.cos(omega)
    beta = r * np.sin(omega)

    return {"alpha": alpha, "beta": beta, "gainI": gainI, "gainQ": gainQ}