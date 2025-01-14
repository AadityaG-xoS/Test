from dotenv import load_dotenv
import os
import json
from flask import Flask, request, jsonify, render_template
import cohere
import logging
from scrapy.http import HtmlResponse
from zyte_api import ZyteAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
cohere_api_key = os.getenv("COHERE_API_KEY")
zyte_api_key = os.getenv("ZYTE_API_KEY")

if not cohere_api_key:
    raise EnvironmentError("COHERE_API_KEY environment variable is not set.")
if not zyte_api_key:
    raise EnvironmentError("ZYTE_API_KEY environment variable is not set.")

# Initialize Cohere client
cohere_client = cohere.Client(cohere_api_key)

# Initialize Zyte client
zyte_client = ZyteAPI(api_key=zyte_api_key)

app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")

        response = cohere_client.chat(
            model="command-r-plus",
            message=f"""
            Analyze the webpage at {url} and provide CSS selectors for extracting the following elements:
            - Review container
            - Review title
            - Review body
            - Review rating
            - Reviewer name

            The output should be a JSON-like dictionary.
            """,
            preamble="You are an AI-assistant chatbot. Provide thorough responses.",
        )

        # Validate the response
        if not response.text.strip():
            raise ValueError("Empty response from Cohere.")

        # Attempt to parse as JSON-like dictionary
        selectors = json.loads(response.text.strip())
        if not isinstance(selectors, dict):
            raise ValueError("Cohere response is not a valid dictionary.")

        logger.info(f"Selectors identified by Cohere: {selectors}")
        return selectors
    except Exception as e:
        logger.error(f"Error identifying selectors with Cohere: {e}")
        return None

def extract_reviews_with_zyte(url, selectors):
    try:
        if not isinstance(selectors, dict):
            raise ValueError("Selectors should be a valid dictionary.")

        logger.info(f"Fetching URL with Zyte: {url}")
        response = zyte_client.get(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch the page with Zyte. Status: {response.status_code}")
            return []

        reviews = []
        scrapy_response = HtmlResponse(url=url, body=response.content, encoding='utf-8')

        # Extract reviews based on selectors
        review_elements = scrapy_response.css(selectors.get('review', 'div.review'))
        for review in review_elements:
            title = review.css(selectors.get('title', '.review-title::text')).get(default="No title").strip()
            body = review.css(selectors.get('body', '.review-body::text')).get(default="No body").strip()
            rating = review.css(selectors.get('rating', '.review-rating::text')).get(default="No rating").strip()
            reviewer = review.css(selectors.get('reviewer', '.reviewer-name::text')).get(default="Anonymous").strip()

            reviews.append({
                "title": title,
                "body": body,
                "rating": rating,
                "reviewer": reviewer
            })

        logger.info(f"Extracted {len(reviews)} reviews.")
        return reviews
    except Exception as e:
        logger.error(f"Error extracting reviews with Zyte: {e}")
        return []

def process_reviews_with_cohere(reviews):
    try:
        if not reviews:
            raise ValueError("No reviews to process.")

        review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
        logger.info("Processing reviews with Cohere AI.")

        prompt = """
        Perform a sentiment analysis on the following reviews and summarize the results:
        """ + "\n".join(review_texts)

        response = cohere_client.generate(
            model='command-r-plus',
            prompt=prompt,
            max_tokens=300,
            temperature=0.5
        )

        if not response.generations:
            raise ValueError("No generations returned from Cohere.")

        processed_reviews = response.generations[0].text.strip()
        logger.info("Reviews processed successfully with Cohere.")
        return processed_reviews
    except Exception as e:
        logger.error(f"Error processing reviews with Cohere: {e}")
        return "Error processing reviews."

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            return render_template('index.html', error="URL is required!")

        try:
            # Identify selectors using Cohere
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                return render_template('index.html', error="Could not identify selectors for the URL!")

            # Extract reviews using Zyte
            reviews = extract_reviews_with_zyte(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            # Process reviews with Cohere AI
            processed_reviews = process_reviews_with_cohere(reviews)
            if not processed_reviews:
                return render_template('index.html', error="Error processing reviews with Cohere.")

            return render_template('index.html', reviews=processed_reviews)
        except Exception as e:
            logger.error(f"Error processing: {e}")
            return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)

