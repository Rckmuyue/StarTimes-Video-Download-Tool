import base64
import zlib
import os
import re
import binascii
import glob
import subprocess
import sys
import requests
import shutil
import time
import threading
import concurrent.futures
from collections import OrderedDict
from urllib.parse import urlparse, urljoin
import json

class Downloader:
    def __init__(self):
        self.completed = 0
        self.total = 0
        self.failed = 0
        self.lock = threading.Lock()
        self.start_time = time.time()

    def print_progress(self, lang_strings):
        """Prints the download progress."""
        with self.lock:
            if self.total == 0:
                return
            elapsed = time.time() - self.start_time
            percent = (self.completed / self.total) * 100
            if self.completed > 0:
                time_per_file = elapsed / self.completed
                eta = (self.total - self.completed) * time_per_file
            else:
                eta = 0
                
            sys.stdout.write("\r")
            sys.stdout.write(
                lang_strings["download_progress"].format(
                    completed=self.completed,
                    total=self.total,
                    percent=percent,
                    failed=self.failed,
                    elapsed=elapsed/60,
                    eta=eta/60
                )
            )
            sys.stdout.flush()

    def download_segment(self, idx, ts_url, output_path, headers, max_retries):
        """Downloads a single segment with retries."""
        for retry in range(max_retries + 1):
            try:
                response = requests.get(ts_url, headers=headers, stream=True, timeout=(30, 60))
                response.raise_for_status()
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                if os.path.getsize(output_path) == 0:
                    raise Exception("Downloaded file size is 0")
                
                with self.lock:
                    self.completed += 1
                return True
                
            except Exception as e:
                if retry < max_retries:
                    time.sleep(1)
                    continue
                else:
                    with self.lock:
                        self.completed += 1
                        self.failed += 1
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except:
                            pass
                    return False
        return False

