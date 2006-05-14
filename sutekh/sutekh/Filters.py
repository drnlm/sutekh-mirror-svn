# Filters.py
# Copyright 2005,2006 Simon Cross <hodgestar@gmail.com>
# Minor modifications copyright 2006 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

from SutekhObjects import *
from sqlobject import AND, OR, LIKE
from sqlobject.sqlbuilder import Table

# Filter Base Class

class Filter(object):
    def getExpression(self):
        raise NotImplementedError

# Collections of Filters
    
class FilterBox(Filter,list):
    pass
    
class FilterAndBox(FilterBox):
    def getExpression(self):
        return AND(*[x.getExpression() for x in self])
    
class FilterOrBox(FilterBox):
    def getExpression(self):
        return OR(*[x.getExpression() for x in self])

# Individual Filters

class ClanFilter(Filter):
    def __init__(self,sClan):
        self.__oClan = IClan(sClan)
        
    def getExpression(self):
        oT = Table('abs_clan_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   oT.clan_id == self.__oClan.id)

class MultiClanFilter(Filter):
    def __init__(self,aClans):
        self.__aClanIds = [IClan(x).id for x in aClans]
        
    def getExpression(self):
        oT = Table('abs_clan_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   IN(oT.clan_id,self.__aClanIds))
    
class DisciplineFilter(Filter):
    def __init__(self,sDiscipline):
        self.__oDis = IDiscipline(sDiscipline)
        
    def getExpression(self):
        oT = Table('abs_discipline_pair_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   oT.discipline_pair_id == DisciplinePair.q.id,
                   DisciplinePair.q.disciplineID == self.__oDis.id)

class MultiDisciplineFilter(Filter):
    def __init__(self,aDisciplines):
        self.__aDisIds = [IDiscipline(x).id for x in aDisciplines]
        
    def getExpression(self):
        oT = Table('abs_discipline_pair_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   oT.discipline_pair_id == DisciplinePair.q.id,
                   IN(DisciplinePair.q.disciplineID,self.__aDisIds))
    
class CardTypeFilter(Filter):
    def __init__(self,sCardType):
        self.__oType = ICardType(sCardType)
        
    def getExpression(self):
        oT = Table('abs_type_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   oT.card_type_id == self.__oType.id)

class MultiCardTypeFilter(Filter):
    def __init__(self,aCardTypes):
        self.__aTypeIds = [ICardType(x).id for x in aCardTypes]
        
    def getExpression(self):
        oT = Table('abs_type_map')
        return AND(AbstractCard.q.id == oT.abstract_card_id,
                   IN(oT.card_type_id,self.__aTypeIds))

class GroupFilter(Filter):
    def __init__(self,iGroup):
        self.__iGroup = iGroup

    def getExpression(self):
        return AbstractCard.q.group == self.__iGroup

class MultiGroupFilter(Filter):
    def __init__(self,aGroups):
        self.__aGroups = aGroups
        
    def getExpression(self):
        return IN(AbstractCard.q.group,self.__aGroups)

class CardTextFilter(Filter):
    def __init__(self,sPattern):
        self.__sPattern = sPattern
        
    def getExpression(self):
        return LIKE(AbstractCard.q.text,'%' + self.__sPattern + '%')

class PhysicalCardFilter(Filter):
    def __init__(self):
        # Specifies Physical Cards, intended to be anded with other filters
        pass
        
    def getExpression(self):
        oT = Table('physical_card')
        return AND(AbstractCard.q.id == oT.abstract_card_id)

class DeckFilter(Filter):
    def __init__(self,sName):
        # Select cards belonging to a deck
        self.__iDeckId = IPhysicalCardSet(sName).id

    def getExpression(self):
        oT = Table('physical_map')
        oPT = Table('physical_card')
        return AND(oT.physical_card_set_id == self.__iDeckId,
                   PhysicalCard.q.id == oT.physical_card_id,
                   AbstractCard.q.id == oPT.abstract_card_id)
        
class SpecificCardFilter(Filter):
    def __init__(self,oCard):
        self.__iCardId = IAbstractCard(oCard).id
        
    def getExpression(self):
        return (AbstractCard.q.id == self.__iCardId)  
