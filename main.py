import os
import csv
import time
from typing import List, Dict

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from serpapi import GoogleSearch
import openai
from bs4 import BeautifulSoup
import requests

# --- Configuration ---
# Replace with your actual API keys and search engine ID
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")  # Get from environment variable
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")  # Get from environment variable
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # Get from environment variable


if not all([GOOGLE_API_KEY, GOOGLE_CSE_ID, OPENAI_API_KEY]):
    raise ValueError(
        "Please set the GOOGLE_API_KEY, GOOGLE_CSE_ID, and OPENAI_API_KEY environment variables."
    )

openai.api_key = OPENAI_API_KEY

CSV_FILE = "lead_customer_list.csv"
SEARCH_KEYWORDS = [
    "software development company in New York",
    "marketing agency in London",
    "web design company in Los Angeles",
    # Add more keywords here
]
MAX_RESULTS_PER_KEYWORD = 5  # Number of results to fetch per keyword
MAX_RETRIES = 3
RETRY_DELAY = 5

# --- Helper Functions ---


def google_search_cse(query: str, num_results: int = 10) -> List[str]:
    """
    Searches Google using the Custom Search Engine API and returns a list of result URLs.

    Args:
        query: The search query.
        num_results: The number of results to return.

    Returns:
        A list of URLs.
    """
    service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
    urls = []
    start_index = 1
    while len(urls) < num_results:
        try:
            res = (
                service.cse()
                .list(q=query, cx=GOOGLE_CSE_ID, start=start_index, num=min(10, num_results - len(urls)))
                .execute()
            )
            if "items" in res:
                for item in res["items"]:
                    urls.append(item["link"])
            start_index += 10
            if start_index > 100:
                break
        except HttpError as e:
            print(f"An HTTP error occurred: {e}")
            break
    return urls


def extract_company_info(url: str) -> Dict:
    """
    Extracts company information from a URL using OpenAI.

    Args:
        url: The URL of the company website.

    Returns:
        A dictionary containing company name, address, tel, fax, and overview.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, "html.parser")
        text_content = soup.get_text(separator=" ", strip=True)

        prompt = f"""
        Extract the following information from the text below:
        - Company Name
        - Address
        - Telephone Number (Tel)
        - Fax Number (Fax)
        - A short overview of the company (Overview)

        If any information is not found, leave the field blank.

        Text:
        {text_content}
        """

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts information from text."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        extracted_info = completion.choices[0].message.content

        # Basic parsing of the extracted information (can be improved)
        company_data = {
            "Company Name": "",
            "Address": "",
            "Tel": "",
            "Fax": "",
            "Overview": "",
        }
        for line in extracted_info.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "Company Name":
                    company_data["Company Name"] = value
                elif key == "Address":
                    company_data["Address"] = value
                elif key == "Tel":
                    company_data["Tel"] = value
                elif key == "Fax":
                    company_data["Fax"] = value
                elif key == "Overview":
                    company_data["Overview"] = value

        return company_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None


def save_to_csv(data: List[Dict], filename: str):
    """
    Saves the extracted data to a CSV file.

    Args:
        data: A list of dictionaries containing company information.
        filename: The name of the CSV file.
    """
    if not data:
        print("No data to save.")
        return

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["Keyword", "Company Name", "Address", "Tel", "Fax", "Overview", "URL"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"Data saved to {filename}")


# --- Main Execution ---
def main():
    """
    Main function to generate the lead customer list.
    """
    all_company_data = []
    for keyword in SEARCH_KEYWORDS:
        print(f"Searching for: {keyword}")
        urls = google_search_cse(keyword, MAX_RESULTS_PER_KEYWORD)
        print(f"Found {len(urls)} URLs for keyword: {keyword}")

        for url in urls:
            print(f"Processing URL: {url}")
            retries = 0
            while retries < MAX_RETRIES:
                company_info = extract_company_info(url)
                if company_info:
                    company_info["Keyword"] = keyword
                    company_info["URL"] = url
                    all_company_data.append(company_info)
                    break
                else:
                    retries += 1
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
            if retries == MAX_RETRIES:
                print(f"Failed to process URL {url} after {MAX_RETRIES} retries.")

    save_to_csv(all_company_data, CSV_FILE)


if __name__ == "__main__":
    main()
