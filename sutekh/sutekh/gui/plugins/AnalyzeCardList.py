# AnalyzeCardList.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Dialog to display deck analysis software
# Copyright 2006, 2007 Neil Muller <drnlmuller+sutekh@gmail.com>,
# Copyright 2006 Simon Cross <hodgestar@gmail.com>
# GPL - see COPYING for details
"""
Display interesting statistics and properties of the card set
"""

import gtk
from sutekh.core.SutekhObjects import PhysicalCardSet, \
        IAbstractCard
from sutekh.core.Filters import CardTypeFilter
from sutekh.gui.PluginManager import CardListPlugin
from sutekh.gui.SutekhDialog import SutekhDialog
from sutekh.gui.MultiSelectComboBox import MultiSelectComboBox

# utility functions
def _percentage(iNum, iTot, sDesc):
    """Utility function for calculating _percentages"""
    if iTot > 0:
        fPrec = iNum/float(iTot)
    else:
        fPrec = 0.0
    return '<i>(%5.3f %% of %s)</i>' % (fPrec*100, sDesc)

def escape(sInput):
    """Escape strings so that markup and special characters don't break
       things."""
    from gobject import markup_escape_text
    if sInput:
        return markup_escape_text(sInput)
    else:
        return sInput # pass None straigh through

def _get_abstract_cards(aCards):
    """Get the asbtract cards given the list of names"""
    return [IAbstractCard(x) for x in aCards]

def _lookup_discipline(sKey, dDisciplines):
    """Return the object with the fullname sKey"""
    return [x for x in dDisciplines if sKey == x.fullname][0]

def _disc_sort_key(oTuple):
    """Ensure we sort the disciplines or virtues on the right key"""
    return (oTuple[1][1], oTuple[0].fullname)

def _format_card_line(sString, sTrailer, iNum, iNumberLibrary):
    """Format card lines for notebook"""
    sPer = _percentage(iNum, iNumberLibrary, "Library")
    return "Number of %(type)s %(trail)s = %(num)d %(per)s\n" % {
            'type' : sString,
            'trail' : sTrailer,
            'num' : iNum,
            'per' : sPer, }

def _get_card_costs(aCards):
    """Calculate the cost of the list of Abstract Cards

       Return lists of costs, for pool, blood and convictions
       Each list contains: Number with variable cost, Maximum Cost, Total Cost,
       Number of cards with a cost
       """
    dCosts = {}
    for sType in ['blood', 'pool', 'conviction']:
        dCosts.setdefault(sType, [0, 0, 0, 0])
    for oAbsCard in aCards:
        if oAbsCard.cost is not None:
            dCosts[oAbsCard.costtype][3] += 1
            if oAbsCard.cost == -1:
                dCosts[oAbsCard.costtype][0] += 1
            else:
                iMaxCost = dCosts[oAbsCard.costtype][1]
                dCosts[oAbsCard.costtype][1] = max(iMaxCost, oAbsCard.cost)
                dCosts[oAbsCard.costtype][2] += oAbsCard.cost
    return dCosts['blood'], dCosts['pool'], dCosts['conviction']

def _get_card_disciplines(aCards):
    """Extract the set of disciplines and virtues from the cards"""
    dDisciplines = {}
    dVirtues = {}
    iNoneCount = 0
    for oAbsCard in aCards:
        if len(oAbsCard.discipline) > 0:
            aThisDisc = [oP.discipline.fullname for oP
                    in oAbsCard.discipline]
        else:
            aThisDisc = []
        if len(oAbsCard.virtue) > 0:
            aThisVirtue = [oV.fullname for oV in oAbsCard.virtue]
        else:
            aThisVirtue = []
        for sDisc in aThisDisc:
            dDisciplines.setdefault(sDisc, 0)
            dDisciplines[sDisc] += 1
        for sVirtue in aThisVirtue:
            dVirtues.setdefault(sVirtue, 0)
            dVirtues[sVirtue] += 1
        if len(oAbsCard.discipline) == 0 and len(oAbsCard.virtue) == 0:
            iNoneCount += 1
    return dDisciplines, dVirtues, iNoneCount

def _get_card_clan_multi(aCards):
    """Extract the clan requirements and the multi discipline cards
       form the list of Abstract Cards"""
    dClan = {}
    iClanRequirement = 0
    dMulti = {}
    for oAbsCard in aCards:
        if len(oAbsCard.clan) > 0:
            iClanRequirement += 1
            aClans = [x.name for x in oAbsCard.clan]
            for sClan in aClans:
                dClan.setdefault(sClan, 0)
                dClan[sClan] += 1
        aTypes = [x.name for x in oAbsCard.cardtype]
        if len(aTypes) > 1:
            sKey = "/".join(sorted(aTypes))
            dMulti.setdefault(sKey, 0)
            dMulti[sKey] += 1
    return iClanRequirement, dClan, dMulti

