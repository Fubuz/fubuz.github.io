# -*- coding: utf-8 -*-
"""
DaddyLive Kodi Addon (Full Version with Fixes)
- SSL bypass
- Proxy support (209.135.168.41)
- Xbox optimizations
- Retry logic for connection issues
"""

import re
import os
import sys
import json
import html
import ssl
from urllib.parse import urlencode, quote, unquote, parse_qsl, quote_plus, urlparse, urlunparse
from datetime import datetime, timedelta, timezone
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
import xbmcaddon
import base64
import traceback

# ===== CRITICAL FIXES =====
ssl._create_default_https_context = ssl._create_unverified_context  # Disable SSL verification

# Proxy Configuration (REPLACE WITH YOUR PROXY)
PROXY = "http://209.135.168.41:8080"  # Format: "http://IP:PORT"
PROXIES = {
    'http': PROXY,
    'https': PROXY
} if PROXY else None

# ===== ADDON SETUP =====
addon_url = sys.argv[0]
addon_handle = int(sys.argv[1])
params = dict(parse_qsl(sys.argv[2][1:]))
addon = xbmcaddon.Addon(id='plugin.video.daddylivehd')

# Settings
mode = addon.getSetting('mode')
baseurl = addon.getSetting('baseurl').strip() or 'https://daddylivehd.sx/'
schedule_path = addon.getSetting('schedule_path').strip() or 'schedule.json'
schedule_url = baseurl + schedule_path
UA = 'Mozilla/5.0 (Xbox; Xbox One) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
FANART = addon.getAddonInfo('fanart')
ICON = addon.getAddonInfo('icon')

# Cache settings
schedule_cache = None
cache_timestamp = 0
livetv_cache = None
livetv_cache_timestamp = 0
cache_duration = 900  # 15 minutes

# API endpoints
AUTH_SERVER = "https://top2new.newkso.ru"
CDN1_BASE = "https://top1.newkso.ru/top1/cdn"
CDN_DEFAULT = "newkso.ru"

# ===== IMPROVED NETWORK HANDLING =====
def setup_session():
    """Create a requests session with proxy and retries"""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.mount('http://', HTTPAdapter(max_retries=retries))
    if PROXIES:
        session.proxies = PROXIES
    session.verify = False  # Ignore SSL errors
    return session

# ===== ORIGINAL FUNCTIONS WITH FIXES =====
def log(msg):
    LOGPATH = xbmcvfs.translatePath('special://logpath/')
    FILENAME = 'daddylivehd.log'
    LOG_FILE = os.path.join(LOGPATH, FILENAME)
    try:
        if isinstance(msg, str):
            _msg = f'\n    {msg}'
        else:
            raise TypeError('log() msg not of type str!')

        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                pass
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            line = ('[{} {}]: {}').format(datetime.now().date(), str(datetime.now().time())[:8], _msg)
            f.write(line.rstrip('\r\n') + '\n')
    except Exception as e:
        xbmc.log(f'[DaddyLive] Logging Failure: {e}', xbmc.LOGERROR)

def preload_cache():
    global schedule_cache, cache_timestamp
    global livetv_cache, livetv_cache_timestamp
    session = setup_session()

    # Preload schedule
    try:
        headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': baseurl
        }
        response = session.get(schedule_url, headers=headers, timeout=10)
        if response.status_code == 200:
            schedule_cache = response.json()
            cache_timestamp = time.time()
    except Exception as e:
        log(f"Failed to preload schedule: {str(e)}")

    # Preload live TV
    try:
        livetv_cache = channels(fetch_live=True)
        livetv_cache_timestamp = time.time()
    except Exception as e:
        log(f"Failed to preload live TV: {str(e)}")

def clean_category_name(name):
    """Cleans up HTML entities from sport categories."""
    if isinstance(name, str):
        name = html.unescape(name).strip()
    return name

