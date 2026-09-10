import os
import io
import json
import boto3
from flask import Flask, request, jsonify, render_template
from PIL import Image
from google import genai
from google.genai import types

app = Flask(__name__, template_folder='.')

# Environment Variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.environ.get("AWS_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

# Initialize New Google GenAI Client
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize AWS S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/process-image', methods=['POST'])
def process_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400

        file = request.files['image']
        image_bytes = file.read()
        pil_img = Image.open(io.BytesIO(image_bytes))
        width, height = pil_img.size

        if not gemini_client:
            return jsonify({'error': 'GEMINI_API_KEY environment variable missing'}), 500

        # Step 1: Gemini API call using official google-genai SDK
        prompt_text = """
        Detect the main interior or property room photograph inside this screenshot.
        Completely ignore status bar, header, floating videos, bottom contact/WhatsApp buttons, and surrounding white spaces.
        Return ONLY a JSON array with 4 integer coordinates [ymin, xmin, ymax, xmax] normalized from 0 to 1000.
        Example output: [300, 0, 700, 1000]
        """

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[pil_img, prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        clean_text = response.text.strip()
        coords = json.loads(clean_text)

        # Scale normalized coordinates to actual pixels
        ymin = max(0, int((coords[0] / 1000) * height))
        xmin = max(0, int((coords[1] / 1000) * width))
        ymax = min(height, int((coords[2] / 1000) * height))
        xmax = min(width, int((coords[3] / 1000) * width))

        # Step 2: Crop Image
        cropped_img = pil_img.crop((xmin, ymin, xmax, ymax))

        # Output to byte stream
        output_buffer = io.BytesIO()
        cropped_img.save(output_buffer, format='JPEG', quality=95)
        output_buffer.seek(0)

        # Step 3: Upload to S3 Bucket
        file_name = f"cropped_{os.urandom(8).hex()}.jpg"
        s3_client.upload_fileobj(
            output_buffer,
            AWS_BUCKET_NAME,
            file_name,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )

        s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_name}"

        return jsonify({
            'success': True,
            'url': s3_url
        })

    except Exception as e:
        print("Error during processing:", str(e))
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    
