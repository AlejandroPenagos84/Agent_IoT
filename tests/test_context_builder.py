import math
import unittest

from application.ports.ports_out import FeatureSource
from application.ports.types import Frame
from domain.model import FrameContext
from infrastructure.features import ContextFeatureSource


class StubSource(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


def frame(ip, epoch, length, stream=1, msgtype=3):
    return Frame(
        {'frame.time_epoch': epoch, 'frame.len': length, 'mqtt.msgtype': msgtype},
        FrameContext(ts=epoch, ip=ip, srcport=40000, dst_ip='broker',
                     dstport=1883, stream_id=stream))


def l2_frame(eth_src, eth_dst, epoch, length=60, ip=None):
    return Frame(
        {'frame.time_epoch': epoch, 'frame.len': length, 'mqtt.msgtype': None},
        FrameContext(ts=epoch, eth_src=eth_src, eth_dst=eth_dst, ip=ip))


class ContextBuilderTests(unittest.TestCase):
    def collect(self, frames, window=5.0):
        builder = ContextFeatureSource(StubSource(frames), window_seconds=window)
        builder.start()
        return list(builder.rows())

    def test_uses_only_earlier_frames(self):
        rows = self.collect([frame('a', 0.0, 60), frame('a', 1.0, 100)])
        first, second = rows
        self.assertEqual(first.features['_ctx_origen_frames_s'], 0.0)
        self.assertEqual(first.features['_ctx_origen_bytes_s'], 0.0)
        self.assertEqual(second.features['_ctx_origen_frames_s'], 1 / 5)
        self.assertEqual(second.features['_ctx_origen_bytes_s'], 60 / 5)
        self.assertEqual(second.features['_ctx_origen_conexiones'], 1)
        self.assertEqual(second.features['_ctx_origen_connects'], 0)

    def test_window_eviction(self):
        rows = self.collect([frame('a', 0.0, 60), frame('a', 10.0, 60)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 0.0)

    def test_same_timestamp_earlier_in_stream_counts(self):
        rows = self.collect([frame('a', 5.0, 60), frame('a', 5.0, 60)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 1 / 5)

    def test_missing_ip_is_nan(self):
        rows = self.collect([frame(None, 0.0, 60)])
        self.assertTrue(math.isnan(rows[0].features['_ctx_origen_frames_s']))

    def test_sources_do_not_mix(self):
        rows = self.collect([frame('a', 0.0, 60), frame('b', 1.0, 60)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 0.0)

    def test_connect_counted(self):
        rows = self.collect([frame('a', 0.0, 60, msgtype=1), frame('a', 1.0, 60)])
        self.assertEqual(rows[1].features['_ctx_origen_connects'], 1)

    def test_broadcast_and_multicast_flags(self):
        rows = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', 'ff:ff:ff:ff:ff:ff', 0.0),
            l2_frame('aa:aa:aa:aa:aa:aa', '01:00:5e:00:00:01', 0.1),
            l2_frame('aa:aa:aa:aa:aa:aa', 'b8:bb:bb:bb:bb:bb', 0.2),
        ])
        self.assertEqual(rows[0].features['_ctx_is_broadcast'], 1.0)
        self.assertEqual(rows[0].features['_ctx_is_multicast'], 1.0)
        self.assertEqual(rows[1].features['_ctx_is_broadcast'], 0.0)
        self.assertEqual(rows[1].features['_ctx_is_multicast'], 1.0)
        self.assertEqual(rows[2].features['_ctx_is_broadcast'], 0.0)
        self.assertEqual(rows[2].features['_ctx_is_multicast'], 0.0)

    def test_l2_rates_keyed_by_eth_src(self):
        rows = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', 'ff:ff:ff:ff:ff:ff', 0.0),
            l2_frame('aa:aa:aa:aa:aa:aa', 'ff:ff:ff:ff:ff:ff', 0.5),
        ])
        self.assertEqual(rows[1].features['_ctx_l2_frames_s'], 1 / 5)
        self.assertEqual(rows[1].features['_ctx_l2_broadcasts'], 1)
        self.assertEqual(rows[1].features['_ctx_l2_burst_ratio'], 0.0)

    def test_l2_missing_eth_src_is_nan(self):
        rows = self.collect([l2_frame(None, 'ff:ff:ff:ff:ff:ff', 0.0)])
        self.assertTrue(math.isnan(rows[0].features['_ctx_l2_frames_s']))
        self.assertEqual(rows[0].features['_ctx_is_broadcast'], 1.0)


if __name__ == '__main__':
    unittest.main()
