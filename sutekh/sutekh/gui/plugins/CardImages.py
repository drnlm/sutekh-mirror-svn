# -*- coding: utf-8 -*-
# vim:fileencoding=utf-8 ai ts=4 sts=4 et sw=4
# Copyright 2008 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""Adds a frame which will display card images from ARDB in the GUI"""

import os
import logging

import gtk
from sqlobject import SQLObjectNotFound

from sutekh.base.core.BaseObjects import IExpansion
from sutekh.base.gui.SutekhDialog import do_complaint_error
from sutekh.base.Utility import ensure_dir_exists
from sutekh.base.gui.plugins.BaseImages import (BaseImageFrame,
                                                BaseImageConfigDialog,
                                                BaseImagePlugin,
                                                check_file, unaccent,
                                                CARD_IMAGE_PATH,
                                                DOWNLOAD_IMAGES,
                                                DOWNLOAD_EXPANSIONS)

from sutekh.gui.PluginManager import SutekhPlugin
from sutekh.SutekhInfo import SutekhInfo

# Base url for downloading the images from
SUTEKH_IMAGE_SITE = 'https://sutekh.vtes.za.net'


class CardImageFrame(BaseImageFrame):
    # pylint: disable=R0904, R0902
    # R0904 - can't not trigger these warning with pygtk
    # R0902 - we need to keep quite a lot of internal state
    """Frame which displays the image.

       Adds the VtES specific handling.
       """

    APP_NAME = SutekhInfo.NAME

    # Cloudflare doesn't like the urllib2 default
    _dReqHeaders = {
        'User-Agent': 'Sutekh Image Plugin'
    }

    def _have_expansions(self, sTestPath=''):
        """Test if directory contains expansion/image structure used by ARDB"""
        # Config, if set to download, overrides the current state
        oConfig = self._config_download_expansions()
        if oConfig is not None:
            return oConfig
        # Config isn't set for downloads, so check the current state
        if sTestPath == '':
            sTestFile = os.path.join(self._sPrefsPath, 'bh', 'acrobatics.jpg')
        else:
            sTestFile = os.path.join(sTestPath, 'bh', 'acrobatics.jpg')
        return check_file(sTestFile)

    def _check_test_file(self, sTestPath=''):
        """Test if acrobatics.jpg exists"""
        # If we're configured to download images, we assume everythings
        # kosher, since we check that the directory exists when configuring
        # things
        if self._config_download_images():
            return True
        # Downloads not set, so the state on disk matters
        if sTestPath == '':
            sTestFile = os.path.join(self._sPrefsPath, 'acrobatics.jpg')
        else:
            sTestFile = os.path.join(sTestPath, 'acrobatics.jpg')
        return check_file(sTestFile)

    def _convert_expansion(self, sExpansionName):
        """Convert the Full Expansion name into the abbreviation needed."""
        if sExpansionName == '':
            return ''
        # pylint: disable=E1101
        # pylint doesn't pick up IExpansion methods correctly
        try:
            oExpansion = IExpansion(sExpansionName)
        except SQLObjectNotFound:
            # This can happen because we cache the expansion name and
            # a new database import may cause that to vanish.
            # We return just return a blank path segment, as the safest choice
            logging.warn('Expansion %s no longer found in the database',
                         sExpansionName)
            return ''
        # special case Anarchs and alastors due to promo hack shortname
        if oExpansion.name == 'Anarchs and Alastors Storyline':
            sExpName = oExpansion.name.lower()
        else:
            sExpName = oExpansion.shortname.lower()
        # Normalise for storyline cards
        sExpName = sExpName.replace(' ', '_').replace("'", '')
        return sExpName

    def _make_card_urls(self, _sFullFilename):
        """Return a url pointing to the scan of the image"""
        sFilename = self._norm_cardname(self._sCardName)[0]
        if sFilename == '':
            # Error out - we don't know where to look
            return None
        if self._bShowExpansions:
            # Only try download the current expansion
            aUrlExps = [self._convert_expansion(self._sCurExpansion)]
        else:
            # Try all the expansions, latest to oldest
            aUrlExps = [self._convert_expansion(x) for x in self._aExpansions]
        aUrls = []
        for sCurExpansionPath in aUrlExps:
            if sCurExpansionPath == '':
                # Error path, we don't know where to search for the image
                return None
            sUrl = '%s/cardimages/%s/%s' % (SUTEKH_IMAGE_SITE,
                                            sCurExpansionPath,
                                            sFilename)
            aUrls.append(sUrl)
        return aUrls

    def _norm_cardname(self, sCardName):
        """Normalise the card name"""
        sFilename = unaccent(sCardName)
        if sFilename.startswith('the '):
            sFilename = sFilename[4:] + 'the'
        elif sFilename.startswith('an '):
            sFilename = sFilename[3:] + 'an'
        sFilename = sFilename.replace('(advanced)', 'adv')
        # Should probably do this via translate
        for sChar in (" ", ".", ",", "'", "(", ")", "-", ":", "!", '"', "/"):
            sFilename = sFilename.replace(sChar, '')
        sFilename = sFilename + '.jpg'
        return [sFilename]


