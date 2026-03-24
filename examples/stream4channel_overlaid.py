from redpitaya_control.redpitaya_dev import redpitaya_dev
import time
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore
import sys
from scipy import signal

# Connect to Red Pitaya
title  = "X, Y QPD and feedback - Press Q to quit"
dev = redpitaya_dev("171.64.56.120", "config/iir2nd_coupled_2ch_stream.json")
dev = redpitaya_dev("171.64.56.120", "config/z_control_stream.json")

frame_len = 2048
sampling_frequency = 50e3  # 125 kHz

dev.base.load_bitfile()

# Setup parameters
# Configure CDMA using config file addresses
print("Configuring CDMA...")
config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=sampling_frequency)

actual_fs = config['actual_frequency']
print(f"Frame length: {frame_len} samples")
print(f"Sampling rate: {actual_fs / 1e6:.3f} MHz")
print(f"Acquisition time: {config['acquisition_time']*1000:.3f} ms")
print(f"Log_div: {config['log_div']}")

# Setup pyqtgraph application
app = QtWidgets.QApplication(sys.argv)

# Create main window with layout
main_widget = QtWidgets.QWidget()
main_widget.setWindowTitle(title)
main_widget.resize(1600, 600)
layout = QtWidgets.QVBoxLayout()
main_widget.setLayout(layout)

# Add averaging control
control_layout = QtWidgets.QHBoxLayout()
control_label = QtWidgets.QLabel("ASD Averaging (frames):")
averaging_input = QtWidgets.QLineEdit("10")
averaging_input.setMaximumWidth(100)
reset_avg_button = QtWidgets.QPushButton("Reset Averages")
reset_avg_button.setMaximumWidth(120)
control_layout.addWidget(control_label)
control_layout.addWidget(averaging_input)
control_layout.addWidget(reset_avg_button)
control_layout.addSpacing(20)

# Sampling frequency control with actual display below
sampling_layout = QtWidgets.QVBoxLayout()
sampling_control_layout = QtWidgets.QHBoxLayout()
sampling_label = QtWidgets.QLabel("Sampling Freq (Hz):")
sampling_input = QtWidgets.QLineEdit(str(sampling_frequency))
sampling_input.setMaximumWidth(100)
set_sampling_button = QtWidgets.QPushButton("Set Sampling Freq")
set_sampling_button.setMaximumWidth(130)
sampling_control_layout.addWidget(sampling_label)
sampling_control_layout.addWidget(sampling_input)
sampling_control_layout.addWidget(set_sampling_button)
actual_fs_display = QtWidgets.QLabel(f"Actual: {actual_fs/1e3:.3f} kHz")
sampling_layout.addLayout(sampling_control_layout)
sampling_layout.addWidget(actual_fs_display)
control_layout.addLayout(sampling_layout)
control_layout.addSpacing(20)

# Number of samples control with BW display below
nsamples_layout = QtWidgets.QVBoxLayout()
nsamples_control_layout = QtWidgets.QHBoxLayout()
nsamples_label = QtWidgets.QLabel("N Samples:")
nsamples_input = QtWidgets.QLineEdit(str(frame_len))
nsamples_input.setMaximumWidth(100)
set_nsamples_button = QtWidgets.QPushButton("Set N Samples")
set_nsamples_button.setMaximumWidth(120)
nsamples_control_layout.addWidget(nsamples_label)
nsamples_control_layout.addWidget(nsamples_input)
nsamples_control_layout.addWidget(set_nsamples_button)
bw_display = QtWidgets.QLabel(f"BW: {actual_fs/frame_len:.2f} Hz")
nsamples_layout.addLayout(nsamples_control_layout)
nsamples_layout.addWidget(bw_display)
control_layout.addLayout(nsamples_layout)
control_layout.addSpacing(20)

# Reset zoom button
reset_zoom_button = QtWidgets.QPushButton("Reset Zoom")
reset_zoom_button.setMaximumWidth(100)
control_layout.addWidget(reset_zoom_button)
control_layout.addStretch()

# Frame rate display (in settings row)
rate_display = QtWidgets.QLabel("Frame rate: -- Hz")
control_layout.addWidget(rate_display)
layout.addLayout(control_layout)

# Create graphics layout widget for plots
graphics_widget = pg.GraphicsLayoutWidget()
layout.addWidget(graphics_widget)

# Create 2 rows: even channels (In0, Out0), odd channels (In1, Out1)
# Each row has 2 columns: time trace (left), ASD (right)
colors = ['c', 'g', 'r', 'y']  # cyan, green, red, yellow
labels = ['In0', 'In1', 'Out0', 'Out1']
# Time axis in seconds
t_s = np.arange(frame_len) / actual_fs

