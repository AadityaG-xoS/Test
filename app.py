from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, render_template
import cohere
import logging
import scrapy
from scrapy_splash import SplashRequest
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.http import HtmlResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
cohere_api_key = os.getenv("COHERE_API_KEY")  # Make sure your API key is set as an environment variable
if not cohere_api_key:
    raise EnvironmentError("COHERE_API_KEY environment variable is not set.")

# Initialize Cohere Client
cohere_client = cohere.Client(cohere_api_key)

app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")
        
        # Create a prompt to instruct Cohere to detect the selectors
        prompt = f"""
        Analyze the page at {url} and identify CSS selectors for the following:
        - Review container
        - Review title
        - Review body
        - Review rating
        - Reviewer name
        Return the selectors in the form of a dictionary, for example:
        {{
            "review": "div.review",
            "title": ".review-title",
            "body": ".review-body",
            "rating": ".review-rating",
            "reviewer": ".reviewer-name"
        }}
        """

        # Send the prompt to Cohere for generating CSS selectors
        response = cohere_client.generate(
            model='command-xlarge',  # Use Cohere's best model for this task
            prompt=prompt,
            max_tokens=150,  # Limit response length
            temperature=0.5
        )

        selectors = response.generations[0].text.strip()
        if not selectors:
            logger.error("No selectors identified by Cohere.")
            return None
        logger.info(f"Selectors identified by Cohere: {selectors}")
        return selectors
    except Exception as e:
        logger.error(f"Error while identifying selectors with Cohere: {e}")
        return None

class ReviewSpider(scrapy.Spider):
    name = "review_spider"
    
    def __init__(self, url, selectors, *args, **kwargs):
        super(ReviewSpider, self).__init__(*args, **kwargs)
        self.url = url
        self.selectors = selectors

    def start_requests(self):
        yield SplashRequest(self.url, self.parse, args={'wait': 2})

    def parse(self, response):
        reviews = []
        review_elements = response.css(self.selectors.get('review', 'div.review'))
        
        for review in review_elements:
            title = review.css(self.selectors.get('title', '.review-title::text')).get(default="No title").strip()
            body = review.css(self.selectors.get('body', '.review-body::text')).get(default="No body").strip()
            rating = review.css(self.selectors.get('rating', '.review-rating::text')).get(default="No rating").strip()
            reviewer = review.css(self.selectors.get('reviewer', '.reviewer-name::text')).get(default="Anonymous").strip()

            reviews.append({
                "title": title,
                "body": body,
                "rating": rating,
                "reviewer": reviewer
            })
        
        logger.info(f"Extracted {len(reviews)} reviews.")
        return reviews

def extract_reviews_with_scrapy(url, selectors):
    reviews = []

    settings = Settings()
    settings.set('BOT_NAME', 'scrapybot')
    settings.set('ROBOTSTXT_OBEY', False)
    settings.set('DOWNLOADER_MIDDLEWARES', {
        'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
        'scrapy_splash.SplashMiddleware': 725,
    })
    settings.set('SPIDER_MIDDLEWARES', {
        'scrapy_splash.SplashDeduplicateArgsMiddleware': 100,
    })
    settings.set('DUPEFILTER_CLASS', 'scrapy_splash.SplashAwareDupeFilter')
    settings.set('SPLASH_URL', 'http://localhost:8050')

    process = CrawlerProcess(settings)
    spider = ReviewSpider(url, selectors)
    process.crawl(spider)
    
    try:
        process.start()
    except Exception as e:
        logger.error(f"Error while scraping with Scrapy: {e}")

    return spider.reviews

def process_reviews_with_cohere(reviews):
    try:
        review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
        logger.info("Sending reviews to Cohere for processing.")
        
        # Send the reviews to Cohere for processing
        response = cohere_client.generate(
            model='command-xlarge',
            prompt="Process these reviews and provide a sentiment analysis summary:\n" + "\n".join(review_texts),
            max_tokens=200,
            temperature=0.5
        )
        
        processed_reviews = response.generations[0].text.strip()
        logger.info("Reviews processed successfully with Cohere.")
        return processed_reviews
    except Exception as e:
        logger.error(f"Error while processing reviews with Cohere: {e}")
        return []

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

            # Extract reviews using Scrapy with dynamic selectors
            reviews = extract_reviews_with_scrapy(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            # Process reviews with Cohere AI
            processed_reviews = process_reviews_with_cohere(reviews)
            if not processed_reviews:
                return render_template('index.html', error="Error processing reviews with Cohere.")

            return render_template('index.html', reviews=processed_reviews)
        except Exception as e:
            logger.error(f"Error in processing: {e}")
            return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
