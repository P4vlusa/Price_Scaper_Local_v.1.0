import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- ĐIỀN ID THƯ MỤC CỦA BẠN VÀO ĐÂY ---
PARENT_FOLDER_ID = '1H_xxxxxxxxxxxxxxxxxxxxxx'  # <--- NHỚ THAY ID VÀO ĐÂY
SERVICE_ACCOUNT_FILE = 'service_account.json'

def test_upload():
    print("1. Đang kết nối Google Drive...")
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Lỗi file key json: {e}")
        return

    print("2. Đang tạo file test...")
    file_name = "test_ket_noi.csv" # Đổi đuôi thành csv giả lập
    with open(file_name, "w") as f:
        f.write("Cot A,Cot B\nDu lieu 1,Du lieu 2")

    print("3. Đang upload lên Drive (Chuyển sang Google Sheet)...")
    try:
        # --- QUAN TRỌNG: CẤU HÌNH ĐỂ LÁCH LUẬT DUNG LƯỢNG ---
        file_metadata = {
            'name': 'Test_Ket_Noi_Sheet',  # Tên file trên Drive
            'parents': [PARENT_FOLDER_ID],
            # Dòng này ép Google chuyển file CSV thành Google Sheet (Không tốn dung lượng)
            'mimeType': 'application/vnd.google-apps.spreadsheet' 
        }
        
        # File gốc ở máy vẫn là CSV/Text
        media = MediaFileUpload(file_name, mimetype='text/csv')
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"✅ THÀNH CÔNG! File ID: {file.get('id')}")
        print("👉 Vào Drive xem có file 'Test_Ket_Noi_Sheet' (màu xanh lá) chưa.")
        
    except Exception as e:
        print(f"❌ VẪN LỖI: {e}")
        print("👉 Kiểm tra: Bạn đã Share quyền EDITOR (Người chỉnh sửa) cho email Robot chưa?")

if __name__ == "__main__":
    test_upload()