time_curves = [None] * 4
asd_curves = [None] * 4

# Row 0: Even channels (In0, Out0)
p_time_even = graphics_widget.addPlot(row=0, col=0)
p_time_even.setLabel('left', 'Voltage', units='V')
p_time_even.setLabel('bottom', 'Time', units='s')
p_time_even.showGrid(x=True, y=True, alpha=0.3)
p_time_even.setYRange(-1.0, 1.0)
p_time_even.addLegend()
vb_time_even = p_time_even.getViewBox()
vb_time_even.setMouseMode(vb_time_even.RectMode)
time_curves[0] = p_time_even.plot(pen=colors[0], name='In0')
time_curves[2] = p_time_even.plot(pen=colors[2], name='Out0')

p_asd_even = graphics_widget.addPlot(row=0, col=1)
p_asd_even.setLabel('left', 'ASD', units='V/√Hz')
p_asd_even.setLabel('bottom', 'Frequency', units='Hz')
p_asd_even.showGrid(x=True, y=True, alpha=0.3)
p_asd_even.setLogMode(x=True, y=True)
p_asd_even.addLegend()
vb_asd_even = p_asd_even.getViewBox()
vb_asd_even.setMouseMode(vb_asd_even.RectMode)
asd_curves[0] = p_asd_even.plot(pen=colors[0], name='In0')
asd_curves[2] = p_asd_even.plot(pen=colors[2], name='Out0')

# Row 1: Odd channels (In1, Out1)
p_time_odd = graphics_widget.addPlot(row=1, col=0)
p_time_odd.setLabel('left', 'Voltage', units='V')
p_time_odd.setLabel('bottom', 'Time', units='s')
p_time_odd.showGrid(x=True, y=True, alpha=0.3)
p_time_odd.setYRange(-1.0, 1.0)
p_time_odd.addLegend()
vb_time_odd = p_time_odd.getViewBox()
vb_time_odd.setMouseMode(vb_time_odd.RectMode)
time_curves[1] = p_time_odd.plot(pen=colors[1], name='In1')
time_curves[3] = p_time_odd.plot(pen=colors[3], name='Out1')

p_asd_odd = graphics_widget.addPlot(row=1, col=1)
p_asd_odd.setLabel('left', 'ASD', units='V/√Hz')
p_asd_odd.setLabel('bottom', 'Frequency', units='Hz')
p_asd_odd.showGrid(x=True, y=True, alpha=0.3)
p_asd_odd.setLogMode(x=True, y=True)
p_asd_odd.addLegend()
vb_asd_odd = p_asd_odd.getViewBox()
vb_asd_odd.setMouseMode(vb_asd_odd.RectMode)
asd_curves[1] = p_asd_odd.plot(pen=colors[1], name='In1')
asd_curves[3] = p_asd_odd.plot(pen=colors[3], name='Out1')

time_plots = [p_time_even, p_time_odd]
asd_plots = [p_asd_even, p_asd_odd]

# Continuous acquisition variables
frame_count = 0
start_time = time.time()
running = True

# ASD averaging buffers - store recent ASDs
n_avg_prev = 10
asd_buffers = [[] for _ in range(4)]  # One buffer per channel

# Button callbacks
def reset_averages():
    """Clear all ASD buffers to restart averaging"""
    for buf in asd_buffers:
        buf.clear()
    print("ASD averages reset")

def set_sampling_freq():
    """Reconfigure CDMA with new sampling frequency"""
    global actual_fs, t_s
    try:
        new_fs = float(eval(sampling_input.text()))  # Allow scientific notation
        if new_fs > 0 and new_fs <= 125e6:
            print(f"Reconfiguring with sampling frequency: {new_fs/1e6:.3f} MHz")
            new_config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=new_fs)
            actual_fs = new_config['actual_frequency']
            print(f"Actual sampling rate: {actual_fs / 1e6:.3f} MHz")
            print(f"Acquisition time: {new_config['acquisition_time']*1000:.3f} ms")
            print(f"Bandwidth: {actual_fs/frame_len:.2f} Hz")
            print(f"Log_div: {new_config['log_div']}")
            # Update displays
            actual_fs_display.setText(f"Actual: {actual_fs/1e3:.3f} kHz")
            bw_display.setText(f"BW: {actual_fs/frame_len:.2f} Hz")
            # Recalculate time axis
            t_s = np.arange(frame_len) / actual_fs
            # Clear ASD buffers since frequency changed
            for buf in asd_buffers:
                buf.clear()
        else:
            print("Invalid frequency (must be 0 < f <= 125 MHz)")
            sampling_input.setText("125e6")
    except Exception as e:
        print(f"Error setting sampling frequency: {e}")
        sampling_input.setText("125e6")

