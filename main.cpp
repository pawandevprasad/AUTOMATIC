#include <iostream>
#include <vector>
#include <string>
#include <stdexcept>
#include <opencv2/opencv.hpp>
#include <curl/curl.h>

// Helper Function: Callback to write stream data from libcurl HTTP request
static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t totalSize = size * nmemb;
    std::vector<uchar>* stream = static_cast<std::vector<uchar>*>(userp);
    stream->insert(stream->end(), static_cast<uchar*>(contents), static_cast<uchar*>(contents) + totalSize);
    return totalSize;
}

// HTTP Downloader: Downloads raw image bytes from URL into cv::Mat
cv::Mat downloadImage(const std::string& url) {
    CURL* curl = curl_easy_init();
    std::vector<uchar> stream;
    
    if (!curl) {
        throw std::runtime_error("Failed to initialize CURL instance.");
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &stream);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 15L);

    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        throw std::runtime_error("HTTP Request failed: " + std::string(curl_easy_strerror(res)));
    }

    cv::Mat decodedImg = cv::imdecode(stream, cv::IMREAD_COLOR);
    if (decodedImg.empty()) {
        throw std::runtime_error("Failed to decode fetched image stream into Mat format.");
    }

    return decodedImg;
}

// Core C++ Image Processing Engine (OpenCV C++ Native Execution)
cv::Mat processWatermarkAI(const cv::Mat& inputImg) {
    cv::Mat gray, adaptiveThresh, edges, combinedMask, dilatedMask;

    // 1. Convert BGR Color Space to Grayscale
    cv::cvtColor(inputImg, gray, cv::COLOR_BGR2GRAY);

    // 2. Adaptive Gaussian Thresholding to isolate text/logo watermark overlay
    cv::adaptiveThreshold(gray, adaptiveThresh, 255, cv::ADAPTIVE_THRESH_GAUSSIAN_C, cv::THRESH_BINARY_INV, 11, 2);

    // 3. Canny Edge Detector for exact boundary identification
    cv::Canny(gray, edges, 100, 200);

    // 4. Bitwise OR channel fusion
    cv::bitwise_or(adaptiveThresh, edges, combinedMask);

    // 5. Morphological Dilation to cover soft edge translucency
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::dilate(combinedMask, dilatedMask, kernel, cv::Point(-1, -1), 2);

    // 6. Pass 1: Fast Marching Method (Telea Inpainting)
    cv::Mat inpaintedPass1;
    cv::inpaint(inputImg, dilatedMask, inpaintedPass1, 3.0, cv::INPAINT_TELEA);

    // 7. Pass 2: Navier-Stokes Fluid Dynamics Inpainting
    cv::Mat inpaintedPass2;
    cv::inpaint(inpaintedPass1, dilatedMask, inpaintedPass2, 3.0, cv::INPAINT_NS);

    // 8. Output Noise Reduction Filter
    cv::Mat finalOutput;
    cv::fastNlMeansDenoiseColored(inpaintedPass2, finalOutput, 10.0, 10.0, 7, 21);

    return finalOutput;
}

int main(int argc, char** argv) {
    std::cout << "==========================================================" << std::endl;
    std::cout << "  Enterprise C++ AI Watermark Removal Engine (Native Core)  " << std::endl;
    std::cout << "==========================================================" << std::endl;

    if (argc < 3) {
        std::cout << "\n[Usage]: ./watermark_engine <INPUT_IMAGE_URL> <OUTPUT_PATH>" << std::endl;
        std::cout << "[Example]: ./watermark_engine https://example.com/sample.jpg result.jpg\n" << std::endl;
        return 1;
    }

    std::string imageUrl = argv[1];
    std::string outputPath = argv[2];

    try {
        std::cout << "[+] Downloading Image from URL: " << imageUrl << std::endl;
        cv::Mat rawImage = downloadImage(imageUrl);

        std::cout << "[+] Processing Image through C++ OpenCV Inpainting Engine..." << std::endl;
        cv::Mat resultImage = processWatermarkAI(rawImage);

        bool saved = cv::imwrite(outputPath, resultImage);
        if (saved) {
            std::cout << "[SUCCESS] Image processed and saved successfully to: " << outputPath << std::endl;
        } else {
            std::cerr << "[ERROR] Failed to write processed image file to disk." << std::endl;
            return -1;
        }

    } catch (const std::exception& e) {
        std::cerr << "[CRITICAL EXCEPTION]: " << e.what() << std::endl;
        return -1;
    }

    return 0;
}
