import base64
import zlib
import os
import re
import binascii
import glob
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

# --- Configuration and Language Handling ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config.json')
LANG_FILE = os.path.join(SCRIPT_DIR, 'languages.json')

def load_config():
    """Loads configuration from config.json."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("Error: config.json is corrupted. Creating a new one.")
                return {}
    return {}

def save_config(config):
    """Saves configuration to config.json."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_language_strings(lang_code):
    """Loads language strings from languages.json."""
    if not os.path.exists(LANG_FILE):
        print(f"Error: {LANG_FILE} not found. Ensure it's in the script directory.")
        sys.exit(1)
    with open(LANG_FILE, 'r', encoding='utf-8') as f:
        languages = json.load(f)
    return languages.get(lang_code, languages['en']) # Default to English

# --- Video Processing Functions ---

def parse_star_init_data(data_string):
    """Parses STAR-INIT-DATA string."""
    try:
        decoded_bytes = base64.b64decode(data_string)
        decompressed_bytes = zlib.decompress(decoded_bytes)
        json_data = json.loads(decompressed_bytes.decode('utf-8'))
        return json_data
    except Exception as e:
        return None

def extract_key_from_pssh(pssh_data):
    """Extracts Key ID from PSSH data."""
    try:
        pssh_bytes = binascii.unhexlify(pssh_data)
        widevine_system_id = binascii.unhexlify("EDEF8BA979D64ACEA3C827E2FC21DCD2")
        system_id_offset = 4 + 4 + 1 + 3 # Standard PSSH box format
        
        if pssh_bytes[system_id_offset : system_id_offset + 16] == widevine_system_id:
            data_size_offset = system_id_offset + 16
            data_size = int.from_bytes(pssh_bytes[data_size_offset : data_size_offset + 4], 'big')
            
            num_key_ids_offset = data_size_offset + 4
            if len(pssh_bytes) >= num_key_ids_offset + 4:
                num_key_ids = int.from_bytes(pssh_bytes[num_key_ids_offset : num_key_ids_offset + 4], 'big')
                if num_key_ids > 0:
                    first_key_id_offset = num_key_ids_offset + 4
                    if len(pssh_bytes) >= first_key_id_offset + 16:
                        key_id_bytes = pssh_bytes[first_key_id_offset : first_key_id_offset + 16]
                        return binascii.hexlify(key_id_bytes).decode('utf-8')
            return "KID_NOT_FOUND_IN_PSSH_DATA"
        
        return None
    except Exception as e:
        return None

def decrypt_key(encrypted_key_data, content_key_id):
    """Placeholder for key decryption."""
    return None

def download_m3u8(url, headers, lang_strings):
    """Downloads the M3U8 file."""
    print(lang_strings["downloading_m3u8"].format(m3u8_url=url))
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        print(lang_strings["m3u8_download_success"].format(length=len(response.content)))
        return response.text
    except requests.exceptions.RequestException as e:
        print(lang_strings["m3u8_download_failed"].format(error=e))
        return None