def set_nsamples():
    """Reconfigure CDMA with new number of samples"""
    global frame_len, t_s
    try:
        new_nsamples = int(nsamples_input.text())
        if new_nsamples > 0 and new_nsamples <= 4096:
            print(f"Reconfiguring with {new_nsamples} samples")
            frame_len = new_nsamples
            new_config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=actual_fs)
            print(f"Acquisition time: {new_config['acquisition_time']*1000:.3f} ms")
            print(f"Bandwidth: {actual_fs/frame_len:.2f} Hz")
            # Update displays
            bw_display.setText(f"BW: {actual_fs/frame_len:.2f} Hz")
            # Recalculate time axis
            t_s = np.arange(frame_len) / actual_fs
            # Clear ASD buffers since frame length changed
            for buf in asd_buffers:
                buf.clear()
        else:
            print("Invalid number of samples (must be 0 < N <= 4096)")
            nsamples_input.setText(str(frame_len))
    except Exception as e:
        print(f"Error setting number of samples: {e}")
        nsamples_input.setText(str(frame_len))

def reset_zoom():
    """Reset zoom on all plots to auto-range"""
    for p in time_plots:
        p.autoRange()
    for p in asd_plots:
        p.autoRange()
    print("Zoom reset on all plots")

# Connect button signals
reset_avg_button.clicked.connect(reset_averages)
set_sampling_button.clicked.connect(set_sampling_freq)
set_nsamples_button.clicked.connect(set_nsamples)
reset_zoom_button.clicked.connect(reset_zoom)

def update():
    global frame_count, start_time, running, n_avg_prev
    
    if not running:
        return
    
    # Read averaging value
    try:
        n_avg = max(1, int(averaging_input.text()))
    except ValueError:
        n_avg = 10
        averaging_input.setText("10")
    
    # Clear buffers if averaging changed
    if n_avg != n_avg_prev:
        for buf in asd_buffers:
            buf.clear()
        n_avg_prev = n_avg
    
    # Read frame
    ch0, ch1, ch2, ch3 = dev.read_cdma_frame()
    channels = [ch0, ch1, ch2, ch3]
    
    # Convert to volts (14-bit ADC: ±8192 counts = ±1V)
    channels_v = [ch / 8192.0 for ch in channels]
    
    # Update time traces
    for i, (curve, ch_data) in enumerate(zip(time_curves, channels_v)):
        curve.setData(t_s, ch_data)
    
    # Compute and average ASDs
    for i, ch_data in enumerate(channels_v):
        # Compute ASD using Welch's method (sqrt of PSD)
        f, psd = signal.welch(ch_data, fs=actual_fs, nperseg=frame_len, 
                             scaling='density', return_onesided=True)
        asd = np.sqrt(psd)
        
        # Add to buffer
        asd_buffers[i].append(asd)
        if len(asd_buffers[i]) > n_avg:
            asd_buffers[i].pop(0)
        
        # Average ASDs
        asd_avg = np.mean(asd_buffers[i], axis=0)
        
        # Update ASD plot (avoid zero/negative values for log scale)
        asd_avg = np.maximum(asd_avg, 1e-20)
        asd_curves[i].setData(f[1:], asd_avg[1:])  # Skip DC component
    
    # Update frame rate
    frame_count += 1
    current_time = time.time()
    elapsed = current_time - start_time
    
    # Update rate display every 10 frames
    if frame_count % 10 == 0:
        rate = frame_count / elapsed
        rate_display.setText(f"Frame rate: {rate:.2f} Hz (Frames: {frame_count}, Avg: {len(asd_buffers[0])}/{n_avg})")
    
    app.processEvents()
    
    # Schedule next update
    if running:
        QtCore.QTimer.singleShot(1, update)

# Handle key press
def keyPressEvent(event):
    global running
    if event.key() == QtCore.Qt.Key_Q:
        running = False
        elapsed = time.time() - start_time
        print(f"\nStopping acquisition.")
        print(f"Total frames: {frame_count}")
        print(f"Average rate: {frame_count/elapsed:.2f} Hz")
        main_widget.close()

main_widget.keyPressEvent = keyPressEvent

# Start continuous acquisition
print("\nStarting continuous acquisition. Press Q in plot window to quit.")
main_widget.show()
QtCore.QTimer.singleShot(0, update)

sys.exit(app.exec_())
