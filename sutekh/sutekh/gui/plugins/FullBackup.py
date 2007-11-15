# FullBack.py
# Copyright 2007 Simon Cross <hodgestar@gmail.com>
# GPL - see COPYING for details

from sutekh.gui.PluginManager import CardListPlugin
from sutekh.core.SutekhObjects import AbstractCard
from sutekh.io.ZipFileWrapper import ZipFileWrapper
import gtk
import os

class FullBackup(CardListPlugin):
    dTableVersions = {}
    aModelsSupported = [AbstractCard]

    def __init__(self,*args,**kws):
        super(FullBackup,self).__init__(*args,**kws)

    # Dialog and Menu Item Creation

    def get_menu_item(self):
        """
        Overrides method from base class.
        """
        if not self.check_versions() or not self.check_model_type():
            return None

        iMenu = gtk.MenuItem("Backup")
        wMenu = gtk.Menu()
        iMenu.set_submenu(wMenu)

        iBackup = gtk.MenuItem("Save a Full Backup")
        iBackup.connect("activate", self.activateBackup)
        iRestore = gtk.MenuItem("Restore a Full Backup")
        iRestore.connect("activate", self.activateRestore)

        wMenu.add(iBackup)
        wMenu.add(iRestore)

        return iMenu

    def get_desired_menu(self):
        return "Plugin"

    # Backup

    def activateBackup(self,oWidget):
        dlg = self.makeBackupDialog()
        dlg.run()

    def makeBackupDialog(self):
        sName = "Choose a file to save the full backup to ..."

        oDlg = gtk.FileChooserDialog(sName,self.parent,action=gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons = (gtk.STOCK_OK, gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))

        oDlg.connect("response", self.handleBackupResponse)
        oDlg.set_local_only(True)
        oDlg.set_select_multiple(False)
        oDlg.show_all()

        return oDlg

    def handleBackupResponse(self,oDlg,oResponse):
        if oResponse == gtk.RESPONSE_OK:
            sFile = oDlg.get_filename()
            bContinue = True

            if os.path.exists(sFile):
                Complaint = gtk.MessageDialog(None,0,gtk.MESSAGE_WARNING,
                        gtk.BUTTONS_OK_CANCEL,"Overwrite existing file %s?" % sFile)
                bContinue = Complaint.run() != gtk.RESPONSE_CANCEL
                Complaint.destroy()

            if bContinue:
                try:
                    oFile = ZipFileWrapper(sFile)
                    oFile.doDumpAllToZip()
                except Exception, e:
                    sMsg = "Failed to write backup.\n\n" + str(e)
                    Complaint = gtk.MessageDialog(None,0,gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_CLOSE,sMsg)
                    Complaint.run()
                    Complaint.destroy()

        oDlg.destroy()

    # Restore

    def activateRestore(self,oWidget):
        dlg = self.makeRestoreDialog()
        dlg.run()

    def makeRestoreDialog(self):
        sName = "Restore a Full Backup ...."

        oDlg = gtk.FileChooserDialog(sName,self.parent,action=gtk.FILE_CHOOSER_ACTION_OPEN,
                buttons = (gtk.STOCK_OK, gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))

        oWarning = gtk.Label("This will delete all existing Physical Cards and Card Sets")
        oDlg.vbox.pack_start(oWarning,expand=False)
        oDlg.vbox.reorder_child(oWarning,0)
        oDlg.connect("response", self.handleRestoreResponse)
        oDlg.set_local_only(True)
        oDlg.set_select_multiple(False)
        oDlg.show_all()

        return oDlg

    def handleRestoreResponse(self,oDlg,oResponse):
        if oResponse == gtk.RESPONSE_OK:
            sFile = oDlg.get_filename()
            bContinue = True

            if not os.path.exists(sFile):
                Complaint = gtk.MessageDialog(None,0,gtk.MESSAGE_WARNING,
                        gtk.BUTTONS_OK_CANCEL,"Backup file %s does not seem to exist." % sFile)
                bContinue = Complaint.run() != gtk.RESPONSE_CANCEL
                Complaint.destroy()

            if bContinue:
                try:
                    oFile = ZipFileWrapper(sFile)
                    oFile.doRestoreFromZip(oCardLookup=self.cardlookup)
                    # restore successful, refresh display
                    self.reload_all()
                except Exception, e:
                    sMsg = "Failed to restore backup.\n\n" + str(e)
                    Complaint = gtk.MessageDialog(None,0,gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_CLOSE,sMsg)
                    Complaint.run()
                    Complaint.destroy()

        oDlg.destroy()

plugin = FullBackup
