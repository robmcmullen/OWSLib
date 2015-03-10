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

from .wcsBase import WCSBase, WCSCapabilitiesReader, ServiceException
from owslib.util import openURL, testXMLValue
from urllib import urlencode
from owslib.crs import Crs

import logging
from owslib.util import log


def ns(tags):
    """go by the tag name, no namspaces for future/version-proofing
    """
    return '/'.join(['*[local-name()="%s"]' % t for t in tags.split('/') if t])


def find(elem, xpath):
    """assumes one element to return
    """
    return next(iter(elem.xpath(xpath)), None)


def findall(elem, xpath):
    return elem.xpath(xpath)


class WebCoverageService_1_1_x(WCSBase):
    """Abstraction for OGC Web Coverage Service (WCS), version 1.1.0
    Implements IWebCoverageService.
    """

    def __getitem__(self, name):
        ''' check contents dictionary to allow dict like access to service layers'''
        if name in self.__getattribute__('contents').keys():
            return self.__getattribute__('contents')[name]
        else:
            raise KeyError("No content named %s" % name)

    def __init__(self, url, xml=None, cookies=None, version='1.1.0'):
        self.version = version
        self.url = url
        self.cookies = cookies
        # initialize from saved capability document or access the server
        reader = WCSCapabilitiesReader(self.version)
        if xml:
            self._capabilities = reader.readString(xml)
        else:
            self._capabilities = reader.read(self.url)

        # check for exceptions
        se = find(self._capabilities, ns("Exception"))

        if se is not None:
            err_message = str(se.text).strip()
            raise ServiceException(err_message, xml)

        # build metadata objects:

        # serviceIdentification metadata
        elem = find(self._capabilities, ns('ServiceIdentification'))
        if elem is None:
            elem = find(self._capabilities, ns('ServiceIdentification'))
        self.identification = ServiceIdentification(elem)

        # serviceProvider
        elem = find(self._capabilities, ns('ServiceProvider'))
        self.provider = ServiceProvider(elem)

        # serviceOperations
        self.operations = []
        for elem in findall(self._capabilities, ns('OperationsMetadata/Operation')):
            self.operations.append(Operation(elem))

        # exceptions - ***********TO DO *************
            self.exceptions = [f.text for f
                               in findall(self._capabilities, ns('Capability/Exception/Format'))]

        # serviceContents: our assumption is that services use a top-level layer
        # as a metadata organizer, nothing more.
        self.contents = {}
        top = find(self._capabilities, ns('Contents/CoverageSummary'))
        for elem in findall(self._capabilities, ns('Contents/CoverageSummary/CoverageSummary')):
            cm = ContentMetadata(elem, top, self)
            self.contents[cm.id] = cm

        if self.contents == {}:
            # non-hierarchical.
            top = None
            for elem in findall(self._capabilities, ns('Contents/CoverageSummary')):
                cm = ContentMetadata(elem, top, self)
                # make the describeCoverage requests to
                # populate the supported formats/crs attributes
                self.contents[cm.id] = cm

    def items(self):
        '''supports dict-like items() access'''
        items = []
        for item in self.contents:
            items.append((item, self.contents[item]))
        return items


    #TO DO: Handle rest of the  WCS 1.1.0 keyword parameters e.g. GridCRS etc. 
    def getCoverage(self, identifier=None, bbox=None, time=None, format = None, store=False, rangesubset=None, gridbaseCRS=None, gridtype=None, gridCS=None, gridorigin=None, gridoffsets=None, method='Get',**kwargs):
        """Request and return a coverage from the WCS as a file-like object
        note: additional **kwargs helps with multi-version implementation
        core keyword arguments should be supported cross version
        example:
        cvg=wcs.getCoverageRequest(identifier=['TuMYrRQ4'], time=['2792-06-01T00:00:00.0'], bbox=(-112,36,-106,41),format='application/netcdf', store='true')

        is equivalent to:
        http://myhost/mywcs?SERVICE=WCS&REQUEST=GetCoverage&IDENTIFIER=TuMYrRQ4&VERSION=1.1.0&BOUNDINGBOX=-180,-90,180,90&TIMESEQUENCE=2792-06-01T00:00:00.0&FORMAT=application/netcdf
        
        if store = true, returns a coverages XML file
        if store = false, returns a multipart mime
        """
        if log.isEnabledFor(logging.DEBUG):
            log.debug('WCS 1.1.0 DEBUG: Parameters passed to GetCoverage: identifier=%s, bbox=%s, time=%s, format=%s, rangesubset=%s, gridbaseCRS=%s, gridtype=%s, gridCS=%s, gridorigin=%s, gridoffsets=%s, method=%s, other_arguments=%s'%(identifier, bbox, time, format, rangesubset, gridbaseCRS, gridtype, gridCS, gridorigin, gridoffsets, method, str(kwargs)))
        
        if method == 'Get':
            method='{http://www.opengis.net/wcs/1.1/ows}Get'
        try:
            base_url = next((m.get('url') for m in self.getOperationByName('GetCoverage').methods if m.get('type').lower() == method.lower()))
        except StopIteration:
            base_url = self.url


        #process kwargs
        request = {'version': self.version, 'request': 'GetCoverage', 'service':'WCS'}
        assert len(identifier) > 0
        request['identifier']=identifier
        #request['identifier'] = ','.join(identifier)
        if bbox:
            request['boundingbox']=','.join([repr(x) for x in bbox])
        if time:
            request['timesequence']=','.join(time)
        request['format']=format
        request['store']=store
        
        #rangesubset: untested - require a server implementation
        if rangesubset:
            request['RangeSubset']=rangesubset
        
        #GridCRS structure: untested - require a server implementation
        if gridbaseCRS:
            request['gridbaseCRS']=gridbaseCRS
        if gridtype:
            request['gridtype']=gridtype
        if gridCS:
            request['gridCS']=gridCS
        if gridorigin:
            request['gridorigin']=gridorigin
        if gridoffsets:
            request['gridoffsets']=gridoffsets
       
       #anything else e.g. vendor specific parameters must go through kwargs
        if kwargs:
            for kw in kwargs:
                request[kw]=kwargs[kw]
        
        #encode and request
        data = urlencode(request)
        
        u=openURL(base_url, data, method, self.cookies)
        return u

    def getOperationByName(self, name):
        """Return a named operation item."""
        for item in self.operations:
            if item.name == name:
                return item
        raise KeyError("No operation named %s" % name)


