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
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import json

# Display Packages
import subprocess
# from board import SCL, SDA, D4
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1305

cmd = "hostname -I | cut -d' ' -f1"
IP = subprocess.check_output(cmd, shell=True).decode("utf-8")
print("Local IP: " + str(IP))

degree_sign = u'\N{DEGREE SIGN}'
# Tuned to account for small bumps on the scale when placing and removing containers
thresholdMass = 27 # units are grams, +/-1 gram 

# Fetch the service account key JSON file contents
cred = credentials.Certificate('ece-180-project-firebase-adminsdk-7eg04-74b6c29e0b.json')
#                               ^ DO NOT PUSH THIS JSON FILE TO GITHUB, CONTAINS ACCESS TOKENS!!!

# Initialize the app with a service account, granting admin privileges
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ece-180-project-default-rtdb.firebaseio.com/'
})

# Be sure to update this line for other scales
# i.e. ref = db.reference("/Scale_2/")
ref = db.reference("/Scale_1/")

# update_firebase_container(Container Name, Parameter to Update, Value to Update to)
# Example usage update_firebase_container("Container_1", "Current Mass", val) 
# Note the container names have underscores while the parameters do not
def update_firebase_container(container, parameter, updated_value):
	ref.child(container).update({parameter:updated_value})

# update_firebase(Parameter to Update, Value to Update to)
# Example usage update_firebase_scale("Scale UV", val) 
def update_firebase_scale(parameter, updated_value):
	ref.update({parameter:updated_value})

# Pull the scale's gain from Firebase, returns a float
def get_scale_gain():
	return ref.child("Scale Gain").get()

def get_initial_mass(container):
    # Get a database reference to our posts
    initialMass = db.reference("/Scale_1/" + container + "/Initial Container Mass" )
    return initialMass.get()

def get_name(container):
    # Get a database reference to our posts
    name = db.reference("/Scale_1/" + container + "/Container Name" )
    return name.get()

# define the variables that will store information, all are floats
# NAU7802 (ADC)
# SHT40 (temp + humidity sensor)
# LTR390 (UV + LUX sensor)
loadCellMass = gain = 0.0
sht_temperature = sht_relative_humidity = 0.0
ltr_uvi = ltr_lux = 0.0
# Keep track of the number of OpenCV frames we are storing
imageCount = 1

# Put readings to an array to display
overlayArray = ['Load Cell Raw Value: ' + str(loadCellMass) + 'g',
                'Temp: ' + str(sht_temperature) + ' C', 
                'Humidity: ' + str(sht_relative_humidity) + '%',
                'UV Index: ' + str(ltr_uvi),
                'Lux: ' + str(ltr_lux)]

# Get readings and round them accordingly, this updates the variables defined above and pushes them to Firebase
def getSensorReadings():
    global loadCellMass
    global sht_temperature
    global sht_relative_humidity
    global ltr_uvi
    global ltr_lux
    global overlayArray
    # get the raw value around to a whole number and multiply by gain
    loadCellMass = round(read_raw_value() * gain, 1)
    if loadCellMass < 0.0:
         loadCellMass = 0.0
    # get the temperature (C) and round to one decimal
    sht_temperature = round(sht.temperature, 1)
    # get the humidity (%) and round to one decimal
    sht_relative_humidity = round(sht.relative_humidity, 1)
    # get the UV index and round to one decimal
    ltr_uvi = round(ltr.uvi, 1)
    # get the LUX level and round to whole number
    ltr_lux = round(ltr.lux)

    # update the overlay array
    overlayArray = ['Load Cell Raw Value: ' + str(loadCellMass) + 'g',
                'Temp: ' + str(sht_temperature) + ' ' + degree_sign +'C', 
                'Humidity: ' + str(sht_relative_humidity) + '%',
                'UV Index: ' + str(ltr_uvi),
                'LUX: ' + str(ltr_lux) + 'lx']
    
    # push these values to Firebase 
    update_firebase_scale("Scale Mass",loadCellMass) 
    update_firebase_scale("Scale Temperature", sht_temperature) 
    update_firebase_scale("Scale Humidity", sht_relative_humidity) 
    update_firebase_scale("Scale UV", ltr_uvi) 
    update_firebase_scale("Scale Lux", ltr_lux) 

    # Print the sensor readings to console for logging purposes
    print("=====")

    print('NAU7802: Mass = ' + str(loadCellMass) + 'g')

    print('SHT4X: Temperature = ' + str(sht_temperature) + degree_sign + 'C, Humidity = ' + str(sht_relative_humidity) + '%')

    print('LTR390: UV Index = ' + str(ltr_uvi) + ', Lux = ' + str(ltr_lux))


