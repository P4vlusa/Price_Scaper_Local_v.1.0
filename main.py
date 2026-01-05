import json
import sys
import os
import time
import random
import glob
from datetime import datetime

# --- CÀI ĐẶT THƯ VIỆN ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
# Thêm thư viện để xử lý chờ đợi thông minh
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ==============================================================================
# CẤU HÌNH
# ==============================================================================

MASTER_SHEET_ID = '1WYj8fx8jLanw5gzb1-zxJSDyRB8aOMh8j6zEosfzJAw' 

# File nằm cùng thư mục trên Cloud
SERVICE_ACCOUNT_FILE = 'service_account.json'
FOLDER_CONFIG = 'configs'

# ==============================================================================
# CÁC HÀM XỬ LÝ
# ==============================================================================

def get_google_sheet_client():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ Lỗi: Không thấy file '{SERVICE_ACCOUNT_FILE}'")
        return None
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return None

def upload_to_sheet(client, dealer_name, data_rows):
    if not client or not data_rows: return

    try:
        sh = client.open_by_key(MASTER_SHEET_ID)
        tab_name = dealer_name.strip().replace(" ", "_").upper()
        
        try:
            worksheet = sh.worksheet(tab_name)
        except:
            print(f"   ✨ Tạo Tab mới '{tab_name}'...")
            worksheet = sh.add_worksheet(title=tab_name, rows=2000, cols=10)
            worksheet.append_row(["Date", "Time", "Dealer", "Product", "Price", "Status", "URL"])

        current_date_str = datetime.now().strftime("%d/%m/%Y")
        rows_to_append = []
        for item in data_rows:
            rows_to_append.append([
                current_date_str, item['Time'], dealer_name,
                item['Product'], item['Price'], item['Status'], item['URL']
            ])
            
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
            print(f"   ✅ Đã lưu {len(rows_to_append)} dòng.")
        
    except Exception as e:
        print(f"   ❌ Lỗi Upload Sheet: {e}")

def get_driver():
    opts = Options()
    # Chế độ chạy ẩn bắt buộc cho Server
    opts.add_argument("--headless=new") 
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    
    # Fake User Agent như máy thật
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Chặn ảnh để load nhanh
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        
        # --- QUAN TRỌNG: CÀI ĐẶT TIMEOUT ---
        # Nếu trang web load quá 30 giây -> Cắt bụp, báo lỗi ngay (Không treo máy)
        driver.set_page_load_timeout(30)
        return driver
    except:
        return webdriver.Chrome(options=opts)

def process_dealer_smart(config_file, gs_client):
    dealer_name = os.path.basename(config_file).replace('.json', '')
    print(f"\n🔵 XỬ LÝ: {dealer_name.upper()}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except: return

    results = []
    driver = None

    try:
        print("   🚀 Đang khởi động Chrome...")
        driver = get_driver()
        
        total = len(products)
        for i, product in enumerate(products):
            result = {
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Product": product.get('name', 'Unknown'),
                "Price": "0",
                "Status": "Fail",
                "URL": product['url']
            }

            try:
                # 1. Tải trang (Có timeout 30s đã set ở trên)
                driver.get(product['url'])
                
                # 2. Kiểm tra chặn (403 Forbidden)
                title = driver.title
                if "Access Denied" in title or "403" in title or "Captcha" in title:
                    result['Status'] = "BLOCKED (Cloud IP)"
                    print(f"   🚫 [{i+1}/{total}] Bị chặn IP!")
                else:
                    # 3. Tìm giá (Chờ tối đa 10 giây, không thấy thì bỏ qua)
                    selector = product.get('selector')
                    sel_type = product.get('type', 'css')
                    
                    by_type = By.XPATH if sel_type == 'xpath' else By.CSS_SELECTOR
                    
                    # Dùng WebDriverWait thay vì find_element thông thường
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((by_type, selector))
                    )
                    
                    if element:
                        clean_price = ''.join(filter(str.isdigit, element.text))
                        if clean_price:
                            result['Price'] = clean_price
                            result['Status'] = 'OK'
                            print(f"   ✅ [{i+1}/{total}] {clean_price} VNĐ")
                        else:
                            result['Status'] = "No Number"
                            print(f"   ⚠️ [{i+1}/{total}] Không thấy số")

            except TimeoutException:
                # Nếu quá thời gian quy định
                result['Status'] = "TIMEOUT"
                print(f"   ⏰ [{i+1}/{total}] Quá thời gian tải trang.")
            except Exception as e:
                # Các lỗi khác
                result['Status'] = "ERROR"
                print(f"   ❌ [{i+1}/{total}] Lỗi.")

            results.append(result)
            # Nghỉ ngắn giữa các link
            time.sleep(2)

    except Exception as e:
        print(f"❌ Lỗi Driver tổng: {e}")
    finally:
        if driver: 
            driver.quit()
            print("   💤 Đã đóng Chrome.")

    print("   -> Upload dữ liệu...")
    upload_to_sheet(gs_client, dealer_name, results)

def main():
    print(f"📂 Thư mục hiện tại: {os.getcwd()}")
    
    gs_client = get_google_sheet_client()
    if not gs_client: return

    if not os.path.exists(FOLDER_CONFIG):
        print(f"⚠️ Không thấy thư mục configs. Hãy kiểm tra lại repo!")
        return

    config_files = glob.glob(os.path.join(FOLDER_CONFIG, "*.json"))
    print(f"🚀 TÌM THẤY {len(config_files)} ĐẠI LÝ.")
    
    for config_file in config_files:
        process_dealer_smart(config_file, gs_client)
        print("-" * 40)

    print("\n🎉 HOÀN TẤT!")

if __name__ == "__main__":
    main()
