from redpitaya_dev import redpitaya_dev
import time
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore
import sys
from scipy import signal

# Connect to both Red Pitayas


dev1 = redpitaya_dev("171.64.56.120", "config/stream_cdma_4ch.json")
dev1.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_cdma_4ch\\stream_cdma_4ch.runs\\impl_1\\system_wrapper.bit'
#dev1.base.load_bitfile()

dev2 = redpitaya_dev("171.64.56.120", "config/stream_cdma_4ch.json")  # Change IP for second device
dev2.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_cdma_4ch\\stream_cdma_4ch.runs\\impl_1\\system_wrapper.bit'
#dev2.base.load_bitfile()

# Setup parameters
frame_len = 2048
sampling_frequency = 125e6  # 125 MHz
color_in = 'c'   # Cyan for all In channels
color_out = 'r'  # Red for all Out channels
labels_in = ['In0', 'In1', 'In2', 'In3']
labels_out = ['Out0', 'Out1', 'Out2', 'Out3']

# Configure CDMA on both devices
print("Configuring CDMA on Device 1...")
config1 = dev1.setup_cdma(frame_len=frame_len, sampling_frequency=sampling_frequency)
print("Configuring CDMA on Device 2...")
config2 = dev2.setup_cdma(frame_len=frame_len, sampling_frequency=sampling_frequency)

actual_fs = config1['actual_frequency']
print(f"Frame length: {frame_len} samples")
print(f"Sampling rate: {actual_fs / 1e6:.3f} MHz")
print(f"Acquisition time: {config1['acquisition_time']*1000:.3f} ms")

# Setup pyqtgraph application
app = QtWidgets.QApplication(sys.argv)

# Create main window with layout
main_widget = QtWidgets.QWidget()
main_widget.setWindowTitle("2 Devices (8 Channels) - 4 In/Out Pairs - Press Q to quit")
main_widget.resize(1600, 1200)
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

# Create 4 rows x 2 columns: 4 pairs (In0/Out0, In1/Out1, In2/Out2, In3/Out3)
# Row 0: Dev1 Ch0/Ch2 (In0/Out0)
# Row 1: Dev1 Ch1/Ch3 (In1/Out1)  
# Row 2: Dev2 Ch0/Ch2 (In2/Out2)
# Row 3: Dev2 Ch1/Ch3 (In3/Out3)


# Time axis in seconds
t_s = np.arange(frame_len) / actual_fs

time_curves = [None] * 8  # 4 channels x 2 devices
asd_curves = [None] * 8
time_plots = []
asd_plots = []

# Map: row -> (dev, ch_in, ch_out)
# Row 0: Dev1 Ch0/Ch2, Row 1: Dev1 Ch1/Ch3, Row 2: Dev2 Ch0/Ch2, Row 3: Dev2 Ch1/Ch3
row_config = [
    (0, 0, 2),  # Dev1-Ch0, Dev1-Ch2
    (0, 1, 3),  # Dev1-Ch1, Dev1-Ch3
    (4, 0, 2),  # Dev2-Ch0, Dev2-Ch2
    (4, 1, 3),  # Dev2-Ch1, Dev2-Ch3
]

for row, (base_idx, ch_in_offset, ch_out_offset) in enumerate(row_config):
    # Time trace (left column)
    p_time = graphics_widget.addPlot(row=row, col=0)
    p_time.setLabel('left', 'Voltage', units='V')
    if row == 3:
        p_time.setLabel('bottom', 'Time', units='s')
    p_time.showGrid(x=True, y=True, alpha=0.3)
    p_time.setYRange(-1.0, 1.0)
    p_time.addLegend()
    vb_time = p_time.getViewBox()
    vb_time.setMouseMode(vb_time.RectMode)
    
    # Add In and Out curves
    time_curves[base_idx + ch_in_offset] = p_time.plot(pen=color_in, name=labels_in[row])
    time_curves[base_idx + ch_out_offset] = p_time.plot(pen=color_out, name=labels_out[row])
    time_plots.append(p_time)
    
    # ASD (right column)
    p_asd = graphics_widget.addPlot(row=row, col=1)
    p_asd.setLabel('left', 'ASD', units='V/√Hz')
    if row == 3:
        p_asd.setLabel('bottom', 'Frequency', units='Hz')
    p_asd.showGrid(x=True, y=True, alpha=0.3)
    p_asd.setLogMode(x=True, y=True)
    p_asd.addLegend()
    vb_asd = p_asd.getViewBox()
    vb_asd.setMouseMode(vb_asd.RectMode)
    
    # Add In and Out curves
    asd_curves[base_idx + ch_in_offset] = p_asd.plot(pen=color_in, name=labels_in[row])
    asd_curves[base_idx + ch_out_offset] = p_asd.plot(pen=color_out, name=labels_out[row])
    asd_plots.append(p_asd)

# Continuous acquisition variables
frame_count = 0
start_time = time.time()
running = True

# ASD averaging buffers - store recent ASDs
n_avg_prev = 10
asd_buffers = [[] for _ in range(8)]  # 8 channels total

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
            new_config1 = dev1.setup_cdma(frame_len=frame_len, sampling_frequency=new_fs)
            new_config2 = dev2.setup_cdma(frame_len=frame_len, sampling_frequency=new_fs)
            actual_fs = new_config1['actual_frequency']
            print(f"Actual sampling rate: {actual_fs / 1e6:.3f} MHz")
            print(f"Acquisition time: {new_config1['acquisition_time']*1000:.3f} ms")
            print(f"Bandwidth: {actual_fs/frame_len:.2f} Hz")
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
            new_config1 = dev1.setup_cdma(frame_len=frame_len, sampling_frequency=actual_fs)
            new_config2 = dev2.setup_cdma(frame_len=frame_len, sampling_frequency=actual_fs)
            print(f"Acquisition time: {new_config1['acquisition_time']*1000:.3f} ms")
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
    
    # Read frames from both devices
    ch0_d1, ch1_d1, ch2_d1, ch3_d1 = dev1.read_cdma_frame()
    ch0_d2, ch1_d2, ch2_d2, ch3_d2 = dev2.read_cdma_frame()
    
    # Combine all 8 channels: [Dev1-Ch0, Dev1-Ch1, Dev1-Ch2, Dev1-Ch3, Dev2-Ch0, Dev2-Ch1, Dev2-Ch2, Dev2-Ch3]
    channels = [ch0_d1, ch1_d1, ch2_d1, ch3_d1, ch0_d2, ch1_d2, ch2_d2, ch3_d2]
    
    # Convert to volts (14-bit ADC: ±8192 counts = ±1V)
    channels_v = [ch / 8192.0 for ch in channels]
    
    # Update time traces (all 8 channels)
    for i in range(8):
        if time_curves[i] is not None:
            time_curves[i].setData(t_s, channels_v[i])
    
    # Compute and average ASDs (all 8 channels)
    for i in range(8):
        if asd_curves[i] is not None:
            ch_data = channels_v[i]
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