# this defines the container data structure which will store information we have on each container
# containers will be identified via their numbers and their names can be adjusted in the web GUI
class container:
    def __init__(thisContainer, qr, initialMass, currentMass):
        # qr is an int, ranging from 1 - 4 as this project will only have at most 4 containers 
        # the qr codes should only store int values
        thisContainer.qr = qr
        
        # initialMass is an int >= 0 representing the container's initial mass
        # we will subtract out the known mass of the containers so that this value only reflects
        # the mass of the contents
        thisContainer.initialMass = initialMass

        # currentMass is an int >= 0 representing the amount of product left in the container
        # this value should always be within the following range 
        # initialMass >= currentMass >= 0
        thisContainer.currentMass = currentMass
    
    # this function returns the percentage of product in the container as an int
    # the percentage is rounded to the nearest whole number
    def updatePercentage(thisContainer):
        if thisContainer.initialMass == 0: # handle the edge case
             returnVal = 0
        else:
            returnVal = round(thisContainer.currentMass / thisContainer.initialMass * 100)
        update_firebase_container(thisContainer.qr,"Percentage Remaining", returnVal)
        print(str(thisContainer.qr) + ": Percentage updated, now " + str(returnVal) + "%")
        return returnVal
    
    def getPercentage(thisContainer):
        if thisContainer.initialMass == 0: # handle the edge case
             return str(0) + "%"
        else:
            return str(round(thisContainer.currentMass / thisContainer.initialMass * 100)) + "%"

    # this function updates the current mass locally and in Firebase, it accepts an int 
    # updates the % in Firebase also!
    def updateCurrentMass(thisContainer, newMass):
        thisContainer.currentMass = newMass
        print(str(thisContainer.qr) + ": Current mass updated, now " + str(thisContainer.currentMass) + "g")
        update_firebase_container(thisContainer.qr,"Current Container Mass", newMass)
        if newMass > thisContainer.initialMass:
            thisContainer.initialMass = thisContainer.currentMass
            update_firebase_container(thisContainer.qr,"Initial Container Mass", newMass)
            print(str(thisContainer.qr) + ": Initial mass updated, now " + str(thisContainer.initialMass) + "g")
        thisContainer.updatePercentage()

# the dictionary to store containers, now pulls the initial masses from firebase 
containerDict = dict()
containerDict["Container_1"] = container("Container_1", get_initial_mass("Container_1"), 0)
containerDict["Container_2"] = container("Container_2", get_initial_mass("Container_2"), 0)
containerDict["Container_3"] = container("Container_3", get_initial_mass("Container_3"), 0)
containerDict["Container_4"] = container("Container_4", get_initial_mass("Container_4"), 0)


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

# Returns a gain value, we will store this and multiply read_raw_value's output to get the mass in grams 
def calibrate_weight_sensor():
    global gain
    # Prompt the user to press enter when the sensor is empty
    print("Press enter when the sensor is empty.")
    input()

    # Read the value of the sensor when empty
    empty_weight_reading = read_raw_value(10)

    # Prompt the user to enter the weight in grams of the item they place on the scale
    print("Now place the item on the scale.")
    item_weight = float(input("Enter the weight of the item in grams: "))

    # Read the value of the sensor with the item on it
    item_weight_reading = read_raw_value()

    # Calculate the calibration parameters
    gain = item_weight / (item_weight_reading - empty_weight_reading)

    # Print the calibration parameters
    print("Scale Gain:", gain)
    update_firebase_scale("Scale Gain", gain)

