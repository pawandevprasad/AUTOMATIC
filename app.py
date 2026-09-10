import os
import io
import json
import base64
import boto3
import requests
from flask import Flask, request, jsonify, render_template
from PIL import Image

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATIONS & ENV VARIABLES ---
MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = "property_database"
COLLECTION_NAME = "properties"

collection = None
if MONGO_URI:
    try:
        from pymongo import MongoClient
        client_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client_db[DB_NAME]
        collection = db[COLLECTION_NAME]
    except Exception as mongo_err:
        print(f"MongoDB Warning: {mongo_err}")

# AWS S3 Configuration
S3_BUCKET = (
    os.environ.get("AWS_S3_BUCKET") 
    or os.environ.get("S3_BUCKET") 
    or os.environ.get("AWS_S3_BUCKET_NAME")
    or "property-images-estatex-1"
)

AWS_ACCESS_KEY = (
    os.environ.get("AWS_ACCESS_KEY_ID") 
    or os.environ.get("AWS_ACCESS_KEY")
)

AWS_SECRET_KEY = (
    os.environ.get("AWS_SECRET_ACCESS_KEY") 
    or os.environ.get("AWS_SECRET_KEY")
)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3_client = None
if AWS_ACCESS_KEY and AWS_SECRET_KEY:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION
        )
    except Exception as s3_err:
        print(f"S3 Warning: {s3_err}")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# --- HELPER FUNCTION: Enforce Rules & Logic ---
