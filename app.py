import os
import json
import base64
import boto3
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.')

# Environment Variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.environ.get("AWS_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

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
        mime_type = file.mimetype or 'image/jpeg'
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        if not GEMINI_API_KEY:
            return jsonify({'error': 'GEMINI_API_KEY environment variable missing'}), 500

        # Step 1: Gemini REST API Call
        prompt_text = (
            "Detect the main interior or property room photograph inside this screenshot. "
            "Completely ignore status bar, header, floating videos, bottom contact/WhatsApp buttons, and surrounding white spaces. "
            "Return ONLY a JSON array with 4 integer coordinates [ymin, xmin, ymax, xmax] normalized from 0 to 1000."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": mime_type, "data": base64_image}}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"}
                }
            }
        }

        # Call Gemini REST API directly (using stable endpoint)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json=payload)
        
        if not res.ok:
            return jsonify({'error': f"Gemini API Error: {res.text}"}), 500

        res_data = res.json()
        coords = json.loads(res_data['candidates'][0]['content']['parts'][0]['text'])

        return jsonify({
            'success': True,
            'coords': coords
        })

    except Exception as e:
        print("Error during processing:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/upload-s3', methods=['POST'])
def upload_s3():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No cropped image received'}), 400

        cropped_file = request.files['image']
        file_name = f"cropped_{os.urandom(8).hex()}.jpg"

        # Direct Stream Upload to S3
        s3_client.upload_fileobj(
            cropped_file,
            AWS_BUCKET_NAME,
            file_name,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )

        s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_name}"
        return jsonify({'success': True, 'url': s3_url})

    except Exception as e:
        print("S3 Upload Error:", str(e))
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    
