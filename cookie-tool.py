import requests

def get_program_contents():
    # User input for Authorization Token (用户输入 Authorization Token)
    auth_token = input("Please enter Authorization Token (starts with 'Bearer '): \n请输入 Authorization Token（Bearer 开头）：").strip()
    if not auth_token.lower().startswith("bearer "):
        print("Error: Authorization must start with 'Bearer ' (错误：Authorization 必须以 'Bearer ' 开头)")
        return

    url = "https://upms.startimestv.com/play-service/v1/aaa/program-contents/ad-gslb"
    params = {
        "program_id": "16164",
        "play_id": "1fa2f503-6e1f-4f42-9181-2e78730b653f",
        "video_limit": "0",
        "pic_limit": "2",
        "memory": "L6",
        "cpu": "8x3.2GHz",
        "resolution": "1080x2320"
    }
    headers = {
        "Authorization": auth_token,
        "lnCode": "en",
        "sysLang": "zh",
        "appVersion": "61650",
        "timeZoneId": "Asia/Shanghai",
        "clientType": "android",
        "User-Agent": "StarTimesON/6.16.5(Android)",
        "Host": "upms.startimestv.com",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }

    try:
        # Explicitly disable proxies to avoid VPN or local proxy interference with requests (显式禁用代理，以避免 VPN 或本地代理干扰请求)
        proxies = {
            "http": None,
            "https": None
        }

        response = requests.get(url, headers=headers, params=params, proxies=proxies)
        response.raise_for_status()  # If the response is not 200, an exception will be raised (如果响应不是 200，会抛出异常)

        data = response.json()
        header_props = data.get("header_propertys")

        if header_props:
            print("\nExtracted 'header_propertys' field is as follows: \n(提取的 header_propertys 字段如下：)\n")
            print(header_props)
        else:
            print("Field 'header_propertys' not found, full response is as follows: (未找到 header_propertys 字段，完整响应如下：)")
            print(response.text)

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP Error: {http_err} (HTTP 错误: {http_err})")
        print("Response content: (响应内容：)", response.text)
    except Exception as err:
        print(f"An error occurred during the request: {err} (请求过程中出现错误: {err})")

if __name__ == "__main__":
    get_program_contents()