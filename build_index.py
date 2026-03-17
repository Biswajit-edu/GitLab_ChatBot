import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Build GitLab Handbook FAISS index")
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape and re-index"
    )
    parser.add_argument(
        "--max-pages", type=int, default=80, help="Max pages to scrape (default: 80)"
    )
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_google_api_key_here":
        logger.error(
            "GOOGLE_API_KEY not set. Copy .env.example → .env and add your key."
        )
        sys.exit(1)

    from ingestion import scrape_all
    from vector_store import build_index

    logger.info("=== Step 1/2: Scraping GitLab pages ===")
    pages = scrape_all(max_pages=args.max_pages, force=args.force)
    total_chunks = sum(len(p.get("chunks", [])) for p in pages)
    logger.info(f"✅ Scraped {len(pages)} pages, {total_chunks} chunks")

    logger.info("=== Step 2/2: Building FAISS index ===")
    vectorstore = build_index(pages, force=args.force)
    logger.info("✅ Index built and saved to data/faiss_index/")

    logger.info("")
    logger.info("🚀 Ready! Start the app with: streamlit run app.py")


if __name__ == "__main__":
    main()
