import os
from django.conf import settings
from django.core.files import File
from django.core.files.storage import Storage
from dateutil import parser, tz
import requests
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


VERSION = (0, 0, 1, 'alpha')

# Dynamically calculate the version based on VERSION tuple
if len(VERSION) > 2 and VERSION[2] is not None:
    if isinstance(VERSION[2], int):
        str_version = "%s.%s.%s" % VERSION[:3]
    else:
        str_version = "%s.%s_%s" % VERSION[:3]
else:
    str_version = "%s.%s" % VERSION[:2]

__version__ = str_version


class UpYunStorage(Storage):
    """
    UpYun Storage
    """
    def __init__(self, options=None):
        if not options:
            self.account = settings.UPYUN_ACCOUNT
            self.password = settings.UPYUN_PASSWORD
            self.bucket = settings.UPYUN_BUCKET
            self.api_url = "http://v2.api.upyun.com"
            self.cache = {}

    def _endpoint(self, name):
        return "%s/%s/%s" % (self.api_url, self.bucket, name)

    def _request(self, method, url, data=None, **kwargs):
        return requests.request(method, url, data=data, auth=(self.account, self.password), **kwargs)

    def _open(self, name, mode="rb"):
        file = UpYunFile(name, self, mode)
        self.cache[name] = file
        return file

    def _save(self, name, content):
        file_data = content.read()
        headers = {
            'Mkdir': 'true',
        }
        url = self._endpoint(name)
        # requests.put(url, file_data, headers=headers, auth=(self.account, self.password))
        resp = self._request('PUT', url, file_data, headers=headers)
        if not resp.status_code == 200:
            raise IOError("UpYunStorageError: %s" % resp.content)
        return name

    def delete(self, name):
        url = self._endpoint(name)
        resp = self._request("DELETE", url)
        print resp
        print resp.headers
        print resp.content
        if not resp.content == 'true':
            raise IOError("UpYunStorageError: failed to delete file")

    def save(self, name, content):
        return self._save(name, content)

    def modified_time(self, name):
        url = self._endpoint(name)
        resp = self.cache[url]

        last_modified_date = parser.parse(resp.headers.get('date'))

        # if the date has no timzone, assume UTC
        if last_modified_date.tzinfo == None:
            last_modified_date = last_modified_date.replace(tzinfo=tz.tzutc())

        # convert date to local time w/o timezone
        return last_modified_date.astimezone(tz.tzlocal()).replace(tzinfo=None)

    def exists(self, name):
        url = self._endpoint(name)
        resp = self._request('HEAD', url)
        return resp.status_code == 200

    def size(self, name):
        if name in self.cache:
            return self.cache[name].size
        url = self._endpoint(name)
        return self._request('HEAD', url).headers.get('Content-Length')

    def _read(self, name):
        url = self._endpoint(name)
        return self._request('GET', url).content

    def url(self, name):
        return name


class UpYunFile(File):
    def __init__(self, name, storage, mode):
        self._name = name
        self._storage = storage
        self._mode = mode
        self.file = StringIO()
        self._is_dirty = False

    @property
    def size(self):
        if not hasattr(self, '_size'):
            self._size = self._storage.size(self._name)
        return self._size

    def read(self):
        data = self._storage._read(self._name)
        self.file = StringIO(data)
        return self.file.getvalue()

    def write(self, content):
        if 'w' not in self._mode:
            raise AttributeError("File was opened for read-only access.")
        self.file = StringIO(content)
        self._is_dirty = True

    def close(self):
        if self._is_dirty:
            self._storage._put_file(self._name, self.file.getvalue())
        self.file.close()

