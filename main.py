import os
import cv2
import numpy as np
import requests
import cloudinary
import cloudinary.uploader
from PIL import Image
from io import BytesIO
from fastapi import FastAPI, HTTPException, Query
import onnxruntime as ort

# Cloudinary Configuration
cloudinary.config(
    cloud_name="uq8eywxb",
    api_key="118664333995381",
    api_secret="JUVeYTckPyu6LknKqYQ6PEuNoM0"
)

app = FastAPI(title="Watermark Removal AI Engine")

def download_image(url: str) -> np.ndarray:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert('RGB')
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image download failed: {str(e)}")

def ai_inpaint_watermark(image: np.ndarray, passes: int = 5) -> np.ndarray:
    """
    Multi-pass Watermark Removal Engine using OpenCV & Edge Detection Algorithms.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Adaptive thresholding for text and logo detection
    adaptive_thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Edge detection for fine watermark boundaries
    edges = cv2.Canny(gray, 100, 200)
    
    # Combine mask channels
    combined_mask = cv2.bitwise_or(adaptive_thresh, edges)
    
    # Dilate mask to ensure translucent edges are covered
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated_mask = cv2.dilate(combined_mask, kernel, iterations=2)
    
    # Dual Inpainting passes (Navier-Stokes & Fast Marching Telea)
    inpainted = cv2.inpaint(image, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    inpainted = cv2.inpaint(inpainted, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_NS)
    
    # Denoising filter for output smooth quality
    final_output = cv2.fastNlMeansDenoiseColored(inpainted, None, 10, 10, 7, 21)
    
    return final_output

@app.get("/")
def read_root():
    return {
        "status": "online",
        "engine": "Enterprise Watermark Removal AI Engine",
        "version": "1.0.0"
    }

@app.post("/process-watermark")
def process_watermark(image_url: str = Query(...), passes: int = Query(5)):
    # 1. Fetch input image
    raw_img = download_image(image_url)
    
    # 2. Process image with inpainting engine
    processed_img = ai_inpaint_watermark(raw_img, passes=passes)
    
    # 3. Encode result to JPG
    is_success, buffer = cv2.imencode(".jpg", processed_img)
    if not is_success:
        raise HTTPException(status_code=500, detail="Failed to encode image")
    
    # 4. Upload result to Cloudinary
    upload_result = cloudinary.uploader.upload(
        buffer.tobytes(),
        folder="watermark_removed_results"
    )
    
    return {
        "success": True,
        "processed_url": upload_result.get("secure_url"),
        "public_id": upload_result.get("public_id")
}

