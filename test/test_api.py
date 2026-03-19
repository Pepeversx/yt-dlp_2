#!/usr/bin/env python3

import os
import tempfile
import unittest
from unittest import mock

from api.common import download_media, requires_native_download


class TestApiHelpers(unittest.TestCase):
    def test_requires_native_download_for_manifest_protocols(self):
        self.assertTrue(requires_native_download({
            'protocol': 'm3u8_native',
            'stream_url': 'https://video.twimg.com/ext_tw_video/test.m3u8',
        }))
        self.assertTrue(requires_native_download({
            'protocol': 'https',
            'stream_url': 'https://example.com/video/master.mpd',
        }))
        self.assertFalse(requires_native_download({
            'protocol': 'https',
            'stream_url': 'https://video.twimg.com/ext_tw_video/test.mp4',
        }))

    def test_download_media_returns_downloaded_filepath(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'video.mp4')
            with open(filepath, 'wb') as fh:
                fh.write(b'test-data')

            class FakeYDL:
                def __init__(self, opts):
                    self.opts = opts

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def extract_info(self, url, download=True):
                    self.url = url
                    self.download = download
                    return {
                        'id': 'abc123',
                        'title': 'Sample',
                        'ext': 'mp4',
                        'requested_downloads': [{'filepath': filepath}],
                    }

            with mock.patch('api.common.YoutubeDL', FakeYDL):
                result = download_media('https://x.com/i/broadcasts/1abc', directory=tmpdir)

            self.assertEqual(result['id'], 'abc123')
            self.assertEqual(result['title'], 'Sample')
            self.assertEqual(result['ext'], 'mp4')
            self.assertEqual(result['filepath'], filepath)


if __name__ == '__main__':
    unittest.main()
