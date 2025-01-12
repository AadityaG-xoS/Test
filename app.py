from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, render_template
from playwright.sync_api import sync_playwright
from jina import Client
import subprocess

load_dotenv()
api_key = os.getenv("JINA_API_KEY")

def install_playwright_browsers():
    if not os.path.exists("/opt/render/.cache/ms-playwright"):
        subprocess.run(["playwright", "install"], check=True)

install_playwright_browsers()

app = Flask(__name__)

# Jina client configuration
client = Client(host="https://test-d2se.onrender.com", api_key=api_key)

def extract_reviews_with_playwright(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Navigate to the URL
        page.goto(url)
        
        # Wait for the page to load completely (network idle state)
        page.wait_for_load_state('networkidle')  # Ensure no active network requests are pending
        
        # Initialize an empty list to store reviews
        reviews = []

        try:
            # Increase the timeout to 60 seconds to wait for the reviews to load
            page.wait_for_selector('div.review', timeout=60000)  # 60 seconds timeout for reviews

            review_elements = page.query_selector_all('div.review')
            for review in review_elements:
                title = review.query_selector('.review-title').text_content().strip() if review.query_selector('.review-title') else "No title"
                body = review.query_selector('.review-body').text_content().strip() if review.query_selector('.review-body') else "No body"
                rating = review.query_selector('.review-rating').text_content().strip() if review.query_selector('.review-rating') else "No rating"
                reviewer = review.query_selector('.reviewer-name').text_content().strip() if review.query_selector('.reviewer-name') else "Anonymous"
                
                reviews.append({
                    "title": title,
                    "body": body,
                    "rating": rating,
                    "reviewer": reviewer
                })

            # Handle pagination and extract reviews from subsequent pages
            next_page_button = page.query_selector('a.next')
            while next_page_button:
                next_page_button.click()
                page.wait_for_selector('div.review')
                review_elements = page.query_selector_all('div.review')
                for review in review_elements:
                    title = review.query_selector('.review-title').text_content().strip() if review.query_selector('.review-title') else "No title"
                    body = review.query_selector('.review-body').text_content().strip() if review.query_selector('.review-body') else "No body"
                    rating = review.query_selector('.review-rating').text_content().strip() if review.query_selector('.review-rating') else "No rating"
                    reviewer = review.query_selector('.reviewer-name').text_content().strip() if review.query_selector('.reviewer-name') else "Anonymous"
                    
                    reviews.append({
                        "title": title,
                        "body": body,
                        "rating": rating,
                        "reviewer": reviewer
                    })
                next_page_button = page.query_selector('a.next')

        except Exception as e:
            print(f"Error while fetching reviews: {str(e)}")
        
        # Optional: Capture a screenshot for debugging if needed
        page.screenshot(path='screenshot.png')  # This will save the screenshot in the current directory

        browser.close()
    return reviews

def process_reviews_with_jina(reviews):
    review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
    result = client.post('/reviews', inputs=review_texts)
    return result

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        url = request.form.get('url')  # Get the URL from the form
        if not url:
            return render_template('index.html', error="URL is required!")

        # Extract reviews using Playwright for dynamic content
        reviews = extract_reviews_with_playwright(url)

        # Process reviews with Jina AI for structured extraction
        result = process_reviews_with_jina(reviews)

        # Return the reviews and results to the user
        return render_template('index.html', reviews=result)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
