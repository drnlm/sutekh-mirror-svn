# MultiPaneWindow.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Handle the multi pane UI for Sutkeh
# Copyright 2007, 2008 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - See COPYING for details

"""Main window for Sutekh."""

import pygtk
pygtk.require('2.0')
import gtk
# pylint: disable-msg=E0611
# pylint doesn't see resource_stream here, for some reason
from pkg_resources import resource_stream, resource_exists
from itertools import chain
# pylint: enable-msg=E0611
from sutekh.core.SutekhObjectCache import SutekhObjectCache
from sutekh.core.SutekhObjects import PhysicalCardSet, flush_cache, \
        PhysicalCard
from sutekh.gui.BasicFrame import BasicFrame
from sutekh.gui.PhysicalCardFrame import PhysicalCardFrame
from sutekh.gui.CardTextFrame import CardTextFrame
from sutekh.gui.CardSetFrame import CardSetFrame
from sutekh.gui.AboutDialog import SutekhAboutDialog
from sutekh.gui.MainMenu import MainMenu
from sutekh.gui.MainToolbar import MainToolbar
from sutekh.gui.GuiCardLookup import GuiLookup
from sutekh.gui.GuiCardSetFunctions import break_existing_loops
from sutekh.gui.CardSetManagementFrame import CardSetManagementFrame
from sutekh.gui.PluginManager import PluginManager
from sutekh.gui import SutekhIcon
from sutekh.gui.HTMLTextView import HTMLViewDialog
from sutekh.gui.IconManager import IconManager

