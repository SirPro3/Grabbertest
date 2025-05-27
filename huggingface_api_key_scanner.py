import os
import re
import time
import shutil
from huggingface_hub import HfApi, list_spaces, snapshot_download

# --- Configuration ---
SCAN_INTERVAL_SECONDS = 120  # Scan every hour
SEEN_SPACES_FILE = "seen_spaces.txt"
DOWNLOAD_DIR_BASE = "downloaded_spaces"

# API Key Patterns (Regex)
# OpenAI: sk- followed by 40+ alphanumeric characters
# Claude:
#   1. sk-ant-api03-[A-Za-z0-9\-_]{93}AA
#   2. sk-ant-[A-Za-z0-9\-_]{86}
#   3. sk-[A-Za-z0-9]{86}
# GoogleAI: AIzaSy followed by 33 alphanumeric/hyphen/underscore characters
# DeepSeek: sk- followed by 32 hexadecimal characters
# XAI: xai- followed by 80 alphanumeric characters
API_KEY_PATTERNS = {
    "OpenAI": r"sk-[a-zA-Z0-9]{40,}",
    "Claude": r"(sk-ant-api03-[A-Za-z0-9\-_]{93}AA|sk-ant-[A-Za-z0-9\-_]{86}|sk-[A-Za-z0-9]{86})",
    "GoogleAI": r"AIzaSy[A-Za-z0-9\-_]{33}",
    "DeepSeek": r"sk-[a-f0-9]{32}",
    "XAI": r"xai-[A-Za-z0-9]{80}"
}

# Output files for found keys
OPENAI_KEYS_OUTPUT_FILE = "found_openai_keys.txt"
CLAUDE_KEYS_OUTPUT_FILE = "found_claude_keys.txt"
GOOGLEAI_KEYS_OUTPUT_FILE = "found_googleai_keys.txt"
DEEPSEEK_KEYS_OUTPUT_FILE = "found_deepseek_keys.txt"
XAI_KEYS_OUTPUT_FILE = "found_xai_keys.txt"

# --- Helper Functions ---

