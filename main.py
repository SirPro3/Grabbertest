import requests
from tqdm import tqdm
import json
import re
from concurrent.futures import ThreadPoolExecutor


def get_all_spaces():
    url = "https://huggingface.co/api/spaces"
    params = {
        "full": "true",
        "limit": 50,
        "page": 1
    }
    all_spaces = []

    with tqdm(desc="Scraping Spaces", unit="page") as pbar:
        while True:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                print(f"Error fetching page {params['page']}")
                break

            data = response.json()
            if not data:
                break

            all_spaces.extend(data)
            params["page"] += 1
            pbar.update(1)
            pbar.set_postfix({"spaces": len(all_spaces)})

    return all_spaces

def list_space_files(space_id):
    files = []
    stack = [""]

    while stack:
        current_dir = stack.pop()
        url = f"https://huggingface.co/api/spaces/{space_id}/tree/main/{current_dir}"
        response = requests.get(url)
        if response.status_code == 200:
            items = response.json()
            for item in items:
                if item['type'] == 'file':
                    files.append(f"{current_dir}{item['path']}")
                elif item['type'] == 'directory':
                    stack.append(f"{current_dir}{item['path']}/")
        else:
            pass  # Silent error for cleaner output
    return files

def scan_file(space_id, file_path):
    try:
        text_extensions = ['py', 'txt', 'env', 'json', 'md', 'yaml', 'yml', 'js', 'html']
        if file_path.split('.')[-1].lower() not in text_extensions:
            return []

        raw_url = f"https://huggingface.co/spaces/{space_id}/raw/main/{file_path}"
        response = requests.get(raw_url, timeout=10)
        if response.status_code == 200:
            return re.findall(r'sk-[a-zA-Z0-9]{48}', response.text)
        return []
    except:
        return []

def main():
    spaces = get_all_spaces()
    found_keys = set()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []

        for space in spaces:
            space_id = space['id']
            files = list_space_files(space_id)

            for file in files:
                futures.append(
                    executor.submit(
                        scan_file,
                        space_id,
                        file
                    )
                )

        for future in tqdm(futures, desc="Scanning files", unit="file"):
            keys = future.result()
            if keys:
                found_keys.update(keys)

    with open("found_keys.txt", "w") as f:
        f.write("\n".join(found_keys))

    print(f"\nFound {len(found_keys)} unique API keys")

if __name__ == "__main__":
    main()
