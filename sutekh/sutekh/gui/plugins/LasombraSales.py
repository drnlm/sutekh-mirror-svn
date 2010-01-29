# LasombraSales.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Copyright 2009 Simon Cross <hodgestar@gmail.com>
# GPL - see COPYING for details
"""Display Lasombra single card prices in extra columns in the tree view"""

import gtk
import gobject
import xlrd
import zipfile
import os
import re
import cPickle
import cgi
from cStringIO import StringIO
from sqlobject import SQLObjectNotFound
from sutekh.gui.PluginManager import SutekhPlugin
from sutekh.gui.SutekhDialog import SutekhDialog, do_complaint_error
from sutekh.gui.CellRendererIcons import CellRendererIcons, SHOW_TEXT_ONLY
from sutekh.gui.CardListModel import CardListModel, CardListModelListener
from sutekh.gui.FileOrUrlWidget import FileOrUrlWidget
from sutekh.gui.AutoScrolledWindow import AutoScrolledWindow
from sutekh.core.SutekhObjects import PhysicalCard, PhysicalCardSet, \
        IExpansion, IAbstractCard
from sutekh.SutekhUtility import prefs_dir, ensure_dir_exists


SORT_COLUMN_OFFSET = 200 # ensure we don't clash with other extra columns

TOOLPRICE_FORMAT = 'Tot: $%(tot).2f  Unknown: %(unknown)d'
TOOLPRICE_TOOLTIP = 'Total cost: $%(tot).2f Cards with unknown price:' \
        ' %(unknown)d'

# pylint: disable-msg=R0904
# R0904 - gtk Widget, so has many public methods
class LasombraConfigDialog(SutekhDialog):
    """Dialog for configuring the LasombraSales plugin."""

    INVENTORY_URL = "http://www.thelasombra.com/inventory.zip"

    def __init__(self, oParent, bFirstTime=False):
        super(LasombraConfigDialog, self).__init__('Configure Lasombra Sales'
                ' Plugin', oParent,
                gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                (gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL,
                    gtk.RESPONSE_CANCEL))

        # pylint: disable-msg=E1101
        # pylint doesn't pick up vbox methods correctly
        self.vbox.set_spacing(10)

        oDescLabel = gtk.Label()
        if not bFirstTime:
            oDescLabel.set_markup('<b>Load the Lasombra '
                'sales inventory</b>')
        else:
            oDescLabel.set_markup('<b>Load the Lasombra '
                'sales inventory</b>\nChoose cancel to skip configuring the '
                'Lasombra sales plugin\nYou will not be prompted again')

        self._oFileSelector = FileOrUrlWidget(oParent,
            dUrls = {
                'www.thelasombra.com': self.INVENTORY_URL,
            },
            sTitle="Select inventory file ...",
        )

        # pylint: disable-msg=E1101
        # pylint doesn't pick up vbox methods correctly
        self.vbox.pack_start(oDescLabel, False, False)
        self.vbox.pack_start(self._oFileSelector, False, False)

        self.show_all()

    def get_binary_data(self):
        """Return the data for the inventory file."""
        return self._oFileSelector.get_binary_data()


