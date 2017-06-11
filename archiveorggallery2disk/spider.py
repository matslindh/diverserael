import sys
import logging

from utils import ArchiveOrgHandler

logging.basicConfig(level=logging.DEBUG)
logging.getLogger().setLevel(logging.DEBUG)

if len(sys.argv) < 2:
    sys.stderr.write('Usage: ' + sys.argv[0] + ' <url>');
    sys.exit(-1)

base_url = sys.argv[1]
output_dir = 'output/'
cache_dir = 'cache/'
content_before = '20080101'

# sleep between requests if not cached
sleep = 10

handler = ArchiveOrgHandler(cache_dir=cache_dir, content_before=content_before, sleep=sleep)

albums = handler.get_all_albums_at_url(base_url)

for album in albums:
    handler.download_album(album, output_dir)
