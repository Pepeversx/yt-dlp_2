#!/usr/bin/env python3

import unittest

from api.common import _direct_http_formats, _is_twitter_or_x_source, extract_media


class TestApiHelpers(unittest.TestCase):
    def test_twitter_formats_prefer_direct_http_mp4(self):
        info = {
            'formats': [
                {
                    'url': 'https://video.twimg.com/ext_tw_video/test/master.m3u8',
                    'protocol': 'm3u8_native',
                    'ext': 'mp4',
                    'height': 1080,
                },
                {
                    'url': 'https://video.twimg.com/ext_tw_video/test/1280x720/video.mp4',
                    'protocol': 'https',
                    'ext': 'mp4',
                    'height': 720,
                    'width': 1280,
                    'tbr': 2176,
                    'vcodec': 'h264',
                    'http_headers': {'Referer': 'https://x.com/'},
                },
                {
                    'url': 'https://video.twimg.com/ext_tw_video/test/640x360/video.mp4',
                    'protocol': 'https',
                    'ext': 'mp4',
                    'height': 360,
                    'width': 640,
                    'tbr': 832,
                    'vcodec': 'h264',
                },
            ],
        }
        selected = _direct_http_formats(info)
        self.assertEqual(selected['url'], 'https://video.twimg.com/ext_tw_video/test/1280x720/video.mp4')
        self.assertEqual(selected['http_headers'], {'Referer': 'https://x.com/'})

    def test_is_twitter_or_x_source_detects_x_urls(self):
        self.assertTrue(_is_twitter_or_x_source('https://x.com/i/broadcasts/1abc', {'extractor_key': 'TwitterBroadcast'}))
        self.assertFalse(_is_twitter_or_x_source('https://www.youtube.com/watch?v=test', {'extractor_key': 'Youtube'}))

    def test_extract_media_prefers_direct_twitter_format(self):
        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {
                    'id': '1abc',
                    'title': 'Broadcast',
                    'extractor_key': 'TwitterBroadcast',
                    'url': 'https://video.twimg.com/ext_tw_video/test/master.m3u8',
                    'protocol': 'm3u8_native',
                    'ext': 'mp4',
                    'formats': [
                        {
                            'url': 'https://video.twimg.com/ext_tw_video/test/master.m3u8',
                            'protocol': 'm3u8_native',
                            'ext': 'mp4',
                            'vcodec': 'h264',
                        },
                        {
                            'url': 'https://video.twimg.com/ext_tw_video/test/1280x720/video.mp4',
                            'protocol': 'https',
                            'ext': 'mp4',
                            'height': 720,
                            'width': 1280,
                            'tbr': 2176,
                            'vcodec': 'h264',
                            'http_headers': {'Referer': 'https://x.com/'},
                        },
                    ],
                }

        from unittest import mock
        with mock.patch('api.common.YoutubeDL', FakeYDL):
            result = extract_media('https://x.com/i/broadcasts/1abc')

        self.assertEqual(result['stream_url'], 'https://video.twimg.com/ext_tw_video/test/1280x720/video.mp4')
        self.assertEqual(result['protocol'], 'https')
        self.assertEqual(result['http_headers'], {'Referer': 'https://x.com/'})


if __name__ == '__main__':
    unittest.main()
