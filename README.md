# LiquidityLab

Công cụ phân tích học thuật dùng SSI FastConnect Data theo yêu cầu của giảng viên. Web hiển thị giá, khối lượng, chỉ số, RV20 và bản chụp sổ lệnh. Công cụ nhập tay tính các chỉ số và mô phỏng quét tối đa ba mức giá.

## Chạy và kiểm thử

Dùng Python 3.12 trở lên và Node.js. Trên Windows có thể mở bằng `MO_LIQUIDITY_LAB.cmd`. Sau khi chạy lệnh đầu, mở http://127.0.0.1:8792. Biểu mẫu demo dùng `LiquidityLab` / `123456789`.

```sh
python run.py --port 8792
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
node scripts/build_vercel_demo.mjs
```

Bản tải sạch chạy được công cụ nhập tay và kiểm thử dùng dữ liệu giả lập. Các mục lịch sử cần bản chụp SSI tương ứng trong `data/`. Để thu dữ liệu bằng tài khoản được cấp quyền, cài `requirements-ssi.txt` và cấu hình theo `.env.example`. Các quy trình GitHub đọc thông tin kết nối từ GitHub Secrets. Máy khách SSI chỉ gọi các điểm cuối đọc dữ liệu trong `src/ssi_client.py`.

## Thử nhập sổ lệnh ngày 25/11/2026

Vào **Sổ lệnh → Nhập sổ lệnh**, đặt tên **FPT-MAU**. Đây là ví dụ giả lập, giá tính bằng đồng/cổ phiếu, khối lượng tính bằng cổ phiếu. Có thể để trống thời gian để dùng giờ bấm tính.

| Mức | Giá mua | KL mua | Giá bán | KL bán |
| --- | ---: | ---: | ---: | ---: |
| 1 | 47000 | 200 | 47050 | 200 |
| 2 | 46950 | 300 | 47100 | 300 |
| 3 | 46900 | 500 | 47150 | 500 |

Bấm **Tính toán**. Chênh lệch giá tốt nhất là 50 đồng/cp, giá giữa 47.025 đồng/cp. Mở **Mô phỏng quét tối đa ba mức**, chọn **Mua** và thử hai lượng:

- **300 cp**. Khớp đủ, giá bình quân 47.066,67 đồng/cp, trượt giá khoảng 8,86 bps.
- **1.200 cp**. Khớp 1.000 cp (83,33%), còn 200 cp. Giá bình quân phần khớp 47.115 đồng/cp. Công cụ bỏ trống trượt giá toàn lệnh.

Nếu thử bằng sổ FPT thực tế, chép ba mức mua và bán tại cùng thời điểm, chỉ quy đổi sau khi xác nhận đơn vị nguồn.

## Dữ liệu và nguồn gốc

| Thư mục | Nội dung |
| --- | --- |
| `src/`, `scripts/` | Đọc và kiểm tra SSI, công bố nến, thu sổ lệnh, tính toán và nghiên cứu |
| `web/`, `api/`, `demo/` | Giao diện cục bộ và Vercel, API chỉ đọc và phần kết nối trình duyệt |
| `config/` | Tham chiếu bản chụp lịch sử, giao thức thí điểm và mẫu xác minh đơn vị SSI |
| `data_sample/` | Danh mục giả lập theo cấu trúc SSI dành cho kiểm thử HTTP/SSE |
| `data/` | Bản chụp SSI và hồ sơ nghiên cứu lưu ngoài Git |

Biểu đồ dùng nến một phút đã đóng từ SSI. Nến M15 làm mới theo mốc giao dịch. Các khung dài hơn có thể gồm kỳ đang mở. Lịch sử cuối ngày chính thức được công bố riêng. Giám sát biểu đồ có lịch độc lập với bộ thu sổ lệnh. Bộ thu ghi mẫu mỗi giây và lưu nhật ký sự kiện SSI khi có.

```sh
python -m scripts.audit_book_archives data/research_exports
```

Lệnh trên kiểm mã băm và báo độ phủ theo mã trong phiên khớp liên tục. Cần xác minh nguồn gốc, quyền sử dụng, ý nghĩa thời gian và chất lượng trước khi gộp dữ liệu ngoài. Bộ chạy nghiên cứu đọc nhật ký đã chuẩn bị trong `data/live_snapshots/`. Hồ sơ phân biệt thời điểm lấy mẫu, thời điểm nguồn và thời điểm nhận. Giá và khối lượng giữ đơn vị nguồn cho đến khi có bằng chứng xác minh. Bản chụp lưu định kỳ không khôi phục được chuỗi báo giá ở giữa.

## Diễn giải tài chính

- **RV20** chia khối lượng quan sát cho trung bình 20 phiên hoàn tất trước đó. RV20 trong phiên là tạm tính và vẫn so với khối lượng tham chiếu cả ngày.
- **Kịch bản thoát vị thế** chia 100.000 cp cho tích của khối lượng bình quân và tỷ lệ tham gia 5%. Đổi tỷ lệ sang 2,5% hoặc 10% làm số phiên ước tính tăng gấp đôi hoặc giảm một nửa.
- **Quan sát độ sâu 60 giây** dùng phân vị 10% của độ sâu trước đó và tìm đợt thấp kéo dài ít nhất 15 giây. Các ngưỡng thí điểm cần được chốt trước khi đánh giá ngoài mẫu.
- **Mô phỏng nhập tay** lấy giá tốt nhất phía đối diện trước. Giá bình quân tính trên lượng khớp. Mô phỏng dùng lượng hiển thị tại thời điểm chụp, chưa tính phí, hàng đợi, quy tắc lô hoặc phản ứng thị trường.

H1 vẫn là `NOT_TESTED` cho đến khi đủ dữ liệu, có bằng chứng xác minh đơn vị SSI và khóa giao thức đánh giá ngoài mẫu. LiquidityLab phục vụ phân tích học thuật. [Phạm vi dữ liệu và phương pháp](docs/production-ssi-coverage.md)

## Thư viện và giấy phép

- [KaTeX](https://github.com/KaTeX/KaTeX) · [Giấy phép](web/vendor/katex/LICENSE.txt)
- [Apache ECharts](https://echarts.apache.org/) · [Giấy phép](web/vendor/echarts-LICENSE.txt) · [Thông báo bản quyền](web/vendor/echarts-NOTICE.txt)
- [Lightweight Charts](https://github.com/tradingview/lightweight-charts) · [Giấy phép](web/vendor/lightweight-charts-LICENSE.txt)
- SSI FastConnect Python SDK (`ssi-sdk`). Xem phiên bản trong `requirements-ssi.txt`.
