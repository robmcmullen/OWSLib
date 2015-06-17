# -*- coding: ISO-8859-15 -*-
# =============================================================================
# Copyright (c) 2004, 2006 Sean C. Gillies
# Copyright (c) 2007 STFC <http://www.stfc.ac.uk>
#
# Authors : 
#          Dominic Lowe <d.lowe@rl.ac.uk>
#
# Contact email: d.lowe@rl.ac.uk
# =============================================================================

from __future__ import (absolute_import, division, print_function)

from urllib import urlencode
from urllib2 import urlopen, Request
from bcube_owslib.etree import etree
import cgi
from StringIO import StringIO
from bcube_owslib.namespaces import Namespaces
from bcube_owslib.utils import testXMLValue, xmltag_split, nspath_eval


class ServiceException(Exception):
    """WCS ServiceException

    Attributes:
        message -- short error message
        xml  -- full xml error message from server
    """

    def __init__(self, message, xml):
        self.message = message
        self.xml = xml

    def __str__(self):
        return repr(self.message)

class WCSBase(object):
    """Base class to be subclassed by version dependent WCS classes. Provides 'high-level' version independent methods"""
    def __new__(self,url, xml, cookies):
        """ overridden __new__ method 
        
        @type url: string
        @param url: url of WCS capabilities document
        @type xml: string
        @param xml: elementtree object
        @return: inititalised WCSBase object
        """
        obj=object.__new__(self)
        obj.__init__(url, xml, cookies)
        self.cookies=cookies
        self._describeCoverage = {} #cache for DescribeCoverage responses
        return obj
    
    def __init__(self):
        pass    

    def getDescribeCoverage(self, identifier):
        ''' returns a describe coverage document - checks the internal cache to see if it has been fetched before '''
        if identifier not in self._describeCoverage.keys():
            reader = DescribeCoverageReader(self.version, identifier, self.cookies)
            self._describeCoverage[identifier] = reader.read(self.url)
        return self._describeCoverage[identifier]


class WCSCapabilitiesReader(object):
    """Read and parses WCS capabilities document into a lxml.etree infoset
    """

    def __init__(self, version=None, cookies = None):
        """Initialize
        @type version: string
        @param version: WCS Version parameter e.g '1.0.0'
        """
        self.version = version
        self._infoset = None
        self.cookies = cookies

    def capabilities_url(self, service_url):
        """Return a capabilities url
        @type service_url: string
        @param service_url: base url of WCS service
        @rtype: string
        @return: getCapabilities URL
        """
        qs = []
        if service_url.find('?') != -1:
            qs = cgi.parse_qsl(service_url.split('?')[1])

        params = [x[0] for x in qs]

        if 'service' not in params:
            qs.append(('service', 'WCS'))
        if 'request' not in params:
            qs.append(('request', 'GetCapabilities'))
        if ('version' not in params) and (self.version is not None):
            qs.append(('version', self.version))

        urlqs = urlencode(tuple(qs))
        return service_url.split('?')[0] + '?' + urlqs

    def read(self, service_url, timeout=30):
        """Get and parse a WCS capabilities document, returning an
        elementtree tree

        @type service_url: string
        @param service_url: The base url, to which is appended the service,
        version, and request parameters
        @rtype: elementtree tree
        @return: An elementtree tree representation of the capabilities document
        """
        request = self.capabilities_url(service_url)
        req = Request(request)
        if self.cookies is not None:
            req.add_header('Cookie', self.cookies)
        u = urlopen(req, timeout=timeout)
        return etree.fromstring(u.read())

    def readString(self, st):
        """Parse a WCS capabilities document, returning an
        instance of WCSCapabilitiesInfoset
        string should be an XML capabilities document
        """
        if not isinstance(st, str):
            raise ValueError("String must be of type string, not %s" % type(st))
        return etree.fromstring(st)


