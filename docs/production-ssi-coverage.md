# LiquidityLab · Bộ đo thanh khoản cổ phiếu

Đây là hướng 3 của đề học phần 261BFF401101/261BFF401102. Đề gốc dùng NEO API làm nguồn lõi và cho phép SSI bổ sung. Theo yêu cầu cập nhật của giảng viên do sinh viên cung cấp, LiquidityLab dùng SSI FastConnect V3 thay NEO. Đồ án chỉ đọc dữ liệu thị trường và phục vụ phân tích học thuật.

## Dữ liệu và tái lập

- `SSI Market History` và `SSI Intraday OHLCV` chạy trên GitHub-hosted runners với `SSI_PUBLISH_EOD=true`, khóa SSI và Redis đặt trong GitHub Secrets. Vercel đọc dữ liệu Redis theo mã. Dữ liệu mới xuất hiện mà không cần deploy lại.
- Danh mục lấy `stockType=Stock` và thành viên VN30 trực tiếp từ SSI. Mã vắng trong danh mục được ghi là vắng mặt. Chỉ gọi là đã hết giao dịch khi SSI trả ngày cuối đã qua. Giữ lịch sử đã công bố của mã vắng mặt.
- `SSI_EOD_SYMBOLS` và `SSI_INTRADAY_SYMBOLS` nhận danh sách phân cách dấu phẩy và nhóm `VN30`. Mặc định ưu tiên VN30, giữ thêm REE và SAM ở EOD. Mã ngoài VN30 có thể cấu hình theo từng lô. Chỉ áp dụng quy tắc nội ngày hiện tại cho HOSE. Giới hạn 80 mã EOD, 32 mã nội ngày mặc định. Ngân sách JSON EOD đang tham chiếu là 90 MB để còn dung lượng cho dữ liệu tạm khi cập nhật.
- Workflow EOD làm mới vùng chồng lấn 10 ngày và gộp theo ngày. Các phiên bất hợp lệ được cách ly, giữ ngày bị loại trong metadata. Nếu phân trang hỏng hoặc dữ liệu xung đột, giữ dữ liệu đã lưu. Giá theo SSI, chính sách điều chỉnh chưa xác minh. Khi mã được tái sử dụng hoặc niêm yết lại, cần xác minh pháp nhân trước khi diễn giải lịch sử. SSI trả chuỗi VPL giai đoạn cũ từ 2008. Với niêm yết hiện tại, giới hạn chuỗi từ 13/05/2025 theo [thông báo của HOSE](https://statics.vinpearl.com/250506_VPL_CBTT%20vv%20nhan%20duoc%20TB%20ngay%20giao%20dich%20dau%20tien_1746529635.pdf).
- Nến nội ngày lấy từ 1m SSI, dùng UTC+7. Dữ liệu M15 HOSE bám khớp liên tục 09:15–11:30 và 13:00–14:30. Mốc ATC 14:45 được xuất riêng khi SSI có dữ liệu tại mốc đó. Trên UI, H1 và H2 tách theo buổi, H4 neo từ giờ mở cửa và tính giờ nghỉ trưa vào khoảng thời gian bốn giờ. UI gộp từ các nến M15 đã đóng để cập nhật kỳ đang mở. API lịch sử có chế độ `4h` theo buổi riêng. Dữ liệu thiếu được đánh dấu, khối lượng chỉ cộng từ nến đã quan sát.
- Nội ngày giữ tối đa 24 ngày lịch. Lượt định kỳ lấy từ ngày nến cuối đã lưu, lượt thủ công có thể lấy lại cửa sổ để tải bù. Các endpoint `?kind=catalog&board=VN30&page=1&size=30`, `?kind=series&symbol=HPG` và `?kind=intraday&symbol=HPG&resolution=15m` cung cấp dữ liệu theo phạm vi.
- Kiểm thử với `python -m unittest discover -s tests` và `node --test tests/*.test.cjs`. Các kiểm thử lịch sử local cần snapshot và checksum SSI trong `data/`. Dữ liệu nguồn nằm ngoài Git.

## Phương pháp

| Chỉ báo | Công thức và đơn vị | Diễn giải và giá trị thiếu |
| --- | --- | --- |
| Spread | Ask₁ − Bid₁ (VND/cp). Spread tương đối bằng kết quả chia cho mid và nhân 10.000 (bps). Mid là trung bình hai giá tốt nhất. | Đo khoảng cách giữa hai giá chờ tốt nhất. Cần báo giá hai phía hợp lệ và đơn vị đã xác minh. |
| Độ sâu | Tổng giá × khối lượng (VND) hoặc tổng khối lượng (cp) theo từng phía. | Mô tả lượng lệnh chờ trong phạm vi tối đa ba mức. SSI LIVE yêu cầu đủ ba mức, báo giá mới, phiên liên tục và hợp đồng đơn vị đã xác minh. |
| Imbalance | (Độ sâu mua − độ sâu bán) / tổng hai phía. Không đơn vị. | Giá trị dương thể hiện độ sâu mua chiếm tỷ trọng lớn hơn. Cần sổ lệnh hợp lệ và tổng dương. |
| RV20 | Khối lượng phiên / khối lượng bình quân 20 phiên trước (lần). | Phản ánh mức giao dịch so với thông lệ gần đây. Cần đủ 20 quan sát, trung bình dương. |
| Kịch bản thoát 100.000 cp | 100.000 / (5% × khối lượng bình quân 20 phiên trước), đơn vị phiên. | Ước lượng dựa trên mức tham gia 5% và giả định thanh khoản tương lai tương tự. Thiếu 20 quan sát hoặc trung bình bằng 0 thì bỏ trống. Khối lượng giữ đơn vị nguồn SSI. |

Các lệnh chờ có thể đổi hoặc hủy. Kịch bản thoát vị thế dựa trên OHLCV là chỉ báo đại diện. Đo khả năng hấp thụ thực tế cần chuỗi báo giá và khớp lệnh đồng bộ với đơn vị đã xác minh, đủ phiên và phương pháp nhận diện tác động giá.