# pylint: disable-msg=R0904
# R0904 - gtk Widget, so has many public methods
class LasombraWarningsDialog(SutekhDialog):
    """Dialog for showing warnings generated by the LasombraSales plugin."""

    def __init__(self, oParent, aWarnings):
        super(LasombraWarningsDialog, self).__init__('Lasombra Sales Plugin'
                ' Warnings', oParent,
                gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                (gtk.STOCK_OK, gtk.RESPONSE_OK))

        # pylint: disable-msg=E1101
        # pylint doesn't pick up vbox methods correctly
        self.vbox.set_spacing(10)
        self.set_size_request(400, 600)

        oDescLabel = gtk.Label()
        oDescLabel.set_markup('<b>Lasombra Sales Plugin Warnings:</b>')

        # Model - (sheet name / row number, message)
        oWarningModel = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING)

        dSheetIters = {}
        for sSheet, iRow, sMsg in aWarnings:
            if sSheet is None:
                sSheet = 'All sheets'

            oSheetIter = dSheetIters.get(sSheet)
            if oSheetIter is None:
                oSheetIter = oWarningModel.append(None)
                oWarningModel.set(oSheetIter,
                    0, '<b>%s</b>' % (cgi.escape(sSheet),))
                dSheetIters[sSheet] = oSheetIter

            if iRow is None:
                oIter = oWarningModel.prepend(oSheetIter)
                oWarningModel.set(oIter, 0, 'All rows',
                                         1, sMsg)
            else:
                oIter = oWarningModel.append(oSheetIter)
                oWarningModel.set(oIter, 0, 'Row %d' % (iRow,),
                                         1, sMsg)

        oWarningTree = gtk.TreeView(oWarningModel)

        oWarningTree.append_column(gtk.TreeViewColumn('Sheet / Row',
            gtk.CellRendererText(), markup=0))
        oWarningTree.append_column(gtk.TreeViewColumn('Message',
            gtk.CellRendererText(), text=1))

        # pylint: disable-msg=E1101
        # pylint doesn't pick up vbox methods correctly
        self.vbox.pack_start(oDescLabel, False, False)
        self.vbox.pack_start(AutoScrolledWindow(oWarningTree), expand=True)

        self.show_all()


