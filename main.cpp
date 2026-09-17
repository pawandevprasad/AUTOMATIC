cd /home/ubuntu/app && cat << 'EOF' > main.cpp
#include <iostream>
#include <vector>
#include <string>
#include <stdexcept>
#include <opencv2/opencv.hpp>
#include <curl/curl.h>

static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t totalSize = size * nmemb;
    std::vector<uchar>* stream = static_cast<std::vector<uchar>*>(userp);
    stream->insert(stream->end(), static_cast<uchar*>(contents), static_cast<uchar*>(contents) + totalSize);
    return totalSize;
}

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

cv::Mat processWatermarkAI(const cv::Mat& inputImg) {
    cv::Mat gray, adaptiveThresh, edges, combinedMask, dilatedMask;
    cv::cvtColor(inputImg, gray, cv::COLOR_BGR2GRAY);
    cv::adaptiveThreshold(gray, adaptiveThresh, 255, cv::ADAPTIVE_THRESH_GAUSSIAN_C, cv::THRESH_BINARY_INV, 11, 2);
    cv::Canny(gray, edges, 100, 200);
    cv::bitwise_or(adaptiveThresh, edges, combinedMask);
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::dilate(combinedMask, dilatedMask, kernel, cv::Point(-1, -1), 2);

    cv::Mat inpaintedPass1, inpaintedPass2, finalOutput;
    cv::inpaint(inputImg, dilatedMask, inpaintedPass1, 3.0, cv::INPAINT_TELEA);
    cv::inpaint(inpaintedPass1, dilatedMask, inpaintedPass2, 3.0, cv::INPAINT_NS);
    cv::fastNlMeansDenoiseColored(inpaintedPass2, finalOutput, 10.0, 10.0, 7, 21);

    return finalOutput;
}

int main(int argc, char** argv) {
    std::cout << "==========================================================" << std::endl;
    std::cout << "  Enterprise C++ AI Watermark Removal Engine (Native Core)  " << std::endl;
    std::cout << "==========================================================" << std::endl;

    if (argc < 3) {
        std::cout << "\n[Usage]: ./watermark_engine <INPUT_IMAGE_URL> <OUTPUT_PATH>\n" << std::endl;
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
            std::cout << "[SUCCESS] Image saved successfully to: " << outputPath << std::endl;
        } else {
            std::cerr << "[ERROR] Failed to write processed image file." << std::endl;
            return -1;
        }
    } catch (const std::exception& e) {
        std::cerr << "[CRITICAL EXCEPTION]: " << e.what() << std::endl;
        return -1;
    }
    return 0;
}
EOF
git add main.cpp && git commit -m "Updated main.cpp with robust enterprise C++ engine" && git push -u origin main --force
    