class Operation(object):
    """Abstraction for operation metadata
    Implements IOperationMetadata.
    """
    def __init__(self, elem):
        self.name = elem.get('name')
        self.formatOptions = [f.text for f in findall(elem, ns('Parameter/AllowedValues/Value'))]
        methods = []
        for verb in findall(elem, ns('DCP/HTTP/*')):
            url = verb.attrib['{http://www.w3.org/1999/xlink}href']
            methods.append((verb.tag, {'url': url}))
        self.methods = dict(methods)

        # for the parameters
        parameters = []
        for parameter in findall(elem, ns('Parameter')):
            parameters.append(
                {
                    parameter.attrib['name']: {'values': [i.text for i in findall(parameter,
                                                          ns('AllowedValues/Value'))]}
                }
            )

        self.parameters = parameters

        # for the constraints, to match the parameter values
        self.constraints = []
        for constraint in findall(elem, ns('Constraint')):
            # let's just make that an or?
            cxp = ns('AllowedValues/Values') + ' | ' + ns('Values')
            self.constraints.append({
                constraint.attrib.get('name'): {
                    "values": [i.text for i in findall(constraint, cxp)]
                }
            })


class ServiceIdentification(object):
    """ Abstraction for ServiceIdentification Metadata
    implements IServiceIdentificationMetadata"""
    def __init__(self, elem):
        self.service = "WCS"
        # TODO: fix this
        self.version = "1.1.0"
        self.title = testXMLValue(find(elem, ns('Title')))
        self.abstract = testXMLValue(find(elem, ns('Abstract')))
        self.keywords = [f.text for f in findall(elem, ns('Keywords/Keyword'))]

        self.fees = testXMLValue(find(elem, ns('Fees')))

        self.accessConstraints = testXMLValue(find(elem, ns('AccessConstraints')))


class ServiceProvider(object):
    """ Abstraction for ServiceProvider metadata 
    implements IServiceProviderMetadata """
    def __init__(self,elem):
        name=elem.find('{http://www.opengis.net/ows}ProviderName')
        if name is not None:
            self.name=name.text
        else:
            self.name=None
        #self.contact=ServiceContact(elem.find('{http://www.opengis.net/ows}ServiceContact'))
        self.contact =ContactMetadata(elem)
        self.url=self.name # no obvious definitive place for url in wcs, repeat provider name?


class ContactMetadata(object):
    ''' implements IContactMetadata'''
    def __init__(self, elem):
        self.name = testXMLValue(find(elem, ns('ServiceContact/IndividualName')))

        self.organization = testXMLValue(find(elem, ns('ProviderName')))

        self.address = testXMLValue(find(elem,
                                    ns('ServiceContact/ContactInfo/Address/DeliveryPoint')))

        self.city = testXMLValue(find(elem, ns('ServiceContact/ContactInfo/Address/City')))

        self.region = testXMLValue(find(elem,
                                   ns('ServiceContact/ContactInfo/Address/AdministrativeArea')))

        self.postcode = testXMLValue(find(elem,
                                     ns('ServiceContact/ContactInfo/Address/PostalCode')))

        self.country = testXMLValue(find(elem, ns('ServiceContact/ContactInfo/Address/Country')))

        self.email = testXMLValue(find(elem,
                                  ns('ServiceContact/ContactInfo/Address/ElectronicMailAddress')))


