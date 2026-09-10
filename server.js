const express = require('express');
const path = require('path');
const AWS = require('aws-sdk');

const app = express();
const PORT = process.env.PORT || 3000;

// JSON Payload limit set for Base64 Images
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Configure AWS S3 using Render Environment Variables
const s3 = new AWS.S3({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION
});

// Endpoint to fetch Gemini API Key safely
app.get('/api/get-gemini-key', (req, res) => {
  res.json({ apiKey: process.env.GEMINI_API_KEY || '' });
});

// Endpoint to upload base64 image directly to S3
app.post('/api/upload-s3', async (req, res) => {
  try {
    const { imageBase64, filename } = req.body;
    if (!imageBase64) return res.status(400).json({ error: 'Image data missing' });

    const base64Data = Buffer.from(imageBase64.replace(/^data:image\/\w+;base64,/, ""), 'base64');

    const params = {
      Bucket: process.env.AWS_BUCKET_NAME,
      Key: filename || `cropped_property_${Date.now()}.jpg`,
      Body: base64Data,
      ContentEncoding: 'base64',
      ContentType: 'image/jpeg'
    };

    const data = await s3.upload(params).promise();
    res.json({ success: true, url: data.Location });
  } catch (err) {
    console.error('S3 Upload Error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

