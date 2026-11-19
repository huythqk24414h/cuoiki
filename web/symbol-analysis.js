/* Evidence-based interpretation of the selected SSI daily series. */
(function(){
 const numeric=v=>v==null||v===''?null:Number.isFinite(Number(v))?Number(v):null;
 const fmt=v=>Number(v).toLocaleString('vi-VN',{maximumFractionDigits:2});
 window.SSIInterpretation=function(symbol,rows){
  const current=rows.at(-1);if(!current)return ['Chưa có dữ liệu SSI trong khoảng đã chọn.'];
  const prior=rows.slice(0,-1),close=numeric(current.close_vnd),previous=numeric(prior.at(-1)?.close_vnd);
  const out=[symbol+' · '+current.date+(current.provisional?' · Phiên đang mở, đến '+String(current.closed_at).slice(11,16)+' ICT':' · Phiên đã chốt')+'.'];
  if(close==null)return [...out,'Chưa đủ giá nguồn để đánh giá.'];
  out.push('Giá gần nhất '+fmt(close)+(previous>0?' · thay đổi '+fmt((close/previous-1)*100)+'% so với phiên trước':'')+'.');
  const reference=prior.slice(-20),lows=reference.map(r=>numeric(r.low_vnd)),highs=reference.map(r=>numeric(r.high_vnd));
  if(reference.length===20&&lows.every(v=>v>0)&&highs.every(v=>v>0)){
   const low=Math.min(...lows),high=Math.max(...highs),todayLow=numeric(current.low_vnd);
   out.push('Vùng giá 20 phiên trước '+fmt(low)+'–'+fmt(high)+'. '+(close<low?'Giá gần nhất đã xuống dưới đáy 20 phiên trước.':todayLow!=null&&todayLow<=low?'Giá trong phiên đã chạm hoặc xuyên đáy 20 phiên trước, giá gần nhất hiện '+fmt(close)+'.':'Giá gần nhất cách đáy 20 phiên '+fmt((close/low-1)*100)+'%.'));
   out.push(close<=low?'Cần theo dõi khả năng quay lại trên '+fmt(low)+' ở các nến tiếp theo, cùng sự thay đổi khối lượng.':'Mốc theo dõi gần nhất là đáy tham chiếu '+fmt(low)+' và đỉnh tham chiếu '+fmt(high)+'.');
  }else out.push('Khoảng chọn chưa đủ 20 phiên giá hợp lệ để xác định vùng thấp/cao tham chiếu.');
  const rv=numeric(current.relative_volume20),volume=numeric(current.volume_shares);
  if(volume!=null)out.push('Khối lượng '+(current.provisional?'tích lũy đã quan sát ':'phiên ')+fmt(volume)+(rv!=null?' · bằng '+fmt(rv)+' lần TB20 phiên trước':'')+'.'+(rv>=2?' Khối lượng đạt ngưỡng theo dõi bất thường.':rv!=null&&rv<1?' Khối lượng hiện thấp hơn bình quân một phiên hoàn chỉnh.':''));
  if(current.provisional)out.push('Khối lượng đang tích lũy được so với khối lượng cả ngày của 20 phiên trước, cần đọc cùng giờ quan sát.');
  const high=numeric(current.high_vnd),low=numeric(current.low_vnd);
  if(high>low)out.push('Giá gần nhất nằm ở '+fmt((close-low)/(high-low)*100)+'% biên độ thấp–cao của phiên. '+((close-low)/(high-low)<.25?'Giá còn gần vùng thấp trong phiên; cần theo dõi lực mua và spread trước khi đánh giá khả năng hồi phục.':'Đối chiếu với khối lượng và diễn biến các nến tiếp theo để đánh giá sức duy trì của giá.'));
  const volatility=numeric(current.volatility20_pct);
  if(volatility!=null)out.push('Độ lệch chuẩn 20 lợi suất ngày '+fmt(volatility)+'%. Đây là mức dao động lịch sử phục vụ cân nhắc quy mô vị thế.');
  return out;
 };
})();