class ImageConfigDialog(BaseImageConfigDialog):
    # pylint: disable=R0904
    # R0904 - gtk Widget, so has many public methods
    """Dialog for configuring the Image plugin."""

    # These two are descriptive, so set them to the final value
    sDefUrlId = 'sutekh.vtes.za.net'
    sImgDownloadSite = 'sutekh.vtes.za.net'
    # Will be changed later
    sDefaultUrl = '%s/zipped/%s' % (SUTEKH_IMAGE_SITE, 'cardimages.zip')

    def __init__(self, oImagePlugin, bFirstTime=False, bDownloadUpgrade=False):
        super(ImageConfigDialog, self).__init__(oImagePlugin, bFirstTime)
        # This is a bit horrible, but we stick the download upgrade logic
        # here, rather than cluttering up the generic ConfigDialog with
        # this entirely Sutekh specific logic
        if bDownloadUpgrade:
            # pylint: disable=E1101
            # pylint doesn't pick up vbox methods correctly
            # Clear the dialog vbox and start again
            self.vbox.remove(self.oDescLabel)
            self.vbox.remove(self.oChoice)
            self.vbox.remove(self.oDownload)
            self.oDescLabel.set_markup('<b>Choose how to configure the '
                                       'cardimages plugin</b>\n'
                                       'The card images plugin can now '
                                       'download missing images from '
                                       'sutekh.vtes.za.net.\nDo you wish to '
                                       'enable this (you will not be prompted '
                                       'again)?')
            self.vbox.pack_start(self.oDescLabel, False, False)
            self.vbox.pack_start(self.oDownload, False, False)
            self.set_size_request(400, 200)
            self.show_all()


class CardImagePlugin(SutekhPlugin, BaseImagePlugin):
    """Plugin providing access to CardImageFrame."""

    DOWNLOAD_SUPPORTED = True

    _cImageFrame = CardImageFrame

    @classmethod
    def update_config(cls):
        super(CardImagePlugin, cls).update_config()
        # We default to download expansions is true, since that matches
        # the zip file we provide from sutekh.vtes.za.net
        cls.dGlobalConfig[DOWNLOAD_EXPANSIONS] = 'boolean(default=True)'

    def setup(self):
        """Prompt the user to download/setup images the first time"""
        sPrefsPath = self.get_config_item(CARD_IMAGE_PATH)
        if not os.path.exists(sPrefsPath):
            # Looks like the first time
            oDialog = ImageConfigDialog(self, True, False)
            self.handle_response(oDialog)
            # Path may have been changed, so we need to requery config file
            sPrefsPath = self.get_config_item(CARD_IMAGE_PATH)
            # Don't get called next time
            ensure_dir_exists(sPrefsPath)
        else:
            oDownloadImages = self.get_config_item(DOWNLOAD_IMAGES)
            if oDownloadImages is None:
                # Doesn't look like we've asked this question
                oDialog = ImageConfigDialog(self, False, True)
                # Default to false
                self.set_config_item(DOWNLOAD_IMAGES, False)
                self.handle_response(oDialog)

    def config_activate(self, _oMenuWidget):
        """Configure the plugin dialog."""
        oDialog = ImageConfigDialog(self, False, False)
        self.handle_response(oDialog)

    def handle_response(self, oDialog):
        """Handle the response from the config dialog"""
        iResponse = oDialog.run()
        if iResponse == gtk.RESPONSE_OK:
            oFile, bDir, bDownload, bDownloadExpansions = oDialog.get_data()
            if bDir:
                # New directory
                if self._accept_path(oFile):
                    # Update preferences
                    self.image_frame.update_config_path(oFile)
                    self._activate_menu()
            elif oFile:
                if self._unzip_file(oFile):
                    self._activate_menu()
                else:
                    do_complaint_error('Unable to successfully unzip data')
                oFile.close()  # clean up temp file
            else:
                # Unable to get data
                do_complaint_error('Unable to configure card images plugin')
            # Update download option
            self.set_config_item(DOWNLOAD_IMAGES, bDownload)
            self.set_config_item(DOWNLOAD_EXPANSIONS, bDownloadExpansions)
            # Reset expansions settings if needed
            self.image_frame.check_images()
        # get rid of the dialog
        oDialog.destroy()


plugin = CardImagePlugin