def load_seen_spaces():
    """Loads the set of seen space IDs from a file."""
    if not os.path.exists(SEEN_SPACES_FILE):
        return set()
    with open(SEEN_SPACES_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_seen_space(space_id):
    """Appends a new space ID to the seen spaces file."""
    with open(SEEN_SPACES_FILE, "a") as f:
        f.write(space_id + "\n")

def search_keys_in_content(content, patterns):
    """Searches for API key patterns in a given string content."""
    found_keys = {}
    for key_type, pattern in patterns.items():
        matches = re.findall(pattern, content)
        if matches:
            if key_type not in found_keys:
                found_keys[key_type] = []
            found_keys[key_type].extend(matches)
    return found_keys

def scan_directory_for_keys(directory_path, patterns):
    """Recursively scans files in a directory for API keys."""
    all_found_keys = {}
    print(f"Scanning directory: {directory_path}")
    for root, _, files in os.walk(directory_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f_content:
                    content = f_content.read()
                
                # Limit content size to avoid memory issues with very large files
                if len(content) > 5 * 1024 * 1024: # 5MB limit
                    print(f"Skipping large file (>{len(content)/(1024*1024):.2f}MB): {file_path}")
                    continue

                found_in_file = search_keys_in_content(content, patterns)
                if found_in_file:
                    print(f"  Found keys in file: {file_path}")
                    for key_type, keys in found_in_file.items():
                        print(f"    {key_type}: {keys}")
                        if key_type not in all_found_keys:
                            all_found_keys[key_type] = []
                        all_found_keys[key_type].extend(keys)
            except Exception as e:
                print(f"  Error reading or processing file {file_path}: {e}")
    return all_found_keys

def save_key_to_file(key_type, key, space_id):
    """Appends a found key to its respective file, noting the source space."""
    filename = ""
    if key_type == "OpenAI":
        filename = OPENAI_KEYS_OUTPUT_FILE
    elif key_type == "Claude":
        filename = CLAUDE_KEYS_OUTPUT_FILE
    elif key_type == "GoogleAI":
        filename = GOOGLEAI_KEYS_OUTPUT_FILE
    elif key_type == "DeepSeek":
        filename = DEEPSEEK_KEYS_OUTPUT_FILE
    elif key_type == "XAI":
        filename = XAI_KEYS_OUTPUT_FILE
    else:
        return # Unknown key type

    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{key} # Found in space: {space_id}\n")
        print(f"    Saved {key_type} key to {filename}")
    except Exception as e:
        print(f"    Error saving key to {filename}: {e}")

# --- Main Scan Logic ---

def main():
    """Main function to run the Hugging Face Space scanner."""
    print("Starting Hugging Face API Key Scanner...")

    if not os.path.exists(DOWNLOAD_DIR_BASE):
        os.makedirs(DOWNLOAD_DIR_BASE)

    if not os.path.exists(SEEN_SPACES_FILE):
        print(f"First run detected. Cataloging all current Hugging Face Spaces to '{SEEN_SPACES_FILE}'.")
        print("These initial spaces will NOT be scanned in this setup phase.")
        try:
            initial_spaces = list(list_spaces(sort="lastModified", direction=-1))
            seen_spaces = set()
            with open(SEEN_SPACES_FILE, "w") as f: # Create/overwrite the file
                for space_info in initial_spaces:
                    space_id = space_info.id
                    f.write(space_id + "\n")
                    seen_spaces.add(space_id)
            print(f"Cataloged {len(seen_spaces)} initial spaces. Subsequent new spaces will be scanned.")
        except Exception as e:
            print(f"Error during initial cataloging of spaces: {e}")
            print("Please check your internet connection and Hugging Face Hub access.")
            print("Exiting, as a baseline could not be established.")
            return # Exit if we can't establish a baseline
    else:
        seen_spaces = load_seen_spaces()
        print(f"Loaded {len(seen_spaces)} seen spaces from '{SEEN_SPACES_FILE}'.")


    while True:
        print(f"\n--- New Scan Cycle ({time.ctime()}) ---")
        current_new_spaces_found = 0
        try:
            print("Fetching list of Hugging Face Spaces...")
            # Sort by lastModified to try and get newer ones first if possible,
            # though the API might not return them strictly in order or all at once.
            # We will still rely on our seen_spaces set for true "newness".
            
            # Reload seen_spaces at the beginning of each cycle in case it was modified externally
            # or to ensure consistency if the script was restarted.
            # However, for a continuously running script, the in-memory 'seen_spaces' set
            # that gets updated with save_seen_space should be sufficient.
            # For this specific request (baseline on first run), the initial load is key.
            # The current `seen_spaces = load_seen_spaces()` outside the loop handles this.

            all_current_spaces = list(list_spaces(sort="lastModified", direction=-1))
            print(f"Fetched {len(all_current_spaces)} spaces from Hugging Face.")

            new_spaces_to_scan = []
            for space_info in all_current_spaces:
                space_id = space_info.id
                if space_id not in seen_spaces:
                    new_spaces_to_scan.append(space_info)
            
            if new_spaces_to_scan:
                print(f"Identified {len(new_spaces_to_scan)} new space(s) to scan since last check or initial baseline.")
            else:
                print("No new spaces found to scan in this cycle.")


            for i, space_info in enumerate(new_spaces_to_scan):
                space_id = space_info.id
                print(f"\nProcessing new space ({i+1}/{len(new_spaces_to_scan)}): {space_id}")
                
                # Create a unique directory for this space's download
                space_download_dir = os.path.join(DOWNLOAD_DIR_BASE, space_id.replace("/", "_"))
                
                if os.path.exists(space_download_dir):
                    print(f"  Cleaning up old download directory: {space_download_dir}")
                    shutil.rmtree(space_download_dir)
                
                try:
                    print(f"  Downloading space: {space_id} to {space_download_dir}...")
                    # Using snapshot_download to get all files.
                    # allow_patterns and ignore_patterns can be used for more fine-grained control.
                    snapshot_download(
                        repo_id=space_id,
                        repo_type="space",
                        local_dir=space_download_dir,
                        local_dir_use_symlinks=False, # Easier for cross-platform and simple scanning
                        # token=HF_TOKEN # Add if you have a token and need to access private/gated spaces
                    )
                    print(f"  Space {space_id} downloaded successfully.")
                    
                    print(f"  Scanning {space_id} for API keys...")
                    found_keys = scan_directory_for_keys(space_download_dir, API_KEY_PATTERNS)
                    
                    if found_keys:
                        current_new_spaces_found +=1
                        print(f"  --- Keys found in {space_id} ---")
                        for key_type, keys_list in found_keys.items():
                            print(f"    {key_type}: {', '.join(keys_list)}")
                            for key in keys_list:
                                save_key_to_file(key_type, key, space_id)
                        print(f"  ----------------------------")
                    else:
                        print(f"  No specified API keys found in {space_id}.")

                    # Mark as seen after successful processing
                    seen_spaces.add(space_id)
                    save_seen_space(space_id)
                    
                except Exception as e:
                    print(f"  Error processing space {space_id}: {e}")
                    # Optionally, decide if you want to mark it as seen even if an error occurred
                    # or retry later. For now, we'll skip and it will be picked up next cycle if not seen.
                finally:
                    # Clean up downloaded files after scanning to save space
                    if os.path.exists(space_download_dir):
                        print(f"  Cleaning up downloaded files for {space_id}...")
                        shutil.rmtree(space_download_dir)
                        print(f"  Cleanup complete for {space_id}.")
                    else:
                        print(f"  Download directory {space_download_dir} not found for cleanup (may have failed to download).")

            if not new_spaces_to_scan:
                print("No new spaces found in this cycle.")
            else:
                print(f"\nFinished processing {len(new_spaces_to_scan)} new spaces. Found keys in {current_new_spaces_found} of them.")

        except Exception as e:
            print(f"An error occurred in the main scan loop: {e}")

        print(f"\nWaiting for {SCAN_INTERVAL_SECONDS} seconds before next scan cycle...")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()