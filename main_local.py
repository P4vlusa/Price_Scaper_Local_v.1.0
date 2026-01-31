import json
import sys
import io
import os
import time
import random
import glob
import subprocess
import concurrent.futures
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
# ==============================================================================

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- THAY ID GOOGLE SHEET CỦA BẠN ---
SPREADSHEET_ID = '1YqO4MVEzAz61jc_WCVSS00LpRlrDb5r0LnuzNi6BYUY'
MASTER_SHEET_NAME = 'Sheet2'

MAX_WORKERS = 4

# --- CẤU HÌNH ĐƯỜNG DẪN HYBRID ---
FIXED_KEY_PATH = r'C:\Users\Pavlusa\OneDrive\Work\Python\Google_Token\service_account.json'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_CONFIG = os.path.join(BASE_DIR, 'configs')

if os.path.exists(FIXED_KEY_PATH):
    SERVICE_ACCOUNT_FILE = FIXED_KEY_PATH
    print(f"🔑 Dùng Key Local: {SERVICE_ACCOUNT_FILE}")
else:
    SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'service_account.json')
    print(f"⚠️ Dùng Key Repo: {SERVICE_ACCOUNT_FILE}")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# ==============================================================================
# 2. CÁC HÀM XỬ LÝ
# ==============================================================================

def kill_old_drivers():
    try:
        if os.name == 'nt':
            subprocess.call("taskkill /F /IM chromedriver.exe /T", shell=True, stderr=subprocess.DEVNULL)
    except: pass

def get_google_sheet_client():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ Lỗi: Không tìm thấy file Key.")
        return None
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return None

def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--log-level=3")
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=opts)
    except:
        return webdriver.Chrome(options=opts)

def scrape_product_logic(driver, product):
    """
    Hàm tìm giá thông minh: Hỗ trợ nhiều Selector + Tự động nhận diện XPath/CSS
    """
    # 1. Gom tất cả selector vào 1 danh sách
    selector = []
    
    # Ưu tiên list 'selector' mới
    if 'selector' in product and isinstance(product['selector'], list):
        selector.extend(product['selector'])
    
    # Hỗ trợ cả key 'selector' cũ (để không bị lỗi file config cũ)
    if 'selector' in product and product['selector']:
        selector.append(product['selector'])
        
    # Nếu không có cái nào thì chịu
    if not selector:
        return "0", "No Selector"

    # 2. Thử từng cái một (Cơ chế Backup)
    for sel in selector:
        try:
            # Tự động nhận diện XPath (Bắt đầu bằng / hoặc () hoặc ..)
            by_type = By.CSS_SELECTOR
            if sel.strip().startswith('/') or sel.strip().startswith('(') or sel.strip().startswith('..'):
                by_type = By.XPATH
            
            # Tìm phần tử
            element = driver.find_element(by_type, sel)
            
            # Lọc lấy số
            raw_text = element.text
            clean_price = ''.join(filter(str.isdigit, raw_text))
            
            # Nếu lấy được giá > 0 thì trả về ngay (Thành công)
            if clean_price and int(clean_price) > 0:
                return clean_price, "OK"
                
        except Exception:
            # Lỗi selector này thì lẳng lặng thử cái tiếp theo
            continue
            
    # Thử hết danh sách mà vẫn không được
    return "0", "Fail"

def scrape_dealer(config_path):
    dealer_name = os.path.basename(config_path).replace('.json', '').upper()
    print(f"🔵 [{dealer_name}] Bắt đầu chạy...")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except Exception as e:
        print(f"❌ Lỗi đọc file {dealer_name}: {e}")
        return []

    driver = None
    results = []

    try:
        driver = get_driver()
        
        for i, product in enumerate(products):
            current_time = datetime.now()
            
            row = [
                current_time.strftime("%d/%m/%Y"), 
                current_time.strftime("%H:%M:%S"), 
                dealer_name,                       
                product.get('name', 'Unknown'),    
                "0",                               
                "Fail",                            
                product.get('url', '')             
            ]

            try:
                driver.get(product['url'])
                
                # --- GỌI HÀM TÌM GIÁ THÔNG MINH ---
                price, status = scrape_product_logic(driver, product)
                
                row[4] = price
                row[5] = status
                # ----------------------------------

            except Exception:
                pass 

            results.append(row)
            
            if i % 20 == 0:
                 print(f"   [{dealer_name}] {i}/{len(products)}...")

    except Exception as e:
        print(f"❌ Lỗi Driver [{dealer_name}]: {e}")
    finally:
        if driver: 
            try: driver.quit()
            except: pass
            
    print(f"✅ [{dealer_name}] Xong {len(results)} dòng.")
    return results

def save_to_sheet_safe(data_rows):
    if not data_rows: return
    client = get_google_sheet_client()
    if not client: return

    for attempt in range(5):
        try:
            sh = client.open_by_key(SPREADSHEET_ID)
            try:
                ws = sh.worksheet(MASTER_SHEET_NAME)
            except:
                ws = sh.add_worksheet(title=MASTER_SHEET_NAME, rows=5000, cols=10)
                ws.append_row(["Ngày", "Thời gian", "Đại lý", "Sản phẩm", "Giá", "Trạng thái", "Link"])
            
            time.sleep(random.uniform(1, 5))
            ws.append_rows(data_rows)
            print(f"💾 ĐÃ LƯU {len(data_rows)} DÒNG LÊN SHEET!")
            return
        except Exception as e:
            wait = random.uniform(5, 10)
            print(f"⚠️ Sheet bận, chờ {wait:.1f}s... (Lỗi: {e})")
            time.sleep(wait)

def main():
    kill_old_drivers()
    print(f"📂 Configs: {FOLDER_CONFIG}")

    if not os.path.exists(FOLDER_CONFIG):
        print(f"❌ Không tìm thấy thư mục configs.")
        return

    config_files = glob.glob(os.path.join(FOLDER_CONFIG, "*.json"))
    print(f"🚀 Tìm thấy {len(config_files)} đại lý. Chạy {MAX_WORKERS} luồng...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(scrape_dealer, f): f for f in config_files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                data = future.result()
                save_to_sheet_safe(data)
            except Exception as exc:
                print(f"❌ Lỗi luồng: {exc}")

    print("\n🎉 HOÀN TẤT!")

if __name__ == "__main__":
    main()
