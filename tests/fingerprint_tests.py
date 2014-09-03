from cement.utils import test
from common.testutils import decallmethods, xml_validate
from common import VersionsFile
from glob import glob
from lxml import etree
from mock import patch, MagicMock
from plugins.drupal import Drupal
from requests.exceptions import ConnectionError
from tests import BaseTest
import hashlib
import requests
import responses

@decallmethods(responses.activate)
class FingerprintTests(BaseTest):
    '''
        Tests related to version fingerprinting for all plugins.
    '''

    versions_xsd = 'common/versions.xsd'
    xml_file = 'tests/versions.xml'

    class MockHash():
        files = None
        def mock_func(self, *args, **kwargs):
            url = kwargs['file_url']
            return self.files[url]

    def setUp(self):
        super(FingerprintTests, self).setUp()
        self.add_argv(['scan', 'drupal'])
        self.add_argv(['--method', 'forbidden'])
        self.add_argv(self.param_version)
        self._init_scanner()
        self.v = VersionsFile(self.xml_file)

    def mock_xml(self, xml_file, version_to_mock):
        '''
            generates all mock data, and patches Drupal.get_hash

            @param xml_file a file, which contains the XML to mock.
            @param version_to_mock the version which we will pretend to be.
            @return a function which can be used to mock
                BasePlugin.enumerate_file_hash
        '''
        with open(xml_file) as f:
            doc = etree.fromstring(f.read())
            files_xml = doc.xpath('//cms/files/file')

            files = {}
            for file in files_xml:
                url = file.get('url')
                versions = file.xpath('version')
                for file_version in versions:
                    version_number = file_version.get('nb')
                    md5 = file_version.get('md5')

                    if version_number == version_to_mock:
                        files[url] = md5

                if not url in files:
                    files[url] = '5d41402abc4b2a76b9719d911017c592'

        mock_hash = self.MockHash()
        mock_hash.files = files
        mock = MagicMock(side_effect=mock_hash.mock_func)

        return mock

    @patch('common.VersionsFile.files_get', return_value=['misc/drupal.js'])
    def test_calls_version(self, m):
        responses.add(responses.GET, self.base_url + 'misc/drupal.js')
        # with no mocked calls, any HTTP req will cause a ConnectionError.
        self.app.run()

    @test.raises(ConnectionError)
    def test_calls_version_no_mock(self):
        # with no mocked calls, any HTTP req will cause a ConnectionError.
        self.app.run()

    def test_xml_validates_all(self):
        for xml_path in glob('plugins/*/versions.xml'):
            xml_validate(xml_path, self.versions_xsd)

    def test_determines_version(self):
        real_version = '7.26'
        self.scanner.enumerate_file_hash = self.mock_xml(self.xml_file, real_version)

        version, is_empty = self.scanner.enumerate_version(self.base_url, self.xml_file)

        assert version[0] == real_version
        assert is_empty == False

    def test_determines_version_similar(self):
        real_version = '6.15'
        self.scanner.enumerate_file_hash = self.mock_xml(self.xml_file, real_version)
        returned_version, is_empty = self.scanner.enumerate_version(self.base_url, self.xml_file)

        assert len(returned_version) == 2
        assert real_version in returned_version
        assert is_empty == False

    def test_enumerate_hash(self):
        file_url = '/misc/drupal.js'
        body = 'zjyzjy2076'
        responses.add(responses.GET, self.base_url + file_url, body=body)

        actual_md5 = hashlib.md5(body).hexdigest()

        md5 = self.scanner.enumerate_file_hash(self.base_url, file_url)

        assert md5 == actual_md5

    @patch('common.VersionsFile.files_get', return_value=['misc/drupal.js'])
    def test_fingerprint_correct_verb(self, patch):
        # this needs to be a get, otherwise, how are going to get the request body?
        responses.add(responses.GET, self.base_url + 'misc/drupal.js')

        # will exception if attempts to HEAD
        self.scanner.enumerate_version(self.base_url,
                self.scanner.versions_file, verb='head')

    def test_version_gt(self):
        assert self.v.version_gt("10.1", "9.1")
        assert self.v.version_gt("5.23", "5.9")
        assert self.v.version_gt("5.23.10", "5.23.9")

        assert self.v.version_gt("10.1", "10.1") == False
        assert self.v.version_gt("9.1", "10.1") == False
        assert self.v.version_gt("5.9", "5.23") == False
        assert self.v.version_gt("5.23.8", "5.23.9") == False

    def test_version_gt_different_length(self):
        self.v.version_gt("10.0.0.0.0", "10")
        self.v.version_gt("10", "10.0.0.0.0.0")

        assert self.v.version_gt("10.0.0.0.0", "10") == False
        assert self.v.version_gt("10.0.0.0.1", "10") == True

    def test_version_gt_ascii(self):
        # strips all letters?
        assert self.v.version_gt('1.0a', '2.0a') == False
        assert self.v.version_gt('4.0a', '2.0a')

    def test_version_highest(self):
        assert self.v.highest_version() == '7.28'

    def test_version_highest_major(self):
        res = self.v.highest_version_major()

        assert res['6'] == '6.15'
        assert res['7'] == '7.28'

    def test_add_to_xml(self):
        add_versions = {
            '7.31': {
                'misc/ajax.js': '30d9e08baa11f3836eca00425b550f82',
                'misc/drupal.js': '0bb055ea361b208072be45e8e004117b',
                'misc/tabledrag.js': 'caaf444bbba2811b4fa0d5aecfa837e5',
                'misc/tableheader.js': 'bd98fa07941364726469e7666b91d14d'
            },
            '6.33': {
                'misc/drupal.js': '1904f6fd4a4fe747d6b53ca9fd81f848',
                'misc/tabledrag.js': '50ebbc8dc949d7cb8d4cc5e6e0a6c1ca',
                'misc/tableheader.js': '570b3f821441cd8f75395224fc43a0ea'
            }
        }

        self.v.update(add_versions)

        highest = self.v.highest_version_major()

        assert highest['6'] == '6.33'
        assert highest['7'] == '7.31'