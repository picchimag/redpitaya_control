# python_rp

Python control and data acquisition library for Red Pitaya FPGA projects.
check this, [[iir2nd_direct_2ch]], [[z_control]], [[mca_simple]]

## Installation

```bash
cd python_rp
pip install -e .
```

## Usage

```python
from python_rp.redpitaya_dev import redpitaya_dev
from python_rp import compute_coeff

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/stream_cdma_4ch.json")
dev.base.load_bitfile()

# Read CDMA frame
config = dev.setup_cdma(frame_len=1024, sampling_frequency=125e6)
ch0, ch1, ch2, ch3 = dev.read_cdma_frame()
```

## Examples

See `examples/` directory:
- `stream4channel_psd.py` - 4-channel time trace and ASD visualization
- `stream4channel_overlaid.py` - Overlaid In/Out pairs
- `iir2nd_coupled_example.py` - Configure coupled IIR filters
- `iir2nd_direct_example.py` - Configure direct form IIR filters
- `mca_example.py` - Multi-channel analyzer example

## Structure

- `python_rp/` - Main package
  - `redpitaya_dev.py` - High-level device interface
  - `redpitaya_base.py` - Low-level SSH/register access
  - `compute_coeff.py` - Filter coefficient calculation
- `config/` - JSON configuration files for different FPGA designs
- `bitfiles/` - Compiled FPGA bitfiles
- `examples/` - Example scripts