class ContentMetadata(object):
    """Abstraction for WCS ContentMetadata
    Implements IContentMetadata
    """
    def __init__(self, elem, parent, service):
        """Initialize."""
        # TODO - examine the parent for bounding box info.
        
        self._service=service
        self._elem=elem
        self._parent=parent
        self.id=self._checkChildAndParent('{http://www.opengis.net/wcs/1.1}Identifier')
        self.description =self._checkChildAndParent('{http://www.opengis.net/wcs/1.1}Description')           
        self.title =self._checkChildAndParent('{http://www.opengis.net/ows}Title')
        self.abstract =self._checkChildAndParent('{http://www.opengis.net/ows}Abstract')
        
        #keywords.
        self.keywords=[]
        for kw in elem.findall('{http://www.opengis.net/ows}Keywords/{http://www.opengis.net/ows}Keyword'):
            if kw is not None:
                self.keywords.append(kw.text)
        
        #also inherit any keywords from parent coverage summary (if there is one)
        if parent is not None:
            for kw in parent.findall('{http://www.opengis.net/ows}Keywords/{http://www.opengis.net/ows}Keyword'):
                if kw is not None:
                    self.keywords.append(kw.text)
            
        self.boundingBox=None #needed for iContentMetadata harmonisation
        self.boundingBoxWGS84 = None
        b = elem.find('{http://www.opengis.net/ows}WGS84BoundingBox')
        if b is not None:
            lc=b.find('{http://www.opengis.net/ows}LowerCorner').text
            uc=b.find('{http://www.opengis.net/ows}UpperCorner').text
            self.boundingBoxWGS84 = (
                    float(lc.split()[0]),float(lc.split()[1]),
                    float(uc.split()[0]), float(uc.split()[1]),
                    )
                
        # bboxes - other CRS 
        self.boundingboxes = []
        for bbox in elem.findall('{http://www.opengis.net/ows}BoundingBox'):
            if bbox is not None:
                try:
                    lc=b.find('{http://www.opengis.net/ows}LowerCorner').text
                    uc=b.find('{http://www.opengis.net/ows}UpperCorner').text
                    boundingBox =  (
                            float(lc.split()[0]),float(lc.split()[1]),
                            float(uc.split()[0]), float(uc.split()[1]),
                            b.attrib['crs'])
                    self.boundingboxes.append(boundingBox)
                except:
                     pass

        #others not used but needed for iContentMetadata harmonisation
        self.styles=None
        self.crsOptions=None
                
        #SupportedCRS
        self.supportedCRS=[]
        for crs in elem.findall('{http://www.opengis.net/wcs/1.1}SupportedCRS'):
            self.supportedCRS.append(Crs(crs.text))
            
            
        #SupportedFormats         
        self.supportedFormats=[]
        for format in elem.findall('{http://www.opengis.net/wcs/1.1}SupportedFormat'):
            self.supportedFormats.append(format.text)
            
    #grid is either a gml:Grid or a gml:RectifiedGrid if supplied as part of the DescribeCoverage response.
    def _getGrid(self):
        grid=None
        #TODO- convert this to 1.1 from 1.0
        #if not hasattr(self, 'descCov'):
                #self.descCov=self._service.getDescribeCoverage(self.id)
        #gridelem= self.descCov.find(ns('CoverageOffering/')+ns('domainSet/')+ns('spatialDomain/')+'{http://www.opengis.net/gml}RectifiedGrid')
        #if gridelem is not None:
            #grid=RectifiedGrid(gridelem)
        #else:
            #gridelem=self.descCov.find(ns('CoverageOffering/')+ns('domainSet/')+ns('spatialDomain/')+'{http://www.opengis.net/gml}Grid')
            #grid=Grid(gridelem)
        return grid
    grid=property(_getGrid, None)
        
        
        
    #time limits/postions require a describeCoverage request therefore only resolve when requested
    def _getTimeLimits(self):
         timelimits=[]
         for elem in self._service.getDescribeCoverage(self.id).findall(ns('CoverageDescription/')+ns('Domain/')+ns('TemporalDomain/')+ns('TimePeriod/')):
             subelems=elem.getchildren()
             timelimits=[subelems[0].text,subelems[1].text]
         return timelimits
    timelimits=property(_getTimeLimits, None)
    
    #TODO timepositions property
    def _getTimePositions(self):
        return []
    timepositions=property(_getTimePositions, None)
    
    def _checkChildAndParent(self, path):
        ''' checks child coverage  summary, and if item not found checks higher level coverage summary'''
        try:
            value = self._elem.find(path).text
        except:
            try:
                value = self._parent.find(path).text
            except:
                value = None
        return value  
