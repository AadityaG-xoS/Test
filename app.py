import os
import json
import time
import logging
import requests
from flask import Flask, request, render_template
import cohere
from dotenv import load_dotenv
from scrapy.http import HtmlResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
cohere_api_key = os.getenv("COHERE_API_KEY")
web_scraping_api_key = os.getenv("WEB_SCRAPING_API_KEY")

if not cohere_api_key:
    raise EnvironmentError("COHERE_API_KEY environment variable is not set.")
if not web_scraping_api_key:
    raise EnvironmentError("WEB_SCRAPING_API_KEY environment variable is not set.")

# Initialize Cohere client
cohere_client = cohere.Client(cohere_api_key)

# Flask app
app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")
        response = cohere_client.generate(
            model="command",
            prompt=f"""
                Analyze the webpage at {url} and provide CSS selectors for extracting the following elements:
                - Review container
                - Review title
                - Review body
                - Review rating
                - Reviewer name

                The output should be a JSON-like dictionary. Only return structured JSON format and no other text in output. Example:
                {{
                    "review": ".product-reviews",
                    "title": ".review-title",
                    "body": ".review-body",
                    "rating": ".review-rating",
                    "reviewer": ".reviewer"
                }}
            """,
            max_tokens=300
        )

        # Log full response for debugging
        logger.info(f"Cohere API response: {response}")

        if not response.generations or not response.generations[0].text:
            raise ValueError("Cohere response does not contain valid text.")

        selectors = response.generations[0].text.strip()
        logger.info(f"Selectors identified by Cohere: {selectors}")

        # Convert to dictionary
        selectors_dict = json.loads(selectors)
        if not isinstance(selectors_dict, dict):
            raise ValueError("Selectors response is not a valid dictionary.")

        return selectors_dict
    except Exception as e:
        logger.error(f"Error identifying selectors with Cohere: {e}")
        return None

def extract_reviews_with_webscraping(url, selectors):
    try:
        if not isinstance(selectors, dict):
            raise ValueError("Selectors should be a valid dictionary.")

        reviews = []
        page_number = 1
        retry_limit = 5
        headers = {
            "Authorization": f"Bearer {web_scraping_api_key}"  # Correct header format for authentication
        }

        while page_number <= retry_limit:
            logger.info(f"Fetching page {page_number} with Web Scraping API: {url}?page={page_number}")
            response = requests.post(
                "https://api.webscrapingapi.com/v1",  # Correct endpoint for extraction
                headers=headers,
                json={
                    "url": f"{url}?page={page_number}",
                    "httpResponseBody": True,
                    "browserHtml": True,  # Ensure browser-rendered HTML is extracted
                    "renderJS": True,  # Ensure JavaScript is rendered for dynamic content
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch the page with Web Scraping API. Status: {response.status_code}")
                break

            response_json = response.json()
            browser_html = response_json.get("content")

            if not browser_html:
                logger.warning(f"No browser HTML found on page {page_number}. Retrying...")
                time.sleep(2)
                continue

            # Log a snippet of the HTML content for debugging
            logger.info(f"Fetched HTML for page {page_number}: {browser_html[:500]}...")

            # Save the HTML response for debugging purposes
            with open(f"page_{page_number}_browser_html.html", "w", encoding="utf-8") as fp:
                fp.write(browser_html)

            scrapy_response = HtmlResponse(url=f"{url}?page={page_number}", body=browser_html, encoding='utf-8')
            review_elements = scrapy_response.css(selectors.get('review'))

            if not review_elements:
                logger.info("No more reviews found, stopping pagination.")
                break

            for review in review_elements:
                title = review.css(selectors.get('title')).get(default='').strip()
                body = review.css(selectors.get('body')).get(default='').strip()
                rating = review.css(selectors.get('rating')).get(default='').strip()
                reviewer = review.css(selectors.get('reviewer')).get(default='').strip()

                reviews.append({
                    "title": title,
                    "body": body,
                    "rating": rating,
                    "reviewer": reviewer
                })

            page_number += 1
            time.sleep(2)  # Add delay to prevent hitting rate limits

        logger.info(f"Extracted {len(reviews)} reviews across {page_number - 1} pages.")
        return reviews

    except requests.exceptions.Timeout as e:
        logger.error(f"Request timed out: {e}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error with the request: {e}")
        return []
    except Exception as e:
        logger.error(f"Error extracting reviews with Web Scraping API: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def home():
    reviews = []
    error_message = None

    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            error_message = "URL is required!"
            return render_template('index.html', reviews=reviews, error=error_message)

        try:
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                error_message = "Could not identify selectors for the URL!"
                return render_template('index.html', reviews=reviews, error=error_message)

            logger.info(f"Selectors passed to Web Scraping API: {selectors}")

            reviews = extract_reviews_with_webscraping(url, selectors)
            if not reviews:
                error_message = "No reviews found!"
                return render_template('index.html', reviews=reviews, error=error_message)

            return render_template('index.html', reviews=reviews)
        except Exception as e:
            logger.error(f"Error processing: {e}")
            error_message = f"Error: {str(e)}"
            return render_template('index.html', reviews=reviews, error=error_message)

    return render_template('index.html', reviews=reviews)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