# this defines the path that openCV frames will be stored to, this is used for debugging purposes
path = './OpenCVImages'

# Instantiate the camera device
# cap = cv2.VideoCapture(0)

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

# Check if we have a gain stored in Firebase, if not obtain a new one
gain = get_scale_gain()
if(gain == 0.0):
    calibrate_weight_sensor()

print("LOAD CELL READY")

bmp.bmp388 = bmp.BMP388()
print("BMP388 READY")

sht = adafruit_sht4x.SHT4x(board.I2C())
print("SHT4X READY")

i2c = busio.I2C(board.SCL, board.SDA)
ltr = adafruit_ltr390.LTR390(i2c)
print("LTR390 READY")

oled_reset = digitalio.DigitalInOut(board.D4)
disp = adafruit_ssd1305.SSD1305_I2C(128, 32, i2c, reset=oled_reset)

# Clear display.
disp.fill(0)
disp.show()

# Create blank image for drawing.
# Make sure to create image with mode '1' for 1-bit color.
width = disp.width
height = disp.height
image = Image.new("1", (width, height))

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=0)

# Draw some shapes.
# First define some constants to allow easy resizing of shapes.
padding = -2
top = padding
bottom = height - padding
# Move left to right keeping track of the current x position for drawing shapes.
x = 0

# Load default font.
font = ImageFont.load_default()
print("SSD1305 DISPLAY READY")

getSensorReadings()

# We will remember the last 5 masses and compare to see if there is a jump 
prevMasses = [0.0, 0.0, 0.0, 0.0, 0.0]

# We are keeping track of what is here
presentContainers = {
  "Container_1": False,
  "Container_2": False,
  "Container_3": False,
  "Container_4": False
}

""" Find the new container that resulted in the mass change """
def findNewContainer(): # Returns a string with the name of the new container
    print ("Searching for the new container...")
    cap = cv2.VideoCapture(0)
    # For debugging purposes we will keep track of how long it takes to find the new container
    count = 1
    # In order to exit this loop we must find a new QR code 
    while True:
        # Get an image from the webcam
        success, img = cap.read()
        # If we can not get an image terminate the program
        if not success: 
            print("Could not get video feed, quitting")
            exit()
        # Read all the QR codes present in the frame
        decoded_list = decode(img)
        # Iterate through all the QR codes
        for code in decoded_list:
            # Get QR code contents
            decoded_data = code.data.decode("utf-8")
            # Check if it is in our presentContainers dictionary
            if decoded_data in presentContainers.keys():
                # If it is in the dictionary, check if it was previously there
                if presentContainers[decoded_data] == False:
                    # If that is the case, return the container's name
                    print("Success! Found " + decoded_data + " in " + str(count) + " iteration(s)!")
                    cap.release()
                    return decoded_data
        # If we don't find it let's keep trying
        print("Could not find the container in iteration: " + str(count) + " searching again")
        count += 1

""" Find the container that was removed """
def findRemovedContainer(): # Returns a string with the name of the container that was removed
    print ("Searching for the container that was removed...")
    cap = cv2.VideoCapture(0)
    # In order to exit this loop we must find a single container that has been removed
    # i.e. The candidates list must be reduced to one element 
    candidates = []
    # Populate the candidates list, with containers that were present on the scale before change in mass
    for key, value in presentContainers.items():
        if value == True:
            candidates.append(key)
    print("Candidate containers: ")
    print(' '.join(candidates))
        
    # For debugging purposes we will keep track of how long it takes to find the container
    count = 1
    # As long as we have more than one candidate in the list continue
    while (len(candidates) > 1):
        # Get an image from the webcam
        success, img = cap.read()
        # If we can not get an image terminate the program
        if not success: 
            print("Could not get video feed, quitting")
            exit()

        # Iterate through all the QR codes
        for code in decode(img):
            # Get QR code contents
            decoded_data = code.data.decode("utf-8")
            # Check if it is in our list of candidates
            if decoded_data in candidates:
                candidates.remove(decoded_data)
                print(decoded_data + " is still here.")

        # If we don't find it let's keep trying
        if (len(candidates) > 1):
            print("Could not find the container in iteration: " + str(count) + " searching again")
            print("Remaining Candidates: ")
            print(' '.join(candidates))
            count += 1
    # If we find that all the containers are still present
    if len(candidates) == 0:
        print("That's odd, all the containers are still here.")
        exit()
    # When we only have one candidate left, return that candidate
    else:
        print("The container that was removed is: " + str(candidates[0]))
        cap.release()
        return str(candidates[0])

