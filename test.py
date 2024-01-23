import time
import board
from cedargrove_nau7802 import NAU7802
import smbus2 as smbus
import math
import bmp388 as bmp
import adafruit_sht4x
import busio
import adafruit_ltr390
import cv2
from pyzbar.pyzbar import decode
import numpy as np
import os 

# define the variables that will store information, all are floats
# NAU7802 (loadcell)
# SHT40 (temp + humidity sensor)
# LTR390 (UV + LUX sensor)
loadCellMass, gain, \
sht_temperature, sht_relative_humidity, \
ltr_uvi, ltr_lux = 0.0

# Put readings to an array to display
overlayArray = ['Load Cell Raw Value: ' + str(loadCellMass),
                'Temp: ' + str(sht_temperature) + ' C', 
                'Humidity: ' + str(sht_relative_humidity) + '%',
                'UV Index: ' + str(ltr_uvi),
                'Lux: ' + str(ltr_lux)]

# Get readings and round them accordingly, this updates the variables defined above
def getSensorReadings():
    # get the raw value around to a whole number and multiply by gain
    loadCellValue = round(read_raw_value()) * gain
    # get the temperature (C) and round to one decimal
    sht_temperature = round(sht.temperature, 1)
    # get the humidity (%) and round to one decimal
    sht_relative_humidity = round(sht.relative_humidity, 1)
    # get the UV index and round to one decimal
    ltr_uvi = round(ltr.uvi, 1)
    # get the LUX level and round to whole number
    ltr_lux = round(ltr.lux)

    """ Notes on LUX level
    Typical Lux
    Direct Sunlight	32,000 to 100,000
    Ambient Daylight	10,000 to 25,000
    Overcast Daylight	1000
    Sunset & Sunrise	400
    Moonlight (Full moon)	1
    Night (No moon)	< 0.01 """
    # source https://greenbusinesslight.com/resources/lighting-lux-lumens-watts/

    overlayArray = ['Load Cell Raw Value: ' + str(loadCellMass),
                'Temp: ' + str(sht_temperature) + ' C', 
                'Humidity: ' + str(sht_relative_humidity) + '%',
                'UV Index: ' + str(ltr_uvi),
                'Lux: ' + str(ltr_lux)]

# this defines the container data structure which will store information we have on each container
# containers will be identified via their numbers and their names can be adjusted in the web GUI
class container:
    def __init__(thisContainer, qr, initalMass, currentMass):
        # qr is an int, ranging from 1 - 4 as this project will only have at most 4 containers 
        # the qr codes should only store int values
        thisContainer.qr = qr
        
        # initialMass is an int >= 0 representing the container's inital mass
        # we will subtract out the known mass of the containers so that this value only reflects
        # the mass of the contents
        thisContainer.initialMass = initalMass

        # currentMass is an int >= 0 representing the amount of product left in the container
        # this value should always be within the following range 
        # initialMass >= currentMass >= 0
        thisContainer.currentMass = currentMass
    
    # this function returns the precentage of product in the container as a string with the % symbol
    # the percentage is rounded to the nearest whole number
    def percentage(thisContainer):
        return str(round(thisContainer.currentMass / thisContainer.initialMass * 100)) + '%'

    # this function returns the RGB color values that correspond with how full or empty the container is
    # green = full, red = empty
    def labelColor(thisContainer):
        pct  =  round(thisContainer.currentMass / thisContainer.initialMass * 100, 2)
        pct_diff = 1.0 - pct
        red_color = min(255, pct_diff*2 * 255)
        green_color = min(255, pct*2 * 255)
        col = (red_color, green_color, 0)
        r,g,b = red_color, green_color, 0
        return r,g,b

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

# Read and average consecutive raw sample values from the scale. Return average raw value.
def read_raw_value(samples=5):
    sample_sum = 0
    sample_count = samples
    while sample_count > 0:
        while not nau7802.available():
            pass
        sample_sum = sample_sum + nau7802.read()
        sample_count -= 1
    return int(sample_sum / samples)

# Returns a gain value, we will store this and multiply read_raw_value's output to get the mass in grams 
def calibrate_weight_sensor():
    # Prompt the user to press enter when the sensor is empty
    print("Press enter when the sensor is empty.")
    input()

    # Read the value of the sensor when empty
    empty_weight_reading = read_raw_value(10)

    # Prompt the user to enter the weight in grams of the item they place on the scale
    item_weight = float(input("Enter the weight of the item in grams: "))

    # Read the value of the sensor with the item on it
    item_weight_reading = read_raw_value()

    # Calculate the calibration parameters
    gain = item_weight / (item_weight_reading - empty_weight_reading)

    # Print the calibration parameters
    print("Gain:", gain)

    return gain

# this defines the path that openCV frames will be stored to, this is used for debugging purposes
path = './OpenCVImages'

# Instantiate the camera device
cap = cv2.VideoCapture(0)

# Instantiate 24-bit load sensor ADC, one channel with default gain of 128
nau7802 = NAU7802(board.I2C(), address=0x2A, active_channels=1)

# Instantiate and calibrate load cell inputs
print("*** Instantiate and calibrate load cell")
# Enable NAU7802 digital and analog power
enabled = nau7802.enable(True)
print("Digital and analog power enabled:", enabled)

print("REMOVE WEIGHTS FROM LOAD CELLS")
time.sleep(3)

nau7802.channel = 1
zero_channel()  # Calibrate and zero channel

gain = calibrate_weight_sensor()

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

getSensorReadings()

imageCount = 0

### Main loop: Read load cells and display raw values
while True:

    # If we can get video, read
    success, img = cap.read()

    # If we can not get video, break
    if not success: 
        break

    # r,g,b = c1.color() ----> set this later?

    # Look for QR codes and add labels 
    for code in decode(img):
        # Get QR code contents
        decoded_data = code.data.decode("utf-8")
        
         # Get bounding QR code box
        rect_pts = code.rect
        # Print what is decoded from that QR code into console
        print(decoded_data)
        # If info in QR code, display on screen in frame
        if decoded_data:
            # call color function
            #
            #
            pts = np.array([code.polygon], np.int32)
            cv2.polylines(img, [pts], True, (0, 255, 0), 3)
            cv2.putText(img, str(decoded_data), (rect_pts[0], rect_pts[1]), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0, 0, 255), 2)

    getSensorReadings()

    # Print the sensor readings to console for logging purposes
    print("=====")

    print('NAU7802: Mass = ', loadCellMass)

    print('SHT4X: Temperature = ', sht_temperature, 'Humidity = ', sht_relative_humidity, '%')

    print('LTR390: UV Index = ', ltr.uvi, 'Lux = ', ltr_lux)

    # Display the array of data on the top left
    # frame = np.ones([400,400,3])*255
    offset = 35
    x,y = 10,10+35
    for idx,lbl in enumerate(overlayArray):
        cv2.putText(img, str(lbl), (x,y+offset*idx), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0,255,0), 2)

    filename = 'savedImage' + str(imageCount) + '.jpg'
    if imageCount == 60:
        imageCount = 0
    
    cv2.imwrite(os.path.join(path , filename), img)
    imageCount += 1





"""  
    ** If we were using a headful system we would use this section **

    # Display the image
    cv2.imshow("image", img)

    # waitKey(0) will display the window infinitely until any keypress (it is suitable for image display).
    # waitKey(1) will display a frame for 1 ms, after which display will be automatically closed.
    cv2.waitKey(1)

"""


# release the camera that we have initialized for our code
cap.release()