def process_and_enforce_rules(data, s3_urls):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    elif not isinstance(data, dict):
        data = {}

    def safe_get_dict(obj, key):
        val = obj.get(key, {}) if isinstance(obj, dict) else {}
        return val if isinstance(val, dict) else {}

    cat = safe_get_dict(data, "category")
    cnt = safe_get_dict(data, "contact")
    td = safe_get_dict(data, "title_and_description")
    loc = safe_get_dict(data, "location")
    prc = safe_get_dict(data, "pricing")
    spec = safe_get_dict(data, "specifications")
    med = safe_get_dict(data, "media")

    # RULE 1: Bathrooms & Balconies Logic
    raw_bathrooms = spec.get("bathrooms", "1")
    try:
        bath_num = int(''.join(filter(str.isdigit, str(raw_bathrooms))))
    except ValueError:
        bath_num = 1

    balconies_val = "2" if bath_num >= 4 else "1"

    # RULE 2: Area Math Calculation
    builtup = str(spec.get("builtup_sqft", "na")).strip()
    carpet = str(spec.get("carpet_sqft", "na")).strip()
    super_built = str(spec.get("super_builtup_sqft", "na")).strip()

    def extract_number(val):
        try:
            nums = ''.join(c for c in val if c.isdigit() or c == '.')
            return float(nums) if nums else None
        except ValueError:
            return None

    b_num = extract_number(builtup)
    c_num = extract_number(carpet)
    s_num = extract_number(super_built)

    if b_num is not None:
        if c_num is None: c_num = round(b_num * 0.8, 2)
        if s_num is None: s_num = round(b_num * 1.25, 2)
    elif c_num is not None:
        if b_num is None: b_num = round(c_num / 0.8, 2)
        if s_num is None: s_num = round(b_num * 1.25, 2)
    elif s_num is not None:
        if b_num is None: b_num = round(s_num / 1.25, 2)
        if c_num is None: c_num = round(b_num * 0.8, 2)

    final_builtup = str(int(b_num)) if b_num else "na"
    final_carpet = str(int(c_num)) if c_num else "na"
    final_super = str(int(s_num)) if s_num else "na"

    # RULE 3: Construction Status & Property Age
    raw_status = str(spec.get("construction_status", "")).upper()
    if "UNDER" in raw_status or "CONSTRUCTION" in raw_status:
        construction_status = "UNDER_CONSTRUCTION"
        property_age = "0"
    elif "READY" in raw_status or "MOVE" in raw_status:
        construction_status = "READY_TO_MOVE"
        property_age = spec.get("property_age", "na")
    else:
        construction_status = spec.get("construction_status", "READY_TO_MOVE")
        property_age = spec.get("property_age", "na")

    # RULE 4: Location, Sub-locality & Full Address
    locality_val = loc.get("locality", "na")
    city_val = loc.get("city", "Kolkata")
    state_val = loc.get("state", "West Bengal")
    pincode_val = str(loc.get("pincode", "na")).strip()
    landmark_val = loc.get("landmark", "na")

    sub_locality_val = locality_val

    addr_parts = []
    if locality_val != "na": addr_parts.append(locality_val)
    if city_val != "na": addr_parts.append(city_val)
    if state_val != "na": addr_parts.append(state_val)
    
    base_addr = ", ".join(addr_parts) if addr_parts else "na"
    if pincode_val != "na" and pincode_val:
        full_addr = f"{base_addr} - {pincode_val}"
    else:
        full_addr = base_addr

    # RULE 5: BHK Numeric Calculation
    raw_bhk = spec.get("bhk_type", "na")
    bhk_num_val = spec.get("bhk_numeric", "na")
    if (bhk_num_val == "na" or not bhk_num_val) and raw_bhk != "na":
        extracted_digits = ''.join(filter(str.isdigit, str(raw_bhk)))
        if extracted_digits:
            bhk_num_val = extracted_digits

    # RULE 6: Phone Number Fallback
    raw_phone = str(cnt.get("phone", "na")).strip()
    if not raw_phone or raw_phone.lower() in ["na", "none", "null"]:
        raw_phone = "9073662554"

    # RULE 7: Title & Description Anti-NA Fallbacks
    raw_title = str(td.get("title", "na")).strip()
    raw_desc = str(td.get("description", "na")).strip()

    loc_clean = locality_val if locality_val != "na" else "Garia"
    city_clean = city_val if city_val != "na" else "Kolkata"

    if not raw_title or raw_title.lower() in ["na", "none", "null"]:
        raw_title = "Upohar The Condoville"

    if not raw_desc or raw_desc.lower() in ["na", "none", "null"]:
        raw_desc = f"Flat for Resale in Upohar The Condoville {loc_clean}, {city_clean}"

    # RULE 8: Smart Defaults
    parking_val = spec.get("parking", "YES")
    if not parking_val or str(parking_val).lower() in ["na", "none", "null"]:
        parking_val = "YES"

    facing_val = spec.get("facing_direction", "NORTH EAST")
    if not facing_val or str(facing_val).lower() in ["na", "none", "null"]:
        facing_val = "NORTH EAST"

    created_at_val = data.get("created_at", "few years")
    if not created_at_val or str(created_at_val).lower() in ["na", "none", "null"]:
        created_at_val = "few years"

    return {
        "user_id": data.get("user_id", "ADMIN"),
        "posted_by_type": data.get("posted_by_type", "ADMIN"),
        "category": {
            "purpose": cat.get("purpose", "BUY"),
            "property_type": cat.get("property_type", "RESIDENTIAL"),
            "sub_type": cat.get("sub_type", "FLAT_APARTMENT")
        },
        "contact": {
            "owner_name": cnt.get("owner_name", "Mr Pradeep"),
            "phone": raw_phone,
            "owner_type": cnt.get("owner_type", "AGENT")
        },
        "title_and_description": {
            "title": raw_title,
            "description": raw_desc
        },
        "location": {
            "city": city_val,
            "locality": locality_val,
            "sub_locality": sub_locality_val,
            "landmark": landmark_val,
            "pincode": pincode_val,
            "state": state_val,
            "full_address": full_addr
        },
        "pricing": {
            "price_display": prc.get("price_display", "na"),
            "price_numeric": prc.get("price_numeric", "na"),
            "is_negotiable": prc.get("is_negotiable", True)
        },
        "specifications": {
            "bhk_type": raw_bhk,
            "bhk_numeric": bhk_num_val,
            "builtup_sqft": final_builtup,
            "carpet_sqft": final_carpet,
            "super_builtup_sqft": final_super,
            "floor_no": spec.get("floor_no", "na"),
            "total_floors": spec.get("total_floors", "na"),
            "bathrooms": str(bath_num),
            "balconies": balconies_val,
            "furnishing_status": spec.get("furnishing_status", "na"),
            "construction_status": construction_status,
            "facing_direction": facing_val,
            "property_age": property_age,
            "parking": parking_val,
            "ownership_type": spec.get("ownership_type", "FREEHOLD")
        },
        "amenities": data.get("amenities", []) if isinstance(data, dict) and isinstance(data.get("amenities"), list) else [],
        "media": {
            "images": s3_urls,
            "ai_short_video_url": med.get("ai_short_video_url", "na")
        },
        "created_at": created_at_val
    }


# --- ROUTES ---

@app.route('/')
def index():
    try:
        return render_template('index.html', db_name=DB_NAME, collection_name=COLLECTION_NAME)
    except Exception as e:
        return f"Template Render Error: {str(e)}", 500

@app.route('/api/detect-crop-box', methods=['POST'])
def detect_crop_box():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'}), 400

        file = request.files['image']
        
        img = Image.open(file.stream).convert("RGB")
        img.thumbnail((600, 600))
        
        byte_arr = io.BytesIO()
        img.save(byte_arr, format='JPEG', quality=75)
        base64_str = base64.b64encode(byte_arr.getvalue()).decode('utf-8')

        prompt_text = (
            "Detect the main interior or property room photograph inside this screenshot. "
            "Completely ignore top status bar, header X buttons, floating video windows, bottom WhatsApp/contact buttons, and white spaces. "
            "Return strictly 4 integer coordinates [ymin, xmin, ymax, xmax] normalized from 0 to 1000."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": "image/jpeg", "data": base64_str}}
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json=payload, timeout=20)

        if not res.ok:
            return jsonify({'success': False, 'error': f"Gemini API Error: {res.text}"}), 500

        res_data = res.json()
        raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
        coords = json.loads(raw_text)

        return jsonify({'success': True, 'coords': coords})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-s3-single', methods=['POST'])