class MultiPaneWindow(gtk.Window):
    """Window that has a configurable number of panes."""
    # pylint: disable-msg=R0904, R0902
    # R0904 - gtk.Widget, so many public methods
    # R0902 - we need to keep a lot of state, so many instance attributes
    def __init__(self):
        super(MultiPaneWindow, self).__init__(gtk.WINDOW_TOPLEVEL)
        self.set_name("Sutekh")
        self.set_title("Sutekh")
        self.set_border_width(2)

        # make sure we can quit
        self.connect("destroy", self.action_quit)
        self.connect("delete-event", self.action_close)
        # We can shrink the window quite small
        self.set_size_request(100, 100)
        # But we start at a reasonable size
        self.set_default_size(800, 600)

        # Set Default Window Icon for all Windows
        gtk.window_set_default_icon(SutekhIcon.SUTEKH_ICON)

        # common current directory for file dialogs
        self._sWorkingDir = ''

        # This always increments when panes are added, so the number is unique
        # for each new frame
        self._iCount = 0

        # Need to keep track of open card sets globally
        self.dOpenFrames = {}
        self.dClosedFrames = {}

        self._sCardSelection = '' # copy + paste selection
        self._aHPanes = []
        self._aPlugins = []
        self.__dMenus = {}

        self._oFocussed = None

        # CardText frame is special, and there is only ever one of it
        # but we will set it up later
        self._bCardTextShown = False
        self._oCardTextPane = None
        self._oPCSListPane = None
        self._oHelpDlg = None
        # Global icon manager
        self._oIconManager = None
        self._oBusyCursor = gtk.gdk.Cursor(gtk.gdk.WATCH)

    # pylint: disable-msg=W0201
    # We define attributes here, since this is called after database checks
    def setup(self, oConfig):
        """After database checks are passed, setup what we need to display
           data from the database."""
        self._oConfig = oConfig
        self._oCardLookup = GuiLookup(self._oConfig)

        # Create object cache
        self.__oSutekhObjectCache = SutekhObjectCache()

        # Create global icon manager
        self._oIconManager = IconManager(oConfig)
        # Create card text pane
        self._oCardTextPane = CardTextFrame(self, self._oIconManager)

        # Load plugins
        self._oPluginManager = PluginManager()
        self._oPluginManager.load_plugins()
        for cPlugin in self._oPluginManager.get_card_list_plugins():
            # Find plugins that will work on the Main Window
            self._aPlugins.append(cPlugin(self, None,
                "MainWindow"))

        self.__oMenu = MainMenu(self, oConfig)
        self.__oToolbar = MainToolbar(self)

        # Do setup - prompt for downloads, etc. if needed
        self._oIconManager.setup()
        # plugins as well
        for cPlugin in self._aPlugins:
            cPlugin.setup()

        self.oVBox = gtk.VBox(False, 1)
        self.oVBox.pack_start(self.__oMenu, False, False)
        self.oVBox.pack_start(self.__oToolbar, False, False)
        self.oVBox.show()
        self.add(self.oVBox)

        # Break any loops in the database
        break_existing_loops()

        self.show_all()
        self.restore_from_config()

        self.connect('key-press-event',
                self.key_press)

    # pylint: enable-msg=W0201

    # pylint: disable-msg=W0212
    # We allow access via these properties
    # Needed for Backup plugin
    cardLookup = property(fget=lambda self: self._oCardLookup,
        doc="Used if user instance is needed to identify card names.")
    # Needed for plugins
    plugin_manager = property(fget=lambda self: self._oPluginManager,
            doc="The plugin manager for the application")
    plugins = property(fget=lambda self: self._aPlugins,
            doc="Plugins enabled for the main window.")
    config_file = property(fget=lambda self: self._oConfig,
            doc="The confi file")
    focussed_pane = property(fget=lambda self: self._oFocussed,
            doc="The currently focussed pane.")
    mainwindow = property(fget=lambda self: self,
            doc="Return reference to the main window")
    icon_manager = property(fget=lambda self: self._oIconManager,
            doc="Used to lookup icons for disciplines, clans, etc.")
    card_text_pane = property(fget=lambda self: self._oCardTextPane,
            doc="Return reference to the card text pane")

    # pylint: enable-msg=W0212

    def add_to_menu_list(self, sMenuFlag, oMenuActiveFunc):
        """Add a key to the list of menu items to manage."""
        if not self.__dMenus.has_key(sMenuFlag):
            self.__dMenus[sMenuFlag] = oMenuActiveFunc

    # working directory methods

    def get_working_dir(self):
        """Get the current working dir for file chooser widgets"""
        return self._sWorkingDir

    def set_working_dir(self, sNewDir):
        """Set the working dir to sNewDir."""
        self._sWorkingDir = sNewDir

    # Config file handling

    def restore_from_config(self):
        """Restore all the frame form the config file."""
        # pylint: disable-msg=R0912, R0914, W9967
        # R0912: Need to consider all these cases, so many branches
        # R0914: Consequently, many local variables
        # W9967: Need to use keys(), since we remove items from the
        # dictionary in remove_frame

        # Clear out all existing frames
        for oFrame in self.dOpenFrames.keys():
            self.remove_frame(oFrame, True)

        aClosedFrames = []

        iWidth, iHeight = self._oConfig.get_window_size()
        if iWidth > 0 and iHeight > 0:
            self.resize(iWidth, iHeight)
        # Reset the pane number count, since we're starting afresh
        self._iCount = 0
        dPaneInfo = self._oConfig.get_all_pane_info()
        for _iNumber, sType, sName, bVert, bClosed, iPos in \
                self._oConfig.get_all_panes():
            oNewFrame = self.add_pane(bVert, iPos)
            oRestored = None
            self.win_focus(None, None, oNewFrame)
            if sType == PhysicalCardSet.sqlmeta.table:
                tInfo = dPaneInfo.get(sName)
                oRestored = self.replace_with_physical_card_set(sName,
                        oNewFrame, tInfo)
            elif sType == 'Card Text':
                oRestored = self.replace_with_card_text(None)
            elif sType == PhysicalCard.sqlmeta.table:
                oRestored = self.replace_with_physical_card_list(None)
            elif sType == 'Card Set List':
                oRestored = self.replace_with_pcs_list(None)
            else:
                # See if one of the plugins claims this type
                for oPlugin in self._aPlugins:
                    tResult = oPlugin.get_frame_from_config(sType)
                    if tResult:
                        oFrame, sMenuFlag = tResult
                        self.replace_frame(oNewFrame, oFrame, sMenuFlag)
                        oRestored = oFrame
            if bClosed and oRestored:
                # Hold off minimizing until all frames are added to avoid
                # corner cases around the 1st restored frame needing to be
                # minimised
                aClosedFrames.append(oRestored)
        for oFrame in aClosedFrames:
            self.minimize_to_toolbar(oFrame)
        if not self.dOpenFrames:
            # We always have at least one pane
            self.add_pane()

    # Pane manipulation functions

    def top_level_panes(self):
        """Return a list of top-level panes.

           This is just the contents of the MainWindow vbox minus
           the toolbar and menu.
           """
        return [x for x in self.oVBox.get_children() if
                    x not in (self.__oMenu, self.__oToolbar)]

    def find_pane_by_name(self, sName):
        """Return the gtk widget corresponding to the given pane name"""
        # pylint: disable-msg=W0704
        # not doing anything for ValueError is the right thing here
        try:
            iIndex = self.dOpenFrames.values().index(sName)
            oPane = self.dOpenFrames.keys()[iIndex]
            return oPane
        except ValueError:
            return None

    def find_cs_pane_by_set_name(self, sSetName):
        """Find all the panes that correspond to the same card set"""
        aPanes = []
        for oPane, sName in self.dOpenFrames.iteritems():
            if sName.startswith(sSetName) and hasattr(oPane, 'view') and \
                    hasattr(oPane.view, 'sSetName'):
                if oPane.view.sSetName == sSetName:
                    aPanes.append(oPane)
        return aPanes

    def rename_pane(self, sOldName, sNewName):
        """Rename a frame"""
        oFrame = self.find_pane_by_name(sOldName)
        if not oFrame:
            return
        self.dOpenFrames[oFrame] = sNewName

    def replace_with_physical_card_set(self, sName, oFrame, tInfo=None):
        """Replace the pane oFrame with the physical card set sName"""
        if oFrame:
            # pylint: disable-msg=W0704
            # not doing anything for errors right now
            try:
                oPane = CardSetFrame(self, sName, tInfo)
                self.replace_frame(oFrame, oPane, oPane.name)
                return oPane
            except RuntimeError:
                # add warning dialog?
                pass
        return None

    def add_new_physical_card_set(self, sName):
        """Create a new pane and replace with the PCS sName"""
        oFrame = self.add_pane_end()
        self.replace_with_physical_card_set(sName, oFrame)

    def replace_with_pcs_list(self, _oWidget, oOldFrame=None):
        """Replace the focussed or given pane with the physical card set
           list."""
        sMenuFlag = "Card Set List"
        if oOldFrame is None:
            oOldFrame = self._oFocussed
        if sMenuFlag not in self.dOpenFrames.values() and oOldFrame:
            oPane = CardSetManagementFrame(self)
            self.replace_frame(oOldFrame, oPane, sMenuFlag)
            self._oPCSListPane = oPane
            return oPane
        return None

    def add_new_pcs_list(self, oMenuWidget):
        """Add a new pane and replace it with the physical card set list."""
        oNewPane = self.add_pane_end()
        self.replace_with_pcs_list(oMenuWidget, oNewPane)

    def replace_with_physical_card_list(self, _oWidget, oOldFrame=None):
        """Replace the currently focussed or given pane with the physical
           card list."""
        sMenuFlag = "White Wolf Card List"
        if oOldFrame is None:
            oOldFrame = self._oFocussed
        if sMenuFlag not in self.dOpenFrames.values() and oOldFrame:
            oPane = PhysicalCardFrame(self)
            self.replace_frame(oOldFrame, oPane, sMenuFlag)
            return oPane
        return None

    def add_new_physical_card_list(self, oMenuWidget):
        """Add a new pane and replace it with the physical card list."""
        oNewPane = self.add_pane_end()
        self.replace_with_physical_card_list(oMenuWidget, oNewPane)

    def replace_with_card_text(self, _oWidget, oOldFrame=None):
        """Replace the current or given pane with the card set pane."""
        sMenuFlag = "Card Text"
        if oOldFrame is None:
            oOldFrame = self._oFocussed
        if sMenuFlag not in self.dOpenFrames.values() and oOldFrame:
            self.replace_frame(oOldFrame, self._oCardTextPane, sMenuFlag)
            return self._oCardTextPane
        return None

    def add_new_card_text(self, oMenuWidget):
        """Add a new pane and replace it with the card set pane."""
        oNewPane = self.add_pane_end()
        self.replace_with_card_text(oMenuWidget, oNewPane)

    # state manipulation
    def reload_pcs_list(self):
        """Reload the list of physical card sets."""
        if self._oPCSListPane is not None:
            self._oPCSListPane.reload()

    def reload_all(self):
        """Reload all open frames. Useful for major DB changes"""
        for oPane in self.dOpenFrames:
            oPane.reload()

    def do_all_queued_reloads(self):
        """Do any deferred reloads from the database signal handlers."""
        for oPane in self.dOpenFrames:
            oPane.do_queued_reload()

    def update_to_new_db(self):
        """Resync open Panes against the database.

           Needed because ids aren't kept across re-reading the WW
           cardlist, since card sets with children are always created
           before there children are added.
           """
        # Flush the caches, so we don't hit stale lookups
        flush_cache()
        # Reset the lookup cache holder
        self.__oSutekhObjectCache = SutekhObjectCache()
        aToLoopOver = self.dOpenFrames.keys()
        # We may close frames here, so loop over a copy of the list
        for oPane in aToLoopOver:
            oPane.update_to_new_db()

    def clear_cache(self):
        """Remove the cached set of objects, for card list reloads, etc."""
        del self.__oSutekhObjectCache

    def get_editable_panes(self):
        """Get a list of panes, which are currently editable.

           Used by the WW import code, and backup restores to correct
           for the zero card list state setting the cardlist's to editable.
           """
        aEditable = []
        for oPane in self.dOpenFrames:
            if hasattr(oPane.view, 'toggle_editable'):
                if oPane.view.get_model().bEditable:
                    aEditable.append(oPane)
        return aEditable

    def restore_editable_panes(self, aEditable):
        """Restore the editable state so only the panes in aEditable are
           editable."""
        for oPane in self.dOpenFrames:
            if hasattr(oPane.view, 'toggle_editable'):
                if oPane in aEditable:
                    oPane.view.toggle_editable(True)
                else:
                    oPane.view.toggle_editable(False)
                    # Empty panes still need to be editable, though
                    oPane.view.check_editable()

    def set_card_text(self, oCard):
        """Update the card text frame to the currently selected card."""
        if oCard:
            # Skip if None
            self._oCardTextPane.view.set_card_text(oCard)

    def reset_menu(self):
        """Ensure menu state is correct."""
        for sMenu, fSetSensitiveFunc in self.__dMenus.iteritems():
            if sMenu in self.dOpenFrames.values() or \
                    sMenu in self.dClosedFrames.values():
                fSetSensitiveFunc(False)
            else:
                fSetSensitiveFunc(True)
        # Disable the menu accelerators for unfocussed panes
        for oFrame in chain(self.dOpenFrames, self.dClosedFrames):
            if self._oFocussed != oFrame and hasattr(oFrame, 'menu') and \
                    hasattr(oFrame.menu, 'remove_accels'):
                oFrame.menu.remove_accels()
        # Handle focussed pane stuff
        if self._oFocussed:
            # Can always split horizontally
            self.__oMenu.set_split_horizontal_active(True)
            self.__oMenu.replace_pane_set_sensitive(True)
            # But we can't split vertically more than once
            if isinstance(self._oFocussed.get_parent(), gtk.VPaned):
                self.__oMenu.set_split_vertical_active(False)
            else:
                self.__oMenu.set_split_vertical_active(True)
            # can't delete the last pane
            if len(self.dOpenFrames) > 1:
                self.__oMenu.del_pane_set_sensitive(True)
            else:
                self.__oMenu.del_pane_set_sensitive(False)
            # Ensure accelerators are active
            if hasattr(self._oFocussed, 'menu') and \
                    hasattr(self._oFocussed.menu, 'activate_accels'):
                self._oFocussed.menu.activate_accels()
        else:
            # Can't split when no pane chosen
            self.__oMenu.set_split_vertical_active(False)
            self.__oMenu.set_split_horizontal_active(False)
            # Can't delete either
            self.__oMenu.del_pane_set_sensitive(False)
            self.__oMenu.replace_pane_set_sensitive(False)

    def set_selection_text(self, sText):
        """Set the current selection text for copy+paste."""
        self._sCardSelection = sText

    def get_selection_text(self):
        """Get the current selection for copy+paste."""
        return self._sCardSelection

    # startup, exit and other misc functions

    # pylint: disable-msg=R0201
    # making this a function would not be convient
    def run(self):
        """gtk entry point"""
        gtk.main()

    def action_quit(self, _oWidget):
        """Exit the app"""
        # ensure we cleanup all signals (needed for tests)
        for oFrame in self.dOpenFrames:
            oFrame.cleanup()
        # Don't call gtk.main_quit when the main loop isn't running (true in
        # the tests)
        if gtk.main_level() > 0:
            gtk.main_quit()

    def show_about_dialog(self, _oWidget):
        """Display the about dialog"""
        oDlg = SutekhAboutDialog()
        oDlg.run()
        oDlg.destroy()

    def _link_resource(self, sLocalUrl):
        """Return a file-like object which sLocalUrl can be read from."""
        sResource = '/docs/html/%s' % sLocalUrl
        if resource_exists('sutekh', sResource):
            return resource_stream('sutekh', sResource)
        else:
            raise ValueError("Unknown resource %s" % sLocalUrl)

    # pylint: enable-msg=R0201

    def win_focus(self, _oWidget, _oEvent, oFrame):
        """Respond to focus change events.

           Keep track of focussed pane, update menus and handle highlighting.
           """
        if self._oFocussed is not None:
            self._oFocussed.set_unfocussed_title()
        self._oFocussed = oFrame
        if oFrame:
            # oFrame can be None when win_focus is called directly
            self._oFocussed.set_focussed_title()
            self._oFocussed.view.grab_focus()
        self.reset_menu()

    def key_press(self, _oWidget, oEvent):
        """Move to the next frame on Tab"""
        if oEvent.keyval == gtk.gdk.keyval_from_name('Tab') or \
                oEvent.keyval == gtk.gdk.keyval_from_name('KP_Tab'):
            self.move_to_frame(+1)
            return True
        elif oEvent.keyval == gtk.gdk.keyval_from_name('ISO_Left_Tab'):
            # Shift & tab should always be this, AFAICT
            self.move_to_frame(-1)
            return True
        return False # propogate event

    def action_close(self, _oWidget, _oEvent):
        """Close the app (menu or window manager) and save the settings"""
        if self._oConfig.get_save_on_exit():
            self.save_frames()
        if self._oConfig.get_save_window_size():
            self.save_window_size()
        # cue app exit
        self.destroy()

    def show_tutorial(self, _oMenuWidget, oHelpLast):
        """Show the HTML Tutorial"""
        fTutorial = self._link_resource('Tutorial.html')
        oHelpLast.set_sensitive(True)
        self._do_html_dialog(fTutorial)

    def show_manual(self, _oMenuWidget, oHelpLast):
        """Show the HTML Manual"""
        fManual = self._link_resource('Manual.html')
        oHelpLast.set_sensitive(True)
        self._do_html_dialog(fManual)

    def show_last_help(self, _oMenuWidget):
        """Reshow the help dialog with the last shown page"""
        if self._oHelpDlg is not None:
            self._oHelpDlg.show()

    # _oWidget needed so this can be also be called from the menu
    def add_pane_end(self, _oWidget=None):
        """Add a pane to the right edge of the window.

           Used for the add pane menu items and double clicking on card set
           names.
           """
        if not self.dOpenFrames:
            oPane = None
        else:
            # Descend the right child of the panes, until we get a
            # non-paned item
            oPane = self.top_level_panes()[0]
            while isinstance(oPane, (gtk.HPaned, gtk.VPaned)):
                oPane = oPane.get_child2()
        oOldFocus = self._oFocussed
        self.win_focus(None, None, oPane)
        oNewPane = self.add_pane()
        self.win_focus(None, None, oOldFocus)
        return oNewPane

    def menu_remove_frame(self, _oMenuWidget):
        """Handle the remove pane request from the menu"""
        self.remove_frame(self._oFocussed)

    def _do_html_dialog(self, fInput):
        """Popup and run HTML Dialog widget"""
        if self._oHelpDlg is None:
            self._oHelpDlg = HTMLViewDialog(self, fInput, self._link_resource)
        else:
            self._oHelpDlg.show_page(fInput)
        self._oHelpDlg.show()

    # window setup saving functions

    def save_window_size(self):
        """Write the current window size to the config file"""
        self._oConfig.save_window_size(self.get_size())

    def save_frames(self):
        """save the current frame layout"""
        self._oConfig.pre_save_clear()

        def save_children(oPane, oConfig, bVert, iNum, iPos):
            """Walk the tree of HPanes + VPanes, and save their info."""
            # oPane.get_position() gives us the position relative to the paned
            # we're contained in. However, when we recreate the layout, we
            # don't split panes in the same order, hence the fancy
            # score-keeping work to convert the obtained positions to those
            # needed for restoring
            if isinstance(oPane, gtk.HPaned):
                oChild1 = oPane.get_child1()
                oChild2 = oPane.get_child2()
                iNum, iChildPos = save_children(oChild1, oConfig, False,
                        iNum, iPos)
                iMyPos = oPane.get_position()
                if isinstance(oChild1, gtk.HPaned):
                    iMyPos = iMyPos - iChildPos
                    iChildPos = oPane.get_position()
                else:
                    iChildPos = iMyPos
                if iMyPos < 1:
                    # Setting pos to < 1 doesn't do what we want
                    iMyPos = 1
                iNum, iChild2Pos = save_children(oChild2, oConfig, False,
                        iNum, iMyPos)
                if isinstance(oChild2, gtk.HPaned):
                    iChildPos += iChild2Pos
            elif isinstance(oPane, gtk.VPaned):
                oChild1 = oPane.get_child1()
                oChild2 = oPane.get_child2()
                iMyPos = oPane.get_position()
                iNum, _iTemp = save_children(oChild1, oConfig, False, iNum,
                        iPos)
                iNum, _iTemp = save_children(oChild2, oConfig, True, iNum,
                        iMyPos)
                iChildPos = iPos
            else:
                oConfig.add_frame(iNum, oPane.type, oPane.name, bVert, False,
                        iPos)
                if oPane.type == PhysicalCardSet.sqlmeta.table:
                    tInfo = oPane.get_model_modes()
                    oConfig.add_pane_info(iNum, oPane.name, tInfo)
                iNum += 1
                iChildPos = iPos
            return iNum, iChildPos

        iNum = 1
        aTopLevelPanes = self.top_level_panes()
        if aTopLevelPanes:
            iNum, _iPos = save_children(aTopLevelPanes[0], self._oConfig,
                    False, 1, -1)
        for oFrame in self.dClosedFrames:
            self._oConfig.add_frame(iNum, oFrame.type, oFrame.name, False,
                    True, -1)
            if oFrame.type == PhysicalCardSet.sqlmeta.table:
                tInfo = oFrame.get_model_modes()
                self._oConfig.add_pane_info(iNum, oFrame.name, tInfo)
            iNum += 1

    # frame management functions

    def move_to_frame(self, iDir):
        """Move the focus to the previous frame"""
        if iDir > 0:
            oNewFrame = self._find_next_frame(self._oFocussed)
        else:
            oNewFrame = self._find_prev_frame(self._oFocussed)
        if oNewFrame:
            self.win_focus(None, None, oNewFrame)

    def _find_prev_frame(self, oFrame):
        """Move the focus to the next frame in the window"""
        if not oFrame:
            if not self.dOpenFrames:
                # No frame, so nothing to focus
                return
            # get first child, and descent that
            oChild = self.top_level_panes()[0]
            oParent = self.oVBox
        else:
            oParent = oFrame.get_parent()
            if isinstance(oParent, gtk.VPaned):
                if oParent.get_child2() == oFrame:
                    # Need to go to the top frame
                    return oParent.get_child1()
                oChild = oParent
            else:
                oChild = oFrame
            # Need to move to the 'neighbouring' HPane
            oParent = oChild.get_parent()
            while isinstance(oParent, gtk.HPaned) and \
                        oChild == oParent.get_child1():
                # As long as we're the left-most branch, we ascend
                oChild = oParent
                oParent = oChild.get_parent()
        # prepare to descend to the correct frame
        if isinstance(oParent, gtk.HPaned) and oChild == oParent.get_child2():
            # We need to start going down the left-hand tree
            oChild = oParent.get_child1()
        while isinstance(oChild, gtk.HPaned):
            # we descend down the right branch until we reach a frame
            oChild = oChild.get_child2()
        if isinstance(oChild, gtk.VPaned):
            # go to the bottom frame in this case
            oChild = oChild.get_child2()
        return oChild

    def _find_next_frame(self, oFrame):
        """Move the focus to the next frame in the window"""
        if not oFrame:
            if not self.dOpenFrames:
                # No frame, so nothing to focus
                return
            # get first child, and descent that
            oChild = self.top_level_panes()[0]
            oParent = self.oVBox
        else:
            oParent = oFrame.get_parent()
            if isinstance(oParent, gtk.VPaned):
                if oParent.get_child1() == oFrame:
                    # Need to go to the bottom frame
                    return oParent.get_child2()
                oChild = oParent
            else:
                oChild = oFrame
            # Need to move to the 'neighbouring' HPane
            oParent = oChild.get_parent()
            while isinstance(oParent, gtk.HPaned) and \
                        oChild == oParent.get_child2():
                # As long as we're the right-most branch, we ascend
                oChild = oParent
                oParent = oChild.get_parent()
        # prepare to descend to the correct frame
        if isinstance(oParent, gtk.HPaned) and oChild == oParent.get_child1():
            # We need to start going down the right-hand tree
            oChild = oParent.get_child2()
        while isinstance(oChild, gtk.HPaned):
            # we descend down the left branch until we reach a frame
            oChild = oChild.get_child1()
        if isinstance(oChild, gtk.VPaned):
            # go to the top frame in this case
            oChild = oChild.get_child1()
        return oChild

    def replace_frame(self, oOldFrame, oNewFrame, sMenuFlag):
        """Replace oOldFrame with oNewFrame + update menus"""
        oNewFrame.show()
        oNewFrame.set_focus_handler(self.win_focus)
        oParent = oOldFrame.get_parent()
        oParent.remove(oOldFrame)
        oParent.add(oNewFrame)
        del self.dOpenFrames[oOldFrame]
        self.dOpenFrames[oNewFrame] = sMenuFlag
        if oNewFrame in self.dClosedFrames:
            del self.dClosedFrames[oNewFrame]
        if self._oFocussed == oOldFrame:
            self.win_focus(None, None, None)
        self.reset_menu()
        # Open card lists may have changed because of the frame we've
        # kicked out
        self.reload_pcs_list()

    def swap_frames(self, oFrame1, oFrame2):
        """swap two frames - used by drag-n-drop code"""
        if oFrame1 != oFrame2:
            oParent1 = oFrame1.get_parent()
            oParent2 = oFrame2.get_parent()
            if oParent1 == oParent2:
                # Special logic to ensure that we get them swapped
                if oFrame1 == oParent1.get_child1():
                    oParent1.remove(oFrame1)
                    oParent1.remove(oFrame2)
                    oParent1.add1(oFrame2)
                    oParent1.add2(oFrame1)
                else:
                    oParent1.remove(oFrame1)
                    oParent1.remove(oFrame2)
                    oParent1.add1(oFrame1)
                    oParent1.add2(oFrame2)
            else:
                oParent2.remove(oFrame2)
                oParent1.remove(oFrame1)
                oParent2.add(oFrame1)
                oParent1.add(oFrame2)
            oParent1.show()
            oParent2.show()
            self.reset_menu()

    def get_current_pane(self):
        """Get the parent HPane of the focussed pane.

           If there's no Focussed Pane, return the last added pane,
           which does the right thing for restore_from_config.
           """
        if self._oFocussed:
            oParent = self._oFocussed.get_parent()
            if isinstance(oParent, gtk.VPaned):
                # Get the HPane this belongs to
                oParent = oParent.get_parent()
            return oParent
        else:
            # Return the last added pane, for automatic adds
            return self._aHPanes[-1]

    # Utility functions for add_pane
    def _get_pane_to_replace(self):
        """Get the pane to be replaced in add_pane

           Return the pane and the part to replace"""
        oParent = self.get_current_pane()
        # Must be a hpane, by construction
        if self._oFocussed:
            oPart1 = self._oFocussed
            if isinstance(oPart1.get_parent(), gtk.VPaned):
                # Veritical pane, so we need to use the pane, not
                # the Frame
                oPart1 = oPart1.get_parent()
        else:
            # Replace right child of last added pane when no
            # obvious option
            oPart1 = oParent.get_child2()
        return oPart1, oParent

    def _do_replace_pane(self, oParent, oPart1, oNewPane, iConfigPos):
        """Handle the nitty gritty of replacing a pane in the window"""
        if oPart1 == oParent.get_child1():
            oParent.remove(oPart1)
            oParent.add1(oNewPane)
            # Going to the left of the current pane,
            iPos = oParent.get_position()/2
        else:
            oParent.remove(oPart1)
            oParent.add2(oNewPane)
            oCur = oParent.get_allocation()
            if oCur.width == 1 and oParent.get_position() > 1 and \
                    iConfigPos == -1:
                # we are in early startup, so we can move the
                # Parent as well
                # We want to split ourselves into equally sized
                # sections
                oCur = self.oVBox.get_allocation()
                iPos = oCur.width / (len(self._aHPanes) + 2)
                self.set_pos_for_all_hpanes(iPos)
            else:
                iPos = (oCur.width - oParent.get_position())/2
        return iPos

    def add_pane(self, bVertical=False, iConfigPos=-1):
        """Add a blank frame to the window.

           bVertical -> set True to split the current pane vertically
           iConfigPos -> Layout parameter for restoring positions.
           if iConfigPos == -1, the currently focussed frame is
           halved in size.
           """
        # this is a complex function (arguably too complex). Simplifying
        # it is non trivial
        oWidget = BasicFrame(self)
        oWidget.add_parts()
        oWidget.set_focus_handler(self.win_focus)
        self._iCount += 1
        sKey = 'Blank Pane:' + str(self._iCount)
        oWidget.set_title(sKey)
        self.dOpenFrames[oWidget] = sKey
        if len(self.dOpenFrames) == 1:
            # We have a blank space to fill, so just plonk in the widget
            self.oVBox.pack_start(oWidget)
        else:
            # We already have a widget, so we add a pane
            if bVertical:
                oNewPane = gtk.VPaned()
                oCurAlloc = self.oVBox.get_allocation()
                oMenuAlloc = self.__oMenu.get_allocation()
                iPos = (oCurAlloc.height - oMenuAlloc.height) / 2
            else:
                oNewPane = gtk.HPaned()
            if len(self._aHPanes) > 0:
                # We pop out the current frame, and plonk it in
                # the new pane - we add the new widget to the other
                # part
                oPart1, oParent = self._get_pane_to_replace()
                iTPos = self._do_replace_pane(oParent, oPart1, oNewPane,
                        iConfigPos)
                if not bVertical:
                    iPos = iTPos
            else:
                # This is the first HPane, or the 1st VPane we add, so
                # vbox has 2 children
                # The menu, and the one we want
                oPart1 = self.top_level_panes()[0]
                oParent = self.oVBox
                # Just split the window
                oCur = oParent.get_allocation()
                if not bVertical:
                    iPos = oCur.width/2
                oParent.remove(oPart1)
                oParent.pack_start(oNewPane)
            oNewPane.add1(oPart1)
            oNewPane.add2(oWidget)
            oPart1.show()
            oNewPane.show()
            oParent.show()
            if not bVertical:
                self._aHPanes.append(oNewPane)
            if iConfigPos == -1:
                oNewPane.set_position(iPos)
            else:
                oNewPane.set_position(iConfigPos)
        self.oVBox.show()
        self.reset_menu()
        # Reset frame focussed state
        if self._oFocussed:
            self.win_focus(None, None, self._oFocussed)
        return oWidget

    def remove_frame_by_name(self, sName):
        """Remove the pane with the given name"""
        oPane = self.find_pane_by_name(sName)
        if oPane is not None:
            self.remove_frame(oPane)

    def remove_frame(self, oFrame, bForceZero=False, bClose=False):
        """Remove the Frame oFrame from the window.

           bForceZero is used to force the removal of the last widget in
           the window.

           bClose is used to add the frame to the list of closed frames
           rather than destroying it and cleaning it up.
           """
        if oFrame is not None:
            oNeighbour = self._find_prev_frame(oFrame)
            if len(self.dOpenFrames) == 1:
                if not bForceZero:
                    # Break out, as we do nothing
                    return
                # Removing last widget, so just clear the vbox
                oWidget = self.top_level_panes()[0]
                self.oVBox.remove(oWidget)
            elif isinstance(oFrame.get_parent(), gtk.VPaned):
                # Removing a vertical frame, keep the correct child
                oParent = oFrame.get_parent()
                oKept = [x for x in oParent.get_children() if x != oFrame][0]
                oHPane = oParent.get_parent()
                oHPane.remove(oParent)
                oParent.remove(oFrame)
                oParent.remove(oKept)
                oHPane.add(oKept)
            elif len(self._aHPanes) == 1:
                # Removing from the only pane, so keep the other pane
                oThisPane = self._aHPanes[0] # Only pane
                self._aHPanes.remove(oThisPane)
                oKept = [x for x in oThisPane.get_children() if x != oFrame][0]
                # clear out pane
                oThisPane.remove(oFrame)
                oThisPane.remove(oKept)
                self.oVBox.remove(oThisPane)
                self.oVBox.pack_start(oKept)
            else:
                oFocussedPane = [x for x in self._aHPanes if oFrame in
                        x.get_children()][0]
                oKept = [x for x in oFocussedPane.get_children() if
                        x != oFrame][0]
                oParent = oFocussedPane.get_parent()
                oParent.remove(oFocussedPane)
                oFocussedPane.remove(oKept)
                oParent.add(oKept)
                # Housekeeping
                oFocussedPane.remove(oFrame)
                self._aHPanes.remove(oFocussedPane)
            self.oVBox.show()
            # Remove from dictionary of open panes
            sKey = self.dOpenFrames[oFrame]
            del self.dOpenFrames[oFrame]
            # Any cleanup events we need?
            if bClose:
                self.dClosedFrames[oFrame] = sKey
            else:
                oFrame.cleanup()
            if oFrame == self._oFocussed:
                if oNeighbour != oFrame:
                    # Removing the focussed frame, so we move
                    self.win_focus(None, None, oNeighbour)
                else:
                    # Can't do better than this, really
                    self.win_focus(None, None, None)
            self.reset_menu()

    def set_all_panes_equal(self):
        """Evenly distribute the space between all the frames."""
        oCurAlloc = self.oVBox.get_allocation()
        iNewPos = oCurAlloc.width / (len(self._aHPanes) + 1)
        self.set_pos_for_all_hpanes(iNewPos)

    def set_pos_for_all_hpanes(self, iNewPos):
        """Set all the panes to the same Position value"""
        oCurAlloc = self.oVBox.get_allocation()
        oMenuAlloc = self.__oMenu.get_allocation()
        iVertPos = (oCurAlloc.height - oMenuAlloc.height) / 2
        def set_pos_children(oPane, iPos, iVertPos):
            """Walk the tree in display order, setting positions accordingly"""
            oChild1 = oPane.get_child1()
            oChild2 = oPane.get_child2()
            if isinstance(oChild1, gtk.HPaned):
                iMyPos = iPos + set_pos_children(oChild1, iPos, iVertPos)
            else:
                if isinstance(oChild1, gtk.VPaned):
                    oChild1.set_position(iVertPos)
                iMyPos = iPos
            oPane.set_position(iMyPos)
            if isinstance(oChild2, gtk.HPaned):
                iMyPos += set_pos_children(oChild2, iPos, iVertPos)
            elif isinstance(oChild2, gtk.VPaned):
                oChild2.set_position(iVertPos)
            return iMyPos

        aTopLevelPanes = self.top_level_panes()
        for oPane in aTopLevelPanes:
            # Should only be 1 here
            if isinstance(oPane, gtk.HPaned):
                set_pos_children(oPane, iNewPos, iVertPos)
            elif isinstance(oPane, gtk.VPaned):
                # Do something sensible for single VPane case
                oPane.set_position(iVertPos)

    def set_busy_cursor(self):
        """Set the window cursor to indicate busy status"""
        # This needs to be on the top level widget, so has to be here
        # pylint: disable-msg=E1101
        # gtk properties confuse pylint here
        # Safe-guard for if we're called while shutting down
        if self.window:
            self.window.set_cursor(self._oBusyCursor)
            # Since we're about to do a buncg of CPU grinding, tell gtk
            # to redraw now
            gtk.gdk.flush()

    def restore_cursor(self):
        """Restore the ordinary cursor"""
        # pylint: disable-msg=E1101
        # gtk properties confuse pylint here
        # Safe-guard for if we're called while shutting down
        if self.window:
            self.window.set_cursor(None)

    def minimize_to_toolbar(self, oFrame):
        """Minimize the given frame to the main menu"""
        # don't allow last frame to be minimized
        if len(self.dOpenFrames) == 1:
            return
        self.__oToolbar.frame_to_toolbar(oFrame, self.dOpenFrames[oFrame])
        self.remove_frame(oFrame, bClose=True)

    def restore_from_toolbar(self, oFrame, sFrameTitle):
        """Restore the given frame from the toolbar"""
        oNewPane = self.add_pane_end()
        self.replace_frame(oNewPane, oFrame, sFrameTitle)
        self.win_focus(None, None, oFrame)