def download_segment(segment_url, headers, segment_path, lang_strings, downloader, max_retries=5):
    """Downloads a single video segment."""
    for attempt in range(max_retries):
        try:
            response = requests.get(segment_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            with open(segment_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            with downloader.lock:
                downloader.completed += 1
            downloader.print_progress(lang_strings)
            return True
        except requests.exceptions.RequestException as e:
            with downloader.lock:
                downloader.failed += 1
            time.sleep(2 ** attempt)
    return False

def parse_m3u8(m3u8_content, lang_strings):
    """Parses M3U8 content to extract segments and init.mp4."""
    segments = []
    star_init_data = None
    init_segment_url = None
    
    # Extract STAR-INIT-DATA from #EXT-X-MAP tag
    map_match = re.search(r'#EXT-X-MAP:URI="([^"]+?\.mp4)"(?:,BYTERANGE="([^"]+?)")?(?:,STAR-INIT-DATA="([^"]+?)")?', m3u8_content)
    if map_match:
        init_segment_url = map_match.group(1)
        if map_match.group(3):
            star_init_data = map_match.group(3)
            print(lang_strings["star_init_data_found_map"].format(data=star_init_data[:50]))

    # If not in EXT-X-MAP, check general STAR-INIT-DATA tag
    if not star_init_data:
        star_init_data_match = re.search(r'#STAR-INIT-DATA:([^\n]+)', m3u8_content)
        if star_init_data_match:
            star_init_data = star_init_data_match.group(1).strip()
            print(lang_strings["star_init_data_found"].format(data=star_init_data[:50]))
    
    if not star_init_data:
        print(lang_strings["star_init_data_not_found"])

    # Extract segment URLs
    for line in m3u8_content.splitlines():
        if line and not line.startswith('#'):
            segments.append(line.strip())
            
    if not segments:
        print(lang_strings["no_segments_found"])
        return None, None, None
    
    print(lang_strings["segments_found"].format(count=len(segments)))
    return init_segment_url, segments, star_init_data

def combine_segments_py_binary(segments_dir, output_file, lang_strings):
    """Combines downloaded video segments using pure Python binary concatenation."""
    
    print(lang_strings["combining_segments"])
    
    # Get all downloaded segment files and sort them numerically
    all_segment_files = glob.glob(os.path.join(segments_dir, "*"))
    segment_files_to_combine = [f for f in all_segment_files if os.path.isfile(f) and not os.path.basename(f).startswith("input")]

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', os.path.basename(s))]

    sorted_segment_paths = sorted(segment_files_to_combine, key=natural_sort_key)
    
    if not sorted_segment_paths:
        print(lang_strings["no_segments_to_combine"])
        return False

    try:
        with open(output_file, 'wb') as outfile:
            for segment_path in sorted_segment_paths:
                with open(segment_path, 'rb') as infile:
                    outfile.write(infile.read())
        print(lang_strings["combine_success"])
        return True
    except IOError as e:
        print(lang_strings["combine_failed_py_binary"].format(error=e))
        print(lang_strings["suggestions_header"])
        print(lang_strings["space_issue_suggestion"])
        print(lang_strings["file_access_issue_suggestion"])
        return False
    except Exception as e:
        print(lang_strings["combine_failed_py_binary_generic"].format(error=e))
        return False


def cleanup_files(lang_strings):
    """Cleans up intermediate files and directories."""
    print(lang_strings["starting_cleanup"])
    deleted_count = 0

    downloads_dir = os.path.join(SCRIPT_DIR, "downloads")
    if os.path.exists(downloads_dir):
        try:
            shutil.rmtree(downloads_dir)
            print(lang_strings["deleted_directory"].format(directory=downloads_dir))
            deleted_count += 1
        except OSError as e:
            print(lang_strings["delete_directory_failed"].format(directory=downloads_dir, error=e))
    
    print(lang_strings["cleanup_complete"].format(deleted=deleted_count))

# --- Main Logic ---

def main():
    config = load_config()
    
    # --- Language Selection ---
    lang_code = config.get('language')
    if not lang_code:
        print("Please choose a language (1 for English, 2 for Chinese):")
        print("请选择语言/ (1 为英文, 2 为中文):")
        while True:
            choice = input("Enter 1 or 2: ").strip()
            if choice == '1':
                lang_code = 'en'
                break
            elif choice == '2':
                lang_code = 'zh'
                break
            else:
                print("Invalid choice. Please enter 1 or 2.")
                print("无效选择。请输入 1 或 2。")
        config['language'] = lang_code
        save_config(config)
    
    lang_strings = load_language_strings(lang_code)
    default_lang_strings = load_language_strings('en') # Fallback for error messages

    print(lang_strings["title"])
    print(lang_strings["titlea"])
    print("=" * 60)

    try:
        # --- M3U8 URL Input ---
        m3u8_url = input(lang_strings["m3u8_url_prompt"]).strip()
        while not (m3u8_url.startswith("http://") or m3u8_url.startswith("https://")):
            print(lang_strings["error_m3u8_url_prefix"])
            m3u8_url = input(lang_strings["m3u8_url_prompt"]).strip()

        # --- Load or Initialize Headers ---
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14) StarTimesON/6.16.5-1',
            'Accept': '*/*',
            'Range': 'bytes=0-',
            'Connection': 'close',
            'Icy-MetaData': '1',
            'Accept-Encoding': 'gzip',
            'Content-Type': 'text/plain',
            'X-UserID': '123456789',
            'X-DeviceID': 'abcdefghijklmnopqrstyvwxyzabcdef_android',
            'X-EventID': 'VOD-mynameis-1145-1419-1910-muyuegithub1',
            'X-PlayID': 'adbcdefg-1a2b-1145-3c4d-114514191910'
        }
        
        headers_from_config = config.get('headers', {})
        current_headers = default_headers.copy()
        current_headers.update(headers_from_config)

        # Prompt for cookie value
        user_cookie = input(lang_strings["cookie_prompt"]).strip()
        if not user_cookie:
            print(lang_strings["warning_no_cookie"])
        
        # Add or update Cookie in the current headers
        if user_cookie:
            current_headers['Cookie'] = user_cookie
        elif 'Cookie' in current_headers:
            del current_headers['Cookie']

        # Save non-Cookie headers back to config
        if not headers_from_config or headers_from_config != {k: v for k, v in default_headers.items()}:
            headers_to_save = {k: v for k, v in current_headers.items() if k != 'Cookie'}
            if headers_to_save != config.get('headers', {}):
                config['headers'] = headers_to_save
                save_config(config)
                print(lang_strings["headers_saved_to_config"])
                print(lang_strings["headers_info_prompt"])


        # --- Download M3U8 ---
        m3u8_content = download_m3u8(m3u8_url, current_headers, lang_strings)
        if not m3u8_content:
            input(lang_strings["press_enter_to_exit"])
            sys.exit(1)

        init_segment_url, segments, star_init_data = parse_m3u8(m3u8_content, lang_strings)

        # --- Handle STAR-INIT-DATA and DRM (if applicable) ---
        decryption_key = None
        content_key_id = None
        if star_init_data:
            parsed_star_data = parse_star_init_data(star_init_data)
            if parsed_star_data:
                pssh_data = parsed_star_data.get('pssh')
                encrypted_key = parsed_star_data.get('encryptedKey')

                if pssh_data:
                    content_key_id = extract_key_from_pssh(pssh_data)
                    if content_key_id:
                        print(lang_strings["content_key_id_found"].format(kid=content_key_id))
                    else:
                        print(lang_strings["content_key_id_not_found"])

                if encrypted_key and content_key_id:
                    print(lang_strings["attempting_key_decryption"])
                    if decryption_key:
                        print(lang_strings["key_decryption_success"])
                    else:
                        print(lang_strings["key_decryption_failed"])
                        print(lang_strings["drm_hint"])
                else:
                    print(lang_strings["no_encrypted_key_or_pssh"])
            else:
                print(lang_strings["failed_to_parse_star_init_data"])
        
        # --- Create downloads directory ---
        downloads_dir = os.path.join(SCRIPT_DIR, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        # Make segment URLs absolute and ensure init.mp4 is first
        processed_segments = []
        if init_segment_url:
            if not (init_segment_url.startswith("http://") or init_segment_url.startswith("https://")):
                processed_segments.append(urljoin(m3u8_url, init_segment_url))
            else:
                processed_segments.append(init_segment_url)
        
        for segment in segments:
            if not (segment.startswith("http://") or segment.startswith("https://")):
                processed_segments.append(urljoin(m3u8_url, segment))
            else:
                processed_segments.append(segment)
        segments = processed_segments


        # --- Download Segments ---
        if not segments:
            print(lang_strings["no_segments_to_download"])
            input(lang_strings["press_enter_to_exit"])
            sys.exit(1)

        downloader = Downloader()
        downloader.total = len(segments)
        
        print(lang_strings["start_downloading_segments"].format(count=len(segments)))
        
        # Use ThreadPoolExecutor for concurrent downloads
        max_workers = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_segment = {}
            for i, segment_url in enumerate(segments):
                ext = os.path.splitext(urlparse(segment_url).path)[1] or '.ts'
                segment_filename = f"{i:05d}{ext}" if not (i == 0 and urlparse(segment_url).path.endswith('.mp4') and 'init' in urlparse(segment_url).path.lower()) else "init.mp4"
                segment_path = os.path.join(downloads_dir, segment_filename)
                
                future = executor.submit(
                    download_segment, 
                    segment_url, 
                    current_headers, 
                    segment_path,
                    lang_strings, 
                    downloader
                )
                future_to_segment[future] = segment_url
            
            for future in concurrent.futures.as_completed(future_to_segment):
                segment_url = future_to_segment[future]
                try:
                    success = future.result()
                    if not success:
                        print(lang_strings["segment_download_failed_summary"].format(url=segment_url))
                except Exception as exc:
                    print(lang_strings["segment_download_exception"].format(url=segment_url, error=exc))
        
        print(f"\n{lang_strings['download_summary'].format(completed=downloader.completed, failed=downloader.failed, total=downloader.total)}")

        # --- Combine Segments ---
        final_output_file_name = os.path.basename(urlparse(m3u8_url).path).replace(".m3u8", ".mp4")
        if not final_output_file_name or final_output_file_name == ".mp4":
            final_output_file_name = "output.mp4"
            
        final_output_file = os.path.join(SCRIPT_DIR, final_output_file_name)
        
        # Call the pure Python binary combine function
        if combine_segments_py_binary(downloads_dir, final_output_file, lang_strings):
            print("\n" + "=" * 60)
            print(lang_strings["final_output_file"].format(file=final_output_file))
            
            if os.path.exists(final_output_file):
                size = os.path.getsize(final_output_file)
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