def upload_s3_single():
    try:
        if 'image' not in request.files:
            return jsonify({"success": False, "error": "No image provided"}), 400
        
        if not s3_client:
            return jsonify({"success": False, "error": "S3 Credentials missing"}), 500

        file = request.files['image']
        filename = f"cropped_{os.urandom(8).hex()}.jpg"

        s3_client.upload_fileobj(
            file,
            S3_BUCKET,
            filename,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )

        file_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{filename}"
        return jsonify({"success": True, "url": file_url}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/extract-json', methods=['POST'])
def extract_json():
    try:
        if 'data_images' not in request.files:
            return jsonify({"success": False, "error": "No detail screenshots provided"}), 400
        
        data_files = request.files.getlist('data_images')
        s3_urls_raw = request.form.get('s3_urls', '[]')
        
        try:
            s3_urls = json.loads(s3_urls_raw)
        except Exception:
            s3_urls = []

        if not GEMINI_API_KEY:
            return jsonify({"success": False, "error": "GEMINI_API_KEY missing"}), 500

        prompt_text = """
Read all uploaded property screenshots with extreme OCR attention and extract details strictly into JSON:

CRITICAL EXTRACTION RULES:
1. 'title': Extract ONLY the main dark/bold property heading text (e.g. 'Upohar The Condoville').
2. 'description': Extract text line above/around title ending at city name (e.g. 'Flat for Resale in Upohar The Condoville Garia, Kolkata'). STOP immediately after Kolkata.
3. 'contact': Extract 'owner_name' (e.g. Mr Pradeep) and 'phone' number (e.g. 91-9073662554 or 9073662554).
4. 'pricing': Extract 'price_display' (e.g. ₹ 2.72 Crore) and 'price_numeric' (e.g. 27200000).
5. 'location': Extract 'locality' and 'city'. Search web knowledge for the 6-digit 'pincode' and nearest famous 'landmark'.
6. 'amenities': Look closely at green checkmarks and bullet features across all screenshots (e.g. 'Overlooking Park', '1 Covered Parking', 'Vaastu Compliant', 'Separate entry for servant room', 'Partial Power Backup') and extract them into a list of strings.
7. 'specifications':
   - 'bhk_type': Extract BHK text (e.g. '4 BHK').
   - 'bhk_numeric': Extract numeric value of BHK (e.g. '4').
   - 'construction_status': If 'Ready To Move', set 'READY_TO_MOVE'. If 'Under Construction', set 'UNDER_CONSTRUCTION'.
   - 'property_age': Extract age text (e.g., '5-10 Year Old Property').
   - Extract floor_no, total_floors, bathrooms, facing_direction, super_builtup_sqft, carpet_sqft, builtup_sqft, furnishing_status.
8. Return strictly raw JSON without markdown code fences (no ```json).
"""

        parts = [{"text": prompt_text}]

        for file in data_files:
            try:
                img = Image.open(file.stream).convert("RGB")
                img.thumbnail((1000, 1000))
                
                byte_arr = io.BytesIO()
                img.save(byte_arr, format='JPEG', quality=85)
                base64_str = base64.b64encode(byte_arr.getvalue()).decode('utf-8')

                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64_str
                    }
                })
            except Exception as img_err:
                print(f"Image warning: {img_err}")

        gemini_url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key=){GEMINI_API_KEY}"
        res = requests.post(gemini_url, json={"contents": [{"parts": parts}]}, timeout=45)

        if not res.ok:
            return jsonify({"success": False, "error": f"Gemini API Error: {res.text}"}), 500

        res_data = res.json()
        raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
        cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

        try:
            parsed_json = json.loads(cleaned_text)
        except Exception:
            parsed_json = {}

        final_ordered_json = process_and_enforce_rules(parsed_json, s3_urls)
        return jsonify({"success": True, "data": final_ordered_json}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/submit-to-db', methods=['POST'])
def submit_to_db():
    try:
        req_data = request.get_json() or {}
        raw_text = req_data.get('json_data', '')
        
        parsed_data = json.loads(raw_text)
        if collection is not None:
            result = collection.insert_one(parsed_data)
            return jsonify({
                "success": True, 
                "message": f"Data successfully submitted to Database! ID: {str(result.inserted_id)}"
            }), 200
        else:
            return jsonify({"success": True, "message": "Database not configured, but JSON is valid."}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
