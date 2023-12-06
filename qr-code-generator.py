import qrcode
from PIL import Image
import os

def combine_pngs(input_folder, output_file, cols):
    script_directory = os.path.dirname(__file__)
    input_folder_path = os.path.join(script_directory, input_folder)

    # Get a list of all PNG files in the input folder
    png_files = [f for f in os.listdir(input_folder_path) if f.endswith('.png')]

    if not png_files:
        print("No PNG files found in the specified folder.")
        return

    # Open the first image to get the size
    first_image_path = os.path.join(input_folder_path, png_files[0])
    first_image = Image.open(first_image_path)
    width, height = first_image.size

    # Calculate the number of rows based on the number of columns
    rows = (len(png_files) + cols - 1) // cols

    # Calculate the size of the combined image
    total_width = width * cols
    total_height = height * rows

    # Create a new image with the total width and height
    combined_image = Image.new('RGBA', (total_width, total_height))

    # Paste each PNG image onto the combined image in a two-column grid
    for i, png_file in enumerate(png_files):
        image_path = os.path.join(input_folder_path, png_file)
        image = Image.open(image_path)

        # Calculate the position in the grid
        row = i // cols
        col = i % cols

        # Paste the image at the appropriate position
        combined_image.paste(image, (col * width, row * height))

    # Save the combined image
    output_file_path = os.path.join(script_directory, output_file)
    combined_image.save(output_file_path)

    print(f"Combined {len(png_files)} PNG files into {output_file_path}")

for i in range (1, 5):
    qr = input("Please enter the name for QR code " + str(i) + ": ")
    jar1Img = qrcode.make(qr)
    jar1Img.save("QR-" + qr + ".png")
input_folder = "./"  # Assuming PNG files are in the same folder as the script
output_file = "QR-combined.png"
cols = 2  # Number of columns in the grid
combine_pngs(input_folder, output_file, cols)