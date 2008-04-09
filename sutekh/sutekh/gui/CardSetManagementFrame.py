# CardSetManagementFrame.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Window for Managing Physical and Abstract Card Sets
# Copyright 2007 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""Pane for a list of card sets"""

import gtk
from sqlobject import SQLObjectNotFound
from sutekh.SutekhUtility import delete_physical_card_set, \
        delete_abstract_card_set
from sutekh.core.SutekhObjects import AbstractCardSet, PhysicalCardSet
from sutekh.core.Filters import NullFilter
from sutekh.gui.SutekhDialog import do_complaint_error, do_complaint_warning
from sutekh.gui.ScrolledList import ScrolledList
from sutekh.gui.BasicFrame import BasicFrame
from sutekh.gui.FilterDialog import FilterDialog
from sutekh.gui.CreateCardSetDialog import CreateCardSetDialog
from sutekh.gui.CardSetManagementMenu import CardSetManagementMenu

class CardSetManagementFrame(BasicFrame):
    """Pane for the List of card sets of the given type.

       Provides the actions associated with this Pane - creating new
       card sets, filtering, etc.
       """
    # pylint: disable-msg=R0904
    # gtk.Widget, so lots of public methods

    __sOpen = "<b>Opened</b>"
    __sAvail = "<b>Available</b>"

    def __init__(self, oMainWindow, oConfig):
        super(CardSetManagementFrame, self).__init__(oMainWindow)
        self._oConfig = oConfig
        self._cSetType = None
        self._oView = None
        self._sName = 'Unknown card set list type'
        self._oFilter = NullFilter()
        self._oFilterDialog = None
        self._sFilterType = None
        self._oMenu = None
        self._oScrolledList = None

    # pylint: disable-msg=W0212
    # We allow access via these properties
    type = property(fget=lambda self: self._sName, doc="Frame Type")
    menu = property(fget=lambda self: self._oMenu, doc="Frame Menu")
    # pylint: enable-msg=W0212

    def add_parts(self):
        """Add a list object to the frame"""
        oMbox = gtk.VBox(False, 2)

        self.set_title(self._sName)
        oMbox.pack_start(self._oTitle, False, False)

        self._oMenu = CardSetManagementMenu(self, self._oMainWindow,
                self._sName)

        oMbox.pack_start(self._oMenu, False, False)
        self._oScrolledList = ScrolledList(self._sName)

        if self._cSetType is PhysicalCardSet:
            self._oScrolledList.add_second_column("In Use")
        self._oView = self._oScrolledList.view
        self._oScrolledList.set_select_single()
        self._oView.connect('row_activated', self.row_clicked)
        self.reload()
        oMbox.pack_start(self._oScrolledList, expand=True)

        aDragTargets = [ ('STRING', 0, 0),
                         ('text/plain', 0, 0) ]

        self._oView.drag_source_set(
                gtk.gdk.BUTTON1_MASK | gtk.gdk.BUTTON3_MASK, aDragTargets,
                gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE)

        self._oView.connect('drag-data-get', self.drag_card_set)

        self._oView.drag_dest_set(gtk.DEST_DEFAULT_ALL,
                aDragTargets,
                gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE)

        self._oView.connect('drag-data-received', self.drag_drop_handler)

        self.add(oMbox)
        self.show_all()

    # pylint: disable-msg=W0613, R0913
    # arguments required by function signature
    def drag_card_set(self, oBtn, oDragContext, oSelectionData, oInfo, oTime):
        """Allow card sets to be dragged to a frame."""
        aSelection = self._oScrolledList.get_selection()
        if len(aSelection) != 1:
            return
        # Don't respond to the dragging of an already open card set, and so on
        if aSelection[0] in [self.__sOpen, self.__sAvail]:
            return
        sSetName = aSelection[0]
        if self._cSetType is PhysicalCardSet:
            sPrefix = 'PCS:'
        else:
            sPrefix = 'ACS:'
        sFrameName = sPrefix + sSetName
        if sFrameName in self._oMainWindow.dOpenFrames.values():
            return
        sData = "\n".join(['Sutekh Pane:', 'Card Set Pane:', sPrefix,
            sSetName])
        oSelectionData.set(oSelectionData.target, 8, sData)

    def create_new_card_set(self, oWidget):
        """Create a new card set"""
        if self._cSetType is PhysicalCardSet:
            oDialog = CreateCardSetDialog(self._oMainWindow, 'Physical')
            fOpenCardSet = self._oMainWindow.add_new_physical_card_set
        else:
            oDialog = CreateCardSetDialog(self._oMainWindow, 'Abstract')
            fOpenCardSet = self._oMainWindow.add_new_abstract_card_set
        oDialog.run()
        (sName, sAuthor, sDescription) = oDialog.get_data()
        oDialog.destroy()
        # pylint: disable-msg=E1102, W0612
        # E1102 - _cSetType is callable, as it's an SQLObject class
        # W0612 - oCS isn't important, as the creation of the new card
        # set is what matters
        if sName is not None:
            iCnt = self._cSetType.selectBy(name=sName).count()
            if iCnt > 0:
                do_complaint_error("Chosen Card Set Name is already in use.")
            else:
                oCS = self._cSetType(name=sName, author=sAuthor,
                        comment=sDescription)
                fOpenCardSet(sName)

    def delete_card_set(self, oWidget):
        """Delete the selected card set."""
        aSelection = self._oScrolledList.get_selection()
        if len(aSelection) != 1:
            return
        else:
            sSetName = aSelection[0]
        try:
            oCS = self._cSetType.byName(sSetName)
        except SQLObjectNotFound:
            return
        if len(oCS.cards) > 0:
            iResponse = do_complaint_warning("Card Set %s Not Empty. Really"
                    " Delete?" % sSetName)
            if iResponse == gtk.RESPONSE_CANCEL:
                # Don't delete
                return
        # Got here, so delete the card set
        if self._cSetType is PhysicalCardSet:
            sFrameName = 'PCS:' + sSetName
            delete_physical_card_set(sSetName)
        else:
            sFrameName = 'ACS:' + sSetName
            delete_abstract_card_set(sSetName)
        self._oMainWindow.remove_frame_by_name(sFrameName)
        self.reload()

    def set_filter(self, oWidget):
        """Set the filter applied to the list."""
        if self._oFilterDialog is None:
            self._oFilterDialog = FilterDialog(self._oMainWindow,
                    self._oConfig, self._sFilterType)
        self._oFilterDialog.run()

        if self._oFilterDialog.was_cancelled():
            return # Change nothing

        oFilter = self._oFilterDialog.get_filter()
        if oFilter != None:
            self._oFilter = oFilter
            if self._oMenu.get_apply_filter():
                self.reload()
            else:
                # Let toggle reload for us
                self._oMenu.set_apply_filter(True)
        else:
            self._oFilter = NullFilter()
            # Filter is set to blank, so we treat this as disabling
            # Filter
            if not self._oMenu.get_apply_filter():
                self.reload()
            else:
                # Let toggle reload for us
                self._oMenu.set_apply_filter(False)

    def row_clicked(self, oTreeView, oPath, oColumn):
        """Handle row clicked events.

           allow double clicks to open a card set.
           """
        oModel = oTreeView.get_model()
        # We are pointing to a ListStore, so the iters should always be valid
        # Need to dereference to the actual path though, as iters not unique
        oIter = oModel.get_iter(oPath)
        sName = oModel.get_value(oIter, 0)
        if sName == self.__sAvail or sName == self.__sOpen:
            return
        # check if card set is open before opening again
        if self._cSetType is PhysicalCardSet:
            sFrameName = 'PCS:' + sName
        else:
            sFrameName = 'ACS:' + sName
        oPane = self._oMainWindow.find_pane_by_name(sFrameName)
        if oPane is not None:
            return # Already open, so do nothing
        oFrame = self._oMainWindow.add_pane_end()
        if self._cSetType is PhysicalCardSet:
            self._oMainWindow.replace_with_physical_card_set(sName, oFrame)
        elif self._cSetType is AbstractCardSet:
            self._oMainWindow.replace_with_abstract_card_set(sName, oFrame)

    # pylint: enable-msg=W0613, R0913

    def reload(self):
        """Reload the contents of the list."""
        aVals = [self.__sOpen, self.__sAvail]
        iAvailIndex = 1
        if self._oMenu.get_apply_filter():
            oSelectFilter = self._oFilter
        else:
            oSelectFilter = NullFilter()
        dInUse = {}
        for oCS in oSelectFilter.select(self._oSetClass).orderBy('name'):
            if self._cSetType is PhysicalCardSet:
                sFrameName = 'PCS:' + oCS.name
                if oCS.inuse:
                    dInUse[oCS.name] = 'Yes'
            else:
                sFrameName = 'ACS:' + oCS.name
            if sFrameName not in self._oMainWindow.dOpenFrames.values():
                aVals.append(oCS.name)
            else:
                aVals.insert(iAvailIndex, oCS.name)
                iAvailIndex += 1
        self._oScrolledList.fill_list(aVals)
        self._oScrolledList.fill_second_column(dInUse)


