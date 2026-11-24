# LiquidityLab

**[Mở LiquidityLab trên web](https://cuoiki-jet.vercel.app/)**

Công cụ học thuật phân tích thanh khoản cổ phiếu Việt Nam từ dữ liệu SSI FastConnect Data. Ứng dụng hiển thị giá, khối lượng, chỉ số, RV20 và sổ lệnh. Công cụ nhập tay cho phép kiểm tra công thức và mô phỏng quét tối đa ba mức giá.

## 1. Xem bản web

1. Mở liên kết ở đầu trang bằng trình duyệt.
2. Bấm **Đăng nhập**, nhập tên mẫu **LiquidityLab** và mật khẩu mẫu **123456789**. Đây là tài khoản demo công khai, không cần tài khoản SSI.
3. Vào **Tổng quan** để xem giá và khối lượng, hoặc **Sổ lệnh → Nhập sổ lệnh** để thử phép tính ở mục 3.

Người xem bản web chỉ cần trình duyệt và Internet. Các bước dưới đây dành cho người muốn chạy hoặc kiểm tra mã nguồn.

## 2. Tải và chạy mã nguồn

Cài Git và Python 3.12. Cài thêm Node.js 24 nếu muốn chạy kiểm thử giao diện hoặc tạo bản dựng Vercel. Mở PowerShell trên Windows hoặc Terminal trên macOS/Linux.

**Bước 1. Tải mã nguồn và kiểm tra Python**

```sh
git clone https://github.com/huythqk24414h/cuoiki.git
cd cuoiki
python --version
```

Dòng cuối cần hiện `Python 3.12.x`. Nếu máy dùng `py -3.12` trên Windows hoặc `python3.12` trên macOS/Linux, thay `python` bằng lệnh tương ứng ở các bước sau.

**Bước 2. Chạy máy chủ từ tệp `run.py`**

```sh
python run.py --port 8792
```

Khi terminal in địa chỉ máy chủ, giữ cửa sổ đó mở và vào [http://127.0.0.1:8792](http://127.0.0.1:8792) trên trình duyệt. Đăng nhập bằng tài khoản mẫu ở mục 1. Nhấn **Ctrl+C** trong terminal để dừng máy chủ.

`run.py` phục vụ `web/index.html` và các tệp giao diện, đồng thời nhận yêu cầu tính toán tại `/api/calculate`. Phép tính phía Python nằm trong `src/finance.py`. Phần mô phỏng quét ba mức nằm trong `web/calculator-core.js`. Chạy máy chủ và thử nhập tay chỉ cần thư viện chuẩn Python. Các trang lịch sử SSI ở bản cục bộ cần dữ liệu tương ứng trong `data/`, vốn được lưu ngoài Git.

## 3. Tái lập một kết quả

Ở bản web hoặc bản chạy cục bộ, vào **Sổ lệnh → Nhập sổ lệnh**, điền mã **FPT-MAU** và nhập các số nguyên bên dưới. Đây là dữ liệu giả lập. Giá tính bằng đồng/cổ phiếu và khối lượng tính bằng cổ phiếu. Để trống thời gian nếu muốn dùng thời điểm bấm tính.

| Mức | Giá mua | KL mua | Giá bán | KL bán |
| --- | ---: | ---: | ---: | ---: |
| 1 | 47000 | 200 | 47050 | 200 |
| 2 | 46950 | 300 | 47100 | 300 |
| 3 | 46900 | 500 | 47150 | 500 |

Bấm **Tính toán**. Chênh lệch giữa hai giá tốt nhất là **50 đồng/cp**, giá giữa là **47.025 đồng/cp**. Mở **Mô phỏng quét tối đa ba mức**, chọn **Mua**, nhập khối lượng rồi bấm **Mô phỏng**.

| Khối lượng | Kết quả cần thấy |
| ---: | --- |
| 300 cp | Khớp đủ. Giá bình quân khoảng 47.066,67 đồng/cp, trượt giá khoảng 8,86 bps so với giá giữa. |
| 1.200 cp | Khớp 1.000 cp (83,33%), còn 200 cp. Giá bình quân phần khớp là 47.115 đồng/cp. Trượt giá toàn lệnh để trống. |

Khi thử bằng sổ FPT thực tế, chép ba mức mua và bán cùng một thời điểm và kiểm tra đơn vị nguồn trước khi nhập. Kết quả mô phỏng chỉ dựa trên lượng hiển thị tại thời điểm chụp.

## 4. Chạy kiểm thử và tạo bản dựng

Chạy từ thư mục `cuoiki`. Với kiểm thử Python, tạo môi trường ảo để cài riêng các phụ thuộc.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-research.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**macOS/Linux**

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-research.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tệp `requirements-research.txt` cung cấp NumPy cho các kiểm thử nghiên cứu. Bộ kiểm thử dùng được trên bản clone sạch. Một số bài kiểm tra bản chụp SSI có thể được bỏ qua nếu thiếu dữ liệu riêng.

**Kiểm thử JavaScript và tạo bản dựng**

```sh
node --version
node --test tests/*.test.cjs
node scripts/build_vercel_demo.mjs
```

Kiểm thử JavaScript đọc mã giao diện trong `web/`. Lệnh cuối tạo `public-demo/index.html` và các tệp tĩnh trong `public-demo/`. Vercel dùng thiết lập trong `vercel.json` để chạy lệnh này. API thị trường của bản web nằm trong `api/market-data.js`.

## 5. Dữ liệu và các tệp chính

| Tệp hoặc thư mục | Dùng để làm gì |
| --- | --- |
| `run.py`, `web/index.html` | Điểm vào của máy chủ và giao diện khi chạy cục bộ |
| `src/finance.py`, `web/calculator-core.js` | Tính chỉ số nhập tay và mô phỏng quét sổ lệnh |
| `scripts/build_vercel_demo.mjs`, `vercel.json`, `api/market-data.js` | Tạo bản dựng, cấu hình Vercel và phục vụ API thị trường |
| `.github/workflows/` | Chạy kiểm thử và các quy trình thu, cập nhật hoặc bảo trì dữ liệu SSI |
| `data_sample/catalog_fixture.json` | Danh mục giả lập dành cho kiểm thử |
| `data/` | Bản chụp SSI và dữ liệu nghiên cứu cục bộ, lưu ngoài Git |
| `config/`, `scripts/run_research.py` | Cấu hình nguồn và điểm vào đánh giá nghiên cứu ngoại tuyến |

Giá và khối lượng trong phiên lấy từ SSI. Nến M15 được cập nhật theo mốc giao dịch, độc lập với việc thu sổ lệnh. Nến ở kỳ đang mở có thể dùng dữ liệu tạm tính, còn lịch sử cuối ngày chính thức được cập nhật riêng. Ai vận hành bộ thu SSI cần cài `requirements-ssi.txt` và thiết lập thông tin kết nối riêng theo `.env.example`. Các bước mở web, chạy máy chủ và nhập tay không cần khóa SSI. [Phạm vi dữ liệu và phương pháp](docs/production-ssi-coverage.md)

Pipeline nghiên cứu `scripts/run_research.py` đọc sự kiện trong `data/live_snapshots/`. Chỉ khi đủ dữ liệu, xác minh đơn vị nguồn và khóa giao thức nghiên cứu thì mới chạy đánh giá và ghi `data/research/evaluation.json`. Nếu thiếu điều kiện, script trả danh sách lý do. Ví dụ nhập tay ở mục 3 tái lập được độc lập với pipeline này.

## 6. Xử lý khi chạy cục bộ

| Triệu chứng | Cách kiểm tra và xử lý |
| --- | --- |
| `python` không chạy hoặc mở Microsoft Store | Kiểm tra `python --version`. Trên Windows thử `py -3.12 --version` nếu đã cài Python 3.12. |
| Trình duyệt không kết nối được | Giữ `run.py` đang chạy và dùng đúng địa chỉ máy chủ in trong terminal. |
| Cổng 8792 đang được dùng | Chạy `python run.py --port 8793`, rồi mở [http://127.0.0.1:8793](http://127.0.0.1:8793). |
| Trang lịch sử cục bộ thiếu dữ liệu SSI | Dùng bản web để xem dữ liệu đã công bố. Dùng mục **Kiểm tra công thức** để thử ví dụ nhập tay ngay trên bản clone. |

LiquidityLab phục vụ phân tích học thuật. Giấy phép của các thư viện giao diện nằm cạnh mã đã đóng gói. [KaTeX](web/vendor/katex/LICENSE.txt) · [Apache ECharts](web/vendor/echarts-LICENSE.txt) · [Lightweight Charts](web/vendor/lightweight-charts-LICENSE.txt)