def _format_cost_numbers(sCardType, sCostString, aCost, iNum):
    """Format the display of the card cost information"""
    sVarPercent = _percentage(aCost[0], iNum, '%s cards' % sCardType)
    sNumPercent = _percentage(aCost[3], iNum, '%s cards' % sCardType)
    sText = "Most Expensive %(name)s Card  (%(type)s) = %(max)d\n" \
            "Cards with variable cost = %(var)d %(per)s\n" \
            "Cards with %(type)s cost = %(numcost)d %(percost)s\n" \
            "Average %(name)s card %(type)s cost = %(avg)5.3f\n" % {
                    'name' : sCardType,
                    'type' : sCostString,
                    'var' : aCost[0],
                    'per' : sVarPercent,
                    'max' : aCost[1],
                    'avg' : aCost[2] / float(iNum),
                    'numcost' : aCost[3],
                    'percost' : sNumPercent,
                    }
    return sText

def _format_disciplines(sDiscType, dDisc, iNum):
    """Format the display of disciplines and virtues"""
    sText = ''
    for sDisc, iNum in sorted(dDisc.items(), key=lambda x: x[1],
            reverse=True):
        sText += 'Number of cards requiring %s %s = %d\n' % (sDiscType,
                sDisc, iNum)
    return sText

def _format_clan(sCardType, iClanRequirement, dClan, iNum):
    """Format the clan requirements list for display"""
    sText = ''
    if iClanRequirement > 0:
        sPer = _percentage(iClanRequirement, iNum, 'Library')
        sText += "Number of %(type)s with a Clan requirement = %(num)d " \
                "%(per)s\n" % { 'type' : sCardType, 'num' : iClanRequirement,
                'per' : sPer, }
        for sClan, iClanNum in sorted(dClan.items(), key=lambda x: x[1],
                reverse=True):
            sPer = _percentage(iClanNum, iNum, '%s cards' % sCardType)
            sText += 'Number of %(type)s requiring %(clan)s = %(num)d ' \
                    '%(per)s\n' % { 'type' : sCardType, 'clan' : sClan,
                    'num' : iClanNum, 'per' : sPer, }
    return sText

def _format_multi(sCardType, dMulti, iNum):
    """Format the multi-role cards list for display"""
    sText = ''
    for sType, iMulti in sorted(dMulti.items(), key=lambda x: x[1],
            reverse=True):
        sPer = _percentage(iMulti, iNum, '%s cards' % sCardType)
        sText += '%(num)d %(type)s cards are %(multitype)s cards' \
                ' %(per)s\n' % { 'num' : iMulti, 'type' : sCardType,
                'multitype' : sType, 'per' : sPer, }
    return sText


def _wrap(sText):
    """Return a gtk.Label which wraps the given text"""
    oLabel = gtk.Label()
    oLabel.set_line_wrap(True)
    oLabel.set_width_chars(80)
    oLabel.set_alignment(0, 0) # Align top-left
    oLabel.set_markup(sText)
    return oLabel

class DisciplineNumberSelect(gtk.HBox):
    """Holds a combo box and a discpline list for choosing a list
       of disciplines to use."""
    # pylint: disable-msg=R0904
    # gtk.Widget so many public methods

    _sUseList = 'Use list of disciplines'

    def __init__(self, aSortedDisciplines, oDlg):
        super(DisciplineNumberSelect, self).__init__(False, 2)
        self._aSortedDisciplines = aSortedDisciplines
        # Never show more than 5 disciplines here - people can use the
        # discpline list in the combo box if they want more
        self._oComboBox = gtk.combo_box_new_text()
        for iNum in range(1, min(5, len(aSortedDisciplines)) + 1):
            self._oComboBox.append_text(str(iNum))
        self._oComboBox.append_text(self._sUseList)
        self._oComboBox.set_active(1)
        self.pack_start(gtk.Label('Number of Disciplines'))
        self.pack_start(self._oComboBox)
        self.pack_start(gtk.Label(' : '))
        self._oDiscWidget = MultiSelectComboBox(oDlg)
        self._oDiscWidget.fill_list(self._aSortedDisciplines)
        self._oDiscWidget.set_sensitive(False)
        self._oDiscWidget.set_list_size(200, 400)
        self.pack_start(self._oDiscWidget)
        self._oComboBox.connect('changed', self._combo_changed)

    # pylint: disable-msg=W0613
    # oWidget required by function signature
    def _combo_changed(self, oWidget):
        """Toggle the sensitivity of the Discipline select widget as needed"""
        if self._oComboBox.get_active_text() == self._sUseList:
            self._oDiscWidget.set_sensitive(True)
        else:
            self._oDiscWidget.set_sensitive(False)

    def get_disciplines(self):
        """Get the list of disciplines to use."""
        if self._oComboBox.get_active_text() == 'Use list of disciplines':
            aTheseDiscs = self._oDiscWidget.get_selection()
        else:
            iNumDiscs = int(self._oComboBox.get_active_text())
            aTheseDiscs = self._aSortedDisciplines[:iNumDiscs]
        return aTheseDiscs


