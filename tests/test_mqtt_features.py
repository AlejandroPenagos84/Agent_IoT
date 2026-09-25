import math
import unittest

from infrastructure.classifiers._common import decode_hdrflags, topic_wildcard


class DecodeTests(unittest.TestCase):
    def test_type_matches_standard_header(self):
        self.assertEqual(decode_hdrflags('0x00000010')[0], 1)
        self.assertEqual(decode_hdrflags('0x00000030')[0], 3)
        self.assertEqual(decode_hdrflags('0x000000c0')[0], 12)

    def test_qos_dup_retain(self):
        header = decode_hdrflags('0x0000003a')  # 0011 1010
        self.assertEqual(header[0], 3)
        self.assertEqual(header[1], 1)
        self.assertEqual(header[2], 1)
        self.assertEqual(header[3], 0)

    def test_missing_is_nan(self):
        for value in (None, '', float('nan')):
            self.assertTrue(all(math.isnan(part) for part in decode_hdrflags(value)))


class WildcardTests(unittest.TestCase):
    def test_wildcards(self):
        self.assertEqual(topic_wildcard('a/#'), 1)
        self.assertEqual(topic_wildcard('a/+'), 1)
        self.assertEqual(topic_wildcard('$SYS/broker'), 1)
        self.assertEqual(topic_wildcard('home/temp'), 0)

    def test_missing_topic_is_nan(self):
        self.assertTrue(math.isnan(topic_wildcard(None)))
        self.assertTrue(math.isnan(topic_wildcard('')))


if __name__ == '__main__':
    unittest.main()
