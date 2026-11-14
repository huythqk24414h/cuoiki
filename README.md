# LiquidityLab · local, chỉ đọc SSI

Nhấp đúp MO_LIQUIDITY_LAB.cmd để chạy. Màn hình đầu là ảnh LiquidityLab với hiệu ứng; bấm Đăng nhập góc phải để mở hộp chính giữa. Tài khoản minh họa công khai: LiquidityLab / 123456789. Sau đăng nhập hiện avatar LL, tên LiquidityLab và Đăng xuất. Đây là minh họa local, không bảo vệ API và không phải tài khoản SSI.

Chín hiệu ứng: laser trái→phải, gợn sóng tâm→ngoài, hạt phải→trái, tia ngoài→tâm, sóng dâng, lưới quét xuống, vệt sáng mềm, nét sáng ngắn, hạt sáng hội tụ nhẹ quanh logo. Mỗi pha 6 giây, vòng 54 giây lặp đến khi đăng nhập. Có tạm dừng, giảm chuyển động và dừng khi tab ẩn. Ô nhập đứng yên, không tự mở hộp đăng nhập. Không có quét bảo mật thật. Workspace sau đăng nhập dùng nền sáng xanh xám, mặt trắng và điểm nhấn đỏ; không còn bốn theme/phím 1–4.

## Lịch sử 2022–2026

Đã tải và kiểm chứng 1.224.178 quan sát EOD, truy vấn 01/01/2022–05/11/2026. Có 1.968 mã/mục có dữ liệu dùng được: 1.956 SUCCESS và 12 PARTIAL; 108 NO_HISTORY; VN50 GROWTH lỗi SSI 400006. 722 dòng lỗi/xung đột được cách ly. Đây là gần năm năm theo các năm lịch, chưa đủ năm năm tròn.

Nguồn ở data/ssi_history_20220101_20261105/: raw, symbols, index_ohlc, checkpoint, quality và checksum. config/history_active.json chỉ trỏ tới bản PASS; file đọc phải khớp hash trong quality. Snapshot sáu mã cũ giữ nguyên. 3Y/5Y/MAX và ngày tùy chọn đã được nối vào API và UI.

VNINDEX/VN30/HNXINDEX/UPCOMINDEX lấy từ OHLC chỉ số chính thức; UPCOM dùng mã nguồn HNXUPCOMINDEX. Mỗi chỉ số đối chiếu khớp 207/207 ngày chung với indexSummary cũ. Chênh lệch điểm/% tính từ đóng cửa so phiên trước.

Giới hạn: danh mục hiện tại không gồm tất cả mã từng niêm yết từ 2022. Nội dung đối chiếu raw; lịch phiên, đơn vị toàn danh mục và chính sách điều chỉnh chưa xác minh đầy đủ. Giữ số nguồn, không tự đổi đơn vị hoặc gọi source.value là giá trị khớp thật. Không công bố tổng hợp thị trường khi mẫu số lịch sử chưa xác minh. EOD không thay sổ lệnh nội ngày cho H1.

## Kết quả kiểm thử mới nhất

- Python 107/107 PASS, gồm HTTP local thật, lịch sử, chỉ số, checksum.
- JavaScript 22/22 PASS, gồm đăng nhập, vòng hiệu ứng, reduced-motion, pause và tab ẩn; dùng DOM/canvas doubles.
- HTTP tại8792 PASS cho trang, ảnh, script và API lịch sử.
- Browser interaction/screenshot/độ mượt/bố cục thực: BLOCKED do chính sách trình duyệt từ chối localhost. Kiểm thử logic không thay nghiệm thu hình ảnh.

Bằng chứng: docs/HISTORY_2022_REPORT.json, docs/WELCOME_HISTORY_HTTP.json, docs/WELCOME_HISTORY_REPORT.md, docs/latest_python_tests.txt và docs/latest_js_tests.txt. Báo cáo cũ mô tả các mốc trước, không phải nghiệm thu hiện tại.

Chạy kiểm thử: python -m unittest discover -s tests; node --test tests/*.test.cjs. Có thể đặt TEMP/TMP vào thư mục được phép ghi nếu môi trường hạn chế.

## An toàn và đóng gói

Bản local không gửi lệnh và đọc dữ liệu từ tệp. Đặt khóa SSI của bản local trong .env. Bản production dùng GitHub Secrets để chạy workflow và Redis để lưu dữ liệu. scripts/build_submission.py quét bí mật và loại .env, SDK, dữ liệu riêng khỏi ZIP; máy khác cần tự cấu hình và thu dữ liệu theo quyền SSI. Không phân phối dữ liệu SSI hoặc thông tin xác thực khi chưa được phép. ZIP source không chứa dataset riêng.


## Cập nhật nội ngày ngày 06/11/2026

Trang Phân tích có mục Theo dõi trong ngày với 15 phút/1 giờ/4 giờ. Các khung lấy từ SSI 1m thật, tách nghỉ trưa; không dựng từ EOD. Trình duyệt đọc local mỗi5giây, bộ tải SSI mỗi mã tối đa1lần/60giây, dùng chung phiên DATA. API trả lần tải và thời gian nguồn riêng; đây là nến cập nhật định kỳ, không phải cam kết realtime tick-by-tick.

Trang Cảnh báo có bộ quan sát độ sâu60giây, lấy mẫu1giây và xác nhận đợt thấp15giây sau khi cửa sổ đủ dữ liệu. Chưa phải dự báo H1; thiếu hợp đồng xác minh đơn vị thì BLOCKED, không tạo xác suất. Nhật ký ở data/depth_watch; API /api/market/depth-warning. Nến ở data/intraday và /api/market/intraday.

Kiểm thử mới:111 Python,22 JavaScript đạt. Gói liquidity-lab_LOCAL_SAMPLE.zip chứa snapshot SSI nhỏ để kiểm tra offline, không .env; thử bản giải nén trả207dòng SSI. Gói chỉ dành sử dụng theo quyền SSI, không phải kho đầy đủ2022–2026. Không tự phân phối công khai. Xem docs/INTRADAY_60S_HTTP.json.

## Demo tinh tren Vercel

Build: `node scripts/build_vercel_demo.mjs`. Vercel serves `public-demo/`.
The demo includes closing prices and an order-book calculator. Its initial
snapshot is labeled simulated. The full local dashboard is launched separately.

Import this repository into Vercel with its root left at the repository root.
On GitHub, configure `SSI_API_KEY` and `SSI_API_SECRET` as Actions secrets.
Set `SSI_PUBLISH_EOD=true` as an Actions variable after confirming that the
selected closing prices may be shown on the demo. Set `SSI_EOD_SYMBOLS` to
override the default SSI,HPG,FPT list.

In Vercel, create a Deploy Hook for the production branch and save its URL as
the GitHub Actions secret `VERCEL_DEPLOY_HOOK`. The workflow **SSI Demo
Closing Prices** runs at 16:37 Vietnam time on weekdays or from **Run workflow**.
It validates a complete batch for the current session before publishing.
A failed fetch keeps the previously published snapshot. Raw order-book files
are handled separately by **SSI Live Capture**.
