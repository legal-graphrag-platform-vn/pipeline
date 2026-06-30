# Quy Trình Hoạt Động (Workflow) của Hierarchy Parser

Tài liệu này mô tả chi tiết luồng xử lý và kiến trúc của module **Parser** trong việc cấu trúc hóa văn bản pháp luật Việt Nam.

---

## 1. Tóm Tắt Quy Trình Hoạt Động (Workflow Steps)

Quy trình xử lý của Hierarchy Parser bao gồm 4 bước chính sau đây:

1. **Nhận diện Đầu vào**: 
   * Người dùng truyền tệp đầu vào thông qua CLI (Tệp PDF, Tệp Text `.txt`, hoặc dữ liệu đã cào sẵn từ vbpl.vn trong thư mục raw).
2. **Trích xuất Nội dung thành Dòng (Text Extraction)**:
   * Nếu là PDF Selectable (có text layer): Sử dụng `PyMuPDF` hoặc `PyPDF` để trích xuất văn bản thô theo từng dòng, kèm thông tin font size và bold.
   * Nếu là PDF dạng ảnh quét (Scan): Tự động fallback sang sử dụng `Tesseract OCR` để nhận diện ký tự quang học tiếng Việt.
   * Nếu là Text hoặc dữ liệu đã cào: Đọc trực tiếp nội dung văn bản.
3. **Phân tích Cấu trúc (State Machine)**:
   * Hệ thống duyệt qua từng dòng văn bản và áp dụng máy trạng thái (State Machine).
   * **Xử lý dấu ngoặc kép (`quote_depth`)**: Nếu dòng nằm trong khối trích dẫn (sửa đổi luật), hệ thống coi đây là nội dung tiếp nối và bỏ qua việc kiểm tra cấu trúc mới để tránh chia tách sai các Điều/Khoản lồng nhau.
   * **Khớp Regex**: Phân loại dòng thành Chương, Tiêu đề chương, Điều, Khoản, hoặc Điểm dựa trên danh sách Regex quy định.
   * **Nối dòng (Continuation)**: Nối dòng văn bản thường vào phần tử đang mở gần nhất (Điều, Khoản hoặc Điểm).
4. **Đóng gói & Lưu kết quả**:
   * Chuẩn hóa dữ liệu cấu trúc thành đối tượng `ParsedDocument` sử dụng các Pydantic models.
   * Ghi dữ liệu ra tệp tin cấu trúc `data/processed/<doc_id>/hierarchy.json`.

---

## 2. Chi Tiết Các Bước Xử Lý

### Bước 1: Trích Xuất Dòng Văn Bản (Text Extraction)
Tùy vào tham số truyền vào CLI, hệ thống sử dụng các backend khác nhau:
*   **PyMuPDF (`fitz`)**: Mặc định cho PDF. Trích xuất text cùng các thông tin metadata của font như cỡ chữ (`size`), in đậm (`bold`). Thông tin này giúp xác định tiêu đề chương chính xác.
*   **PyPDF**: Dành riêng cho PDF có text layer chuẩn, tốc độ cực nhanh, không quan tâm font size.
*   **Tesseract OCR**: Dành cho PDF scan. Hệ thống tự động tiền xử lý ảnh (chuyển xám, tăng độ tương phản) và thực hiện nhận diện ký tự quang học tiếng Việt (`lang="vie"`).
*   **Đọc trực tiếp file text (.txt)**: Không cần trích xuất, đọc trực tiếp bằng bảng mã UTF-8.

### Bước 2: State Machine Phân Tích Cấu Trúc (`parse_lines`)
Sau khi thu được danh sách các dòng văn bản đã làm sạch khoảng trắng, một máy trạng thái (state machine) sẽ duyệt qua từng dòng:

1.  **Theo dõi độ sâu dấu ngoặc kép (`quote_depth`)**:
    *   **Thách thức**: Luật sửa đổi thường có cấu trúc lồng nhau dạng: *Sửa đổi Điều X như sau: “Điều X. Nội dung... 1. Khoản 1... a) Điểm a...”*. Các cấu trúc trong dấu ngoặc kép thực chất là nội dung trích dẫn của điều sửa đổi chứ không phải là điều/khoản/điểm cấp cao của văn bản hiện tại.
    *   **Giải quyết**: Sử dụng bộ đếm `quote_depth`. Khi phát hiện ký tự mở ngoặc kép `“`, tăng `quote_depth`. Khi gặp dấu đóng `”`, giảm `quote_depth`. Nếu `quote_depth > 0`, toàn bộ dòng đó sẽ **bị bỏ qua việc kiểm tra regex cấu trúc mới** và được coi là nội dung tiếp nối của phần tử cha đang xử lý.
2.  **Khớp biểu thức chính quy (Regex Matching)**:
    Nếu dòng không nằm trong dấu trích dẫn, hệ thống sử dụng các regex trong [patterns.py](file:///D:/Workspace/Project/pipline/src/parser/patterns.py) để phân loại:
    *   **Chương (`CHAPTER_RE`)**: Nhận diện `Chương <Số La Mã>` (ví dụ: `Chương II`).
    *   **Tiêu đề chương (`looks_like_title`)**: Heuristic nhận diện dòng toàn chữ in hoa có dấu và độ dài hợp lý ngay sau dòng chứa từ khóa "Chương".
    *   **Điều (`ARTICLE_RE`)**: Nhận diện dòng bắt đầu bằng `Điều <Số>.`. Dành riêng cho OCR sẽ dùng `ARTICLE_RE_LENIENT` để chấp nhận 1-2 ký tự lỗi nhận diện ở đầu dòng.
    *   **Khoản (`CLAUSE_RE`)**: Nhận diện dòng bắt đầu bằng `<Số>. ` (ví dụ: `1. `).
    *   **Điểm (`POINT_RE`)**: Nhận diện dòng bắt đầu bằng `<Chữ cái kđ)>\s` (ví dụ: `a) `).
3.  **Xử lý nội dung tiếp nối (Continuation)**:
    Nếu dòng không khớp bất kỳ cấu trúc nào, nó sẽ được nối vào nội dung của phần tử đang mở gần nhất theo cấp độ ưu tiên: **Điểm** $\rightarrow$ **Khoản** $\rightarrow$ **Điều**.

### Bước 3: Đóng Gói Dữ Liệu (Serialization)
Sau khi kết thúc dòng cuối cùng, các builders sẽ dọn dẹp các khoảng trắng thừa và đóng gói thành đối tượng `ParsedDocument` dựa trên Pydantic Model, đảm bảo tính nhất quán của dữ liệu trước khi ghi ra đĩa.

---

## 3. Các Case Biên Được Xử Lý (Edge Cases)

*   **Lỗi OCR làm sai lệch từ khóa**: Bật chế độ `lenient_article=True` khi OCR để nhận diện được các dòng như `*Điều 5.` hoặc `'Điều 10.` bị dính vết quét bẩn.
*   **Trích dẫn lồng ghép ngoặc kép kép**: Xử lý đếm ký tự mở/đóng ngoặc kép chuẩn xác giúp giữ ranh giới các điều luật sửa đổi trong Luật sửa đổi bổ sung không bị tách vụn thành các Điều cấp cao sai vị trí.
*   **PDF mất thông tin font**: Tự động fallback sang heuristics chữ in hoa (`looks_like_title`) để đoán tiêu đề chương khi tệp PDF bị mất thông tin font trong quá trình nén/chuyển đổi.
