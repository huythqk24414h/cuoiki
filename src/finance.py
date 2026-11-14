"""Pure book calculations. No storage, provider access, or statistical fitting."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json


class ContractError(ValueError):
    pass


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ContractError('Giá và khối lượng phải là số hữu hạn.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ContractError('Giá hoặc khối lượng không hợp lệ.') from exc
    if not result.is_finite() or result < 0 or result > Decimal('1e15'):
        raise ContractError('Cần số từ 0 đến 10^15; không chấp nhận NaN hoặc vô cực.')
    return result


@dataclass(frozen=True)
class Book:
    symbol: str
    event_time: datetime
    received_at: datetime
    bids: tuple
    asks: tuple


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ContractError('Thời gian phải theo ISO 8601 và có múi giờ.') from exc
    if parsed.utcoffset() is None:
        raise ContractError('Thời gian phải có múi giờ.')
    return parsed


def parse_book(payload):
    if not isinstance(payload, dict):
        raise ContractError('Đầu vào phải là một object JSON.')
    if payload.get('contract_version') != '1.0':
        raise ContractError('Contract chưa được hỗ trợ. Cần contract_version 1.0.')
    if payload.get('source') != 'manual':
        raise ContractError('Công cụ này chỉ nhận dữ liệu nhập tay, không nhận dữ liệu SSI giả định.')
    if payload.get('price_unit') != 'VND' or payload.get('quantity_unit') != 'share':
        raise ContractError('Cần xác nhận đơn vị VND và share; không tự suy đoán đơn vị SSI.')
    symbol = payload.get('symbol')
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 20:
        raise ContractError('Mã phải là chuỗi từ 1 đến 20 ký tự.')
    if payload.get('session') != 'continuous':
        raise ContractError('Chỉ tính cho phiên liên tục đã được xác nhận.')
    event = parse_time(payload.get('event_time'))
    received = parse_time(payload.get('received_at'))
    if received < event:
        raise ContractError('Thời gian nhận không được trước thời gian nguồn.')
    sides = []
    for name in ('bids', 'asks'):
        entries = payload.get(name)
        if not isinstance(entries, list) or not 1 <= len(entries) <= 3:
            raise ContractError('Mỗi phía cần từ 1 đến 3 mức; không tự điền mức bị thiếu.')
        levels = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'price', 'quantity'}:
                raise ContractError('Mỗi mức cần đúng price và quantity.')
            price, qty = number(entry['price']), number(entry['quantity'])
            if price <= 0 or qty <= 0 or qty != qty.to_integral_value():
                raise ContractError('Mức có giá/khối lượng bằng 0 phải được adapter xác minh; khối lượng phải nguyên dương.')
            levels.append((price, qty))
        prices = [p for p, _ in levels]
        if len(set(prices)) != len(prices) or prices != sorted(prices, reverse=name == 'bids'):
            raise ContractError('Giá mua phải giảm dần, giá bán tăng dần và không trùng.')
        sides.append(tuple(levels))
    if sides[0][0][0] >= sides[1][0][0]:
        raise ContractError('Sổ lệnh khóa/chéo không hợp lệ cho phép tính này.')
    return Book(symbol.strip().upper(), event, received, *sides)


def calculate(payload):
    book = parse_book(payload)
    bid = sum(p*q for p, q in book.bids)
    ask = sum(p*q for p, q in book.asks)
    mid = (book.bids[0][0]+book.asks[0][0])/2
    digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return {
        'symbol': book.symbol, 'bid_depth_vnd': str(bid), 'ask_depth_vnd': str(ask),
        'imbalance': str((bid-ask)/(bid+ask)),
        'spread_vnd_per_share': str(book.asks[0][0]-book.bids[0][0]),
        'spread_bps': str((book.asks[0][0]-book.bids[0][0])/mid*10000),
        'levels': {'bid': len(book.bids), 'ask': len(book.asks)},
        'source': 'manual', 'contract_version': '1.0', 'engine_version': '0.1.0',
        'input_hash': digest, 'available_at': book.received_at.isoformat(),
        'warnings': ['Dữ liệu nhập tay; không phải dữ liệu thị trường đã xác minh.',
                     'Độ sâu niêm yết không bảo đảm khả năng khớp lệnh.'],
    }


def available_asof(events, decision_time):
    """Keep only information actually received by a decision time; never reorder retroactively."""
    cutoff = parse_time(decision_time)
    return [e for e in events if parse_time(e['received_at']) <= cutoff and parse_time(e['event_time']) <= cutoff]