class PhysicalCardSetListFrame(CardSetManagementFrame):
    """Frame for the Physical Card Set list.

       Adds in-use flag handling.
       """
    # pylint: disable-msg=R0904
    # gtk.Widget, so lots of public methods
    def __init__(self, oMainWindow, oConfig):
        super(PhysicalCardSetListFrame, self).__init__(oMainWindow, oConfig)
        self._cSetType = PhysicalCardSet
        self._sFilterType = 'PhysicalCardSet'
        self._sName = 'Physical Card Set List'
        self._oSetClass = PhysicalCardSet
        self.set_name("physical card sets list")
        self.add_parts()

    # pylint: disable-msg=W0613
    # oMenuItem required by function signature
    def toggle_in_use_flag(self, oMenuItem):
        """Toggle the in-use status of the card set"""
        aSelection = self._oScrolledList.get_selection()
        if len(aSelection) != 1:
            return
        else:
            sSetName = aSelection[0]
        try:
            # pylint: disable-msg=E1101
            # SQLObject confuses pylint
            oCS = self._cSetType.byName(sSetName)
        except SQLObjectNotFound:
            return
        oCS.inuse = not oCS.inuse
        oCS.syncUpdate()
        self.reload()
        # Restore selection
        self._oScrolledList.set_selected(oCS.name)

class AbstractCardSetListFrame(CardSetManagementFrame):
    """Abstract Card Set List Frame.

       Sets values as needed for Abstract Card Sets.
       """
    # pylint: disable-msg=R0904
    # gtk.Widget, so lots of public methods
    def __init__(self, oMainWindow, oConfig):
        super(AbstractCardSetListFrame, self).__init__(oMainWindow, oConfig)
        self._cSetType = AbstractCardSet
        self._sFilterType = 'AbstractCardSet'
        self._sName = 'Abstract Card Set List'
        self._oSetClass = AbstractCardSet
        self.set_name("abstract card sets list")
        self.add_parts()


