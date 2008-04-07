# AbstractCardSetWriter.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Copyright 2006 Simon Cross <hodgestar@gmail.com>
# Copyright 2006, 2008 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""
Write cards from a AbstractCardSet out to an XML file which
looks like:
<abstractcardset sutekh_xml_version='1.1' name='AbstractCardSetName'
      author='Author' comment='Comment' >
  <annotations> Various annotations
  More annotations
  </annotations>
  <card id='3' name='Some Card' count='5' />
  <card id='5' name='Some Other Card' count='2' />
</abstractcardset>
"""

from sutekh.core.SutekhObjects import AbstractCardSet
from sqlobject import SQLObjectNotFound
from sutekh.SutekhUtility import pretty_xml
try:
    # pylint: disable-msg=E0611, F0401
    # xml.etree is a python2.5 thing
    from xml.etree.ElementTree import Element, SubElement, ElementTree, \
            tostring
except ImportError:
    from elementtree.ElementTree import Element, SubElement, ElementTree, \
            tostring

class AbstractCardSetWriter(object):
    """Writer for Abstract Card Sets.

       We generate an ElementTree representation of the Card Set, which
       can then easily be converted to an appropriate XML representation.
       """
    sMyVersion = "1.1"

    def make_tree(self, sAbstractCardSetName):
        """Convert the card set sAbstractCardSetName to an ElementTree."""
        dCards = {}
        try:
            # pylint: disable-msg=E1101
            # SQLObject confuses pylint
            oACS = AbstractCardSet.byName(sAbstractCardSetName)
        except SQLObjectNotFound:
            raise RuntimeError('Unable to find card set %s' %
                    sAbstractCardSetName)

        for oAbs in oACS.cards:
            try:
                dCards[(oAbs.id, oAbs.name)] += 1
            except KeyError:
                dCards[(oAbs.id, oAbs.name)] = 1

        oRoot = Element('abstractcardset', sutekh_xml_version=self.sMyVersion,
                author = oACS.author, name=sAbstractCardSetName,
                comment = oACS.comment)

        oAnnotationNode = SubElement(oRoot, 'annotations')
        oAnnotationNode.text = oACS.annotations

        for tKey, iNum in dCards.iteritems():
            iId, sName = tKey
            # pylint: disable-msg=W0612
            # oCardElem is just created in the tree
            oCardElem = SubElement(oRoot, 'card', id=str(iId), name=sName,
                    count=str(iNum))
        return oRoot

    def gen_xml_string(self, sAbstractCardSetName):
        """Generate a string containing the XML output."""
        oRoot = self.make_tree(sAbstractCardSetName)
        return tostring(oRoot)

    def write(self, fOut, sAbstractCardSetName):
        """Generate prettier XML and write it to the file fOut."""
        oRoot = self.make_tree(sAbstractCardSetName)
        pretty_xml(oRoot)
        ElementTree(oRoot).write(fOut)
