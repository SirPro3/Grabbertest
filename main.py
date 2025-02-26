import requests
import time
import re
import os
from tqdm import tqdm
import concurrent.futures

def get_all_spaces():
    """Fetch all public Hugging Face spaces without page limit."""
    print("Fetching all public Hugging Face spaces...")
    spaces = []
    page = 1

    with tqdm(desc="Fetching spaces") as pbar:
        while True:  # No page limit now
            url = f"https://huggingface.co/api/spaces?limit=100&page={page}&sort=likes"
            response = requests.get(url)

            if response.status_code != 200:
                print(f"Error fetching page {page}: {response.status_code}")
                break

            data = response.json()
            if not data:  # Empty result, we've reached the end
                break

            new_spaces = len(data)
            spaces.extend(data)
            page += 1
            pbar.update(new_spaces)
            pbar.set_description(f"Fetching spaces (found: {len(spaces)})")
            time.sleep(0.5)  # Being nice to the API

    print(f"Found {len(spaces)} spaces total.")
    return spaces

def search_for_openai_keys(space_id):
    """Search a specific space for OpenAI API keys."""
    # Common patterns for OpenAI API keys
    openai_key_pattern = re.compile(r'sk-[a-zA-Z0-9]{48}')
    config_patterns = [
        re.compile(r'openai_api_key\s*=\s*[\'"]([^\'"]+)[\'"]'),
        re.compile(r'OPENAI_API_KEY\s*=\s*[\'"]([^\'"]+)[\'"]'),
        re.compile(r'api_key\s*=\s*[\'"]([^\'"]+)[\'"]')
    ]

    found_keys = []

    # API endpoints to check
    files_url = f"https://huggingface.co/api/spaces/{space_id}/files"

    try:
        response = requests.get(files_url)
        if response.status_code != 200:
            return []

        files = response.json()

        for file in files:
            if not file.get('path'):
                continue

            # Skip non-text files that might contain code
            if not any(file['path'].endswith(ext) for ext in ['.py', '.ipynb', '.txt', '.md', '.js', '.html', '.css', '.yaml', '.yml', '.json', '.env', '.config']):
                continue

            # Get file content
            content_url = f"https://huggingface.co/spaces/{space_id}/raw/{file['path']}"
            content_response = requests.get(content_url)

            if content_response.status_code != 200:
                continue

            content = content_response.text

            # Search for direct API keys
            direct_matches = openai_key_pattern.findall(content)
            for match in direct_matches:
                if match not in found_keys:
                    found_keys.append(match)

            # Search for keys in config patterns
            for pattern in config_patterns:
                matches = pattern.findall(content)
                for match in matches:
                    if match.startswith('sk-') and match not in found_keys:
                        found_keys.append(match)

            # Don't hammer the API
            time.sleep(0.1)

    except Exception as e:
        print(f"Error processing {space_id}: {str(e)}")

    return [(space_id, key) for key in found_keys]

def main():
    # Create results directory
    os.makedirs("results", exist_ok=True)

    # Get all spaces
    spaces = get_all_spaces()

    # Save spaces to file
    with open("results/all_spaces.txt", "w") as f:
        for space in spaces:
            f.write(f"{space['id']}\n")

    print(f"Saved {len(spaces)} spaces to results/all_spaces.txt")

    # Get number of threads from input
    num_threads = int(document.getElementById('threads').value)

    # Search for OpenAI keys
    found_keys = []

    print(f"Searching spaces for OpenAI API keys using {num_threads} threads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_space = {executor.submit(search_for_openai_keys, space['id']): space for space in spaces}

        with tqdm(total=len(spaces), desc="Searching spaces") as pbar:
            for future in concurrent.futures.as_completed(future_to_space):
                space = future_to_space[future]
                try:
                    keys = future.result()
                    if keys:
                        found_keys.extend(keys)
                        print(f"Found key(s) in {space['id']}: {keys}")
                except Exception as e:
                    print(f"Error processing {space['id']}: {str(e)}")
                finally:
                    pbar.update(1)

    # Save results
    print(f"Found {len(found_keys)} potential OpenAI API keys.")
    with open("results/found_keys.txt", "w") as f:
        for space_id, key in found_keys:
            f.write(f"Space: {space_id}, Key: {key}\n")

    print(f"Results saved to results/found_keys.txt")

if __name__ == "__main__":
    main()
