import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- THAY ID FILE SHEET CỦA BẠN VÀO ĐÂY ---
# (File này bạn phải tạo thủ công và Share cho Robot trước)
SHEET_ID = '1WYj8fx8jLanw5gzb1-zxJSDyRB8aOMh8j6zEosfzJAw' 
# ------------------------------------------

SERVICE_ACCOUNT_FILE = 'service_account.json'

def test_ghi_sheet():
    print("1. Đang kết nối Google Sheet...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        
        # Mở file Sheet theo ID
        sh = client.open_by_key(SHEET_ID)
        print(f"✅ Đã tìm thấy file: {sh.title}")
        
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        print("👉 Gợi ý: Kiểm tra xem bạn đã Share quyền Editor cho Robot vào file Sheet này chưa?")
        return

    print("2. Đang tạo Tab (Sheet) mới...")
    try:
        # Tạo tên Tab là ngày giờ hiện tại
        tab_name = datetime.now().strftime("%Y-%m-%d_%H-%M")
        
        # Tạo worksheet mới
        worksheet = sh.add_worksheet(title=tab_name, rows=100, cols=10)
        
        # Ghi dữ liệu test
        worksheet.update('A1', [['Test Robot', 'Giá', 'Link'], ['Iphone 15', '30tr', 'Link Test']])
        
        print(f"🎉 THÀNH CÔNG! Đã ghi dữ liệu vào Tab: {tab_name}")
        print("👉 Hãy mở file Google Sheet của bạn ra kiểm tra ngay!")
        
    except Exception as e:
        print(f"❌ Lỗi ghi dữ liệu: {e}")

if __name__ == "__main__":
    test_ghi_sheet()