class LasombraSales(SutekhPlugin, CardListModelListener):
    """Add singles card sales information as extra columns to the card list
       view and allow sorting on these columns.
       """
    dTableVersions = {}
    aModelsSupported = [PhysicalCardSet, PhysicalCard, "MainWindow"]

    INVENTORY_XLS = "inventory.xls"

    _dWidths = {
            'Price' : 50,
            'Stock' : 50,
            }

    # Lasombra Expansion Name -> WW Expansion Name
    # (used to look up expansions on normal sheets)
    _dExpansionLookup = {
        '3rd Edition Sabbat': 'Third Edition',
        '10th Anniversary Set, broken up.': 'Tenth Anniversary',
        'Anarchs Set': 'Anarchs',
        'Black Hand Set': 'Blackhand',
        'Bloodlines Set': 'Bloodlines',
        'Camarilla Set': 'Camarilla Edition',
        'Ebony Kingdom': 'Ebony Kingdom',
        'Gehenna Set, Rares and Commons': 'Gehenna',
        'Kindred Most Wanted Set': 'Kindred Most Wanted',
        'Keepers of Tradition': 'Keepers of Tradition',
        'Legacies of Blood Set': 'Legacy of Blood',
        'Lords of the Night Set': 'Lords of the Night',
        'Nights of Reckoning Set': 'Nights of Reckoning',
        'Sword of Caine set': 'Sword of Caine',
        'Twilight Rebellion': 'Twilight Rebellion',
    }

    # Lasombra Short Expansion Name -> Preferred Short Name
    # (used for crypt sheet expansion lookup)
    _dShortExpLookup = {
        '3rd': 'Third',
        'S': 'Sabbat',
        'W': 'SW',
        'B': 'BL',
        'V': 'VTES',
        'Camarilla': 'CE',
        'Black Hand': 'BH',
        'F': 'FN',
        'D': 'DS',
        'A': 'AH',
    }

    # (sCardName, sExpansionName) -> (fPrive, iStock)
    # Initialized when module first loaded
    _dPriceCache = None

    # List of warnings generated while populating the cache
    # Initialized when module first loaded
    # _aWarnings is a list of tuples (sheet name, row number, msg)
    # sheet name may be None (indicating all sheets)
    # row number be None (indicating all of the given sheet)
    _aWarnings = None

    # pylint: disable-msg=W0142
    # **magic OK here
    def __init__(self, *aArgs, **kwargs):
        super(LasombraSales, self).__init__(*aArgs, **kwargs)

        self._dCols = {}
        self._bHideZeroCards = False
        self._bTotal = False
        self._oToolbarLabel = None
        self._fTot = 0
        self._iUnknown = 0
        self._dCols['Price'] = self._render_price
        self._dCols['Stock'] = self._render_stock

        self._dSortDataFuncs = {}
        self._dSortDataFuncs['Price'] = self._get_data_price
        self._dSortDataFuncs['Stock'] = self._get_data_stock

        self._sPrefsPath = os.path.join(prefs_dir('Sutekh'), 'lasombra')
        self._sCacheFile = os.path.join(self._sPrefsPath, 'cache.dat')
        self._load_cache()

        # pylint: disable-msg=C0103
        # _get_key name OK here
        if hasattr(self.model, "get_all_names_from_path"):
            self._get_key = self._get_key_for_card_set_list
            self.model.add_listener(self)
        elif hasattr(self.model, "get_all_from_path"):
            self._get_key = self._get_key_for_card_list
            self.model.add_listener(self)
        else:
            # This plugin is also registered on the main window
            self._get_key = None

    def _load_cache(self):
        """Attempt to load the cache from a pickle."""
        if self._dPriceCache is not None:
            return

        if not os.path.exists(self._sCacheFile):
            return

        fIn = file(self._sCacheFile, "rb")

        # pylint: disable-msg=W0703, C0321
        # W0703: we really do want all the exceptions
        # C0321: pylint false positive - see www.logilab.org/ticket/8764
        try:
            try:
                self.__class__._dPriceCache, self.__class__._aWarnings = \
                        cPickle.load(fIn)
            finally:
                fIn.close()
        except Exception, _oExcept:
            if self._aWarnings is None:
                # first time encountering error
                sMsg = "Lasombra Sales plugin cache can't be loaded" \
                    " -- ignoring it. Re-configure the plugin to attempt to" \
                    " correct the problem."
                self.__class__._aWarnings = [(None, None, sMsg)]
                do_complaint_error(sMsg)

    def _initialize_cache(self, fInventory):
        """Initialize the price information from the Lasombra inventory."""
        # might be a zip file, check
        try:
            fZip = zipfile.ZipFile(fInventory, "r")
            aNames = fZip.namelist()
            if self.INVENTORY_XLS in aNames:
                sName = self.INVENTORY_XLS
            elif len(aNames) == 1:
                sName = aNames[0]
            else:
                raise ValueError("Unable to locate inventory spreadsheet"
                            " inside zip file.")
            sData = fZip.read(sName)
        except zipfile.BadZipfile, _oExcept:
            # not a zip file, proceed as if it's a spreadsheet
            # seek is safe because this is a StringIO file.
            fInventory.seek(0)
            sData = fInventory.read()

        self.__class__._dPriceCache = {}
        self.__class__._aWarnings = []

        oBook = xlrd.open_workbook(self.INVENTORY_XLS, file_contents=sData)
        for oSheet in oBook.sheets():
            if oSheet.name == 'Specialty+Boxes':
                # Promos are a very special case, so we handle them seperately
                self._extract_promos(oSheet)
            elif oSheet.name == 'Crypt':
                # The crypt sheet also has its own special format
                self._extract_crypt(oSheet)
            else:
                # Try the default format
                self._extract_default(oSheet)

        fOut = file(self._sCacheFile, "wb")
        try:
            cPickle.dump((self._dPriceCache, self._aWarnings), fOut)
        finally:
            fOut.close()

    def _extract_promos(self, oSheet):
        """Find the start of the promo cards"""
        iStart = 0
        iEnd = 0
        for iNum in range(2, oSheet.nrows):
            oRow = oSheet.row(iNum)
            sVal = oRow[1].value
            sVal.strip()
            if sVal.endswith('Promos'):
                # Success
                iStart = iNum + 2
            elif sVal == 'Description' and iStart > 0 and iNum > iStart:
                # End found
                iEnd = iNum - 2
                break # No need to continue the loop

        if iStart <= 0:
            return

        if iEnd == 0:
            # If we missed the end for some reason
            iEnd = oSheet.nrows

        def get_exp(oAbsCard, _oRow):
            """Retrieve the expansion object for the given card."""
            aCards = PhysicalCard.selectBy(abstractCardID=oAbsCard.id)
            for oCard in aCards:
                if oCard.expansion and oCard.expansion.name.startswith(
                        'Promo'):
                    return oCard.expansion
            # None means no expansion found.
            return None

        tCols = (0, 1, 2, None) # quantity, name, price, rarity
        self._extract_cards(oSheet, iStart, iEnd, fExp=get_exp, tCols=tCols)

    def _extract_crypt(self, oSheet):
        """Extract prices from the crypt sheet."""
        oUnknownExpansions = set()

        def get_exp(_oAbsCard, oRow):
            """Return the expansion for the given row."""
            sShort = str(oRow[5].value).strip()
            sShort = self._dShortExpLookup.get(sShort, sShort)
            # pylint: disable-msg=W0703
            # we really do want all the exceptions
            try:
                oExp = IExpansion(sShort)
            except Exception, _oExcept:
                if sShort not in oUnknownExpansions:
                    sMsg = "Could not map expansion code '%s' to unique" \
                           " expansion (setting expansion to" \
                           " unknown)." % (sShort,)
                    self._aWarnings.append((oSheet.name, None, sMsg))
                    oUnknownExpansions.add(sShort)
                oExp = None
            return oExp

        tCols = (0, 3, 4, 1) # quantity, name, price, rarity
        self._extract_cards(oSheet, 3, oSheet.nrows, fExp=get_exp, tCols=tCols)

    def _extract_default(self, oSheet):
        """Extract prices from the other sheets."""

        oFirstRow = oSheet.row(0)
        # pylint: disable-msg=W0703
        # we really do want all the exceptions
        try:
            sVal = oFirstRow[1].value
            sVal = self._dExpansionLookup[sVal]
            sVal = sVal.strip()
            oExp = IExpansion(sVal)
        except Exception, _oExcept:
            sMsg = "Could not determine expansion for sheet '%s'" \
                    " (skipping sheet)" % (oSheet.name,)
            self._aWarnings.append((oSheet.name, None, sMsg))
            return

        self._extract_cards(oSheet, 3, oSheet.nrows, fExp=lambda oC, oR: oExp)

    # pylint: disable-msg=R0913
    # R0913: We need all these arguments here
    def _extract_cards(self, oSheet, iStart, iEnd, fExp, tCols=(0, 1, 2, 3)):
        """Extract the card info from the cards.

           oSheet - the sheet to extract from
           iStart, iEnd - range of rows to process
           fExp - function fExp(oAbsCard, oRow) -> oExp for
                  obtaining the expansion for a given row and card.
                  fExp should return None if the expansion could not be
                  determined.
           tCols - quantity, name, price and rarity column numbers (default 0, 1, 2, 3).
                   The rarity may be set to None to indicate there is no rarity column.
           """

        # pylint: disable-msg=C0103, R0915
        # C0103: names use the constant convention as they're "psuedo" consts
        # R0915: Function is long, but not much to be gained by splitting it
        QUANTITY, NAME, PRICE, RARITY = tCols

        # Within a given sheet, a card may appear multiple times with different
        # rarity codes. If a given card plus rarity code has already been seen,
        # we check that the stock and price agree with the previous entry [1].
        # If the combination has not been seen before, we add the stock to the
        # existing stock and check that the price is the same [2].
        #
        # [1] This occurs for card printed at multiple rarities within the same
        #     expansion. E.g. Society of Leopold and Ghoul Retainer from KoT.
        #
        # [2] This is the case when a card is available in both the starter
        #     decks (rarity S) and boosters for a particular expansion.
        dPerRarityInfo = {}
        if RARITY is None:
            fGetRarityCode = lambda oRow: None
        else:
            fGetRarityCode = lambda oRow: oRow[RARITY].value

        # regular expression for fixing advance vampire names
        oAdvFixer = re.compile(r"\(adv\)", re.IGNORECASE)

        for iNum in range(iStart, iEnd):
            oRow = oSheet.row(iNum)

            # skip blank rows and some summary lines
            if not (oRow[NAME].value and oRow[QUANTITY].value and
                    oRow[PRICE].value):
                continue

            # pylint: disable-msg=W0703
            # we really do want all the exceptions
            try:
                sCardName = str(oRow[NAME].value)
                iStock = int(oRow[QUANTITY].value)
                fPrice = float(oRow[PRICE].value)
            except Exception, _oExcept:
                sMsg = "Could not read card information (skipping row)"
                self._aWarnings.append((oSheet.name, iNum, sMsg))
                continue

            # Fix advanced vampires
            sCardName = oAdvFixer.sub('(Advanced)', sCardName, 1)

            # Standardise whitespace
            sCardName = " ".join(sCardName.split())

            # pylint: disable-msg=E1101
            # pylint doesn't pick up pyprotocols methods correctly
            try:
                oAbsCard = IAbstractCard(sCardName)
            except SQLObjectNotFound:
                sMsg = "Could not find card '%s'" % (sCardName,)
                self._aWarnings.append((oSheet.name, iNum, sMsg))
                continue

            sCardName = oAbsCard.name

            oExp = fExp(oAbsCard, oRow)
            if oExp is None:
                sExp = CardListModel.sUnknownExpansion
            else:
                sExp = oExp.name

            sRarityCode = fGetRarityCode(oRow)

            tKey = (sCardName, sExp)
            tPerRarityKey = tKey + (sRarityCode,)

            if tPerRarityKey in dPerRarityInfo:
                # skip rarity codes we've seen
                fOldPrice, iOldStock = dPerRarityInfo[tPerRarityKey]
                if (fOldPrice != fPrice) or (iOldStock != iStock):
                    sMsg = "Found duplicate information for card '%s' in" \
                           " expansion '%s' with rarity code '%s' but price" \
                           " and stock do not agree (original price: %.2f;" \
                           " original stock: %d; new price: %.2f;" \
                           " new stock: %d). Keeping old information." \
                           % (sCardName, sExp, sRarityCode, fOldPrice,
                              iOldStock, fPrice, iStock)
                    self._aWarnings.append((oSheet.name, iNum, sMsg))
                continue

            dPerRarityInfo[tPerRarityKey] = (fPrice, iStock)

            if tKey in self._dPriceCache:
                fOldPrice, iOldStock = self._dPriceCache[tKey]
                if fOldPrice != fPrice:
                    sMsg = "Found new rarity code '%s' for card '%s' in" \
                           " expansion '%s' but prices do not agree" \
                           " (old price: %.2f; new price: %.2f). Keeping" \
                           " old price." \
                           % (sRarityCode, sCardName, sExp, fOldPrice, fPrice)
                    self._aWarnings.append((oSheet.name, iNum, sMsg))
                self._dPriceCache[tKey] = (fOldPrice, iStock + iOldStock)
            else:
                self._dPriceCache[tKey] = (fPrice, iStock)

            tKey = (sCardName, None)
            fOverallPrice = self._dPriceCache.get(tKey, (fPrice, 0))[0]
            iOverallStock = self._dPriceCache.get(tKey, (fPrice, 0))[1]
            self._dPriceCache[tKey] = (min(fPrice, fOverallPrice), iStock
                    + iOverallStock)

    # pylint: enable-msg=W0142, R0913

    def _get_key_for_card_list(self, oIter):
        """For the given iterator, get the associated card name and expansion
           name. This tuple is the key used to look up prices and stock numbers
           if the cache.  None is returned for the expansion name if there is
           no relevant expansion.  None is returned as the *key* if there is no
           relevant card.

           This is the key retrieval version for CardListModels.
           """
        sName, sExpansion, _iCount, _iDepth = \
                self.model.get_all_from_iter(oIter)
        if sName is not None:
            # sExpansion may be None.
            return sName, sExpansion
        else:
            return None

    def _get_key_for_card_set_list(self, oIter):
        """For the given iterator, get the associated card name and expansion
           name. This tuple is the key used to look up prices and stock numbers
           if the cache.  None is returned for the expansion name if there is
           no relevant expansion.  None is returned as the *key* if there is no
           relevant card.

           This is the key retrieval version for CardSetListModels.
           """
        sName, sExpansion, _sCardSet = \
                self.model.get_all_names_from_iter(oIter)
        if sName is not None:
            # sExpansion may be None.
            return sName, sExpansion
        else:
            return None

    # Rendering Functions

    # pylint: disable-msg=R0201
    # Making these functions for clarity

    def _get_data_price(self, tKey):
        """get the price for the given key"""
        return self._dPriceCache.get(tKey, (None, None))[0]

    def _render_price(self, _oColumn, oCell, _oModel, oIter):
        """Display the card price."""
        tKey = self._get_key(oIter)
        fPrice = self._get_data_price(tKey)
        if fPrice is None:
            oCell.set_data(["-"], [None], SHOW_TEXT_ONLY)
        else:
            oCell.set_data(["%.2f" % (fPrice,)], [None], SHOW_TEXT_ONLY)

    def _get_data_stock(self, tKey):
        """get the stock for the given key"""
        return self._dPriceCache.get(tKey, (0.0, 0))[1]

    def _render_stock(self, _oColumn, oCell, _oModel, oIter):
        """Display the number of cards available."""
        tKey = self._get_key(oIter)
        iStock = self._get_data_stock(tKey)
        if iStock is None:
            oCell.set_data(["-"], [None], SHOW_TEXT_ONLY)
        else:
            oCell.set_data(["%d" % (iStock,)], [None], SHOW_TEXT_ONLY)

    # pylint: enable-msg=R0201
    # Dialog and Menu Item Creation

    def get_menu_item(self):
        """Register on 'Plugins' menu"""
        if not self.check_versions() or not self.check_model_type():
            return None

        if self.model is not None:
            oSubMenuItem = gtk.MenuItem("Lasombra Singles Sales")
            oSubMenu = gtk.Menu()
            oSubMenuItem.set_submenu(oSubMenu)

            oToggle = gtk.CheckMenuItem("Show Prices")
            oToggle.set_active(False)
            oToggle.connect('toggled', self._toggle_prices)
            oSubMenu.add(oToggle)

            oHide = gtk.CheckMenuItem("Hide cards not listed in the"
                    " Lasombra Inventory")
            oHide.set_active(False)
            oHide.connect('toggled', self._toggle_hide)
            oSubMenu.add(oHide)

            if self._cModelType is PhysicalCardSet:
                oTotal = gtk.CheckMenuItem("Show total cost for card set "
                        "based on the Lasombra Inventory")
                oTotal.set_active(False)
                oTotal.connect('toggled', self._toggle_total)
                oSubMenu.add(oTotal)

            return [('Plugins', oSubMenuItem)]
        else:
            oSubMenuItem = gtk.MenuItem("Lasombra Singles Sales")
            oSubMenu = gtk.Menu()
            oSubMenuItem.set_submenu(oSubMenu)

            oConfigMenuItem = gtk.MenuItem("Configure Lasombra Sales Plugin")
            oConfigMenuItem.connect("activate", self.config_activate)
            oSubMenu.add(oConfigMenuItem)

            oWarningMenuItem = gtk.MenuItem("Lasombra Sales Plugin Warnings")
            oWarningMenuItem.connect("activate", self.warning_activate)
            oSubMenu.add(oWarningMenuItem)

            return [('Plugins', oSubMenuItem)]

    def get_toolbar_widget(self):
        """Overrides method from base class."""
        if not self.check_versions() or not self.check_model_type():
            return None
        if self._cModelType is not PhysicalCardSet:
            return None
        self._oToolbarLabel = gtk.Label()
        self.update_numbers()
        self._oToolbarLabel.hide()
        return self._oToolbarLabel

    def setup(self):
        """Prompt the user to download/setup the plugin the first time"""
        if not os.path.exists(self._sPrefsPath):
            # Make sure path exists before we try to write things
            # This also prevents us asking again next start if the user
            # cancels
            ensure_dir_exists(self._sPrefsPath)
            # Looks like the first time
            oDialog = LasombraConfigDialog(self.parent, True)
            self.handle_config_response(oDialog)
            # Don't get called next time

    def config_activate(self, _oMenuWidget):
        """Launch the configuration dialog."""
        oDialog = LasombraConfigDialog(self.parent, False)
        self.handle_config_response(oDialog)

    def warning_activate(self, _oMenuWidget):
        """Launch the warning dialog."""
        oDialog = LasombraWarningsDialog(self.parent, self._aWarnings)
        try:
            oDialog.run()
        finally:
            oDialog.destroy()

    def handle_config_response(self, oConfigDialog):
        """Handle the response from the config dialog"""
        try:
            iResponse = oConfigDialog.run()

            if iResponse == gtk.RESPONSE_OK:
                fInventory = StringIO(oConfigDialog.get_binary_data())
                self._initialize_cache(fInventory)

                if self._aWarnings:
                    oWarningDialog = LasombraWarningsDialog(oConfigDialog,
                        self._aWarnings)
                    try:
                        oWarningDialog.run()
                    finally:
                        oWarningDialog.destroy()
        finally:
            # get rid of the dialog
            oConfigDialog.destroy()

    def _toggle_prices(self, oToggle):
        """Handle menu activation"""
        if oToggle.get_active():
            self.set_cols_in_use(['Price', 'Stock'])
        else:
            self.set_cols_in_use([])

    def _toggle_hide(self, oHide):
        """Handle menu activation"""
        self._bHideZeroCards = oHide.get_active()
        # Force model reload
        self.view.reload_keep_expanded()

    def _toggle_total(self, oTotal):
        """Handle menu activation"""
        self._bTotal = oTotal.get_active()
        if self._bTotal:
            self._oToolbarLabel.show()
        else:
            self._oToolbarLabel.hide()

    def update_numbers(self):
        """Update the label"""
        # Timing issues mean that this can be called before text label has
        # been properly realised, so we need this guard case
        if self._oToolbarLabel:
            self._oToolbarLabel.set_markup(TOOLPRICE_FORMAT % {
                'tot' : self._fTot,
                'unknown' : self._iUnknown})
            if hasattr(self._oToolbarLabel, 'set_tooltip_markup'):
                self._oToolbarLabel.set_tooltip_markup(TOOLPRICE_TOOLTIP % {
                    'tot' : self._fTot,
                    'unknown' : self._iUnknown})

    def load(self, aCards):
        """Listen on load events & update counts"""
        # pylint: disable-msg=E1101
        # pyprotocols confuses pylint
        if self._cModelType is not PhysicalCardSet:
            return
        self._fTot = 0
        self._iUnknown = 0
        for oCard in aCards:
            if not oCard.expansion:
                # Treat cards with no expansion set as unknown
                self._iUnknown += 1
                continue
            oAbsCard = IAbstractCard(oCard)
            tKey = (oAbsCard.name, oCard.expansion.name)
            fPrice = self._get_data_price(tKey)
            if fPrice is None:
                self._iUnknown += 1
            else:
                self._fTot += fPrice
        self.update_numbers()

    def alter_card_count(self, oCard, iChg):
        """respond to alter_card_count events"""
        # pylint: disable-msg=E1101
        # pyprotocols confuses pylint
        if self._cModelType is not PhysicalCardSet:
            return
        if not oCard.expansion:
            bUnknown = True
        else:
            oAbsCard = IAbstractCard(oCard)
            tKey = (oAbsCard.name, oCard.expansion.name)
            fPrice = self._get_data_price(tKey)
            bUnknown = fPrice is None
        if bUnknown:
            self._iUnknown += iChg
        else:
            self._fTot += iChg * fPrice
        self.update_numbers()

    def add_new_card(self, oCard, iCnt):
        """response to add_new_card events"""
        # pylint: disable-msg=E1101
        # pyprotocols confuses pylint
        if self._cModelType is not PhysicalCardSet:
            return
        if not oCard.expansion:
            bUnknown = True
        else:
            oAbsCard = IAbstractCard(oCard)
            tKey = (oAbsCard.name, oCard.expansion.name)
            fPrice = self._get_data_price(tKey)
            bUnknown = fPrice is None
        if bUnknown:
            self._iUnknown += iCnt
        else:
            self._fTot += iCnt * fPrice
        self.update_numbers()

    def check_card_visible(self, oPhysCard):
        """Implement mechanism for hiding cards if appropriate"""
        if not self._bHideZeroCards:
            return True # Nothing to do
        sCardName = oPhysCard.abstractCard.name
        if oPhysCard.expansion:
            sExpName = oPhysCard.expansion.name
        else:
            sExpName = None
        return self._get_data_stock((sCardName, sExpName)) > 0

    def sort_column(self, _oModel, oIter1, oIter2, oGetData):
        """Stringwise comparision of oIter1 and oIter2.

           Return -1 if oIter1 < oIter, 0 in ==, 1 if >
           """
        tKey1 = self._get_key(oIter1)
        tKey2 = self._get_key(oIter2)
        if tKey1 is None or tKey2 is None:
            # Not comparing cards, revert to default sort
            return self.model.sort_equal_iters(oIter1, oIter2)

        oVal1 = oGetData(tKey1)
        oVal2 = oGetData(tKey2)

        iRes = cmp(oVal1, oVal2)
        if iRes == 0:
            # Values agree, so do fall back sort
            iRes = self.model.sort_equal_iters(oIter1, oIter2)
        return iRes

    # Actions

    def set_cols_in_use(self, aCols):
        """Add columns to the view"""
        iSortCol, _iDir = self.model.get_sort_column_id()
        if iSortCol is not None and iSortCol > 1:
            # We're changing the columns, so restore sorting to default
            self.model.set_sort_column_id(0, 0)

        for oCol in self._get_col_objects():
            self.view.remove_column(oCol)

        if self._dPriceCache is None:
            do_complaint_error("Lasombra price data not available. " \
                " Use the configuration option under the main menu " \
                " to provide it.")
            return

        for iNum, sCol in enumerate(aCols):
            oCell = CellRendererIcons()
            oColumn = gtk.TreeViewColumn(sCol, oCell)
            oColumn.set_cell_data_func(oCell, self._dCols[sCol])
            oColumn.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            oColumn.set_fixed_width(self._dWidths.get(sCol, 100))
            oColumn.set_resizable(True)
            self.view.insert_column(oColumn, iNum + 3)
            oColumn.set_sort_column_id(iNum + 3 + SORT_COLUMN_OFFSET)
            self.model.set_sort_func(iNum + 3 + SORT_COLUMN_OFFSET,
                    self.sort_column, self._dSortDataFuncs[sCol])

    def get_cols_in_use(self):
        """Get which extra columns have been added to view"""
        return [oCol.get_property("title") for oCol in self._get_col_objects()]

    def _get_col_objects(self):
        """Get the actual TreeColumn in the view"""
        return [oCol for oCol in self.view.get_columns() if
                oCol.get_property("title") in self._dCols]

plugin = LasombraSales
