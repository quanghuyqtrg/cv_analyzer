# Changelog

## 2026-08-16 — Text Extractor cho PDF/DOCX

### Files created
| File | Mô tả |
|------|-------|
| `backend/app/services/__init__.py` | Package init (empty) |
| `backend/app/services/extractor.py` | Module trích xuất text từ PDF/DOCX |

### Files modified
| File | Thay đổi |
|------|----------|
| `backend/requirements.txt` | Thêm `pdfplumber==0.11.10`, `python-docx==1.1.2` |

### Sửa đổi sau tạo file

| # | File | Dòng | Cũ | Mới | Lý do |
|---|------|------|----|-----|-------|
| 1 | `backend/app/services/extractor.py` | 16 | `from lxml import etree` | *(xoá dòng)* | Import không được sử dụng — `findall()` chạy trực tiếp trên lxml element từ `python-docx`, không cần import `etree` riêng. Ngoài ra `lxml` chỉ cài trong Docker, gây lỗi IDE ở local. |
