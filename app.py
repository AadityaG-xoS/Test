from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
from jina import Client

load_dotenv()
api_key = os.getenv("JINA_API_KEY")

app = Flask(__name__)

# Jina client configuration
client = Client(host="https://test-d2se.onrender.com", api_key=api_key)

def extract_reviews_with_playwright(url):
    # Launch Playwright to open a browser
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Use Chromium for headless mode
        page = browser.new_page()
        page.goto(url)
        
        # Wait for the reviews section to load (can be modified to suit the structure of the page)
        page.wait_for_selector('div.review')

        reviews = []

        # Example CSS selector for review elements (this may change based on the actual product page)
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

        # Handle pagination if applicable (modify the selector to work with the pagination button on the page)
        next_page_button = page.query_selector('a.next')  # Example of pagination button
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
            # Check if next page button is still available, if not break
            next_page_button = page.query_selector('a.next')

        browser.close()

    return reviews

def process_reviews_with_jina(reviews):
    # Now, we send the reviews to Jina AI for processing
    review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]

    # Sending the review text to Jina model for extracting structured information
    result = client.post('/reviews', inputs=review_texts)

    return result

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    url = request.args.get('page')  # Get the product URL from the query parameters
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    # Extract reviews using Playwright for dynamic content
    reviews = extract_reviews_with_playwright(url)

    # Process reviews with Jina AI for structured extraction
    result = process_reviews_with_jina(reviews)

    # Return the processed result
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
