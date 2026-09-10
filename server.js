const express = require('express');
const path = require('path');
const AWS = require('aws-sdk');

const app = express();
const PORT = process.env.PORT || 3000;

// Base64 images ke liye JSON Payload limit set ki gayi hai
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

// Serve static files from 'public' folder
app.use(express.static(path.join(__dirname, 'public')));

// Configure AWS S3 from Render Environment Variables
const s3 = new AWS.S3({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION || 'ap-south-1'
});

// Endpoint: Gemini Key safely return karein
app.get('/api/get-gemini-key', (req, res) => {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'Render me GEMINI_API_KEY environment variable missing hai!' });
  }
  res.json({ apiKey });
});

// Endpoint: Cropped Base64 Image ko S3 par Upload karein
app.post('/api/upload-s3', async (req, res) => {
  try {
    const { imageBase64, filename } = req.body;

    if (!imageBase64) {
      return res.status(400).json({ error: 'Image data missing hai.' });
    }

    const bucketName = process.env.AWS_BUCKET_NAME;
    if (!bucketName) {
      return res.status(500).json({ error: 'Render me AWS_BUCKET_NAME variable missing hai!' });
    }

    const base64Data = Buffer.from(
      imageBase64.replace(/^data:image\/\w+;base64,/, ""),
      'base64'
    );

    const params = {
      Bucket: bucketName,
      Key: filename || `cropped_property_${Date.now()}.jpg`,
      Body: base64Data,
      ContentEncoding: 'base64',
      ContentType: 'image/jpeg'
    };

    const s3Result = await s3.upload(params).promise();
    
    res.json({ 
      success: true, 
      url: s3Result.Location 
    });
  } catch (err) {
    console.error('S3 Upload Failure:', err);
    res.status(500).json({ error: err.message || 'S3 upload fail ho gaya.' });
  }
});

// Fallback Route
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
