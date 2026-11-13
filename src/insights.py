"""Descriptive point-in-time fact sheets, no forecasts or fabricated turnover."""
from decimal import Decimal
from statistics import median

def fact_sheet(rows, index_rows=()):
    if not rows:return {'status':'EMPTY','paragraphs':['Không có dữ liệu hợp lệ trong khoảng.']}
    current=rows[-1];prior=rows[max(0,len(rows)-121):-1]
    volumes=[Decimal(r['volume_shares']) for r in prior];v=Decimal(current['volume_shares'])
    med=median(volumes) if volumes else None
    mad=median([abs(x-med) for x in volumes]) if volumes else None
    percentile=sum(x<=v for x in volumes)/len(volumes)*100 if volumes else None
    z=Decimal('0.67448975')*(v-med)/mad if mad and len(volumes)>=20 else None
    rv=current.get('relative_volume20');ratio=Decimal(rv) if rv is not None else None
    state='Giao dịch gia tăng' if ratio is not None and ratio>=2 else 'Giao dịch suy giảm' if ratio is not None and ratio<Decimal('.5') else 'Trong vùng quan sát thông thường' if ratio is not None else 'Chưa đủ cửa sổ so sánh'
    benchmark={str(r.get('tradingDate',''))[:10].replace('/','-'):r for r in index_rows}
    ref=benchmark.get(current['date']);reference=ref.get('indexChangePercentage') if ref else None
    previous_index_dates=sorted(day for day in benchmark if day<current['date'])
    previous_index_date=previous_index_dates[-1] if previous_index_dates else None
    previous_stock_date=rows[-2]['date'] if len(rows)>1 else None
    interval_matches=bool(previous_index_date and previous_stock_date==previous_index_date)
    excess=Decimal(current['return_pct'])-Decimal(str(reference)) if interval_matches and reference is not None and current.get('return_pct') is not None else None
    facts={'date':current['date'],'symbol':current['symbol'],'state':state,'volume':str(v),'rv20':rv,'previous_mean20':current.get('volume_avg20_previous'),'prior_observations':len(volumes),'volume_percentile':percentile,'median_volume':str(med) if med is not None else None,'mad_volume':str(mad) if mad is not None else None,'robust_z':str(z) if z is not None else None,'return_pct':current.get('return_pct'),'volatility20_pct':current.get('volatility20_pct'),'vnindex_return_pct':reference,'excess_return_pp':str(excess) if excess is not None else None,'previous_stock_date':previous_stock_date,'previous_index_date':previous_index_date,'benchmark_interval_verified':interval_matches}
    paragraphs=[state+'. RV20 = '+str(rv or 'chưa đủ mẫu')+' lần; so với trung bình 20 quan sát trước, loại ngày hiện tại.']
    if percentile is not None:paragraphs.append(f'Khối lượng lớn hơn hoặc bằng {percentile:.1f}% trong {len(volumes)} quan sát trước của riêng mã (tối đa 120; không gồm ngày đang xét). Đây là phân vị thực nghiệm, không phải xác suất lợi nhuận tương lai.')
    paragraphs.append(f'Robust z = {z:.2f}, dùng độ lệch so trung vị và MAD của cửa sổ trên. Giá trị này không phải p-value và chưa chứng minh ý nghĩa thống kê.' if z is not None else 'Chưa tính robust z: cần ít nhất 20 quan sát và MAD > 0; không gán 0 thay dữ liệu thiếu.')
    paragraphs.append('Lợi suất trừ VNINDEX cùng ngày và cùng phiên gốc = '+str(excess)+' điểm phần trăm. Đây là chênh lệch mô tả, không phải alpha đã điều chỉnh rủi ro.' if excess is not None else 'Chưa so sánh chênh lệch lợi suất: cần VNINDEX đúng ngày và giá gốc cổ phiếu trùng phiên gốc chỉ số. Không so một khoảng nhiều phiên với lợi suất chỉ số một phiên.')
    paragraphs.append('Khối lượng tăng phản ánh mức hoạt động giao dịch, chưa chứng minh khả năng khớp một lệnh lớn. RV20 ≥ 2 và < 0,5 là quy tắc mô tả hai lần/nửa trung bình, không phải ngưỡng dự báo hay khuyến nghị. Percentile và robust z đối chiếu mức bất thường trong lịch sử riêng mã.')
    paragraphs.append('Giá điều chỉnh/đơn vị nguồn mở rộng chưa xác minh đầy đủ. Spread, chi phí thực thi và Amihud không được suy ra từ EOD volume hoặc SSI value chưa xác minh. Sự kiện và chỉ báo chỉ dùng quan sát đến ngày đang xét.')
    return {'status':'DESCRIPTIVE','facts':facts,'paragraphs':paragraphs,'method':{'lookback':120,'percentile':'100 * count(prior volume <= current) / N; inclusive ties','robust_z':'0.67448975 * (V - median(prior V)) / MAD(prior V)','baseline':'up to 120 preceding observed sessions; current excluded','benchmark_guard':'same current date AND matching previous observed stock date / previous index session'},'source':'SSI FastConnect V3'}
