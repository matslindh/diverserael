import requests
import hashlib
import os
import json
import urllib.parse
import time
import re
import logging

from urllib.parse import urljoin
from parsers import parse_gallery_front, parse_gallery_page, parse_image_page

log = logging.getLogger()
last_request_at = None


class ArchiveOrgHandler:
    def __init__(self, cache_dir, content_before=None, sleep=2):
        self.cache_dir = cache_dir
        self.content_before = content_before
        self.sleep = sleep
        self.last_request_at = None

    def get_url_content_via_archive_org(self, url, raw=False):
        archive_url = self.get_latest_archive_org_mirror_url(url)

        if not archive_url:
            return None

        return self.get_url_with_local_cache(archive_url, raw=raw)

    def get_latest_archive_org_mirror_url(self, url):
        params = params = {'url': url}

        if self.content_before:
            params['timestamp'] = self.content_before

        content = self.get_url_with_local_cache('https://archive.org/wayback/available',
                                                params=params)

        if not content:
            return None

        data = json.loads(content)

        if 'archived_snapshots' in data:
            if 'closest' in data['archived_snapshots']:
                return data['archived_snapshots']['closest']['url']

        return None

    def get_url_with_local_cache(self, url, params=None, raw=False):
        global last_request_at
        if not params:
            params = {}

        cache_url = url + '|' + urllib.parse.urlencode(params)
        digest = hashlib.md5(cache_url.encode('utf-8')).hexdigest()
        cache_file = os.path.join(self.cache_dir, digest)

        if os.path.exists(cache_file):
            log.debug("Read local cache file: " + cache_file + " for " + cache_url)

            if raw:
                with open(cache_file, "rb") as f:
                    return f.read()
            else:
                with open(cache_file, encoding='utf-8') as f:
                    return f.read()

        if self.sleep and self.last_request_at and self.last_request_at + self.sleep > time.time():
            log.debug("Sleeping")
            time.sleep(self.sleep + self.last_request_at - time.time())

        log.debug("requesting (cache_url: " + cache_url + ")")
        self.last_request_at = time.time()
        r = requests.get(url, params=params)

        if r.status_code >= 400:
            # TODO: REMOVE
            with open(cache_file, "w", encoding='utf-8') as f:
                log.debug("Wrote local 404 file: " + cache_file)
                f.write('')

            return None

        if raw:
            content = r.content
        else:
            content = r.text

        if raw:
            log.debug("Write local raw cache file: " + cache_file)
            with open(cache_file, "wb") as f:
                f.write(content)
        else:
            log.debug("Write local cache file: " + cache_file)
            with open(cache_file, "w", encoding='utf-8') as f:
                f.write(content)

        return content

    def get_all_albums_at_url(self, url):
        start_html = self.get_url_content_via_archive_org(url)
        result = parse_gallery_front(start_html)
        albums = result['albums']

        # fetch the other albums as well
        if result['last_page'] and result['last_page'] > 1:
            for i in range(1, result['last_page']):
                url = urljoin(url, 'albums.php?set_albumListPage=' + str(i + 1))
                album_html = self.get_url_content_via_archive_org(url)

                if album_html:
                    album_result = parse_gallery_front(album_html)
                    albums += album_result['albums']

        return albums

    def download_album(self, album, base_dir):
        output_path = os.path.join(base_dir, safe_dir_name(album['title']))
        log.info("Downloading " + album['title'] + " into " + output_path)

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        html = self.get_url_with_local_cache(album['href'])

        if not html:
            log.warning("Did not find any valid HTML for gallery page at " + album['href'])
            return

        gallery_page = parse_gallery_page(html)

        for i in range(0, gallery_page['last_page']):
            url = album['href']
            if i > 0:
                html = self.get_url_content_via_archive_org(unarchived_url(album['href'] + '?page=' + str(i+1)))
                url = unarchived_url(album['href'] + '?page=' + str(i+1))
            else:
                html = self.get_url_with_local_cache(album['href'])

            if not html:
                log.warning("Did not get HTML for " + url)
                continue

            gallery_page = parse_gallery_page(html)

            for sub_album in gallery_page['albums']:
                self.download_album(sub_album, output_path)

            for image in gallery_page['images']:
                self.download_image_and_metadata(image, output_path)

    def download_image_and_metadata(self, image, output_path):
        if not image['urls']:
            return

        not_found = open(os.path.join(output_path, 'notfound.urls'), 'a', encoding='utf-8')
        output_name = os.path.basename(image['urls'][0])

        for url in image['urls']:
            # try to fetch the actual image, starting with the original size
            image_data = self.get_url_content_via_archive_org(url, raw=True)

            if image_data:
                output_name = os.path.basename(url)
                file_path = os.path.join(output_path, output_name)

                log.debug('Writing ' + file_path)

                with open(file_path, 'wb') as f:
                    f.write(image_data)

                break
            else:
                not_found.write(url + "\n")

        metadata_file = os.path.join(output_path, output_name + '.metadata')

        # try to fetch metadata
        if image['page_url']:
            result = self.get_url_with_local_cache(image['page_url'])

            if result is None:
                result = self.get_url_content_via_archive_org(unarchived_url(image['page_url']))

            if result:
                page_parsed = parse_image_page(result)

                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(page_parsed, f)
            else:
                not_found.write(unarchived_url(image['page_url']) + "\n")

        not_found.close()


def safe_dir_name(name):
    return re.sub(r'[^a-zA-Z0-9_\- #]', '_', name)


def unarchived_url(url):
    return re.sub('^http://web.archive.org/web/[^/]+/', '', url)


# https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]