class AnalyzeCardList(CardListPlugin):
    """
    Plugin to analyze card sets.
    Displays various interesting stats, and does
    a Happy Family analysis of the deck
    """
    dTableVersions = {PhysicalCardSet : [3, 4, 5]}
    aModelsSupported = [PhysicalCardSet]

    aCryptTypes = ['Vampire', 'Imbued']
    # Map of titles to votes
    # TODO: Defined this in SutekhObjects
    dTitleVoteMap = {
            'Primogen' : 1,
            'Prince' : 2,
            'Justicar' : 3,
            'Inner Circle' : 4,
            'Priscus' : 3,
            'Bishop' : 1,
            'Archbishop' : 2,
            'Cardinal' : 3,
            'Regent' : 4,
            'Independent with 1 vote' : 1,
            'Independent with 2 votes' : 2,
            'Independent with 3 votes' : 3,
            'Magaji' : 2,
            }

    def get_menu_item(self):
        """Register on the 'Plugins' Menu"""
        if not self.check_versions() or not self.check_model_type():
            return None
        oAnalyze = gtk.MenuItem("Analyze Deck")
        oAnalyze.connect("activate", self.activate)
        return ('Plugins', oAnalyze)

    # pylint: disable-msg=W0613, W0201
    # W0613 - oWidget required by gtk function signature
    # W0201 - We define a lot of class variables here, because a) this is the
    # plugin entry point, and, b) they need to reflect the current CardSet,
    # so they can't be filled properly in __init__
    def activate(self, oWidget):
        """Create the actual dialog, and populate it"""
        oDlg = SutekhDialog( "Analysis of Card List", self.parent,
                gtk.DIALOG_DESTROY_WITH_PARENT,
                (gtk.STOCK_OK, gtk.RESPONSE_OK))
        oDlg.connect("response", lambda oDlg, resp: oDlg.destroy())
        dConstruct = {
                'Vampire' : self._process_vampire,
                'Imbued' : self._process_imbued,
                'Combat' : self._process_combat,
                'Reaction' : self._process_reaction,
                'Action' : self._process_action,
                'Action Modifier' : self._process_action_modifier,
                'Retainer' : self._process_retainer,
                'Equipment' : self._process_equipment,
                'Ally' : self._process_allies,
                'Political Action' : self._process_political_action,
                'Power' : self._process_power,
                'Conviction' : self._process_conviction,
                'Event' : self._process_event,
                'Master' : self._process_master,
                'Multirole' : self._process_multi,
                }

        self.dTypeNumbers = {}
        dCardLists = {}

        for sCardType in dConstruct:
            if sCardType != 'Multirole':
                oFilter = CardTypeFilter(sCardType)
                dCardLists[sCardType] = _get_abstract_cards(
                        self.model.get_card_iterator(oFilter))
                self.dTypeNumbers[sCardType] = len(dCardLists[sCardType])
            else:
                 # Multirole values start empty, and are filled in later
                dCardLists[sCardType] = []
                self.dTypeNumbers[sCardType] = 0

        oHappyBox = gtk.VBox(False, 2)

        aAllCards = _get_abstract_cards(self.model.get_card_iterator(None))
        self.iTotNumber = len(aAllCards)
        self.dCryptStats = {}
        self.dLibraryStats = {}

        self.iCryptSize = sum([self.dTypeNumbers[x] for x in self.aCryptTypes])
        self.iNumberLibrary = len(aAllCards) - self.iCryptSize
        self.get_crypt_stats(dCardLists['Vampire'], dCardLists['Imbued'])
        self.get_library_stats(aAllCards, dCardLists)
        # Do happy family analysis
        self.happy_families_init(oHappyBox, oDlg)

        # Fill the dialog with the results
        oNotebook = gtk.Notebook()
        # Oh, popup_enable and scrollable - how I adore thee
        oNotebook.set_scrollable(True)
        oNotebook.popup_enable()
        oMainBox = gtk.VBox(False, 2)
        oNotebook.append_page(oMainBox, gtk.Label('Basic Info'))
        oNotebook.append_page(oHappyBox, gtk.Label('Happy Families Analysis'))

        # overly clever? crypt cards first, then alphabetical, then multirole
        aOrderToList = self.aCryptTypes + \
                [x for x in sorted(self.dTypeNumbers) if (x not in
                    self.aCryptTypes and x != 'Multirole')] + ['Multirole']
        for sCardType in aOrderToList:
            if self.dTypeNumbers[sCardType] > 0:
                fProcess = dConstruct[sCardType]
                oNotebook.append_page(_wrap(fProcess(dCardLists[sCardType])),
                        gtk.Label(sCardType))

        # Setup the main notebook
        oMainBox.pack_start(_wrap(self._prepare_main()))
        if self.iNumberLibrary > 0:
            oMainBox.pack_start(self._process_library())
        # pylint: disable-msg=E1101
        # vbox methods not seen
        oDlg.vbox.pack_start(oNotebook)
        oDlg.show_all()
        oNotebook.set_current_page(0)
        oDlg.run()

    # pylint: enable-msg=W0613

    def get_crypt_stats(self, aVampireCards, aImbuedCards):
        """Extract the relevant statistics about the crypt from the lists
           of cards."""
        def get_info(aVampires, aImbued, sClass):
            """Extract the minimum and maximum for the sets into
               self.dCryptStats, using keys of the form 'vampire min sClass'"""
            sMax = 'max %s' % sClass
            sMin = 'min %s' % sClass
            if len(aImbued):
                iIMax = self.dCryptStats['imbued ' + sMax] = max(aImbued)
                iIMin = self.dCryptStats['imbued ' + sMin] = min(aImbued)
            else:
                iIMax = -500
                iIMin = 500
            if len(aVampires):
                iVMax = self.dCryptStats['vampire ' + sMax] = max(aVampires)
                iVMin = self.dCryptStats['vampire ' + sMin] = min(aVampires)
            else:
                iVMax = -500
                iVMin = 500
            self.dCryptStats[sMax] = max(iVMax, iIMax)
            self.dCryptStats[sMin] = min(iVMin, iIMin)

        get_info([x.group for x in aVampireCards],
                [x.group for x in aImbuedCards], 'group')
        get_info([x.capacity for x in aVampireCards],
                [x.life for x in aImbuedCards], 'cost')
        aAllCosts = sorted([x.capacity for x in aVampireCards] + \
                [x.life for x in aImbuedCards])
        self.dCryptStats['total cost'] = sum(aAllCosts)
        self.dCryptStats['min draw'] = sum(aAllCosts[0:4])
        self.dCryptStats['max draw'] = sum(aAllCosts[-1:-5:-1])
        # Extract discipline stats (will be used in display + HF)
        dDiscs = {}
        self.dCryptStats['crypt discipline'] = dDiscs
        for oCard in aVampireCards:
            for oDisc in oCard.discipline:
                dDiscs.setdefault(oDisc.discipline, ['discipline', 0, 0])
                dDiscs[oDisc.discipline][1] += 1
                if oDisc.level == 'superior':
                    dDiscs[oDisc.discipline][2] += 1
        # We treat virtues as inferior discipline for happy family analysis
        for oCard in aImbuedCards:
            for oVirt in oCard.virtue:
                dDiscs.setdefault(oVirt, ['virtue', 0, 0])
                dDiscs[oVirt.discipline][1] += 1

    def get_library_stats(self, aAllCards, dCardLists):
        """Extract the relevant library stats from the list of cards"""
        aCryptCards = []
        for sType in self.aCryptTypes:
            aCryptCards.extend(dCardLists[sType])
        aLibraryCards = [x for x in aAllCards if x not in aCryptCards]
        # Extract the relevant stats
        self.dLibraryStats['clan'] = {'No Clan' : 0}
        self.dLibraryStats['discipline'] = {'No Discipline' : 0}
        for oCard in aLibraryCards:
            if len(oCard.cardtype) > 1:
                self.dTypeNumbers['Multirole'] += 1
                dCardLists['Multirole'].append(oCard)
            if len(oCard.clan) > 0:
                aClans = [x.name for x in oCard.clan]
            elif len(oCard.creed) > 0:
                aClans = [x.name for x in oCard.creed]
            else:
                aClans = ['No Clan']
            for sClan in aClans:
                self.dLibraryStats['clan'].setdefault(sClan, 0)
                self.dLibraryStats['clan'][sClan] += 1
            if len(oCard.discipline) > 0:
                aDisciplines = [oP.discipline.fullname for oP in
                        oCard.discipline]
            elif len(oCard.virtue) > 0:
                aDisciplines = [oP.virtue.fullname for oP in oCard.virtue]
            else:
                aDisciplines = ['No Discipline']
            for sDisc in aDisciplines:
                self.dLibraryStats['discipline'].setdefault(sDisc, 0)
                self.dLibraryStats['discipline'][sDisc] += 1

    def _prepare_main(self):
        """Setup the main notebook display"""
        oCS = self.get_card_set()

        sMainText = "Analysis Results for :\n\t\t<b>%(name)s</b>\n" \
                "\t\tby <i>%(author)s</i>\n\t\tDescription: <i>%(desc)s</i>" \
                "\n\n" % {
                        'name' : escape(self.view.sSetName),
                        'author' : escape(oCS.author),
                        'desc' : escape(oCS.comment),
                        }

        # Set main notebook text
        for sCardType in self.aCryptTypes:
            if self.dTypeNumbers[sCardType] > 0:
                sMainText += 'Number of %s = %d\n' % (sCardType,
                        self.dTypeNumbers[sCardType])
        if self.dTypeNumbers['Vampire'] > 0 and \
                self.dTypeNumbers['Imbued'] > 0:
            sMainText += "Total Crypt size = %d\n" % self.iCryptSize
        sMainText += "Minimum Group in Crpyt = %d\n" % \
                self.dCryptStats['min group']
        sMainText += "Maximum Group in Crypt = %d\n" % \
                self.dCryptStats['max group']

        if self.iCryptSize < 12:
            sMainText += '<span foreground = "red">Less than 12 Crypt Cards' \
                    '</span>\n'

        if self.dCryptStats['max group'] - self.dCryptStats['min group'] > 1:
            sMainText += '<span foreground = "red">Group Range Exceeded' \
                    '</span>\n'

        sMainText += '\nMaximum cost in crypt = %d\n' % \
                self.dCryptStats['max cost']
        sMainText += 'Minimum cost in crypt = %d\n' % \
                self.dCryptStats['min cost']
        fAvg = float(self.dCryptStats['total cost']) / self.iCryptSize
        sMainText += 'Average cost = %3.2f (%3.2f average crypt draw cost)\n' \
                % (fAvg, 4 * fAvg)
        sMainText += 'Minimum draw cost = %d\n' % self.dCryptStats['min draw']
        sMainText += 'Maximum Draw cost = %d\n' % self.dCryptStats['max draw']

        sMainText += "Total Library Size = " + str(self.iNumberLibrary) + "\n"

        return sMainText

    def _process_library(self):
        """Create a notebook for the basic library card overview"""
        oLibNotebook = gtk.Notebook()
        # Stats by card type
        sTypeText = ''
        # Show card types, sorted by number (then alphabetical by type)
        for sType, iCount in sorted(self.dTypeNumbers.items(),
                key=lambda x: (x[1], x[0]), reverse=True):
            if sType not in self.aCryptTypes and sType != 'Multirole' and \
                    iCount > 0:
                sTypeText += _format_card_line(sType, 'cards', iCount,
                        self.iNumberLibrary)
        if self.dTypeNumbers['Multirole'] > 0:
            sTypeText += '\n' + _format_card_line('Multirole', 'cards',
                    self.dTypeNumbers['Multirole'], self.iNumberLibrary)
        oLibNotebook.append_page(_wrap(sTypeText),
                gtk.Label('Card Types'))
        # Stats by discipline
        sDiscText = _format_card_line('Master', 'cards',
                self.dTypeNumbers['Master'], self.iNumberLibrary)
        sDiscText += _format_card_line('non-master cards with No '
                'discipline requirement', '',
                self.dLibraryStats['discipline']['No Discipline'],
                self.iNumberLibrary) + '\n'
        # sort by number, then name
        for sDisc, iNum in sorted(self.dLibraryStats['discipline'].items(),
                key=lambda x: (x[1], x[0]), reverse=True):
            if sDisc != 'No Discipline' and iNum > 0:
                sDiscDesc = 'non-master cards with %s' % sDisc
                sDiscText += _format_card_line(sDiscDesc, '', iNum,
                        self.iNumberLibrary)
        oLibNotebook.append_page(_wrap(sDiscText),
                gtk.Label('Disciplines'))
        # Stats by clan requirement
        sClanText = _format_card_line('cards with No clan requirement', '',
                self.dLibraryStats['clan']['No Clan'], self.iNumberLibrary) \
                        + '\n'
        for sClan, iNum in sorted(self.dLibraryStats['clan'].items()):
            if sClan != 'No Clan' and iNum > 0:
                sClanDesc = 'cards requiring %s' % sClan
                sClanText += _format_card_line(sClanDesc, '', iNum,
                        self.iNumberLibrary)
        oLibNotebook.append_page(_wrap(sClanText),
                gtk.Label('Clan Requirements'))
        return oLibNotebook

    def _process_vampire(self, aCards):
        """Process the list of vampires"""
        dDeckDetails = {
                'vampires' : {},
                'titles' : {},
                'clans' : {},
                'votes' : 0,
                }
        iNum = self.dTypeNumbers['Vampire']
        for oAbsCard in aCards:
            dDeckDetails['vampires'].setdefault(oAbsCard.name, 0)
            dDeckDetails['vampires'][oAbsCard.name] += 1
            for oClan in oAbsCard.clan:
                dDeckDetails['clans'].setdefault(oClan, 0)
                dDeckDetails['clans'][oClan] += 1
            for oTitle in oAbsCard.title:
                dDeckDetails['titles'].setdefault(oTitle, 0)
                dDeckDetails['titles'][oTitle] += 1
                dDeckDetails['votes'] += self.dTitleVoteMap[oTitle.name]
        # Build up Text
        sVampText = "\t\t<b>Vampires :</b>\n\n"
        sVampText += '<span foreground = "blue">Basic Crypt stats</span>\n'
        sVampText += "Number of Vampires = %d %s\n" % (iNum,
                _percentage(iNum, self.iCryptSize, "Crypt"))
        sVampText += "Number of Unique Vampires = %d\n" % len(
                dDeckDetails['vampires'])
        sVampText += "Minimum Group is : %d\n" % \
                self.dCryptStats['vampire min group']
        sVampText += "Maximum Group is : %d\n" % \
                self.dCryptStats['vampire max group']
        sVampText += '\n<span foreground = "blue">Crypt cost</span>\n'
        sVampText += "Cheapest is : %d\n" % \
                self.dCryptStats['vampire min cost']
        sVampText += "Most Expensive is : %d\n" % \
                self.dCryptStats['vampire max cost']
        sVampText += "Average Capacity is : %2.3f\n\n" % (
                sum([x.capacity for x in aCards]) / float(iNum))
        sVampText += '<span foreground = "blue">Clans</span>\n'
        for oClan, iCount in dDeckDetails['clans'].iteritems():
            sVampText += "%d Vampires of clan %s %s\n" % (iCount,
                    oClan.name, _percentage(iCount, self.iCryptSize, "Crypt"))
        sVampText += '\n<span foreground = "blue">Titles</span>\n'
        for oTitle, iCount in dDeckDetails['titles'].iteritems():
            sVampText += "%d vampires with the title %s (%d votes)\n" % (
                    iCount, oTitle.name, self.dTitleVoteMap[oTitle.name])
        sVampText += "%d titles in the crypt %s\n" % (
                len(dDeckDetails['titles']), _percentage(len(
                    dDeckDetails['titles']), self.iCryptSize, "Crypt"))
        sVampText += "%d votes from titles in the crypt. Average votes per" \
                " vampire is %2.3f\n" % (dDeckDetails['votes'],
                        dDeckDetails['votes'] / float(iNum))
        sVampText += '\n<span foreground = "blue">Disciplines</span>\n'
        for oDisc, aInfo in sorted(
                self.dCryptStats['crypt discipline'].iteritems(),
                key=_disc_sort_key, reverse=True):
            if aInfo[0] == 'discipline':
                sVampText += "%(infcount)d Vampires with %(disc)s %(iper)s," \
                        " %(supcount)d at Superior %(sper)s\n" % {
                                'disc' : oDisc.fullname,
                                'infcount' : aInfo[1],
                                'iper' : _percentage(aInfo[1],
                                    self.iCryptSize, "Crypt"),
                                'supcount' : aInfo[2],
                                'sper' : _percentage(aInfo[2],
                                    self.iCryptSize, "Crypt"),
                                }
        return sVampText

    def _process_imbued(self, aCards):
        """Fill the Imbued tab"""
        dDeckImbued = {}
        dDeckCreed = {}
        iNum = self.dTypeNumbers['Imbued']
        for oAbsCard in aCards:
            dDeckImbued.setdefault(oAbsCard.name, 0)
            dDeckImbued[oAbsCard.name] += 1
            for oCreed in oAbsCard.creed:
                dDeckCreed.setdefault(oCreed, 0)
                dDeckCreed[oCreed] += 1
        # Build up Text
        sImbuedText = "\t\t<b>Imbued</b>\n\n"
        sImbuedText += '<span foreground = "blue">Basic Crypt stats</span>\n'
        sImbuedText += "Number of Imbued = %d %s\n" % (iNum, _percentage(iNum,
            self.iCryptSize, "Crypt"))
        sImbuedText += "Number of Unique Imbued = %d\n" % len(dDeckImbued)
        sImbuedText += 'Minimum Group is : %d\n' % \
                self.dCryptStats['imbued min group']
        sImbuedText += 'Maximum Group is : %d\n' % \
                self.dCryptStats['imbued max group']
        sImbuedText += '\n<span foreground = "blue">Crypt cost</span>\n'
        sImbuedText += "Cheapest is : %d\n" % \
                self.dCryptStats['imbued min cost']
        sImbuedText += "Most Expensive is : %d\n" % \
                self.dCryptStats['imbued max cost']
        sImbuedText += "Average Life is : %2.3f\n\n" % (
                sum([x.life for x in aCards]) / float(iNum))
        for oCreed, iCount in dDeckCreed.iteritems():
            sImbuedText += "%d Imbued of creed %s %s\n" % (iCount,
                    oCreed.name, _percentage(iCount, self.iCryptSize, "Crypt"))
        for oVirtue, aInfo in sorted(
                self.dCryptStats['crypt discipline'].iteritems(),
                key=_disc_sort_key, reverse=True):
            if aInfo[0] == 'virtue':
                sImbuedText += "%d Imbued with %s %s\n" % (aInfo[1],
                        oVirtue.fullname, _percentage(aInfo[1],
                            self.iCryptSize, "Crypt"))
        return sImbuedText

    def _process_master(self, aCards):
        """Display the stats for Master Cards"""
        # pylint: disable-msg=W0612
        # aBlood, aConviction unused, since Master cost isn't paid by minions
        iNum = self.dTypeNumbers['Master']
        aBlood, aPool, aConviction = _get_card_costs(aCards)
        iClanRequirement, dClan, dMulti = _get_card_clan_multi(aCards)
        # Build up Text
        sText = "\t\t<b>Master Cards :</b>\n\n"
        sText += "Number of Masters = %d %s\n" % (self.dTypeNumbers['Master'],
                _percentage(iNum, self.iNumberLibrary, "Library"))
        if aPool[1] > 0:
            sText += '\n<span foreground = "blue">Cost</span>\n'
            sText += _format_cost_numbers('Master', 'pool', aPool, iNum)
        if iClanRequirement > 0:
            sText += '\n<span foreground = "blue">Clan/Creed</span>\n'
            sText += _format_clan('Master', iClanRequirement, dClan, iNum)
        if len(dMulti) > 0:
            sText += '\n' + _format_multi('Master', dMulti, iNum)
        return sText

    def _default_text(self, aCards, sType):
        """Standard boilerplate for most card types"""
        iNum = self.dTypeNumbers[sType]
        aBlood, aPool, aConviction = _get_card_costs(aCards)
        iClanRequirement = 0
        dDisciplines, dVirtues, iNoneCount = _get_card_disciplines(aCards)
        iClanRequirement, dClan, dMulti = _get_card_clan_multi(aCards)
        # Build up Text
        sPerCards = _percentage(iNum, self.iNumberLibrary, 'Library')
        sText = "\t\t<b>%(type)s Cards :</b>\n\n" \
                "Number of %(type)s cards = %(num)d %(per)s\n" % {
                        'type' : sType,
                        'num' : iNum,
                        'per' : sPerCards, }
        if aBlood[1] > 0 or aPool[1] > 0 or aConviction[1] > 0:
            sText += '\n<span foreground = "blue">Costs</span>\n'
        if aBlood[1] > 0:
            sText += _format_cost_numbers(sType, 'blood', aBlood, iNum)
        if aConviction[1] > 0:
            sText += _format_cost_numbers(sType, 'conviction', aConviction,
                    iNum)
        if aPool[1] > 0:
            sText += _format_cost_numbers(sType, 'pool', aPool, iNum)
        if iClanRequirement > 0:
            sText += '\n<span foreground = "blue">Clan/Creed</span>\n'
            sText += _format_clan(sType, iClanRequirement, dClan, iNum)
        sText += '\n<span foreground = "blue">Discipline/Virtues</span>\n'
        sText += 'Number of cards with no discipline/virtue requirement = ' \
                '%d\n' % iNoneCount
        if len(dDisciplines) > 0:
            sText += _format_disciplines('discipline', dDisciplines, iNum)
        if len(dVirtues) > 0:
            sText += _format_disciplines('virtue', dVirtues, iNum)
        if len(dMulti) > 0:
            sText += '\n' + _format_multi(sType, dMulti, iNum)
        return sText

    def _process_combat(self, aCards):
        """Fill the combat tab"""
        sText = self._default_text(aCards, 'Combat')
        return sText

    def _process_action_modifier(self, aCards):
        """Fill the Action Modifier tab"""
        sText = self._default_text(aCards, 'Action Modifier')
        return sText

    def _process_reaction(self, aCards):
        """Fill the reaction tab"""
        sText = self._default_text(aCards, 'Reaction')
        return sText

    def _process_event(self, aCards):
        """Fill the events tab"""
        iNumEvents = len(aCards)
        sEventText = "\t\t<b>Event Cards :</b>\n\n"
        sEventText += "Number of Event cards = %d %s\n\n" % (iNumEvents,
                _percentage(iNumEvents, self.iNumberLibrary, "Library"))
        sEventText += '<span foreground = "blue">Event classes</span>\n'
        dEventTypes = {}
        for oCard in aCards:
            sType = oCard.text.split('.', 1)[0] # first word is type
            dEventTypes.setdefault(sType, 0)
            dEventTypes[sType] += 1
        for sType, iCount in dEventTypes.iteritems():
            sEventText += '%d of type %s : %s (%s) \n' % (iCount, sType,
                    _percentage(iCount, iNumEvents, 'Events'),
                    _percentage(iCount, self.iNumberLibrary, 'Library'))
        return sEventText

    def _process_action(self, aCards):
        """Fill the actions tab"""
        sText = self._default_text(aCards, 'Action')
        return sText

    def _process_political_action(self, aCards):
        """Fill the Political Actions tab"""
        sText = self._default_text(aCards, 'Political Action')
        return sText

    def _process_allies(self, aCards):
        """Fill the allies tab"""
        sText = self._default_text(aCards, 'Ally')
        return sText

    def _process_retainer(self, aCards):
        """Fill the retainer tab"""
        sText = self._default_text(aCards, 'Retainer')
        return sText

    def _process_equipment(self, aCards):
        """Fill the equipment tab"""
        sText = self._default_text(aCards, 'Equipment')
        return sText

    def _process_conviction(self, aCards):
        """Fill the conviction tab"""
        sText = self._default_text(aCards, 'Conviction')
        return sText

    def _process_power(self, aCards):
        """Fill the power tab"""
        sText = self._default_text(aCards, 'Power')
        return sText

    def _process_multi(self, aCards):
        """Fill the multirole card tab"""
        dMulti = {}
        sPerCards = _percentage(self.dTypeNumbers['Multirole'],
                self.iNumberLibrary, 'Library')
        sText = "\t\t<b>Multirole Cards :</b>\n\n" \
                "Number of Multirole cards = %(num)d %(per)s\n" % {
                        'num' : self.dTypeNumbers['Multirole'],
                        'per' : sPerCards
                        }
        for oAbsCard in aCards:
            aTypes = [x.name for x in oAbsCard.cardtype]
            if len(aTypes) > 1:
                sKey = "/".join(sorted(aTypes))
                dMulti.setdefault(sKey, 0)
                dMulti[sKey] += 1
        for sMultiType, iNum in sorted(dMulti.items(), key=lambda x: x[1],
                reverse=True):
            sPer = _percentage(iNum, self.iNumberLibrary, 'Library')
            sText += 'Number of %(multitype)s cards = %(num)d %(per)s\n' % {
                    'multitype' : sMultiType,
                    'num' : iNum,
                    'per' : sPer,
                    }

        return sText

    def happy_families_init(self, oHFVBox, oDlg):
        """Setup data and tab for HF analysis"""
        oMainLabel = gtk.Label()
        oHFVBox.pack_start(oMainLabel)
        # Build up Text
        sHappyFamilyText = "\t\t<b>Happy Families Analysis :</b>\n"
        if self.dTypeNumbers['Imbued'] > 0:
            sHappyFamilyText += '\n<span foreground = "red">This is not' \
                    ' optimised for Imbued, and treats them as small ' \
                    'vampires</span>\n'
        if self.iCryptSize == 0:
            sHappyFamilyText += '\n<span foreground = "red">Need to have' \
                    ' a crypt to do the analysis</span>\n'
            oMainLabel.set_markup(sHappyFamilyText)
            oHFVBox.show_all()
            return
        if len(self.dCryptStats['crypt discipline']) < 1:
            # Crypt only has Smudge, for example
            sHappyFamilyText += '\n<span foreground = "red">Need disciplines' \
                    ' in the crypt to do analysis</span>\n'
            oMainLabel.set_markup(sHappyFamilyText)
            oHFVBox.show_all()
            return
        # OK, for analysis, so set eveything up
        # Masters analysis
        iHFMasters = int(round(0.2 * self.iNumberLibrary))
        iNonMasters = self.iNumberLibrary - self.dTypeNumbers['Master']
        sHappyFamilyText += "\n\t<b>Master Cards</b>\n"
        sHappyFamilyText += str(self.dTypeNumbers['Master']) + " Masters " + \
                _percentage(self.dTypeNumbers['Master'],
                        self.iNumberLibrary, "Library") + \
                ",\nHappy Families recommends 20%, which would be " + \
                str(iHFMasters) + '  : '
        sHappyFamilyText += "<span foreground = \"blue\">Difference = " + \
                str(abs(iHFMasters - self.dTypeNumbers['Master'])) + \
                "</span>\n"
        # Discipline analysis
        aSortedDiscs = [x[0].fullname for x in sorted(
            self.dCryptStats['crypt discipline'].items(), key=_disc_sort_key,
            reverse=True)]
        oMainLabel.set_markup(sHappyFamilyText)
        oDiscSelect = DisciplineNumberSelect(aSortedDiscs, oDlg)
        oHFVBox.pack_start(oDiscSelect, False, False)
        oResLabel = gtk.Label()
        oButton = gtk.Button('Recalculate Happy Family Analysis')
        oButton.connect('clicked', self._redo_happy_family, oDiscSelect,
                oResLabel)
        oHFVBox.pack_start(oButton, False, False)
        oResLabel.set_markup(self._happy_lib_analysis(aSortedDiscs[:2],
            iNonMasters))
        oHFVBox.pack_start(oResLabel)
        oHFVBox.show_all()

    # pylint: disable-msg=W0613
    # oButton Required by function signature
    def _redo_happy_family(self, oButton, oDiscSelect, oResLabel):
        """Redo the HF analysis based on button press"""
        aTheseDiscs = oDiscSelect.get_disciplines()
        if not aTheseDiscs:
            return # Just ignore the zero selection case
        iNonMasters = self.iNumberLibrary - self.dTypeNumbers['Master']
        oResLabel.hide()
        oResLabel.set_markup(self._happy_lib_analysis(aTheseDiscs,
            iNonMasters))
        oResLabel.show()
        oResLabel.get_parent().show_all()

    def _happy_lib_analysis(self, aDiscsToUse, iNonMasters):
        """Heavy lifting of the HF analysis"""

        iNumberToShow = len(aDiscsToUse)

        sHappyFamilyText = "<b>" + str(iNumberToShow) + \
                " Discipline Case</b>\n"
        sHappyFamilyText += "Disciplines : <i>%s</i>\n" % ",".join(aDiscsToUse)
        fDemon = float(self.iCryptSize)
        dCryptDiscs = {}
        for sDisc in aDiscsToUse:
            if self.dLibraryStats['discipline'].has_key(sDisc):
                fDemon += self.dLibraryStats['discipline'][sDisc]
            oDisc = _lookup_discipline(sDisc,
                    self.dCryptStats['crypt discipline'])
            dCryptDiscs[sDisc] = self.dCryptStats['crypt discipline'][oDisc][1]
        iHFNoDiscipline = int((iNonMasters * self.iCryptSize / fDemon ))
        iDiff = iNonMasters - iHFNoDiscipline
        dDiscNumbers = {}
        for sDisc in aDiscsToUse:
            iHFNumber = int(iNonMasters * dCryptDiscs[sDisc] / fDemon )
            dDiscNumbers[sDisc] = iHFNumber
            iDiff -= iHFNumber
        if iDiff > 0:
            iHFNoDiscipline += iDiff # Shove rounding errors here
        sHappyFamilyText += "Number of Cards requiring No discipline : %s\n" \
                % self.dLibraryStats['discipline']['No Discipline']
        sHappyFamilyText += "Happy Families recommends %s : " % iHFNoDiscipline
        sHappyFamilyText += '<span foreground = "blue">Difference = ' \
                '%s</span>\n\n' % abs(iHFNoDiscipline -
                        self.dLibraryStats['discipline']['No Discipline'])
        for sDisc in aDiscsToUse:
            iHFNum = dDiscNumbers[sDisc]
            if self.dLibraryStats['discipline'].has_key(sDisc):
                iLibNum = self.dLibraryStats['discipline'][sDisc]
            else:
                iLibNum = 0
            sHappyFamilyText += "Number of Cards requiring %(disc)s :" \
                    " %(lib)d (%(crypt)d crypt members)\n" % {
                            'disc' : sDisc,
                            'lib' : iLibNum,
                            'crypt' : dCryptDiscs[sDisc],
                            }
            sHappyFamilyText += "Happy Families recommends %d : " % iHFNum
            sHappyFamilyText += '<span foreground = "blue">Difference = ' \
                    '%d </span>\n' % abs(iHFNum - iLibNum)
        return sHappyFamilyText

# pylint: disable-msg=C0103
# accept plugin name
plugin = AnalyzeCardList
