import time
import board
from cedargrove_nau7802 import NAU7802
import smbus2 as smbus
import math
import bmp388 as bmp
import adafruit_sht4x
import busio
import adafruit_ltr390

# Instantiate 24-bit load sensor ADC; two channels, default gain of 128
nau7802 = NAU7802(board.I2C(), address=0x2A, active_channels=1)

def zero_channel():
    """Initiate internal calibration for current channel.Use when scale is started,
    a new channel is selected, or to adjust for measurement drift. Remove weight
    and tare from load cell before executing."""
    print(
        "channel %1d calibrate.INTERNAL: %5s"
        % (nau7802.channel, nau7802.calibrate("INTERNAL"))
    )
    print(
        "channel %1d calibrate.OFFSET:   %5s"
        % (nau7802.channel, nau7802.calibrate("OFFSET"))
    )
    print("...channel %1d zeroed" % nau7802.channel)


def read_raw_value(samples=5):
    """Read and average consecutive raw sample values. Return average raw value."""
    sample_sum = 0
    sample_count = samples
    while sample_count > 0:
        while not nau7802.available():
            pass
        sample_sum = sample_sum + nau7802.read()
        sample_count -= 1
    return int(sample_sum / samples)


# Instantiate and calibrate load cell inputs
print("*** Instantiate and calibrate load cell")
# Enable NAU7802 digital and analog power
enabled = nau7802.enable(True)
print("Digital and analog power enabled:", enabled)

print("REMOVE WEIGHTS FROM LOAD CELLS")
time.sleep(3)

nau7802.channel = 1
zero_channel()  # Calibrate and zero channel

print("LOAD CELL READY")

bmp.bmp388 = bmp.BMP388()
print("BMP388 READY")

sht = adafruit_sht4x.SHT4x(board.I2C())
print("Found SHT4x with serial number", hex(sht.serial_number))
print("Current mode is: ", adafruit_sht4x.Mode.string[sht.mode])
print("SHT4X READY")

i2c = busio.I2C(board.SCL, board.SDA)
ltr = adafruit_ltr390.LTR390(i2c)
print("LTR390 READY")

### Main loop: Read load cells and display raw values
while True:
    print("=====")
    nau7802.channel = 1
    value = read_raw_value()
    print("NAU7802: Load Cell %1.0f Raw Value = %7.0f" % (nau7802.channel, value))
    temperature,pressure,altitude = bmp.bmp388.get_temperature_and_pressure_and_altitude()
    print('BMP388: Temperature = %.1fC Pressure = %.2f  Altitude = %.2f '%(temperature/100.0,pressure/100.0,altitude/100.0))
    print('SHT4X: Temperature = %.1fC Humidity = %.1f' %(sht.temperature,sht.relative_humidity))
    print('LTR390: UV = %.1f UV Index = %.1f Lux = %.1f Ambient Light = %.1f' %(ltr.uvs, ltr.uvi, ltr.lux, ltr.light))
    time.sleep(1.0)