import os
import re
import requests
import subprocess
import paramiko
from urllib.parse import urlparse
from time import sleep

yt_info_path = "yt_info.txt"
output_dir = "output"
cookies_path = os.path.join(os.getcwd(), "cookies.txt")

# SFTP 環境變數
SF_L = os.getenv("SF_L")
sftp_targets = [s for s in [SF_L] if s]

def extract_m3u8_from_html(html):
    matches = re.findall(r'(https://[^"]+\.m3u8)', html)
    filtered = [m for m in matches if "index" in m or "playlist" in m or "master" in m]
    if filtered:
        print("✅ 成功從 HTML 抽取 m3u8")
        return filtered[0]
    return None

def grab_m3u8_from_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
    }
    try:
        print(f"🔍 嘗試解析 M3U8 (requests): {url}")
        html = requests.get(url, headers=headers, timeout=10).text
        return extract_m3u8_from_html(html)
    except Exception as e1:
        print(f"⚠️ requests 失敗: {repr(e1)}，改用 cloudscraper")
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper()
            html = scraper.get(url, timeout=10).text
            return extract_m3u8_from_html(html)
        except Exception as e2:
            print(f"❌ cloudscraper 也失敗: {repr(e2)}")
            return None

def fallback_yt_dlp(url, cookies="cookies.txt"):
    print(f"⚙️ 執行 yt-dlp: {url}")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
                "--cookies", cookies,
                "-g", url
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        m3u8 = result.stdout.strip()
        if m3u8.startswith("http"):
            print("✅ 成功取得 m3u8（yt-dlp）")
            return m3u8
        else:
            print(f"❌ yt-dlp 無回傳有效 URL: {result.stderr.strip()}")
    except Exception as e:
        print(f"❌ yt-dlp 執行失敗: {repr(e)}")
    return None

def get_m3u8(url):
    m3u8 = grab_m3u8_from_html(url)
    if m3u8:
        return m3u8
    return fallback_yt_dlp(url)

def parse_yt_info(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("~~"):
            i += 1
            continue
        if "|" in lines[i] and (i + 1) < len(lines):
            info_line = lines[i]
            url_line = lines[i + 1]
            entries.append((info_line, url_line))
            i += 2
        else:
            i += 1
    return entries

def write_single_m3u8(index, name, group, logo, tvg_id, m3u8_url):
    filename = f"y{index:02d}.m3u8"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}\n')
        f.write(f"{m3u8_url}\n")
    print(f"✅ 已寫入 {filename}")
    return filepath, filename

def write_php_redirect(index, m3u8_url):
    filename = f"y{index:02d}.php"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("<?php\n")
        f.write(f"header('Location: {m3u8_url}');\n")
        f.write("?>\n")
    print(f"✅ 已寫入 {filename}")
    return filepath, filename

def upload_via_sftp(sftp_url, local_path, remote_name):
    try:
        parts = urlparse(sftp_url)
        hostname = parts.hostname
        port = parts.port or 22
        username = parts.username
        password = parts.password

        transport = paramiko.Transport((hostname, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        sftp.put(local_path, remote_name)
        print(f"📤 已上傳到 SFTP: {hostname}/{remote_name}")

        sftp.close()
        transport.close()
    except Exception as e:
        print(f"❌ 上傳 SFTP 失敗 ({sftp_url}): {repr(e)}")

def main():
    os.makedirs(output_dir, exist_ok=True)

    entries = parse_yt_info(yt_info_path)
    for idx, (info_line, url) in enumerate(entries, 1):
        try:
            parts = [x.strip() for x in info_line.split("|")]
            name, group, logo, tvg_id = (parts + [""] * 4)[:4]
            print(f"\n🔍 嘗試解析 M3U8: {url}")
            m3u8_url = get_m3u8(url)
            if m3u8_url:
                m3u8_path, m3u8_name = write_single_m3u8(idx, name, group, logo, tvg_id, m3u8_url)
                php_path, php_name = write_php_redirect(idx, m3u8_url)

                for target in sftp_targets:
                    upload_via_sftp(target, m3u8_path, m3u8_name)
                    # 若你要上傳 .php，一併啟用下行
                    # upload_via_sftp(target, php_path, php_name)

                sleep(1)
            else:
                print(f"❌ 無法取得 M3U8: {url}")
        except Exception as e:
            print(f"❌ 錯誤處理頻道 [{info_line}]: {repr(e)}")

if __name__ == "__main__":
    main()
