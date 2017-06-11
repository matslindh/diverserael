from bs4 import BeautifulSoup as BS
import logging
from email.utils import parsedate_tz
import calendar
import datetime
import pytz

log = logging.getLogger()


def parse_gallery_front(data):
    bs = BS(data, 'html.parser')

    albums = []

    for el in bs.select('[class="title"]'):
        album = {}
        album['href'] = el.find('a').get('href')
        album['title'] = el.get_text().strip()

        albums.append(album)

    last_page_image = bs.select('[alt="Last Page"]')
    last_page = None

    if last_page_image:
        href = last_page_image[0].find_parent('a').get('href')
        parts = href.split('=')
        last_page = int(parts[len(parts) - 1])

    return {
        'albums': albums,
        'last_page': last_page
    }


def clean_text(t):
    return t.replace('ï¿½', '_')


def parse_image_page(data):
    bs = BS(data, 'html.parser')

    page = {
        'comments': [],
        'caption': None,
    }

    comment_box = bs.select('.commentbox')

    if comment_box:
        container = comment_box[0]

        from utils import chunks

        for trs in chunks(container.find_all('tr'), 2):
            _, name, date = trs[0].find_all('td')
            name = name.get_text().strip()
            date = parsedate_tz(date.get_text().strip().strip('()').replace('CET', '+0100'))
            comment = trs[1].find('td').get_text().strip()

            if date:
                timestamp = calendar.timegm(date) - date[9]
                date = datetime.datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Oslo'))

            page['comments'].append({
                'name': name,
                'date': date.isoformat(),
                'comment': comment,
            })

    caption_el = bs.select('.pcaption')

    if caption_el:
        page['caption'] = caption_el[0].get_text().strip()

    return page


def parse_gallery_page(data):
    bs = BS(data, 'html.parser')

    page = {
        'albums': [],
        'images': [],
        'last_page': 1
    }

    for img in bs.select('.vathumbs'):
        type_ = 'image'
        image = {
            'urls': [],
            'caption': None,
            'views': None,
            'page_url': None,
        }

        caption_el = img.select('.modcaption')

        if caption_el:
            caption_el = caption_el[0]

            # sub-albums
            if caption_el.find('center') and caption_el.find('center').find('b'):
                album_el = caption_el.find('center').find('b')
                album_name = album_el.get_text().strip()

                if album_name.startswith('Album: '):
                    album_name = album_name[7:]

                page['albums'].append({
                    'title': album_name,
                    'href':  album_el.find('a')['href']
                })

                type_ = 'album'
            elif True:
                divs = caption_el.find_all('div')
                image['caption'] = clean_text(divs[0].get_text().strip()).strip(' *')
                view_text = divs[1].get_text().strip().split(' ')
                image['views'] = int(view_text[1])
        else:
            log.info("Did not find a caption object")

        if type_ == 'image':
            container = img.select('.vafloat2')

            if container:
                image['page_url'] = container[0].find('a')['href']

            image_url = img.select('img')

            for u in image_url:
                src = u['src']

                if '/albums/' in src:
                    from utils import unarchived_url

                    old_url = unarchived_url(src)
                    image['urls'] = [old_url.replace('.thumb', ''), old_url.replace('.thumb', '.sized'), old_url]
                    break

            page['images'].append(image)

    last_page_image = bs.select('[alt="Last Page"]')

    if last_page_image:
        href = last_page_image[0].find_parent('a').get('href')
        parts = href.split('=')
        page['last_page'] = int(parts[len(parts) - 1])

    return page