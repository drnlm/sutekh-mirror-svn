# DBSignals.py
# -*- coding: utf8 -*-
# vim:fileencoding=utf8 ai ts=4 sts=4 et sw=4
# Define the reload singal we need
# Copyright 2007 Simon Cross <hodgestar@gmail.com>,
# Copyright 2007 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""Wrappers around SQLObject signals needed to keep card sets and the card
collection in sync."""

from sqlobject.events import Signal, listen, RowUpdateSignal, RowDestroySignal
from sutekh.core.SutekhObjects import PhysicalCardSet

class ReloadSignal(Signal):
    """Syncronisation signal for card sets.

       Needs to be sent after changes are commited to the database, so card
       sets can reload properly.
       Used so card sets always reflect correct available counts.
       """

# Senders

def send_reload_signal(oCardSet, oPhysCard=None,
        cClass=PhysicalCardSet):
    """Sent when card counts change, so card sets may need to reload."""
    cClass.sqlmeta.send(ReloadSignal, oCardSet, oPhysCard)

# Listeners

def listen_reload(fListener, cClass):
    """Listens for the reload_signal."""
    listen(fListener, cClass, ReloadSignal)

def listen_row_destroy(fListener, cClass):
    """listen for the row destoryed signal sent when a card is deleted."""
    listen(fListener, cClass, RowDestroySignal)

def listen_row_update(fListener, cClass):
    """listen for the row updated signal sent when a card is modified."""
    listen(fListener, cClass, RowUpdateSignal)

