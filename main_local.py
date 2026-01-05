import json
import sys
import io
import os
import time
import random
import glob
import subprocess
import concurrent.futures
from datetime import datetime

# --- CÀI ĐẶT THƯ VIỆN ---
# pip install selenium webdriver-manager gspread oauth2client

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
# ==============================================================================

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- THAY ID SHEET CỦA BẠN VÀO ĐÂY ---
MASTER_SHEET_ID = 'THAY_ID_SHEET_CUA_BAN_VAO_DAY' 

MAX_WORKERS = 3

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = r'C:\Users\Pavlusa\OneDrive\Work\Python\Google_Token\service_account.json'
FOLDER_CONFIG = os.path.join(CURRENT_DIR, 'configs')

# ==============================================================================
# 2. CÁC HÀM XỬ LÝ
# ==============================================================================

def get_google_sheet_client():
    """Kết nối Google Sheet"""
    print(f"🔑 Đang đọc file key tại: {SERVICE_ACCOUNT_FILE}")
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ Lỗi: Không tìm thấy file 'service_account.json'")
        return None

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        print("✅ Kết nối Google Sheet thành công!")
        return client
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return None

def upload_to_sheet(client, dealer_name, data_rows):
    """Upload dữ liệu (Append)"""
    if not client or not data_rows: return

    try:
        sh = client.open_by_key(MASTER_SHEET_ID)
        tab_name = dealer_name.strip().replace(" ", "_").upper()
        
        worksheet = None
        is_new_sheet = False

        try:
            worksheet = sh.worksheet(tab_name)
        except:
            print(f"   ✨ Tab '{tab_name}' chưa có. Đang tạo mới...")
            worksheet = sh.add_worksheet(title=tab_name, rows=2000, cols=10)
            is_new_sheet = True

        current_date_str = datetime.now().strftime("%d/%m/%Y")
        
        if is_new_sheet:
            header = ["Date", "Time", "Dealer", "Product", "Price", "Status", "URL"]
            worksheet.append_row(header)

        rows_to_append = []
        for item in data_rows:
            row = [
                current_date_str, item['Time'], dealer_name,
                item['Product'], item['Price'], item['Status'], item['URL']
            ]
            rows_to_append.append(row)
            
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
            print(f"   ✅ Đã nối thêm {len(rows_to_append)} dòng vào tab '{tab_name}'.")
        
    except Exception as e:
        print(f"   ❌ Lỗi Upload Sheet: {e}")

def get_driver():
    """Cấu hình Selenium"""
    opts = Options()
    opts.add_argument("--headless=new") 
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage") 
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--log-level=3")

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=opts)
    except Exception:
        return webdriver.Chrome(options=opts)

def scrape_product(product):
    """Quét giá 1 sản phẩm"""
    driver = None
    result = {
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Product": product.get('name', 'Unknown'),
        "Price": "0",
        "Status": "Fail",
        "URL": product.get('url', '')
    }

    try:
        driver = get_driver()
        driver.get(product['url'])
        time.sleep(random.uniform(3, 6))

        selector = product.get('selector')
        sel_type = product.get('type', 'css')
        element = None
        
        if sel_type == 'xpath':
            element = driver.find_element(By.XPATH, selector)
        else:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            
        if element:
            raw_text = element.text
            clean_price = ''.join(filter(str.isdigit, raw_text))
            if clean_price:
                result['Price'] = clean_price
                result['Status'] = 'OK'
            else:
                result['Status'] = 'No Price Found'
                
    except Exception:
        result['Status'] = 'Error/Block'
    finally:
        if driver: 
            try: driver.quit()
            except: pass
        
    return result

def process_dealer(config_file, gs_client):
    dealer_name = os.path.basename(config_file).replace('.json', '')
    print(f"\n🔵 ĐANG XỬ LÝ: {dealer_name.upper()}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except Exception as e:
        print(f"❌ Lỗi đọc config: {e}")
        return

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scrape_product, p) for p in products]
        total = len(products)
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            data = future.result()
            results.append(data)
            print(f"   [{i+1}/{total}] {data['Status']} - {data['Product'][:25]}...")

    print(f"   -> Đang upload dữ liệu...")
    upload_to_sheet(gs_client, dealer_name, results)

# ==============================================================================
# 3. CHƯƠNG TRÌNH CHÍNH
# ==============================================================================
def main():
    kill_old_processes()
    print(f"📂 Thư mục làm việc: {CURRENT_DIR}")
    
    gs_client = get_google_sheet_client()
    if not gs_client: return

    if not os.path.exists(FOLDER_CONFIG):
        os.makedirs(FOLDER_CONFIG)
        sample = [{"name":"iPhone 15","url":"https://www.thegioididong.com/dtdd/iphone-15","selector":".box-price-present","type":"css"}]
        with open(os.path.join(FOLDER_CONFIG, 'tgdd.json'), 'w', encoding='utf-8') as f:
            json.dump(sample, f, indent=2)

    config_files = glob.glob(os.path.join(FOLDER_CONFIG, "*.json"))
    print(f"🚀 TÌM THẤY {len(config_files)} ĐẠI LÝ.")
    
    for config_file in config_files:
        process_dealer(config_file, gs_client)
        print("-" * 40)

    print("\n🎉🎉🎉 HOÀN TẤT!")

if __name__ == "__main__":
    main()
