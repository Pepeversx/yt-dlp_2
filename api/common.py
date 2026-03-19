import os
import re
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError



def _is_twitter_or_x_source(url, info):
    netloc = (urlparse(url).netloc or '').lower()
    extractor = (info.get('extractor_key') or info.get('extractor') or '').lower()
    return 'twitter' in extractor or netloc.endswith('x.com') or netloc.endswith('twitter.com')


def _direct_http_formats(info, *, audio_only=False):
    formats = info.get('formats') or []

    def is_direct_http(fmt):
        url = fmt.get('url') or ''
        protocol = (fmt.get('protocol') or '').lower()
        return (
            bool(url)
            and (protocol in ('http', 'https') or url.startswith(('http://', 'https://')))
            and '.m3u8' not in url.lower()
            and '.mpd' not in url.lower()
            and not url.lower().endswith('.ism/manifest')
        )

    candidates = [fmt for fmt in formats if is_direct_http(fmt)]
    if audio_only:
        candidates = [fmt for fmt in candidates if fmt.get('vcodec') == 'none']
    else:
        candidates = [fmt for fmt in candidates if fmt.get('vcodec') != 'none']

    if not candidates:
        return None

    return max(candidates, key=lambda fmt: (
        fmt.get('height') or 0,
        fmt.get('width') or 0,
        fmt.get('tbr') or 0,
        fmt.get('abr') or 0,
    ))

def is_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)

def safe_filename(name, fallback='video'):
    name = (name or fallback).strip()
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    return name[:180] or fallback

def _cookies_from_browser_value(raw):
    # Supported values:
    #   chrome
    #   firefox:default
    #   chrome:Profile 3:/home/user/.config/google-chrome
    if not raw:
        return None
    parts = [part.strip() for part in raw.split(':') if part.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return (parts[0],)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return tuple(parts)

def _configured_cookie_opts():
    cookiefile = os.getenv('YTDLP_COOKIE_FILE', '').strip()
    cookies_from_browser = os.getenv('YTDLP_COOKIES_FROM_BROWSER', '').strip()

    opts = []
    if cookiefile:
        opts.append({'cookiefile': cookiefile})

    parsed = _cookies_from_browser_value(cookies_from_browser)
    if parsed:
        opts.append({'cookiesfrombrowser': parsed})

    return opts


def _youtube_extractor_arg_profiles():
    # None means using yt-dlp defaults, which should be tried first.
    return [
        None,
        {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['configs'],
            }
        },
        {
            'youtube': {
                'player_client': ['ios', 'android', 'tv_embedded'],
                'player_skip': ['webpage', 'configs'],
            }
        },
    ]


def _base_ydl_opts(fmt, audio_only, single_video, extractor_args=None):
    resolved_format = 'bestaudio/best' if audio_only else fmt
    return {
        'format': resolved_format,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': bool(single_video),
        **({'extractor_args': extractor_args} if extractor_args else {}),
    }


def _looks_like_cookie_error(error_message):
    message = (error_message or '').lower()
    cookie_signals = (
        'cookies',
        'sign in to confirm',
        "confirm you're not a bot",
        'login required',
        'age-restricted',
    )
    return any(signal in message for signal in cookie_signals)


def _looks_like_network_or_proxy_error(error_message):
    message = (error_message or '').lower()
    network_signals = (
        'proxyerror',
        'tunnel connection failed',
        'network is unreachable',
        'name or service not known',
        'temporary failure in name resolution',
        'timed out',
        'connection reset',
    )
    return any(signal in message for signal in network_signals)


def extract_media(url, fmt='best', audio_only=False, single_video=True):
    ydl_opts = _base_ydl_opts(fmt, audio_only, single_video)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        if 'youtube' not in (urlparse(url).netloc or '').lower():
            raise

        info = None
        last_error = exc
        cookie_opts = _configured_cookie_opts()

        retry_opts_list = []
        for extractor_args in _youtube_extractor_arg_profiles():
            retry_opts_list.append(_base_ydl_opts(fmt, audio_only, single_video, extractor_args=extractor_args))

        if cookie_opts:
            retry_opts_list.extend(
                {**opts, **cookie_opt}
                for opts in retry_opts_list
                for cookie_opt in cookie_opts
            )

        for retry_opts in retry_opts_list:
            try:
                with YoutubeDL(retry_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                break
            except Exception as retry_exc:
                last_error = retry_exc

        if info is None:
            error_text = str(last_error)
            if cookie_opts:
                raise RuntimeError(
                    'YouTube extraction failed even with configured cookies. '
                    'Please refresh/export cookies and try again. '
                    f'Original error: {error_text}'
                )

            if _looks_like_network_or_proxy_error(error_text):
                raise RuntimeError(
                    'Could not reach YouTube from this server (network/proxy issue). '
                    'If you use an outbound proxy, verify it allows youtube.com/googlevideo.com. '
                    f'Original error: {error_text}'
                )

            if _looks_like_cookie_error(error_text):
                raise RuntimeError(
                    'YouTube may require authenticated cookies for this request. '
                    'Set YTDLP_COOKIE_FILE to an exported cookies.txt, or set '
                    'YTDLP_COOKIES_FROM_BROWSER (e.g. chrome or firefox:default), '
                    f'then retry. Original error: {error_text}'
                )

            raise RuntimeError(f'YouTube extraction failed: {error_text}')

    if 'entries' in info and info.get('entries'):
        info = next((entry for entry in info['entries'] if entry), None) or info

    selected = _direct_http_formats(info, audio_only=audio_only) if _is_twitter_or_x_source(url, info) else None
    selected = selected or info

    return {
        'id': info.get('id'),
        'title': info.get('title'),
        'duration': info.get('duration'),
        'webpage_url': info.get('webpage_url') or url,
        'stream_url': selected.get('url') or info.get('url'),
        'extractor': info.get('extractor_key') or info.get('extractor'),
        'ext': selected.get('ext') or info.get('ext') or 'mp4',
        'protocol': selected.get('protocol') or info.get('protocol'),
        'http_headers': selected.get('http_headers') or info.get('http_headers') or {},
    }


def download_media(url, *, directory, fmt='best', audio_only=False, single_video=True):
    ydl_opts = {
        **_base_ydl_opts(fmt, audio_only, single_video),
        'skip_download': False,
        'paths': {'home': directory, 'temp': directory},
        'outtmpl': {'default': '%(title).180B [%(id)s].%(ext)s'},
        'noprogress': True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if 'entries' in info and info.get('entries'):
        info = next((entry for entry in info['entries'] if entry), None) or info

    filepath = ((info.get('requested_downloads') or [{}])[0].get('filepath')
                or info.get('filepath') or info.get('_filename'))
    if not filepath or not os.path.exists(filepath):
        raise RuntimeError('yt-dlp finished without producing a downloadable file')

    return {
        'id': info.get('id'),
        'title': info.get('title'),
        'ext': info.get('ext') or os.path.splitext(filepath)[1].lstrip('.') or 'mp4',
        'filepath': filepath,
    }
