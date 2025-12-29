import json
import csv
import sys
import os
import time
import random
import concurrent.futures
from datetime import datetime

# Thư viện Google
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Thư viện Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# Thư viện quản lý Driver (Chỉ dùng khi chạy Local)
from webdriver_manager.chrome import ChromeDriverManager

# --- CẤU HÌNH HỆ THỐNG ---
# 1. ID thư mục Google Drive (Thay bằng ID thật của bạn vào bên dưới)
PARENT_FOLDER_ID = '1udCflvt7ujbLCDS2cU1YtNZ9K58i84q5' 

# 2. Tên file key Google
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

# 3. Số luồng chạy song song (GitHub Actions mạnh nên để 3-5 là ổn)
MAX_WORKERS = 4

def get_drive_service():
    """Kết nối API Google Drive"""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            print(f"⚠️ Không thấy file {SERVICE_ACCOUNT_FILE}, bỏ qua bước upload Drive.")
            return None
            
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Drive: {e}")
        return None

def create_daily_folder(service):
    """Tạo folder theo ngày trên Drive"""
    if not service: return None
    
    folder_name = datetime.now().strftime("%Y-%m-%d")
    
    query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [PARENT_FOLDER_ID]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def get_driver():
    """Khởi tạo Chrome Driver thông minh (Tự chọn Local hoặc Server)"""
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Chạy ẩn
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- FIX LỖI QUAN TRỌNG TẠI ĐÂY ---
    # Kiểm tra xem đang chạy trên GitHub Actions hay máy thường
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print("🔧 Environment: GitHub Actions (Using System Driver)")
        # GitHub đã cài sẵn Chrome, không cần tải lại -> Tránh lỗi unzip
        return webdriver.Chrome(options=chrome_options)
    else:
        print("💻 Environment: Local Machine (Using Webdriver Manager)")
        # Máy cá nhân thì tự tải driver mới nhất
        try:
            return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            print(f"⚠️ Lỗi Webdriver Manager: {e}. Thử chạy fallback...")
            return webdriver.Chrome(options=chrome_options)

def get_price_selenium(product):
    """Vào web lấy giá"""
    driver = None
    result = None
    
    try:
        driver = get_driver()
        
        # Random nghỉ 1 chút để tránh spam
        time.sleep(random.uniform(1, 3))
        
        print(f"▶️ Checking: {product['name']}...")
        driver.get(product['url'])
        
        # Đợi web tải (5 giây)
        time.sleep(5) 
        
        # Lấy tiêu đề để debug lỗi chặn IP
        # print(f"   ℹ️ Title: {driver.title}") 

        element = None
        selector = product.get('selector')
        sel_type = product.get('type', 'css')
        
        if sel_type == 'xpath':
            element = driver.find_element(By.XPATH, selector)
        else:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            
        if element:
            raw_text = element.text
            clean_price = ''.join(filter(str.isdigit, raw_text))
            
            if clean_price:
                print(f"   ✅ GIÁ: {clean_price}")
                result = {
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Product": product['name'],
                    "Price": clean_price,
                    "Source": product.get('source', 'Unknown'),
                    "URL": product['url']
                }
            else:
                 print(f"   ⚠️ Có element nhưng không có số: {product['name']}")
        
    except Exception as e:
        # Lỗi thường gặp: NoSuchElementException hoặc Timeout
        print(f"   ❌ Lỗi {product['name']}: Không tìm thấy giá hoặc Web chặn.")
    finally:
        if driver:
            driver.quit()
        
    return result

def main():
    # --- XỬ LÝ THAM SỐ ĐẦU VÀO ---
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # Nếu không có tham số, mặc định chạy test file này
        config_path = 'configs/tgdd.json' 
        print(f"⚠️ Không có tham số config. Chạy chế độ TEST: {config_path}")

    if not os.path.exists(config_path):
        print(f"⛔ File config không tồn tại: {config_path}")
        # Tạo file mẫu nếu chưa có để tránh crash
        if not os.path.exists('configs'): os.makedirs('configs')
        with open(config_path, 'w') as f:
            json.dump([{"name":"Test","url":"https://google.com","selector":"body","type":"css"}], f)
        print("   -> Đã tạo file mẫu. Hãy chạy lại.")
        return

    print(f"\n🚀 BẮT ĐẦU QUÉT: {config_path}")
    
    # 1. Đọc file JSON
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except Exception as e:
        print(f"⛔ Lỗi cú pháp JSON: {e}")
        return

    results = []
    
    # 2. Chạy đa luồng
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_price_selenium, p) for p in products]
        for future in concurrent.futures.as_completed(futures):
            data = future.result()
            if data:
                results.append(data)

    # 3. Ghi file CSV
    if not results:
        print("\n⚠️ KHÔNG LẤY ĐƯỢC DỮ LIỆU NÀO.")
        return

    print(f"\n✅ Tổng kết: {len(results)} sản phẩm. Đang lưu file...")
    
    base_name = os.path.basename(config_path).replace('.json', '.csv')
    csv_filename = f"Report_{base_name}"
    
    keys = ["Time", "Product", "Price", "Source", "URL"]
    
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"💾 Đã lưu CSV: {csv_filename}")
    except Exception as e:
        print(f"❌ Lỗi ghi file CSV: {e}")
        return

    # 4. Upload Drive
    print("☁️ Uploading to Google Drive...")
    service = get_drive_service()
    if service:
        try:
            folder_id = create_daily_folder(service)
            file_metadata = {'name': csv_filename, 'parents': [folder_id]}
            media = MediaFileUpload(csv_filename, mimetype='text/csv')
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"🎉 THÀNH CÔNG! File ID: {file.get('id')}")
        except Exception as e:
            print(f"❌ Lỗi upload: {e}")
    else:
        print("⚠️ Bỏ qua upload vì không kết nối được Drive.")

if __name__ == "__main__":
    main()
