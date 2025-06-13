# StarTimes Video Download Tool

A Python-based dedicated video downloader for the StarTimes APP. This software is under active development - contributions and suggestions are welcome!

---
## Documentation Language
[English](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/README.md) | [中文](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/README_CN-ZH.md)

---
## Install Dependencies

```bash
pip install -r requirements.txt
```

---
## Usage Guide
Simply input the M3U8 URL and Cookie value obtained through packet capture to initiate downloads.

---

## How to Obtain M3U8 Links and Cookies (ProxyPin Example)

### Environment Setup
1. **Install HTTPS Certificate**  
   Root users: Install as a root certificate  
   *Non-root users: Follow standard certificate installation procedure*

2. **Configure Whitelist**
   - Navigate to `Proxy Filter` → `App Whitelist`
   - Enable `Whitelist Mode` (Toggle switch to ON)
   - Tap `+` to add StarTimes APP  
   ![Whitelist Configuration](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG1-P4.png)

### Packet Capture Process
3. **Initiate Packet Capture**
   - Return to the main capture interface
   - Search using the following keywords:
     ```bash
     "m3u8"
     "gcp-video.gslb.startimestv.com"
     "vod_g"
     ```

4. **Key Data Extraction**
   | Location         | Target Data          | Example Screenshot        |
   |------------------|----------------------|--------------------------|
   | `General` tab    | M3U8 URL            | ![General Tab](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG2-P1.png) |
   | `Request` header | Cookie Value        | ![Request Header](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG2-P2.png) |

---

## Troubleshooting
If downloads fail, modify request parameters in the source code:  
`headers = {` (Lines 116-129)

---

## Legal Disclaimer
> **Important Notice**  
> This tool is intended **for educational purposes only**. Users are solely responsible for any violations of local laws or StarTimes' Terms of Service. The developer assumes no liability for any misuse of this software.
