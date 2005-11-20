# WhiteWolf Parser

import HTMLParser, re
from SutekhObjects import *

# Card Saver

class CardDict(dict):
    oDisGaps = re.compile(r'[\\\/{}\s]+')
    oWhiteSp = re.compile(r'[{}\s]+')

    def __init__(self):
        super(CardDict,self).__init__()

    def _makeCard(self,sName):
        try:
            oC = AbstractCard.byName(sName)
        except:
            oC = AbstractCard(name=sName,text="")
        return oC
    
    def _addExpansions(self,oC,aExp):
        for sExp, sRarSet in aExp:
            for sRar in sRarSet.split('/'):
                oP = IRarityPair((sExp,sRar))
            
    def _addDisciplines(self,oC,sDis):
        sDis = self.oDisGaps.sub(' ',sDis).strip()
        
        if sDis == '-none-' or sDis == '': return
                
        for s in sDis.split():
            oD = IDiscipline(s)
        
            try:
                oP = DisciplinePair.selectBy(discipline=oD,level='inferior')[0]
            except:
                oP = DisciplinePair(discipline=oD,level='inferior')
                
            oC.addDisciplinePair(oP)
            
    def _addClans(self,oC,sClan):
        sClan = self.oWhiteSp.sub(' ',sClan).strip()
        
        if sClan == '-none-' or sClan == '': return
        
        for s in sClan.split('/'):
            oC.addClan(IClan(s.strip()))

    def _addCost(self,oC,sCost):
        sCost = self.oWhiteSp.sub(' ',sCost).strip()
        sAmnt, sType = sCost.split()
        
        if sAmnt.lower() == 'x':
            iCost = -1
        else:
            iCost = int(sAmnt,10)
        
        oC.cost = iCost
        oC.costtype = sType.lower()        

    def _addCapacity(self,oC,sCap):
        sCap = self.oWhiteSp.sub(' ',sCap).strip()
        aCap = sCap.split()
        try:
            oC.capacity = int(aCap[0],10)
        except ValueError:
            pass

    def save(self):
        if not self.has_key('name'):
            return

        print self['name']
        
        oC = self._makeCard(self['name'])
            
        if self.has_key('text'):
            oC.text = self['text']
        
        if self.has_key('group'):
            oC.group = int(self.oWhiteSp.sub('',self['group']),10)
            
        if self.has_key('capacity'):
            self._addCapacity(oC,self['capacity'])
            
        if self.has_key('cost'):
            self._addCost(oC,self['cost'])
            
        if self.has_key('expansion'):
            self._addExpansions(oC,self['expansion'])
            
        if self.has_key('discipline'):
            self._addDisciplines(oC,self['discipline'])
        
        if self.has_key('clan'):
            self._addClans(oC,self['clan'])
                                        
# State Base Classes

class StateError(Exception):
    pass

class State(object):
    def __init__(self):
        super(State,self).__init__()
        self._sData = ""

    def transition(self,sTag,dAttr):
        raise NotImplementedError
        
    def data(self,sData):
        self._sData += sData

class StateWithCard(State):
    def __init__(self,dInfo):
        super(StateWithCard,self).__init__()
        self._dInfo = dInfo

# State Classes
        
class NoCard(State):
    def transition(self,sTag,dAttr):
        if sTag == 'p':
            return InCard(CardDict())
        elif sTag == '/p':
            raise StateError()
        else:
            return self
            
class InCard(StateWithCard):
    def transition(self,sTag,dAttr):
        if sTag == 'p':
            raise StateError()
        elif sTag == '/p':
            self._dInfo.save()
            return NoCard()
        elif sTag == 'span' and dAttr.get('class') == 'cardname':
            return InCardName(self._dInfo)
        elif sTag == 'span' and dAttr.get('class') == 'exp':
            return InExpansion(self._dInfo)
        elif sTag == 'span' and dAttr.get('class') == 'key':
            return InKeyValue(self._dInfo)
        elif sTag == 'td' and dAttr.get('colspan') == '2':
            return InCardText(self._dInfo)
        else:
            return self
            
class InCardName(StateWithCard):
    def transition(self,sTag,dAttr):
        if sTag == '/span':
            self._dInfo['name'] = self._sData.strip()
            return InCard(self._dInfo)
        elif sTag == 'span':
            raise StateError()
        else:
            return self
    
class InExpansion(StateWithCard):
    def transition(self,sTag,dAttr):
        if sTag == '/span':
            aPairs = [x.split(':') for x in self._sData.strip('[]').split(',')]
            aExp = []
            for aPair in aPairs:
                if len(aPair) == 1:
                    aExp.append((aPair[0].strip(),'NA'))
                else:
                    aExp.append((aPair[0].strip(),aPair[1].strip()))
            self._dInfo['expansion'] = aExp
            return InCard(self._dInfo)
        elif sTag == 'span':
            raise StateError()
        else:
            return self

class InCardText(StateWithCard):
    def transition(self,sTag,dAttr):
        if sTag == '/td':
            self._dInfo['text'] = self._sData.strip()
            return InCard(self._dInfo)
        elif sTag == 'td':
            raise StateError()
        else:
            return self
    
class InKeyValue(StateWithCard):
    def transition(self,sTag,dAttr):
        if sTag == '/span':
            sKey = self._sData.strip().strip(':').lower()
            return WaitingForValue(sKey,self._dInfo)
        elif sTag == 'span':
            raise StateError()
        else:
            return self
                
class WaitingForValue(StateWithCard):
    def __init__(self,sKey,dInfo):
        super(WaitingForValue,self).__init__(dInfo)
        self._sKey = sKey
        self._bGotTd = False
    
    def transition(self,sTag,dAttr):
        if sTag == 'td':
            self._sData = ""
            self._bGotTd = True
            return self
        elif sTag == '/td' and self._bGotTd:
            self._dInfo[self._sKey] = self._sData.strip()
            return InCard(self._dInfo)
        elif sTag == '/tr':
            self._dInfo[self._sKey] = None
            return InCard(self._dInfo)
        elif sTag == 'tr':
            raise StateError()
        else:
            return self
        
# Parser

class WhiteWolfParser(HTMLParser.HTMLParser,object):
    def reset(self):
        super(WhiteWolfParser,self).reset()
        self._state = NoCard()

    def handle_starttag(self,sTag,aAttr):
        self._state = self._state.transition(sTag.lower(),dict(aAttr))
        
    def handle_endtag(self,sTag):
        self._state = self._state.transition('/'+sTag.lower(),{})
        
    def handle_data(self,sData):
        self._state.data(sData)
    
    def handle_charref(self,sName): pass
    def handle_entityref(self,sName): pass