class DescribeCoverageReader(object):
    """Read and parses WCS DescribeCoverage document into a lxml.etree infoset
    """
    def __init__(self, version, identifier, cookies, xml=None):
        """Initialize
        @type version: string
        @param version: WCS Version parameter e.g '1.0.0'
        """
        self.version = version
        self._infoset = None
        self.identifier = identifier
        self.cookies = cookies
        self.xml = xml

        n = Namespaces()
        self.namespaces = n.get_namespaces(['wcs', 'gml'])

        self.read('')
        self.parse_description()

    def descCov_url(self, service_url):
        """Return a describe coverage url
        @type service_url: string
        @param service_url: base url of WCS service
        @rtype: string
        @return: getCapabilities URL
        """
        qs = []
        if service_url.find('?') != -1:
            qs = cgi.parse_qsl(service_url.split('?')[1])

        params = [x[0] for x in qs]

        if 'service' not in params:
            qs.append(('service', 'WCS'))
        if 'request' not in params:
            # TODO: this will keep a GetCapabilities request value
            #       and execute it INCORRECTLY given the class we're in
            qs.append(('request', 'DescribeCoverage'))
        if 'version' not in params:
            qs.append(('version', self.version))
        if self.version == '1.0.0':
            if 'coverage' not in params:
                qs.append(('coverage', self.identifier))
        elif self.version == '1.1.0':
            # NOTE: WCS 1.1.0 is ambigous about whether it should be identifier
            # or identifiers (see tables 9, 10 of specification)
            if 'identifiers' not in params:
                qs.append(('identifiers', self.identifier))
            if 'identifier' not in params:
                qs.append(('identifier', self.identifier))
                qs.append(('format', 'text/xml'))
        urlqs = urlencode(tuple(qs))
        return service_url.split('?')[0] + '?' + urlqs

    def read(self, service_url, timeout=30):
        """Get and parse a Describe Coverage document, returning an
        elementtree tree

        @type service_url: string
        @param service_url: The base url, to which is appended the service,
        version, and request parameters
        @rtype: elementtree tree
        @return: An elementtree tree representation of the capabilities document
        """
        if self.xml is None:
            # make a request
            request = self.descCov_url(service_url)
            req = Request(request)
            if self.cookies is not None:
                req.add_header('Cookie', self.cookies)
            u = urlopen(req, timeout=timeout)
            self.xml = u.read()
        self.xml = etree.fromstring(self.xml)

    def parse_description(self):
        '''
        parse the xml
        '''
        if self.xml is None:
            return None

        # for the version 1x
        self.coverages = []
        for coverage in self.xml.findall(nspath_eval('wcs:CoverageOffering', self.namespaces)):
            coverage_offering = CoverageOffering(coverage)
            self.coverages.append(coverage_offering)


class CoverageOffering(object):
    # note: currently for 1.x only
    def __init__(self, elem):
        n = Namespaces()
        self.namespaces = n.get_namespaces(['wcs', 'gml'])
        # let's go get some stuff
        self.description = testXMLValue(elem.find(nspath_eval('wcs:description', self.namespaces)))
        self.name = testXMLValue(elem.find(nspath_eval('wcs:name', self.namespaces)))
        self.label = testXMLValue(elem.find(nspath_eval('wcs:label', self.namespaces)))

        # main bbox
        envelope = elem.find(nspath_eval('wcs:lonLatEnvelope', self.namespaces))
        self.min_pos, self.max_pos, self.srs_urn = self._get_envelope(envelope)

        # get the domain set for the temporal extents(s)
        domain_set = elem.find(nspath_eval('wcs:domainSet', self.namespaces))
        if domain_set is not None:
            self.spatial_domain = {}
            spatial_domain = domain_set.find(nspath_eval('wcs:spatialDomain', self.namespaces))
            if spatial_domain is not None:
                envelope = spatial_domain.find(nspath_eval('gml:Envelope', self.namespaces))
                min_pos, max_pos, srs_urn = self._get_envelope(envelope)

                self.spatial_domain['envelope'] = {
                    "min_pos": min_pos,
                    "max_pos": max_pos,
                    "srs_urn": srs_urn
                }
                grid = spatial_domain.find(nspath_eval('gml:Grid', self.namespaces))
                # TODO: i am not really sure what to do with the grid re: ontology
                self.spatial_domain['grid'] = {}

            temporal_domain = domain_set.find(nspath_eval('wcs:temporalDomain', self.namespaces))
            self.temporal_domain = {}
            if temporal_domain is not None:
                time_period = temporal_domain.find(nspath_eval('wcs:timePeriod', self.namespaces))
                self.temporal_domain['begin_position'] = testXMLValue(
                    time_period.find(nspath_eval('wcs:beginPosition', self.namespaces)))
                self.temporal_domain['end_position'] = testXMLValue(
                    time_period.find(nspath_eval('wcs:endPosition', self.namespaces)))

            self.rangesets = []
            rangesets = elem.findall(nspath_eval('wcs:rangeSet/wcs:RangeSet', self.namespaces))
            for rangeset in rangesets:
                pass

            supported_crs = elem.find(nspath_eval('wcs:supportedCRSs', self.namespaces))
            self.supported_crs = {}
            for child in supported_crs.iterchildren():
                # get the tag (kind of support) and the value
                self.supported_crs[xmltag_split(child.tag)] = child.text.strip()

            supported_formats = elem.find(nspath_eval('wcs:supportedFormats', self.namespaces))
            self.supported_formats = []
            self.supported_formats.append(supported_formats.get('nativeFormat'))
            for child in supported_formats.iterchildren():
                self.supported_formats.append(child.text.strip())
            self.supported_formats = list(set(self.supported_formats))

            supported_interpolations = elem.find(
                nspath_eval('wcs:supportedInterpolations', self.namespaces))
            self.supported_interpolations = []
            self.supported_interpolations.append(supported_interpolations.get('default'))
            for child in supported_interpolations.iterchildren():
                self.supported_interpolations.append(child.text.strip())
            self.supported_interpolations = list(set(self.supported_interpolations))

    def _get_envelope(self, envelope):
        srs_urn = envelope.attrib.get('srsName', '')
        min_pos = testXMLValue(envelope.find(nspath_eval('gml:pos', self.namespaces)))
        max_pos = testXMLValue(envelope.find(nspath_eval('gml:pos', self.namespaces)))
        return min_pos, max_pos, srs_urn