def decrypt_string(encoded_string):
    """Decrypts a Base64 + zlib compressed string."""
    # Remove all non-Base64 characters
    clean_string = re.sub(r'[^A-Za-z0-9+/=]', '', encoded_string)
    
    # Base64 decode
    try:
        decoded_data = base64.b64decode(clean_string, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"Base64 decoding failed: {str(e)}") from e
    
    # Zlib decompress
    try:
        decompressed = zlib.decompress(decoded_data)
        return decompressed
    except zlib.error:
        for wbits in (zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
            try:
                decompressed = zlib.decompress(decoded_data, wbits=wbits)
                return decompressed
            except zlib.error:
                continue
        raise ValueError("Decompression failed: invalid or corrupted data format")

def download_m3u8(m3u8_url, user_cookie, lang_strings):
    """Downloads the M3U8 file and parses initialization data."""
    print(lang_strings["downloading_m3u8"].format(m3u8_url=m3u8_url))
    
    # Prepare request headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) StarTimesON/6.16.5-1',
        'Accept': '*/*',
        'Range': 'bytes=0-',
        'Connection': 'close',
        'Icy-MetaData': '1',
        'Accept-Encoding': 'gzip',
        'Content-Type': 'text/plain',
        'X-UserID': '107842057',
        'X-DeviceID': 'cb6e5e09c01a8ee431b362029aea0cdb_android',
        'X-EventID': 'VOD_8d00b597-4d4a-499a-8140-73591eae7bc3',
        'X-PlayID': '96291dac-d3a0-47f1-8362-78d0bd09670e',
        'Cookie': user_cookie,
    }
    
    # Parse base URL
    parsed_url = urlparse(m3u8_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{os.path.dirname(parsed_url.path)}/"
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url += '/'
    
    try:
        response = requests.get(m3u8_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse m3u8 content
        m3u8_content = response.text
        print(lang_strings["m3u8_download_success"].format(length=len(m3u8_content)))
        
        # Find STAR-INIT-DATA in EXT-X-MAP tag
        map_line = re.search(r'#EXT-X-MAP:.*?STAR-INIT-DATA="(.*?)"', m3u8_content)
        if map_line:
            base64_data = map_line.group(1)
            print(lang_strings["star_init_data_found_map"].format(data=base64_data[:50]))
        else:
            # Try old search method
            init_data_match = re.search(r'#EXT-STAR-INIT-DATA:(.*)', m3u8_content)
            if init_data_match:
                base64_data = init_data_match.group(1).strip()
                print(lang_strings["star_init_data_found"].format(data=base64_data[:50]))
            else:
                raise ValueError(lang_strings["star_init_data_not_found"])
        
        # Parse segment list
        ts_files = []
        # Find #EXTINF tag preceding filename line
        extinf_matches = re.finditer(r'#EXTINF:[\d\.]+,\s*\n([^\s#]+\.m4s)', m3u8_content)
        
        for match in extinf_matches:
            ts_url = match.group(1)
            # Handle relative URLs
            if not ts_url.startswith('http'):
                ts_url = urljoin(base_url, ts_url)
            ts_files.append(ts_url)
        
        if not ts_files:
            raise ValueError(lang_strings["no_segments_found"])
        
        print(lang_strings["segments_found"].format(count=len(ts_files)))
        return base64_data, ts_files
        
    except requests.RequestException as e:
        print(lang_strings["m3u8_download_failed"].format(error=str(e)))
        print(lang_strings["suggestions_header"])
        print(lang_strings["suggestion_url_check"])
        print(lang_strings["suggestion_network_check"])
        print(lang_strings["suggestion_cookie_check"])
        return None, None
    except ValueError as e:
        print(lang_strings["m3u8_parse_failed"].format(error=str(e)))
        return None, None

def download_segments(ts_urls, user_cookie, lang_strings, max_retries=3, max_workers=10):
    """Downloads all segments using ThreadPoolExecutor."""
    if not ts_urls:
        return []
    
    # Prepare request headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) StarTimesON/6.16.5-1',
        'Accept': '*/*',
        'Range': 'bytes=0-',
        'Connection': 'close',
        'Icy-MetaData': '1',
        'Accept-Encoding': 'gzip',
        'Cookie': user_cookie,
    }
    
    # Create download directory
    # Use a 'downloads' subdirectory within the script's directory
    download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads") 
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    
    print(lang_strings["starting_multithreaded_download"].format(workers=max_workers))
    print(lang_strings["saving_to_directory"].format(directory=download_dir))
    
    downloader = Downloader()
    downloader.total = len(ts_urls)
    
    # Prepare download tasks
    tasks = []
    for idx, ts_url in enumerate(ts_urls):
        filename = f"{idx:06d}.m4s"
        filepath = os.path.join(download_dir, filename)
        tasks.append((idx, ts_url, filepath))
    
    # Execute download using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for idx, ts_url, filepath in tasks:
            # Skip download if file already exists and has a normal size
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                with downloader.lock:
                    downloader.completed += 1
                continue
                
            future = executor.submit(
                downloader.download_segment,
                idx, ts_url, filepath, headers, max_retries
            )
            futures.append(future)
        
        # Display download progress
        print("")
        while not all(future.done() for future in futures):
            downloader.print_progress(lang_strings)
            time.sleep(0.5)
        downloader.print_progress(lang_strings)
        print("\n")
    
    # Collect all downloaded files
    downloaded_files = []
    for idx in range(len(ts_urls)):
        filename = f"{idx:06d}.m4s"
        filepath = os.path.join(download_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            downloaded_files.append(filepath)
        else:
            print(lang_strings["warning_file_not_downloaded"].format(filename=filename))
    
    print(lang_strings["segments_download_complete"].format(success=len(downloaded_files), total=len(ts_urls)))
    
    # Check failed count
    if downloader.failed > 0:
        print(lang_strings["warning_failed_downloads"].format(failed=downloader.failed))
    
    return downloaded_files

def save_init_mp4_from_base64(base64_data, lang_strings):
    """Creates init.mp4 file from Base64 data in the script's directory."""
    try:
        print(lang_strings["decrypting_star_init_data"])
        result = decrypt_string(base64_data)
        
        # Save as init.mp4 in the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "init.mp4")
        
        if os.path.exists(output_path):
            print(lang_strings["skipping_init_mp4_exists"])
            return True
            
        with open(output_path, 'wb') as f:
            f.write(result)
        print(lang_strings["init_mp4_save_success"].format(path=output_path))
        return True
        
    except Exception as e:
        print(lang_strings["decrypt_or_save_failed"].format(error=str(e)))
        return False

def generate_file_list(lang_strings):
    """Scans the script's download subdirectory and generates input.txt file in the script's root."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Find all m4s files in the script's download subdirectory
        downloads_dir = os.path.join(script_dir, "downloads")
        m4s_files = glob.glob(os.path.join(downloads_dir, '*.m4s'))
        
        if not m4s_files:
            print(lang_strings["no_m4s_files_found"])
            return False
            
        # Sort by numeric part in filename
        def numeric_key(name):
            # Extract numeric part from filename
            base_name = os.path.basename(name)
            match = re.search(r'(\d+)\.m4s$', base_name)
            if match:
                return int(match.group(1))
            return -1
        
        m4s_files.sort(key=numeric_key)
        
        # Add init.mp4 as the first file
        # The input.txt should reference files relative to the script's main directory
        output_files_relative = ["init.mp4"] 
        for f in m4s_files:
            # Need to get relative path from script_dir to downloads/filename.m4s
            relative_path = os.path.relpath(f, script_dir)
            output_files_relative.append(relative_path.replace(os.sep, '/')) # Use '/' for PowerShell compatibility
        
        # Write file list to input.txt in the script's directory
        output_path = os.path.join(script_dir, "input.txt")
        if os.path.exists(output_path):
            print(lang_strings["skipping_input_txt_exists"])
            return True
            
        with open(output_path, 'w') as f:
            for file in output_files_relative:
                f.write(f"{file}\n")
        
        # Output file list
        print(lang_strings["generated_input_txt_content"])
        for file in output_files_relative:
            print(file)
            
        print(lang_strings["input_txt_generation_success"].format(path=output_path, count=len(output_files_relative)))
        return True
        
    except Exception as e:
        print(lang_strings["generate_file_list_failed"].format(error=str(e)))
        return False

# MODIFIED FUNCTION: combine_files_with_powershell is replaced by combine_files_python
def combine_files_python(lang_strings):
    """Combines files using pure Python."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, "input.txt")

    # Ensure input.txt exists
    if not os.path.exists(input_path):
        print(lang_strings["error_input_txt_not_found"].format(path=input_path))
        return False

    # Check file content
    if os.path.getsize(input_path) == 0:
        print(lang_strings["error_input_txt_empty"].format(path=input_path))
        return False

    output_file = os.path.join(script_dir, "combined.mp4")
    # Check if output file already exists
    if os.path.exists(output_file):
        print(lang_strings["skipping_combine_output_exists"].format(file=output_file))
        return True

    print(lang_strings["starting_python_combine"]) # New language string
    try:
        with open(output_file, 'wb') as outfile:
            with open(input_path, 'r', encoding='utf-8') as filelist_fd:
                file_paths = [line.strip() for line in filelist_fd if line.strip()]

            for relative_path in file_paths:
                full_path = os.path.join(script_dir, relative_path)
                if os.path.exists(full_path):
                    try:
                        with open(full_path, 'rb') as infile:
                            bytes_read = infile.read()
                            outfile.write(bytes_read)
                            print(lang_strings["python_adding_bytes_msg"].format(file=relative_path, bytes_length=len(bytes_read))) # New language string
                    except IOError as e:
                        print(lang_strings["python_warning_file_read_failed"].format(file=relative_path, error=str(e))) # New language string
                else:
                    print(lang_strings["python_warning_file_not_found_msg"].format(file=relative_path)) # New language string

        print(lang_strings["file_combine_success"])
        return True
    except Exception as e:
        print(lang_strings["combine_files_failed"].format(error=str(e))) # New language string
        return False

def cleanup_files(lang_strings):
    """Cleans up all intermediate files in the script's directory."""
    print(lang_strings["starting_cleanup"])
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    deleted = 0
    
    # Delete all segment files from the downloads subdirectory
    downloads_dir = os.path.join(script_dir, "downloads")
    for file in glob.glob(os.path.join(downloads_dir, '*.m4s')):
        try:
            os.remove(file)
            print(lang_strings["deleted_file"].format(file=os.path.basename(file)))
            deleted += 1
        except Exception as e:
            print(lang_strings["delete_failed"].format(file=os.path.basename(file), error=str(e)))
    
    # Delete init.mp4
    init_mp4_path = os.path.join(script_dir, 'init.mp4')
    if os.path.exists(init_mp4_path):
        try:
            os.remove(init_mp4_path)
            print(lang_strings["deleted_file"].format(file='init.mp4'))
            deleted += 1
        except Exception as e:
            print(lang_strings["delete_failed"].format(file='init.mp4', error=str(e)))
    
    # Delete input.txt
    input_txt_path = os.path.join(script_dir, 'input.txt')
    if os.path.exists(input_txt_path):
        try:
            os.remove(input_txt_path)
            print(lang_strings["deleted_file"].format(file='input.txt'))
            deleted += 1
        except Exception as e:
            print(lang_strings["delete_failed"].format(file='input.txt', error=str(e)))
    
    # Delete downloads directory (if exists)
    if os.path.exists(downloads_dir) and os.path.isdir(downloads_dir):
        try:
            # Delete entire directory (may not be empty)
            shutil.rmtree(downloads_dir)
            print(lang_strings["deleted_directory"].format(directory=downloads_dir))
            deleted += 1
        except Exception as e:
            print(lang_strings["delete_directory_failed"].format(directory=downloads_dir, error=str(e)))
    
    print(lang_strings["cleanup_complete"].format(deleted=deleted))


# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json") # 配置文件路径
LANGUAGES_FILE = os.path.join(SCRIPT_DIR, "languages.json") # 语言文件路径

# 全局变量，用于存储加载的语言字符串
LOADED_LANG_STRINGS = {}

def load_language_strings():
    """Loads language strings from the languages.json file."""
    global LOADED_LANG_STRINGS
    if os.path.exists(LANGUAGES_FILE):
        try:
            with open(LANGUAGES_FILE, 'r', encoding='utf-8') as f:
                LOADED_LANG_STRINGS = json.load(f)
            return True
        except json.JSONDecodeError:
            print(f"Error: {LANGUAGES_FILE} is corrupted or invalid JSON. Please check the file.")
            return False
        except Exception as e:
            print(f"An unexpected error occurred while loading {LANGUAGES_FILE}: {e}")
            return False
    else:
        # If languages.json is not found, print an error and indicate failure
        print(f"Error: {LANGUAGES_FILE} not found. Please ensure it's in the same directory as the script.")
        print("This file is essential for the program's language display.")
        return False

def load_config():
    """Loads configuration from the config.json file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {CONFIG_FILE} is corrupted or invalid JSON. Using default config.")
            return {}
        except Exception as e:
            print(f"An unexpected error occurred while loading {CONFIG_FILE}: {e}")
            return {}
    return {}

def save_config(config):
    """Saves configuration to the config.json file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error: Failed to save config to {CONFIG_FILE}: {e}")

def main():
    global LOADED_LANG_STRINGS # Declare to use global variable

    # Initialize lang_strings to a default (e.g., English) in case language loading fails
    # This ensures lang_strings is always defined for error messages in finally block.
    # A basic default message for "press_enter_to_exit" is crucial here.
    default_lang_strings = {
        "press_enter_to_exit": "\nPress Enter to exit...",
        "program_error": "\nAn unexpected program error occurred: {error}",
        "choose_language": "Choose language (1 for English, 2 for Chinese): ",
        "invalid_language_choice": "Invalid choice. Please enter 1 or 2.",
        "config_saved": "Configuration saved.",
        "download_progress": "Download progress: {completed}/{total} ({percent:.1f}%) | Failed: {failed} | Elapsed: {elapsed:.1f}m | ETA: {eta:.1f}m",
        "m3u8_url_prompt": "Please enter the M3U8 URL: ",
        "error_m3u8_url_prefix": "Error: The M3U8 URL must start with http:// or https://",
        "cookie_prompt": "Please enter the Cookie value (leave blank if none): ",
        "warning_no_cookie": "Warning: No Cookie value provided, protected content may not be downloadable.",
        "downloading_m3u8": "Downloading M3U8 file: {m3u8_url}",
        "m3u8_download_success": "M3U8 file downloaded successfully ({length} bytes)",
        "star_init_data_found_map": "STAR-INIT-DATA found in EXT-X-MAP tag: {data}...",
        "star_init_data_found": "STAR-INIT-DATA found: {data}...",
        "star_init_data_not_found": "STAR-INIT-DATA not found in M3u8 file",
        "no_segments_found": "No segment files found in M3u8 file",
        "segments_found": "Found {count} segment files",
        "m3u8_download_failed": "Failed to download M3u8 file: {error}",
        "suggestions_header": "Suggestions:",
        "suggestion_url_check": "1. Check if the URL is correct",
        "suggestion_network_check": "2. Confirm network connection is stable",
        "suggestion_cookie_check": "3. Check if the Cookie is valid",
        "m3u8_parse_failed": "Failed to parse M3u8 file: {error}",
        "m3u8_processing_failed": "M3u8 processing failed, exiting program.",
        "preparing_to_download_segments": "Preparing to download {count} video segments...",
        "starting_multithreaded_download": "Starting multi-threaded download of segments (workers: {workers})",
        "saving_to_directory": "Files will be saved to: {directory}",
        "warning_file_not_downloaded": "Warning: File {filename} not downloaded successfully.",
        "segments_download_complete": "Segment files download complete! Success: {success}/{total}",
        "warning_failed_downloads": "Warning: {failed} files failed to download, video integrity may be affected.",
        "no_segments_downloaded": "No segment files downloaded successfully.",
        "decrypting_star_init_data": "Decrypting STAR-INIT-DATA...",
        "skipping_init_mp4_exists": "Skipping creation of init.mp4 (already exists).",
        "init_mp4_save_success": "Successfully saved as: {path}",
        "decrypt_or_save_failed": "Decryption or save failed: {error}",
        "create_init_mp4_failed": "Failed to create init.mp4.",
        "no_m4s_files_found": "No .m4s files found in the downloads subdirectory.",
        "skipping_input_txt_exists": "Skipping creation of input.txt (already exists).",
        "generated_input_txt_content": "Generated input.txt content:",
        "input_txt_generation_success": "Successfully generated {path}, containing {count} files.",
        "generate_file_list_failed": "Failed to generate file list.",
        "error_input_txt_not_found": "Error: input.txt file not found: {path}",
        "error_input_txt_empty": "Error: {path} is an empty file.",
        "skipping_combine_output_exists": "Skipping merge (output file already exists): {file}",
        # New and modified language strings for Python merge
        "starting_python_combine": "Starting file combination using pure Python...",
        "python_adding_bytes_msg": "Adding {bytes_length} bytes from {file}",
        "python_warning_file_not_found_msg": "Warning: File {file} not found! Skipping.",
        "python_warning_file_read_failed": "Warning: Failed to read file {file}: {error}",
        "combine_files_failed": "Failed to combine files: {error}",
        "file_combine_success": "Files merged successfully!",
        "final_output_file": "Final output file: {file}",
        "file_size": "File size: {size:,} bytes ({mb:.2f} MB)",
        "download_and_merge_complete": "\nVideo download and merge complete!",
        "find_video_in_current_dir": "You can find the complete video file in the current directory.",
        "cleanup_prompt": "Do you want to clean up all intermediate files (segments, init.mp4, input.txt, downloads folder)? [y/N]: ",
        "starting_cleanup": "Starting cleanup of intermediate files...",
        "deleted_file": "Deleted: {file}",
        "delete_failed": "Failed to delete {file}: {error}",
        "deleted_directory": "Deleted directory: {directory}",
        "delete_directory_failed": "Failed to delete directory {directory}: {error}",
        "cleanup_complete": "Cleanup complete! Total deleted: {deleted} files and directories.",
        "cleanup_complete_message": "\nAll intermediate files have been cleaned up, only the merged video file remains.",
        "cleanup_skipped_message": "\nAll intermediate files are retained, you can use them to re-execute the merge process.",
        "combine_process_error": "\nAn error occurred during the merge process!",
        "user_interrupted": "\nUser interrupted operation!",
        "title": "StarTimes Video Download Tool",
        "titlea": "by YourName / Version 1.0" # Replace with your name/version
    }
    lang_strings = default_lang_strings

    if not load_language_strings():
        print("Failed to load language strings. Program cannot proceed without 'languages.json'.")
        input(lang_strings["press_enter_to_exit"])
        return

    try:
        config = load_config()
        current_language = config.get("language", None)

        if current_language not in LOADED_LANG_STRINGS or not LOADED_LANG_STRINGS.get(current_language): 
            while True:
                en_prompt = LOADED_LANG_STRINGS.get("en", {}).get("choose_language", default_lang_strings["choose_language"])
                zh_prompt = LOADED_LANG_STRINGS.get("zh", {}).get("choose_language", default_lang_strings["choose_language"])
                print(en_prompt)
                print(zh_prompt)

                lang_choice = input().strip()

                if lang_choice == '1':
                    current_language = "en"
                    break
                elif lang_choice == '2':
                    current_language = "zh"
                    break
                else:
                    invalid_choice_msg = LOADED_LANG_STRINGS.get(current_language, LOADED_LANG_STRINGS.get("en", default_lang_strings)).get("invalid_language_choice", default_lang_strings["invalid_language_choice"])
                    print(invalid_choice_msg)
            config["language"] = current_language
            save_config(config)
            print(LOADED_LANG_STRINGS[current_language]["config_saved"])
        
        lang_strings = LOADED_LANG_STRINGS[current_language]
        
        print("=" * 60)
        print(lang_strings["title"])
        print(lang_strings["titlea"])
        print("=" * 60)
        
        m3u8_url = input(lang_strings["m3u8_url_prompt"]).strip()
        if not m3u8_url.startswith(('http://', 'https://')):
            print(lang_strings["error_m3u8_url_prefix"])
            input(lang_strings["press_enter_to_exit"])
            return
        
        user_cookie = input(lang_strings["cookie_prompt"]).strip()
        if not user_cookie:
            print(lang_strings["warning_no_cookie"])
        
        base64_data, ts_urls = download_m3u8(m3u8_url, user_cookie, lang_strings)
        if not base64_data or not ts_urls:
            print(lang_strings["m3u8_processing_failed"])
            input(lang_strings["press_enter_to_exit"])
            return
        
        print(lang_strings["preparing_to_download_segments"].format(count=len(ts_urls)))
        time.sleep(1)
            
        downloaded_files = download_segments(ts_urls, user_cookie, lang_strings)
        
        if not downloaded_files:
            print(lang_strings["no_segments_downloaded"])
            input(lang_strings["press_enter_to_exit"])
            return
            
        if not save_init_mp4_from_base64(base64_data, lang_strings):
            print(lang_strings["create_init_mp4_failed"])
            input(lang_strings["press_enter_to_exit"])
            return
        
        if not generate_file_list(lang_strings):
            print(lang_strings["generate_file_list_failed"])
            input(lang_strings["press_enter_to_exit"])
            return
        
        # Call the new Python-based combination function
        success = combine_files_python(lang_strings)
        
        if success:
            final_file = os.path.join(SCRIPT_DIR, "combined.mp4")
            print("\n" + "=" * 60)
            print(lang_strings["final_output_file"].format(file=final_file))
            
            if os.path.exists(final_file):
                size = os.path.getsize(final_file)
                print(lang_strings["file_size"].format(size=size, mb=size/(1024 * 1024)))
            
            print(lang_strings["download_and_merge_complete"])
            print(lang_strings["find_video_in_current_dir"])
            
            print("\n" + "-" * 60)
            choice = input(lang_strings["cleanup_prompt"]).strip().lower()
            if choice == 'y':
                cleanup_files(lang_strings)
                print(lang_strings["cleanup_complete_message"])
            else:
                print(lang_strings["cleanup_skipped_message"])
        else:
            print(lang_strings["combine_process_error"])

    except KeyboardInterrupt:
        print(lang_strings["user_interrupted"])
    except Exception as e:
        current_lang_strings = lang_strings if 'lang_strings' in locals() else default_lang_strings
        print(current_lang_strings["program_error"].format(error=str(e)))
        import traceback
        traceback.print_exc()
    finally:
        current_lang_strings = lang_strings if 'lang_strings' in locals() else default_lang_strings
        input(current_lang_strings["press_enter_to_exit"])

if __name__ == "__main__":
    main()