from neutrality_control.redpitaya.python_rp import redpitaya_dev
import time
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore
from scipy import signal
import sys

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.117", "config/z_control_v4_stream.json")
#dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\z_control_v4_stream\\z_control_v4_stream.runs\\impl_1\\system_wrapper.bit'
dev.base.load_bitfile()

# Setup parameters
frame_len = 1024
sampling_frequency = 10e4  # 125 kHz

# Configure CDMA using config file addresses
print("Configuring CDMA...")
config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=sampling_frequency, module_name='stream8ch')

actual_fs = config['actual_frequency']
print(f"Frame length: {frame_len} samples")
print(f"Sampling rate: {actual_fs / 1e6:.3f} MHz")
print(f"Acquisition time: {config['acquisition_time']*1000:.3f} ms")
print(f"Log_div: {config['log_div']}")

# Setup pyqtgraph application
app = QtWidgets.QApplication(sys.argv)

# Create main window with layout
main_widget = QtWidgets.QWidget()
main_widget.setWindowTitle("Overlaid Multi-Channel Analysis - Press Q to quit")
main_widget.resize(1600, 900)
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

# Time axis in seconds
t_s = np.arange(frame_len) / actual_fs

# Define channel configurations
# Top plot: ch0(c), ch2(g), ch4(y) as inputs, ch1(r) as output
# Bottom plot: ch0(c) as input, ch3(r) as output
plot_configs = [
    {
        'title': 'Multi-Input Control Loop',
        'inputs': [(0, 'c', 'In1: QPDsum(ch0)'), (1, 'g', 'In2: Zrf(ch1)'), (4, 'y', 'AuxIn: fb laser power(ch4)')],
        'output': (2, 'r', 'Out1(ch2)')
    },
    {
        'title': 'Single-Input Control Loop',
        'inputs': [(1, 'g', 'In2: Zrf(ch1)')],
        'output': (3, 'r', 'Out2(ch3)')
    }
]

# Storage for plot objects
time_plots = []
asd_plots = []
time_curves = {}  # dict keyed by (row, channel_index)
asd_curves = {}

# ASD averaging buffers - need buffers for channels 0,1,2,3,4
asd_buffers = {i: [] for i in [0, 1, 2, 3, 4]}

# Create plots - 2 rows, 2 columns (time trace, PSD)
for row, config in enumerate(plot_configs):
    # Time trace (left column)
    p_time = graphics_widget.addPlot(row=row, col=0)
    p_time.setLabel('left', 'Voltage', units='V')
    p_time.setLabel('top', config['title'])
    if row == 1:
        p_time.setLabel('bottom', 'Time', units='s')
    p_time.showGrid(x=True, y=True)
    p_time.setYRange(-1.0, 1.0)
    p_time.addLegend()
    vb_time = p_time.getViewBox()
    vb_time.setMouseMode(vb_time.RectMode)
    time_plots.append(p_time)
    
    # ASD (right column)
    p_asd = graphics_widget.addPlot(row=row, col=1)
    p_asd.setLabel('left', 'ASD', units='V/√Hz')
    if row == 1:
        p_asd.setLabel('bottom', 'Frequency', units='Hz')
    p_asd.showGrid(x=True, y=True)
    p_asd.setLogMode(x=True, y=True)
    p_asd.addLegend()
    vb_asd = p_asd.getViewBox()
    vb_asd.setMouseMode(vb_asd.RectMode)
    asd_plots.append(p_asd)
    
    # Create curves for inputs
    for ch_idx, color, label in config['inputs']:
        curve_time = p_time.plot(pen=color, name=f'{label}')
        time_curves[(row, ch_idx)] = curve_time
        
        curve_asd = p_asd.plot(pen=color, name=f'{label}')
        asd_curves[(row, ch_idx)] = curve_asd
    
    # Create curves for output
    ch_idx, color, label = config['output']
    curve_time = p_time.plot(pen=color, name=f'{label}', width=2)
    time_curves[(row, ch_idx)] = curve_time
    
    curve_asd = p_asd.plot(pen=color, name=f'{label}', width=2)
    asd_curves[(row, ch_idx)] = curve_asd

# Continuous acquisition variables
frame_count = 0
start_time = time.time()
running = True
n_avg_prev = 10

# Button callbacks
def reset_averages():
    """Clear all ASD buffers to restart averaging"""
    for buf in asd_buffers.values():
        buf.clear()
    print("ASD averages reset")

def set_sampling_freq():
    """Reconfigure CDMA with new sampling frequency"""
    global actual_fs, t_s
    try:
        new_fs = float(eval(sampling_input.text()))  # Allow scientific notation
        if new_fs > 0 and new_fs <= 125e6:
            print(f"Reconfiguring with sampling frequency: {new_fs/1e6:.3f} MHz")
            new_config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=new_fs, module_name='stream8ch')
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
            for buf in asd_buffers.values():
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
            new_config = dev.setup_cdma(frame_len=frame_len, sampling_frequency=actual_fs, module_name='stream8ch')
            print(f"Acquisition time: {new_config['acquisition_time']*1000:.3f} ms")
            print(f"Bandwidth: {actual_fs/frame_len:.2f} Hz")
            # Update displays
            bw_display.setText(f"BW: {actual_fs/frame_len:.2f} Hz")
            # Recalculate time axis
            t_s = np.arange(frame_len) / actual_fs
            # Clear ASD buffers since frame length changed
            for buf in asd_buffers.values():
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
        for buf in asd_buffers.values():
            buf.clear()
        n_avg_prev = n_avg
    
    # Read frame (8 channels from FPGA, use first 5)
    ch0, ch1, ch2, ch3, ch4, ch5, ch6, ch7 = dev.read_cdma_frame()
    channels = [ch0, ch1, ch2, ch3, ch4]
    
    # Convert to volts (14-bit ADC: ±8192 counts = ±1V)
    channels_v = [ch / 8192.0 for ch in channels]
    
    # Update time traces and compute ASDs for all needed channels
    for ch_idx, ch_data in enumerate(channels_v):
        # Compute ASD using Welch's method (sqrt of PSD)
        f, psd = signal.welch(ch_data, fs=actual_fs, nperseg=frame_len, 
                             scaling='density', return_onesided=True)
        asd = np.sqrt(psd)
        
        # Add to buffer
        asd_buffers[ch_idx].append(asd)
        if len(asd_buffers[ch_idx]) > n_avg:
            asd_buffers[ch_idx].pop(0)
        
        # Average ASDs
        asd_avg = np.mean(asd_buffers[ch_idx], axis=0)
        asd_avg = np.maximum(asd_avg, 1e-20)
        
        # Update curves for this channel in all plots where it appears
        for row in range(2):
            if (row, ch_idx) in time_curves:
                time_curves[(row, ch_idx)].setData(t_s, ch_data)
                asd_curves[(row, ch_idx)].setData(f[1:], asd_avg[1:])
    
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
