import fitz  # PyMuPDF
import io
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
from google.cloud import vision
from google.cloud import translate_v2 as translate
import shutil

# Set the desired font size and box dimensions
PERMANENT_FONT_SIZE = 10
BOX_WIDTH = 50  # Fixed width for the text box
BOX_HEIGHT = 15  # Fixed height for the text box

def pdf_to_images(pdf_path):
    """Convert each page of the PDF to a PNG image within a temp directory."""
    pdf_document = fitz.open(pdf_path)
    temp_dir = tempfile.mkdtemp()
    image_paths = []

    for page_num in range(pdf_document.page_count):
        page = pdf_document.load_page(page_num)
        image = page.get_pixmap()
        image_path = os.path.join(temp_dir, f"page_{page_num + 1}.png")
        image.save(image_path)
        image_paths.append(image_path)

    pdf_document.close()
    return image_paths, temp_dir

def detect_and_translate_words(image_path):
    """Detect words and their positions in the image, then translate each word."""
    # Set up Vision and Translate clients
    vision_client = vision.ImageAnnotatorClient()
    translate_client = translate.Client()

    # Load image into Vision API
    with io.open(image_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)

    response = vision_client.text_detection(image=image)
    annotations = response.text_annotations
    words_data = []

    # Skip the first annotation (it's the full text, not individual words)
    for word_info in annotations[1:]:
        word_text = word_info.description
        bounding_box = word_info.bounding_poly

        # Translate each word to Hebrew
        translation = translate_client.translate(word_text, target_language='he')
        translated_word = translation['translatedText'][::-1]  # Reverse for RTL

        # Store the translated word and its position
        words_data.append((translated_word, bounding_box))

    return words_data

def overlay_translated_text(image_path, words_data):
    # Load image
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    font_path = "arial.ttf"  # Replace with the actual path to your font

    # Set the font with a permanent size
    font = ImageFont.truetype(font_path, PERMANENT_FONT_SIZE)

    # Get image dimensions for right-to-left positioning
    image_width, image_height = image.size

    for word_data in words_data:
        translated_word = word_data[0]  # Translated text
        bounding_poly = word_data[1]    # BoundingPoly object

        # Get coordinates from BoundingPoly
        vertices = bounding_poly.vertices
        x_min = min(vertex.x for vertex in vertices)
        y_min = min(vertex.y for vertex in vertices)

        # Calculate the x position for right-to-left placement
        x_position = image_width - (x_min + BOX_WIDTH)

        # Draw a fixed-size box for the translated text
        draw.rectangle([(x_position, y_min), (x_position + BOX_WIDTH, y_min + BOX_HEIGHT)], fill="white")  # White background
        draw.text((x_position, y_min), translated_word, font=font, fill="black")

    # Save the modified image
    translated_image_path = image_path.replace("temp_images", "temp_translated_images")  # Adjust path as needed
    image.save(translated_image_path)
    return translated_image_path

def process_pdf(pdf_path):
    image_paths, temp_dir = pdf_to_images(pdf_path)

    translated_image_paths = []
    translated_temp_dir = tempfile.mkdtemp()

    try:
        for image_path in image_paths:
            # Detect and translate each word
            words_data = detect_and_translate_words(image_path)
            translated_image_path = overlay_translated_text(image_path, words_data)
            translated_image_paths.append(translated_image_path)

        # Create a new PDF from the translated images
        output_pdf_path = "translated_output.pdf"  # Path for the new PDF
        create_pdf_from_images(translated_image_paths, output_pdf_path)

    finally:
        # Cleanup temporary directories
        shutil.rmtree(temp_dir)
        shutil.rmtree(translated_temp_dir)

def create_pdf_from_images(image_paths, output_pdf_path):
    pdf_document = fitz.open()

    for image_path in image_paths:
        img = fitz.open(image_path)
        pdf_document.insert_page(-1, width=img[0].rect.width, height=img[0].rect.height)
        pdf_document[-1].insert_image(img[0].rect, filename=image_path)

    pdf_document.save(output_pdf_path)
    pdf_document.close()

if __name__ == "__main__":
    pdf_path = r"./examples/sample-2.pdf"  # Update this path to your PDF
    process_pdf(pdf_path)
