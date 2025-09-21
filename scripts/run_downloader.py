import os
import sys
import logging
from src.search.batch.downloader import S3BatchDownloader
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_downloader")


def main():
    try:
        downloader = S3BatchDownloader()
        output = "consolidated_data.csv"
        logger.info(f"Starting downloader, will write to: {os.path.abspath(output)}")
        path = downloader.download_to_file(output_path=output, file_format="csv")
        logger.info(f"Downloader finished. File written to: {os.path.abspath(path)}")
    except Exception as e:
        logger.exception(f"Downloader failed: {e}")


if __name__ == '__main__':
    main()
