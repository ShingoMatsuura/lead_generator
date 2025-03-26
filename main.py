import os
import csv
import time
from typing import List, Dict

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI

from bs4 import BeautifulSoup
import requests

# --- Configuration ---
# Replace with your actual API keys and search engine ID
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")  # Get from environment variable
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")  # Get from environment variable
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # Get from environment variable


client = OpenAI(api_key=OPENAI_API_KEY)

if not all([GOOGLE_API_KEY, GOOGLE_CSE_ID, OPENAI_API_KEY]):
    raise ValueError(
        "Please set the GOOGLE_API_KEY, GOOGLE_CSE_ID, and OPENAI_API_KEY environment variables."
    )


CSV_FILE = "lead_customer_list.csv"
SEARCH_KEYWORDS = [
    "大規模修繕",
    "外壁改修",
    "防水工事",
    "マンション管理",
    "リフォーム 施工"
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
        以下の情報をテキスト情報から抽出してください。:

        - 会社名
        - 住所
        - 代表者名
        - TEL
        - FAX
        - 事業内容

        もし情報が見つからなければ、空白を設定してください。

        テキスト情報:
        {text_content}
        """

        completion = client.chat.completions.create(model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "あなたはWeb上から取得した情報から会社名、住所といった企業情報を抽出し整理するアシスタントです。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2)

        extracted_info = completion.choices[0].message.content

        # Basic parsing of the extracted information (can be improved)
        company_data = {
            "会社名": "",
            "住所": "",
            "代表者名": "",
            "TEL": "",
            "FAX": "",
            "事業内容": ""
        }
        for line in extracted_info.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "会社名":
                    company_data["会社名"] = value
                elif key == "住所":
                    company_data["住所"] = value
                elif key == "代表者名":
                    company_data["代表者名"] = value
                elif key == "TEL":
                    company_data["TEL"] = value
                elif key == "FAX":
                    company_data["FAX"] = value
                elif key == "事業内容":
                    company_data["事業内容"] = value
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