""" Display container names and percentages on the OLED """
def update_display():
    # Draw a black filled box to clear the image.
    draw.rectangle((0, 0, width, height), outline=0, fill=0)

    # Gather the information to display for each container
    c1 = ("*" if presentContainers["Container_1"] else " ") + get_name("Container_1") + ": " + containerDict["Container_1"].getPercentage()
    c2 = ("*" if presentContainers["Container_2"] else " ") + get_name("Container_2") + ": " + containerDict["Container_2"].getPercentage()
    c3 = ("*" if presentContainers["Container_3"] else " ") + get_name("Container_3") + ": " + containerDict["Container_3"].getPercentage()
    c4 = ("*" if presentContainers["Container_4"] else " ") + get_name("Container_4") + ": " + containerDict["Container_4"].getPercentage()

    # Draw our four lines of text
    draw.text((x, top + 0),  c1, font=font, fill=255)
    draw.text((x, top + 8),  c2, font=font, fill=255)
    draw.text((x, top + 16), c3, font=font, fill=255)
    draw.text((x, top + 25), c4, font=font, fill=255)

    # Display image.
    disp.image(image)
    disp.show()
    time.sleep(0.1)

### Main loop
while True:

    getSensorReadings()
    update_display()
    avgOfPrevMasses = sum(prevMasses) / len(prevMasses)
    # print("The average of the last 5 readings is : " + str(avgOfPrevMasses))

    differenceInMass = loadCellMass - avgOfPrevMasses

    # print("The difference in mass from the average is: " + str(differenceInMass))

    # CASE 1: INCREASE IN MASS
    if (differenceInMass > thresholdMass):
        # Find the new container
        newContainer = findNewContainer()

        # Mark it as here in our presentContainers dictionary
        presentContainers[newContainer] = True

        # Get a (hopefully) settled reading from the scale
        getSensorReadings()

        # Update the current mass of the container locally and in Firebase
        containerDict[newContainer].updateCurrentMass(loadCellMass - avgOfPrevMasses)

        # Make all the prevMasses the current mass so the next iteration doesn't think there was a change
        prevMasses = [loadCellMass, loadCellMass, loadCellMass, loadCellMass, loadCellMass]

    # CASE 2: DECREASE IN MASS
    elif (abs(differenceInMass) > thresholdMass):
        # wait one second so the QR is out of the frame 
        time.sleep(1)
        # Find the container that was removed
        removedContainer = findRemovedContainer()
        # Mark it as not present in our presentContainers dictionary
        presentContainers[removedContainer] = False

        # Make all the prevMasses the current mass so the next iteration doesn't think there was a change
        prevMasses = [loadCellMass, loadCellMass, loadCellMass, loadCellMass, loadCellMass]

    # CASE 3:  NO SIGNIFICANT CHANGE IN MASS
    else:
        # print("No significant change in mass.")
        # Remove the oldest mass from prevMasses (which is in front)
        prevMasses.pop(0)
        # Put in the back of prevMasses the newest mass
        prevMasses.append(loadCellMass)

# release the camera that we have initialized for our code
cap.release()
# clear the display
draw.rectangle((0, 0, width, height), outline=0, fill=0)