def get_local_time(utc_time_str):
    time_format = addon.getSetting('time_format') or '12h'
    user_timezone = int(addon.getSetting('epg_timezone') or 0
    
    if addon.getSettingBool('dst_enabled'):
        user_timezone += 1

    try:
        event_time_utc = datetime.strptime(utc_time_str, '%H:%M')
        event_time_local = event_time_utc + timedelta(hours=user_timezone)
        if time_format == '12h':
            return event_time_local.strftime('%I:%M %p').lstrip('0')
        return event_time_local.strftime('%H:%M')
    except:
        return utc_time_str

def build_url(query):
    return addon_url + '?' + urlencode(query)

def addDir(title, dir_url, is_folder=True):
    li = xbmcgui.ListItem(title)
    labels = {'title': title, 'plot': title, 'mediatype': 'video'}
    kodiversion = getKodiversion()
    if kodiversion < 20:
        li.setInfo("video", labels)
    else:
        infotag = li.getVideoInfoTag()
        infotag.setMediaType('video')
        infotag.setTitle(title)
        infotag.setPlot(title)
    li.setArt({'icon': ICON, 'fanart': FANART})
    li.setProperty('IsPlayable', 'false' if is_folder else 'true')
    xbmcplugin.addDirectoryItem(handle=addon_handle, url=dir_url, listitem=li, isFolder=is_folder)

def closeDir():
    xbmcplugin.endOfDirectory(addon_handle)

def getKodiversion():
    return int(xbmc.getInfoLabel("System.BuildVersion")[:2])

def Main_Menu():
    addDir('LIVE SPORTS', build_url({'mode': 'menu', 'serv_type': 'sched'}))
    addDir('LIVE TV', build_url({'mode': 'menu', 'serv_type': 'live_tv'}))
    addDir('Settings', build_url({'mode': 'open_settings'}), False)
    closeDir()

def getCategTrans():
    global schedule_cache, cache_timestamp
    session = setup_session()
    headers = {
        'User-Agent': UA,
        'Referer': baseurl,
        'Accept': 'application/json'
    }

    now = time.time()
    if schedule_cache and (now - cache_timestamp) < cache_duration:
        schedule = schedule_cache
    else:
        try:
            response = session.get(schedule_url, headers=headers, timeout=10)
            if response.status_code == 200:
                schedule = response.json()
                schedule_cache = schedule
                cache_timestamp = now
            else:
                xbmcgui.Dialog().notification("Error", f"Status code: {response.status_code}")
                return []
        except Exception as e:
            xbmcgui.Dialog().notification("Error", str(e))
            return []

    categs = []
    try:
        for date_key, events in schedule.items():
            for categ, events_list in events.items():
                categs.append((clean_category_name(categ), json.dumps(events_list)))
    except Exception as e:
        log(f"Error parsing schedule: {e}")

    return categs

def Menu_Trans():
    for categ_name, events_list in getCategTrans():
        addDir(categ_name, build_url({'mode': 'showChannels', 'trType': categ_name}))
    closeDir()

def getTransData(categ):
    trns = []
    for categ_name, events_list_json in getCategTrans():
        if categ_name == categ:
            events_list = json.loads(events_list_json)
            for item in events_list:
                channels = item.get('channels', [])
                if isinstance(channels, dict):
                    channels = list(channels.values())
                
                trns.append({
                    'title': f"{get_local_time(item.get('time'))} {item.get('event')}",
                    'channels': channels
                })
    return trns

def ShowChannels(categ, channels_list):
    if categ.lower() == 'basketball':
        nba_channels = [c for c in channels_list if 'NBA' in c['title'].upper()]
        if nba_channels:
            addDir('[NBA]', build_url({
                'mode': 'showNBA',
                'trType': categ,
                'nba_channels': json.dumps(nba_channels)
            }), True)

    for item in channels_list:
        addDir(item['title'], build_url({
            'mode': 'trList',
            'trType': categ,
            'channels': json.dumps(item.get('channels', []))
        }), True)
    closeDir()

def TransList(categ, channels):
    for channel in channels:
        addDir(
            html.unescape(channel.get('channel_name')),
            build_url({
                'mode': 'trLinks',
                'trData': json.dumps({'channels': [channel]})
            }),
            False
        )
    closeDir()

def getSource(trData):
    data = json.loads(unquote(trData))
    if data.get('channels'):
        PlayStream(f"{baseurl}stream/stream-{data['channels'][0]['channel_id']}.php")

def channels(fetch_live=False):
    global livetv_cache, livetv_cache_timestamp
    session = setup_session()

    if not fetch_live and livetv_cache and (time.time() - livetv_cache_timestamp) < cache_duration:
        return livetv_cache

    url = baseurl + '/24-7-channels.php'
    do_adult = addon.getSetting('adult_pw') == 'lol'
    headers = {'Referer': baseurl, 'user-agent': UA}

    try:
        resp = session.post(url, headers=headers, timeout=10).text
        ch_block = re.compile('<center><h1(.+?)tab-2', re.DOTALL).findall(resp)[0]
        chan_data = re.compile('href=\"(.*)\" target(.*)<strong>(.*)</strong>').findall(ch_block)
        
        channels = []
        for c in chan_data:
            if not "18+" in c[2]:
                channels.append([c[0], c[2]])
            if do_adult and "18+" in c[2]:
                channels.append([c[0], c[2]])
        
        livetv_cache = channels
        livetv_cache_timestamp = time.time()
        return channels
    except Exception as e:
        log(f"channels() failed: {str(e)}")
        return []

def list_gen():
    for channel in channels():
        addDir(channel[1], build_url({'mode': 'play', 'url': baseurl + channel[0]}), False)
    closeDir()

def PlayStream(link):
    session = setup_session()
    headers = {'Referer': baseurl, 'user-agent': UA}

    try:
        # Step 1: Get initial stream page
        resp0 = session.post(link, headers=headers, timeout=10).text
        m_iframe = re.search(r'iframe\s+src="([^"]+)"', resp0)
        if not m_iframe:
            raise Exception("No iframe URL found")

        # Step 2: Extract auth variables
        iframe_url = m_iframe.group(1)
        resp1 = session.get(iframe_url, headers=headers, timeout=10).text
        
        channel_key = re.search(r'var\s+channelKey\s*=\s*"([^"]+)"', resp1).group(1)
        auth_ts = re.search(r'var\s+authTs\s*=\s*"([^"]+)"', resp1).group(1)
        auth_rnd = re.search(r'var\s+authRnd\s*=\s*"([^"]+)"', resp1).group(1)
        auth_sig = re.search(r'var\s+authSig\s*=\s*"([^"]+)"', resp1).group(1)

        # Step 3: Get auth token
        auth_url = f"{AUTH_SERVER}/auth.php?channel_id={channel_key}&ts={auth_ts}&rnd={auth_rnd}&sig={quote_plus(auth_sig)}"
        auth_resp = session.get(auth_url, headers=headers, timeout=10)

        # Step 4: Get final stream URL
        parsed = urlparse(iframe_url)
        lookup_url = f"{parsed.scheme}://{parsed.netloc}/server_lookup.php?channel_id={channel_key}"
        lookup_resp = session.get(lookup_url, headers=headers, timeout=10).json()
        server_key = lookup_resp.get('server_key')

        if server_key == "top1/cdn":
            m3u8_url = f"{CDN1_BASE}/{channel_key}/mono.m3u8"
        else:
            m3u8_url = f"https://{server_key}.{CDN_DEFAULT}/{server_key}/{channel_key}/mono.m3u8"

        # Step 5: Play stream in Kodi
        stream_url = f"{m3u8_url}|Referer={quote_plus(baseurl)}&User-Agent={quote_plus(UA)}"
        li = xbmcgui.ListItem(path=stream_url)
        li.setProperty('inputstream', 'inputstream.adaptive')
        li.setProperty('inputstream.adaptive.manifest_type', 'hls')
        xbmcplugin.setResolvedUrl(addon_handle, True, li)

    except Exception as e:
        log(traceback.format_exc())
        xbmcgui.Dialog().ok("Stream Error", f"Failed to play:\n{str(e)}")

# ===== MAIN ROUTING =====
if __name__ == '__main__':
    if not params.get('mode'):
        preload_cache()
        Main_Menu()
    else:
        mode = params['mode']
        
        if mode == 'menu':
            servType = params.get('serv_type')
            if servType == 'sched':
                Menu_Trans()
            elif servType == 'live_tv':
                list_gen()
        
        elif mode == 'showChannels':
            ShowChannels(
                params.get('trType'),
                getTransData(params.get('trType'))
            )
        
        elif mode == 'trList':
            TransList(
                params.get('trType'),
                json.loads(params.get('channels'))
            )
        
        elif mode == 'trLinks':
            getSource(params.get('trData'))
        
        elif mode == 'play':
            PlayStream(params.get('url'))
        
        elif mode == 'open_settings':
            addon.openSettings()
            closeDir()
        
        elif mode == 'showNBA':
            ShowChannels(
                params.get('trType'),
                json.loads(params.get('nba_channels'))
    )
