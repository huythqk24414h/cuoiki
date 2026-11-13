"""Legacy manual-source boundary. SSI DATA is isolated in ssi_client/ssi_stream/market."""
from typing import Protocol, Iterable


class DataSource(Protocol):
    def events(self) -> Iterable[dict]: ...
    def health(self) -> dict: ...


class EmptySource:
    def events(self):
        return iter(())

    def health(self):
        return {'source': 'none', 'connection': 'not_configured', 'database': 'disabled',
                'last_event_at': None, 'model': 'not_trained', 'market_metrics': None}


def get_source(name='none'):
    if name=='replay':
        return ReplaySource()
    if name != 'none':
        raise ValueError('Legacy DATA_SOURCE chỉ nhận none. SSI DATA dùng lớp market riêng; replay có chế độ offline riêng, mock không được đưa vào dữ liệu thật.')
    return EmptySource()

class ReplaySource:
    def events(self):
        from src.research_core import replay,ROOT
        rows,_=replay((ROOT/'data/live_snapshots').glob('*.jsonl'))
        return iter(rows)

    def health(self):
        return {'source':'replay','connection':'offline_replay','database':'disabled',
                'model':'not_trained','market_metrics':None,'note':'Receive-order playback, not LIVE or a trained forecast.'}
