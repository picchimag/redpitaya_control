from redpitaya_dev import redpitaya_dev
import time
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore
import sys

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/stream_cdma_4ch.json")
dev.base.bitfile = 'C:\\Users\\magrini\\Documents\\programming\\redpitaya\\projects\\stream_cdma_4ch\\stream_cdma_4ch.runs\\impl_1\\system_wrapper.bit'
dev.base.load_bitfile()

# Setup parameters
frame_len = 1024
sampling_frequency = 125e6  # 125 MHz

# Configure CDMA using config file addresses
print("Configuring CDMA...")
config = dev.setup_cdma(frame_len=frame_len,sampling_frequency=sampling_frequency)

print(f"Frame length: {frame_len} samples")
print(f"Sampling rate: {config['actual_frequency'] / 1e6:.3f} MHz")
print(f"Acquisition time: {config['acquisition_time']*1000:.3f} ms")
print(f"Log_div: {config['log_div']}")

# Setup pyqtgraph plot
app = QtWidgets.QApplication(sys.argv)
win = pg.GraphicsLayoutWidget(show=True, title="CDMA 4-Channel Continuous - Press Q to quit")
win.resize(1200, 900)

# Add rate display at top
rate_label = pg.LabelItem(justify='left')
win.addItem(rate_label, row=0, col=0)
rate_label.setText("Frame rate: -- Hz | Press Q to quit", color='w', size='12pt')

# Create 4 subplots
plots = []
curves = []
colors = ['c', 'g', 'r', 'y']  # cyan, green, red, yellow
labels = ['Ch0', 'Ch1', 'Ch2', 'Ch3']
x = np.arange(frame_len)

for i, (label, color) in enumerate(zip(labels, colors)):
    p = win.addPlot(row=i+1, col=0)
    p.setLabel('left', label, units='ADC')
    if i == 3:
        p.setLabel('bottom', 'Sample')
    p.showGrid(x=True, y=True, alpha=0.3)
    p.setYRange(-8192, 8192)
    curve = p.plot(pen=color)
    plots.append(p)
    curves.append(curve)

# Continuous acquisition variables
frame_count = 0
start_time = time.time()
last_update = time.time()
running = True

def update():
    global frame_count, start_time, last_update, running
    
    if not running:
        return
    
    # Read frame
    ch0, ch1, ch2, ch3 = dev.read_cdma_frame()
    
    # Update plots
    curves[0].setData(x, ch0)
    curves[1].setData(x, ch1)
    curves[2].setData(x, ch2)
    curves[3].setData(x, ch3)
    
    # Update frame rate
    frame_count += 1
    current_time = time.time()
    elapsed = current_time - start_time
    
    # Update rate display every 10 frames
    if frame_count % 10 == 0:
        rate = frame_count / elapsed
        rate_label.setText(f"Frame rate: {rate:.2f} Hz | Frames: {frame_count} | Press Q to quit", 
                          color='w', size='12pt')
    
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
        win.close()

win.keyPressEvent = keyPressEvent

# Start continuous acquisition
print("\nStarting continuous acquisition. Press Q in plot window to quit.")
QtCore.QTimer.singleShot(0, update)

sys.exit(app.exec_())

