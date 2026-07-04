import time
import board
from cedargrove_nau7802 import NAU7802

# Initialize the I2C bus and NAU7802
i2c = board.I2C()
nau7802 = NAU7802(i2c, address=0x2A)

# Set the hardware sample rate (Options: 10, 20, 40, 80, 320 SPS)
# nau7802.conversion_rate = 320   <-- Uncomment for max speed
nau7802.conversion_rate = 80      <-- Recommended for better noise reduction

# Perform internal calibration after rate/gain change
nau7802.calibrate('INTERNAL')

def get_filtered_reading(samples=10):
    """Polls the ADC and returns a filtered (median) reading"""
    reading_list = []
    
    # Poll until we gather enough samples
    while len(reading_list) < samples:
        if nau7802.available():
            reading_list.append(nau7802.read())
            
    # Use median filtering instead of average to drop electrical spikes
    reading_list.sort()
    return reading_list[len(reading_list) // 2]

# Main loop
while True:
    weight = get_filtered_reading(samples=10)
    print(f"Filtered Weight: {weight}")
    # Remove the 0.01 sec sleep; the DRDY flag manages the loop speed
